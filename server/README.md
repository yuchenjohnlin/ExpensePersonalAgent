# server/: CojiDaily, rebuilt

The rebuilt backend (project-rebuild): FastAPI on PostgreSQL, a modular monolith organised by feature (rebuild-modules-by-feature). It starts from an empty database (rebuild-starts-empty) and lives beside the old `backend/` (Django) and `api/` (the comparison port) until it takes over.

## Layout

```
server/
  alembic/versions/       one migration history for every module's tables
  src/cojidaily/
    main.py               create_app(): mounts each module's router
    worker.py             python -m cojidaily.worker: runs background jobs
    models.py             imports every module's tables (Alembic, tests)
    platform/             no domain knowledge: settings, db, errors, clock, blobstore, units, jobs
  tests/
  dev.sh                  PostgreSQL in Docker for the tests
```

Rules the modules keep:

- A table belongs to one module and carries its name as a prefix (`platform_job`, `ledger_expense`).
- Another module uses a module only through its `api.py`, never its models or services.
- A foreign key between modules points the way the modules depend on each other.

## Accounts and signing in (auth/)

Accounts are made with `python -m cojidaily.cli createuser NAME` (no sign-up page; `setpassword NAME` changes one). A sign-in is a row in `auth_session`; the `coji_session` cookie (HttpOnly, SameSite=Lax, two weeks, not extended by use) carries a random token whose SHA-256 is the row's key. The row also keeps an HMAC of the password hash, so a new password ends older sessions. Passwords are Argon2id with the cost the old apps used.

Other modules use `auth.api.Signed` (a dependency that answers 401 until signed in) and the `Principal` it gives: `user_id` is what they store as `owner_id`. They never read auth's tables or the cookie.

CSRF is a double-submit token checked by middleware for every write to `/api/`: `GET /api/session` sets the `coji_csrf` cookie and answers the same token, which writes send back in `X-CSRF-Token`; an `Origin`, when the browser sends one, must be this site or `COJI_CSRF_TRUSTED_ORIGINS`. Signing in rotates the token.

| Endpoint | |
|---|---|
| `GET /api/session` | `csrf_token`, `user` (null until signed in), `today`, `timezone`, `currency` |
| `POST /api/auth/login` | `{username, password}`; 400 `{"__all__": ["帳號或密碼不正確。"]}` for either wrong |
| `POST /api/auth/logout` | deletes the session row |

## The ledger (ledger/)

Three tables: `ledger_category` (each owner's own list: the old app's eight and a system 未分類), `ledger_expense` (what was paid: `amount` is the truth for every total; `tax` NULL means not known yet; `reviewed_at` NULL means posted automatically and not looked at, expense-review-status-not-drafts) and `ledger_line` (what it bought, as printed; edited in place so its id stays). Owned rows carry `owner_id` with no foreign key to auth.

Rules moved from `api/`: a line's checks, `fill_derived` (amount = measure × unit price; the blank side is worked out and marked in `derived_field`, a typed value is never changed) and the tax / tip / receipt-discount split by largest remainder (`adjustments.py`, worked out on reading, never stored). An expense marked `total_only` cannot get lines and one with lines cannot be marked. Tax plus tip must stay below the amount (also a CHECK constraint).

The ledger knows nothing about receipts. `ledger/api.py` is what others use: `create_expense(header, lines, reviewed=)`, `check_line`, `uncategorized_category_id`, `similar_expense_ids`, `summaries`, `delete_expense`.

| Endpoint | |
|---|---|
| `GET /api/categories` | the owner's categories |
| `POST /api/expenses` | a hand-entered expense (reviewed); money as strings |
| `GET /api/expenses/{id}` | with its lines and summary |
| `PATCH /api/expenses/{id}` | any subset of the header, `tax`/`tip`/`receipt_discount`, `total_only`, `reviewed` |
| `DELETE /api/expenses/{id}` | with its lines |
| `GET /api/expenses/unreviewed` | auto-posted, not looked at yet |
| `POST /api/expenses/{id}/lines`, `PATCH /api/lines/{id}`, `DELETE /api/lines/{id}` | lines; each answers the whole expense |
| `GET /api/calendar?month=YYYY-MM` | each day's total, count and merchants |
| `GET /api/calendar/day?date=YYYY-MM-DD` | the day's expenses with lines |

