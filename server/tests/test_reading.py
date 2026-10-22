"""Reading photos (reading/): the engine against a fake vLLM, the arithmetic checks, and readings run
by the worker."""
import hashlib
import json
from dataclasses import replace

import pytest
from sqlalchemy import select

from cojidaily.photos import api as photos
from cojidaily.platform.jobs import Job, Worker
from cojidaily.reading import api as reading
from cojidaily.reading import engine
from cojidaily.reading.checks import arithmetic_warnings
from cojidaily.reading.models import Reading
from cojidaily.worker import handlers

from .fake_vllm import completion, receipt
from .photo_samples import drawing


def test_the_prompt_and_schema_are_the_old_apps():
    # The fingerprint of api/app/reading.py's SYSTEM_PROMPT and RECEIPT_SCHEMA (receipt-draft-v4);
    # changing either needs a new PROMPT_VERSION, so readings say which prompt made them.
    text = engine.SYSTEM_PROMPT + json.dumps(engine.RECEIPT_SCHEMA, sort_keys=True)
    assert hashlib.sha256(text.encode()).hexdigest() == "f3b944fddce0d342bdadf8c6c19d6f483b4ee88f10192fbb03e92181cc915cf8"
    assert engine.PROMPT_VERSION == "receipt-draft-v4"


def read(vllm, images=((1, b"jpeg"),), **settings):
    endpoint, model, timeout = engine.configuration(vllm.base_url, "test-model", settings.get("key", "secret-key"), "5")
    return engine.read_receipt(list(images), endpoint, model, settings.get("key", "secret-key"), timeout)


def test_the_engine_sends_one_request_and_validates_the_answer(vllm):
    result, raw = read(vllm, [(1, b"top"), (2, b"bottom")])
    assert result["merchant"] == "Kroger" and len(result["items"]) == 2
    assert raw["usage"] == {"prompt_tokens": 1200, "completion_tokens": 340, "total_tokens": 1540}
    [sent] = vllm.requests
    assert sent["path"] == "/v1/chat/completions"
    assert sent["headers"]["Authorization"] == "Bearer secret-key"
    body = sent["body"]
    assert (body["temperature"], body["max_tokens"]) == (0, 4096)
    assert body["response_format"]["json_schema"]["schema"] == engine.RECEIPT_SCHEMA
    texts = [part["text"] for part in body["messages"][1]["content"] if part["type"] == "text"]
    assert texts == ["Read this one receipt. Images follow in their stored order.", "Source image 1:", "Source image 2:"]


@pytest.mark.parametrize("answer, code", [
    ((200, completion(receipt(), finish_reason="length")), "truncated"),
    ((200, completion({"merchant": "only this"})), "invalid_result"),
    ((200, completion(receipt(date="2026-02-30"))), "invalid_result"),
    ((500, {"error": "secret internals"}), "server_error"),
    ((200, b"not json"), "invalid_response"),
])
def test_bad_answers_end_as_failures_with_a_code(vllm, answer, code):
    vllm.reset(answer)
    with pytest.raises(engine.ExtractionFailure) as failure:
        read(vllm)
    assert failure.value.code == code


def test_an_unconfigured_service_is_refused_before_any_request(vllm):
    for base in ("", "ftp://spark/v1", "http://user:pw@spark/v1", "http://spark/other"):
        with pytest.raises(engine.ExtractionFailure) as failure:
            engine.configuration(base, "model", "", "300")
        assert failure.value.code == "not_configured"
    with pytest.raises(engine.ExtractionFailure):
        engine.configuration(vllm.base_url, "model", "", "601")


def test_the_api_key_never_reaches_what_is_stored(vllm):
    vllm.reset((200, completion(receipt(raw_text="printed: secret-key"))))  # even if the model echoes it
    _, raw = read(vllm, key="secret-key")
    assert "secret-key" not in json.dumps(raw) and "[redacted]" in json.dumps(raw)


