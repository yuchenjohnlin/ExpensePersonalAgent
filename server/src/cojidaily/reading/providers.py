"""Reading services. The one in use is a setting (COJI_READING_PROVIDER), never the user's choice.

Only vLLM so far; api/ also has AWS Textract and Google Document AI, which can move here as more
providers (each turns JPEGs into the same draft) when a fallback order is decided.
"""
from ..platform.settings import Settings
from . import engine


class VllmProvider:
    id = "vllm"
    prompt_version = engine.PROMPT_VERSION

    def __init__(self, settings: Settings):
        self.settings = settings

    def model(self) -> str:
        return self.settings.vllm_model.strip()

    def parameters(self) -> dict:
        return engine.processing_parameters() | {"timeout_seconds": self.settings.vllm_timeout_seconds}

    def read(self, images: list[tuple[int, bytes]]) -> tuple[dict, dict]:
        """(result, sanitized reply) for one receipt's JPEGs, or ExtractionFailure."""
        settings = self.settings
        endpoint, model, timeout = engine.configuration(settings.vllm_base_url, settings.vllm_model,
                                                        settings.vllm_api_key, settings.vllm_timeout_seconds)
        return engine.read_receipt(images, endpoint, model, settings.vllm_api_key, timeout)


PROVIDERS = {"vllm": VllmProvider}


def provider(settings: Settings):
    """The configured service, or None when the setting names none we have."""
    made = PROVIDERS.get(settings.reading_provider)
    return made(settings) if made else None