Each line in an answer carries its share of the receipt (`net_amount`, `tax_share`, `discount_share`, `tip_share`, `final_amount`); `summary` sets the lines against what was paid (`subtotal`, rates, `unrecorded`).

## The photo library (photos/)

`photos_upload` records what arrived together and through which channel (only `receipt_page` so far); `photos_photo` is one photo with its position in the upload, size, oriented dimensions, type and SHA-256. Photos know nothing about receipts: a receipt points at its photos (photo-library-receipt-or-other).

Moved from `api/`: the streaming multipart receiver with its limits (`uploads.py`: only the `photos` field, 15 MiB per photo, 50 MiB per upload, refused while the body arrives) and the photo checks with preview and thumbnail making (`images.py`: JPEG / PNG / WebP / HEIC stills up to 40 million pixels, decoded for real; a 1600 px preview and a 320 px thumbnail, the same bytes as the old apps make, pinned by hash in the tests).

`photos.api.store()` checks every photo, refuses ones the owner already has (or that appear twice in the upload) unless `allow_duplicates`, then adds the rows to the caller's transaction and writes three files per photo under `photos/<storage_key>/` (`original.<ext>`, `preview.jpg`, `thumb.jpg`). A per-owner advisory lock holds from the duplicate check to the commit. If the transaction does not commit, the files are deleted (`platform.db.on_rollback`); a process killed between writing and committing can still leave files no row points at.

`GET /api/photos/{id}/preview|thumbnail|original` serves them to their owner only (previews cached as immutable, originals `no-store` and downloaded under their own name).

## Reading (reading/)

`reading_reading` is one attempt to read some photos (`reading_photo`, in order): its status (`queued` → `running` → `succeeded` / `failed`, what a page shows while it waits), the service, model and prompt version, how the photos were prepared, the result, the model's own answer without secrets, an error code and message, and the timing. It knows nothing about receipts (reading-attempts-and-provenance-ownership).

`reading.api.request(photo_ids, then_kind=, then_payload=)` queues a reading and its `reading.run` job in the caller's transaction. The worker marks it running, reads the photo files, prepares the JPEGs and calls the service without holding a transaction, stores what came back, and enqueues the requester's `then_kind` job with `then_payload` plus `reading_id`. Every outcome ends the reading: a service failure, a missing photo file or an unexpected error is stored as `failed` with a code (`not_configured`, `unavailable`, `timeout`, `truncated`, `invalid_result`, `photo_unavailable`, `internal`, ...), and the requester still hears back. A finished reading is left alone if its job runs again.

