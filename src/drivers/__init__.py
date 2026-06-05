from .base import Driver, ProviderError, RateLimited
from .ollama import OllamaDriver
from .openai_compatible import OpenAICompatibleDriver

DRIVERS = {
    "openai-compatible": OpenAICompatibleDriver,
    "ollama": OllamaDriver,
}

__all__ = [
    "Driver",
    "ProviderError",
    "RateLimited",
    "OllamaDriver",
    "OpenAICompatibleDriver",
    "DRIVERS",
]
