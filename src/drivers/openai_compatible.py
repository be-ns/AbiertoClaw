"""The one driver that covers OpenRouter, OpenCode Zen, and any BYO endpoint.

They all speak POST {base_url}/chat/completions in the OpenAI shape
(SPEC §4.1), so the vendor differences collapse into config.
"""

from .base import Driver, ProviderError


class OpenAICompatibleDriver(Driver):
    def __init__(self, base_url, api_key=None, models_endpoint="/models",
                 extra_headers=None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.models_endpoint = models_endpoint
        self.extra_headers = extra_headers or {}

    def _headers(self):
        headers = dict(self.extra_headers)
        if self.api_key:
            headers["Authorization"] = "Bearer %s" % self.api_key
        return headers

    def chat(self, messages, model, opts=None):
        opts = opts or {}
        payload = {"model": model, "messages": messages}
        for key in ("temperature", "max_tokens"):
            if key in opts:
                payload[key] = opts[key]
        body = self._request(
            self.base_url + "/chat/completions",
            payload=payload,
            headers=self._headers(),
            timeout=opts.get("timeout", 120),
        )
        try:
            text = body["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise ProviderError("unexpected response shape: %r" % (body,))
        return {"text": text.strip(), "usage": body.get("usage", {})}

    def list_models(self):
        if not self.models_endpoint:
            return []
        body = self._request(
            self.base_url + self.models_endpoint,
            headers=self._headers(),
            timeout=30,
        )
        return body.get("data", [])
