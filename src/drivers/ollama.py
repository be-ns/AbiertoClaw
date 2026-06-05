"""Local Ollama driver.

Deliberately separate from openai_compatible: Ollama's native API is
POST {base}/api/chat with NO /v1 prefix. Pointing the OpenAI driver at
Ollama's /v1 shim silently breaks tool calling (SPEC gotcha #1).
"""

from .base import Driver, ProviderError


class OllamaDriver(Driver):
    def __init__(self, base_url="http://127.0.0.1:11434", **_ignored):
        self.base_url = base_url.rstrip("/")

    def chat(self, messages, model, opts=None):
        opts = opts or {}
        payload = {"model": model, "messages": messages, "stream": False}
        body = self._request(
            self.base_url + "/api/chat",
            payload=payload,
            timeout=opts.get("timeout", 120),
        )
        try:
            text = body["message"]["content"] or ""
        except (KeyError, TypeError):
            raise ProviderError("unexpected Ollama response: %r" % (body,))
        usage = {
            "prompt_tokens": body.get("prompt_eval_count", 0),
            "completion_tokens": body.get("eval_count", 0),
        }
        return {"text": text.strip(), "usage": usage}

    def list_models(self):
        body = self._request(self.base_url + "/api/tags", timeout=10)
        return [{"id": m.get("name", "")} for m in body.get("models", [])]
