"""A stand-in for vLLM's OpenAI-compatible chat API, on a real socket (as contract/fake_vllm.py)."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = "test-model"


def completion(content, finish_reason="stop", usage=(1200, 340)) -> dict:
    """A chat completion whose one choice says `content` (a dict is sent as its JSON)."""
    text = content if isinstance(content, str) else json.dumps(content)
    return {"id": "chatcmpl-test", "object": "chat.completion", "model": MODEL,
            "choices": [{"index": 0, "finish_reason": finish_reason, "message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1], "total_tokens": sum(usage)}}


def receipt(**header) -> dict:
    """A valid draft: Kroger, 2026-10-09, bananas and milk, tax 0.14, total 4.68 (all checks pass)."""
    item = {"description": None, "quantity": None, "unit": None, "quoted_unit_price": None, "price_unit": None,
            "net_weight": None, "weight_unit": None, "amount": None, "discount": None, "photo_indices": [1]}
    items = [item | {"description": "BANANAS", "net_weight": "2.85", "weight_unit": "lb", "quoted_unit_price": "0.55",
                     "price_unit": "lb", "amount": "1.57"},
             item | {"description": "MILK 1 GAL", "amount": "2.97"}]
    return {"merchant": "Kroger", "date": "2026-10-09", "currency": "USD", "items": items, "subtotal": "4.54",
            "tax": "0.14", "tip": None, "receipt_discount": None, "amount": "4.68", "raw_text": "KROGER ...",
            "warnings": [], "photo_indices": [1]} | header


class FakeVllm:
    def __init__(self):
        self.requests: list[dict] = []
        self.answers: list[tuple[int, object]] = []  # used in order; the last one repeats
        self.delay = 0.0
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                fake.requests.append({"path": self.path, "headers": dict(self.headers), "body": json.loads(raw or b"{}")})
                time.sleep(fake.delay)
                status, body = fake.answers.pop(0) if len(fake.answers) > 1 else fake.answers[0]
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"
        self.reset()

    def reset(self, *answers, delay=0.0):
        self.requests.clear()
        self.answers = list(answers) or [(200, completion(receipt()))]
        self.delay = delay
