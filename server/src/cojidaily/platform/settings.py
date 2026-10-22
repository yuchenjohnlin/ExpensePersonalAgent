"""Configuration, read from the environment once when the app or the worker starts."""
import os
from dataclasses import dataclass


def _list(name: str, default: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in os.environ.get(name, default).split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    # postgresql+psycopg://user:password@host:5432/cojidaily
    database_url: str
    # Ties a session to the password it was opened with (auth.service.password_tag).
    secret_key: str
    # Where photos are stored (platform.blobstore).
    blob_root: str = "media"
    # The ledger's "today". One timezone for the app until it is a profile setting.
    timezone: str = "America/New_York"
    # Origins other than the request's own host that may send writes (the Vite dev server).
    csrf_trusted_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    # Session cookie's Secure flag: on once the app is served over HTTPS.
    secure_cookies: bool = False
    db_pool_size: int = 5
    # Jobs the worker runs side by side (python -m cojidaily.worker).
    worker_threads: int = 2
    # Which reading service reads photos (pm/decisions/reading-provider-is-a-setting.md).
    reading_provider: str = "vllm"
    # The same variable names as backend/ and api/, so one .env can serve all three.
    vllm_base_url: str = ""
    vllm_model: str = "Qwen/Qwen3-VL-30B-A3B-Instruct"
    vllm_api_key: str = ""
    vllm_timeout_seconds: str = "300"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ["COJI_DATABASE_URL"],
            secret_key=os.environ["COJI_SECRET_KEY"],
            blob_root=os.environ.get("COJI_BLOB_ROOT", "media"),
            timezone=os.environ.get("COJI_TIMEZONE", "America/New_York"),
            csrf_trusted_origins=_list("COJI_CSRF_TRUSTED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"),
            secure_cookies=os.environ.get("COJI_SECURE_COOKIES", "") == "1",
            db_pool_size=int(os.environ.get("COJI_DB_POOL_SIZE", "5")),
            worker_threads=int(os.environ.get("COJI_WORKER_THREADS", "2")),
            reading_provider=os.environ.get("COJI_READING_PROVIDER", "vllm"),
            vllm_base_url=os.environ.get("VLLM_BASE_URL", ""),
            vllm_model=os.environ.get("VLLM_MODEL", "Qwen/Qwen3-VL-30B-A3B-Instruct"),
            vllm_api_key=os.environ.get("VLLM_API_KEY", ""),
            vllm_timeout_seconds=os.environ.get("VLLM_TIMEOUT_SECONDS", "300"),
        )