def test_the_arithmetic_checks():
    assert arithmetic_warnings(receipt()) == []
    wrong_total = arithmetic_warnings(receipt(amount="5.00"))
    assert wrong_total == ["小計加稅與小費、減整張折扣，與總額不一致；未自動修改任何讀取值。"]
    missed_item = receipt(subtotal="9.99")
    assert arithmetic_warnings(missed_item)[0].startswith("品項金額加總與小計不一致")
    bad_weight = receipt()
    bad_weight["items"][0]["net_weight"] = "3.85"
    assert arithmetic_warnings(bad_weight) == ["第 1 項的數量或淨重乘單價與該行金額不一致，請核對計價方式。"]
    # Within two cents is fine; a subtotal after item discounts is fine too.
    assert arithmetic_warnings(receipt(amount="4.70")) == []


def queue_reading(app, settings, owner, photo_count=1, first_shade=0, **then):
    with app.state.sessions() as db:
        photo_ids = photos.store(db, app.state.blobs, owner, "receipt_page",
                                 [(f"{n}.png", drawing(shade=n)) for n in range(first_shade, first_shade + photo_count)])
        reading_id = reading.request(db, settings, owner, photo_ids, **then)
        db.commit()
    return reading_id


def get(app, reading_id):
    with app.state.sessions() as db:
        return reading.get_many(db, [reading_id])[reading_id]


def test_a_reading_is_queued_then_run_by_the_worker(app, settings, owner, worker, vllm):
    reading_id = queue_reading(app, settings, owner, 2, then_kind="test.after", then_payload={"receipt_id": 7})
    queued = get(app, reading_id)
    assert (queued.status, queued.provider, queued.model, queued.prompt_version) == (
        "queued", "vllm", "test-model", "receipt-draft-v4")
    seen = []
    worker.handlers["test.after"] = lambda _, payload: seen.append(payload)
    assert worker.run_until_idle() == 2
    done = get(app, reading_id)
    assert done.status == "succeeded" and done.result["merchant"] == "Kroger"
    assert done.checks == [] and done.usage["completion_tokens"] == 340 and done.elapsed_ms is not None
    assert seen == [{"receipt_id": 7, "reading_id": reading_id}]
    # The model got the photos as JPEGs, in order.
    images = [part for part in vllm.requests[0]["body"]["messages"][1]["content"] if part["type"] == "image_url"]
    assert len(images) == 2 and images[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    with app.state.sessions() as db:
        stored = db.get(Reading, reading_id)
        assert stored.params["image_dimensions"] == [[2400, 1500], [2400, 1500]]
        assert stored.params["max_long_side"] == 2560


def test_a_failed_reading_is_stored_with_its_code_and_still_reports_back(app, settings, owner, worker, vllm):
    vllm.reset((200, completion(receipt(), finish_reason="length")))
    reading_id = queue_reading(app, settings, owner, then_kind="test.after")
    seen = []
    worker.handlers["test.after"] = lambda _, payload: seen.append(payload)
    worker.run_until_idle()
    failed = get(app, reading_id)
    assert (failed.status, failed.error_code, failed.result) == ("failed", "truncated", None)
    assert seen == [{"reading_id": reading_id}]
    with app.state.sessions() as db:
        assert db.get(Reading, reading_id).raw_response["choices"][0]["finish_reason"] == "length"


def test_a_missing_service_or_photo_file_fails_the_reading_not_the_job(app, settings, owner, vllm):
    reading_id = queue_reading(app, settings, owner)
    Worker(app.state.sessions, handlers(replace(settings, vllm_base_url=""))).run_until_idle()
    assert get(app, reading_id).error_code == "not_configured"
    second = queue_reading_with_missing_file(app, settings, owner)
    Worker(app.state.sessions, handlers(settings)).run_until_idle()
    assert get(app, second).error_code == "photo_unavailable"
    with app.state.sessions() as db:
        assert {job.status for job in db.scalars(select(Job))} == {"done"}


def queue_reading_with_missing_file(app, settings, owner):
    reading_id = queue_reading(app, settings, owner, first_shade=50)
    for path in (app.state.blobs.root / "photos").rglob("original.png"):
        path.unlink()
    return reading_id


def test_running_a_finished_reading_again_changes_nothing(app, settings, owner, worker, vllm):
    reading_id = queue_reading(app, settings, owner)
    worker.run_until_idle()
    from cojidaily.reading.service import run

    run(app.state.sessions, {"reading_id": reading_id}, blobs=app.state.blobs, settings=settings)
    assert len(vllm.requests) == 1
    assert get(app, reading_id).status == "succeeded"