`engine.py` is moved from `api/app/reading.py` (backend/'s `receipt_extraction.py`) with settings passed in and photos as bytes: the prompt and schema are identical (`receipt-draft-v4`, pinned by hash in the tests), as are the JPEG preparation, the validation and the spans. It stays pure so the bench can import it. `checks.py` holds the three arithmetic checks, worked out whenever a reading is looked at, never stored.

Which service reads is `COJI_READING_PROVIDER` (reading-provider-is-a-setting); only `vllm` so far. `api/`'s AWS and Google readers can move in as more providers once a fallback order is decided.

## Receipts (receipts/)

The one module that coordinates others, and the MVP's path (mvp-receipt-page-slice):

1. `POST /api/receipts` (multipart: `photos`, optional `groups` as JSON lists of photo indices, `allow_duplicates`) stores the photos in the library, makes one receipt per group, and queues each one's reading, in one transaction. Up to 20 photos per upload and 10 per receipt.
2. The worker reads it (`reading.run`), then runs `receipts.after_reading`.
3. If the reading has a merchant, a date and a total, passes the arithmetic checks, has no future date and money the ledger can hold, and no expense already exists on that day with the same merchant and total, the receipt is **posted automatically**: an expense in 未分類, not reviewed, with the read items as lines (reading-auto-post-when-checks-pass, auto-post-uncategorized). Items that cannot be lines (a negative deduction, a value a line cannot hold) are skipped and listed on the posting.
4. Otherwise it **needs a look**, with the reasons. From there: post it by hand (`POST /api/receipts/{id}/posting`, the header as checked, optionally with the read items as lines; reviewed), or read it again (`POST /api/receipts/{id}/readings`). There is no automatic repair of failed checks.
5. `DELETE /api/receipts/{id}/posting` unposts: the expense and its lines are deleted. Deleting the expense in the ledger does the same to the links.

Tables, all with foreign keys pointing out of receipts: `receipts_receipt` (owner, `pipeline` reading / done, the reasons it was set aside), `receipts_receipt_photo` (its photos in order), `receipts_receipt_reading` (its readings; the newest is current), `receipts_posting` (the expense it became, from which reading, auto or manual, skipped items) and `receipts_posted_line` (which line came from which read item). A receipt's state is worked out: posted when a posting exists, reading while `pipeline` is reading, otherwise needs a look. So when the ledger deletes the expense, the receipt shows as needing a look without receipts having run any code.

| Endpoint | |
|---|---|
| `POST /api/receipts` | upload; 201 with the receipts, 409 with `duplicates` |
| `GET /api/receipts?state=reading\|needs_review\|posted&page=` | newest first, 20 a page, with counts |
| `GET /api/receipts/{id}` | photos, current reading, posting with its expense |
| `GET /api/receipts/for-expenses?expense_id=…` | the receipt each expense was posted from, by expense id (the ledger does not know receipts) |
| `POST /api/receipts/{id}/readings` | read again (not while reading or posted) |
| `POST /api/receipts/{id}/posting`, `DELETE` same | post by hand, unpost |

## Background jobs

`platform/jobs.py` is a job table with a worker (jobs-hand-written-table). A service enqueues inside its own transaction, so the job exists exactly when the rows that need it were committed. The worker claims the oldest ready job with `FOR UPDATE SKIP LOCKED` and commits the claim before running it, so a handler holds no transaction while it waits on a model. Delivery is at least once: a failed job is retried with a growing delay up to `max_attempts`, and a job left `running` by a dead worker is taken again after the lease (15 minutes). Handlers must therefore be safe to run twice.

## Tests

Needs Docker and `uv`.

```bash
server/dev.sh test
```

This starts PostgreSQL 17 on `127.0.0.1:5434` (data in the Docker volume `cojidaily-serverdev-pgdata`), makes `cojidaily_test` from the migrations once per run, and empties every table before each test. `tests/test_migrations.py` checks that the hand-written migrations produce exactly the models' schema. `server/dev.sh stop` removes the container; the volume stays.

## Running it on the Mac

```bash
server/dev.sh cli createuser yuchen
```

```bash
server/dev.sh run
```

`run` migrates the database `cojidaily_dev` (kept between runs), starts the worker, and serves the API on `127.0.0.1:8000`, reloading on edits. Settings come from `server/.env` when it exists (git-ignored; put `VLLM_BASE_URL`, `VLLM_MODEL`, `VLLM_API_KEY` there to read with Spark); photos go to `server/media/`. The page is `web/` (see `web/README.md`).

## Running it deployed

`server/Dockerfile` builds one image for the API (`opentelemetry-instrument uvicorn ...`, two processes) and the worker (`python -m cojidaily.worker`, the command `deploy/compose.yaml` gives it). It installs exactly `uv.lock` plus the `otel` extra: the OpenTelemetry SDK and the FastAPI, psycopg (SQL at the driver: the SQLAlchemy instrumentation does not support SQLAlchemy 2.1) and urllib instrumentation, configured by `OTEL_*` variables. The code itself only calls the OpenTelemetry API, so in dev, without the extra, those calls do nothing. Test and prod on the PC, the observability stack and backups: `deploy/README.md`.

Jobs report too: each run is a span `job <kind>` (with how long the job waited once ready, its attempt and outcome), and the histograms `coji.job.wait` and `coji.job.duration` show a queue that grows or jobs that slow down.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `COJI_DATABASE_URL` | required | `postgresql+psycopg://user:password@host:5432/cojidaily` |
| `COJI_SECRET_KEY` | required | ties sessions to the password they were opened with |
| `COJI_BLOB_ROOT` | `media` | where photos are stored |
| `COJI_TIMEZONE` | `America/New_York` | the ledger's "today" |
| `COJI_CSRF_TRUSTED_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | other origins allowed to send writes |
| `COJI_SECURE_COOKIES` | off | `1` once served over HTTPS |
| `COJI_DB_POOL_SIZE` | `5` | connections kept per process |
| `COJI_WORKER_THREADS` | `2` | jobs the worker runs side by side |
| `COJI_READING_PROVIDER` | `vllm` | which service reads photos |
| `VLLM_BASE_URL`, `VLLM_MODEL`, `VLLM_API_KEY`, `VLLM_TIMEOUT_SECONDS` | as `backend/` | the vLLM reading service |
