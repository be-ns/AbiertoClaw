"""Provider contract tests (SPEC §14): right request shape, 429 -> RateLimited."""

import io
import json
import unittest
import urllib.error
import urllib.request
from unittest import mock

from src.drivers import OllamaDriver, OpenAICompatibleDriver, RateLimited
from src.drivers.base import _SafeRedirectHandler


def fake_response(body):
    resp = mock.MagicMock()
    resp.read.return_value = json.dumps(body).encode()
    resp.__enter__ = lambda s: s
    resp.__exit__ = mock.MagicMock(return_value=False)
    return resp


OPENAI_BODY = {
    "choices": [{"message": {"content": "hello"}}],
    "usage": {"prompt_tokens": 3, "completion_tokens": 1},
}


class TestOpenAICompatible(unittest.TestCase):
    @mock.patch("src.drivers.base._opener.open")
    def test_chat_sends_openai_shape(self, urlopen):
        urlopen.return_value = fake_response(OPENAI_BODY)
        driver = OpenAICompatibleDriver("https://example.test/v1", api_key="sk-x")
        result = driver.chat([{"role": "user", "content": "hi"}], "some/model")

        req = urlopen.call_args[0][0]
        self.assertEqual(req.full_url, "https://example.test/v1/chat/completions")
        self.assertEqual(req.get_header("Authorization"), "Bearer sk-x")
        payload = json.loads(req.data.decode())
        self.assertEqual(payload["model"], "some/model")
        self.assertEqual(payload["messages"], [{"role": "user", "content": "hi"}])
        self.assertEqual(result["text"], "hello")
        self.assertEqual(result["usage"]["prompt_tokens"], 3)

    @mock.patch("src.drivers.base._opener.open")
    def test_429_maps_to_rate_limited(self, urlopen):
        urlopen.side_effect = urllib.error.HTTPError(
            "https://example.test/v1/chat/completions", 429, "Too Many Requests",
            {"Retry-After": "7"}, io.BytesIO(b"slow down"),
        )
        driver = OpenAICompatibleDriver("https://example.test/v1", api_key="sk-x")
        with self.assertRaises(RateLimited) as ctx:
            driver.chat([{"role": "user", "content": "hi"}], "m")
        self.assertEqual(ctx.exception.retry_after, 7.0)


class TestRedirectSafety(unittest.TestCase):
    def _redirect(self, newurl):
        req = urllib.request.Request(
            "https://api.example.test/v1/chat/completions",
            headers={"Authorization": "Bearer sk-x"},
        )
        return _SafeRedirectHandler().redirect_request(
            req, None, 302, "Found", {}, newurl
        )

    def test_cross_host_redirect_drops_the_key(self):
        new = self._redirect("https://evil.example.test/collect")
        self.assertIsNone(new.get_header("Authorization"))

    def test_same_host_redirect_keeps_the_key(self):
        new = self._redirect("https://api.example.test/v1/chat/completions/")
        self.assertEqual(new.get_header("Authorization"), "Bearer sk-x")


class TestOllama(unittest.TestCase):
    @mock.patch("src.drivers.base._opener.open")
    def test_chat_uses_native_api_not_v1(self, urlopen):
        urlopen.return_value = fake_response(
            {"message": {"content": "hey"}, "prompt_eval_count": 5, "eval_count": 2}
        )
        driver = OllamaDriver("http://127.0.0.1:11434")
        result = driver.chat([{"role": "user", "content": "hi"}], "qwen2.5:7b")

        req = urlopen.call_args[0][0]
        # The single most expensive lesson from Iris: /api/chat, never /v1.
        self.assertEqual(req.full_url, "http://127.0.0.1:11434/api/chat")
        payload = json.loads(req.data.decode())
        self.assertIs(payload["stream"], False)
        self.assertEqual(result["text"], "hey")
        self.assertEqual(result["usage"]["completion_tokens"], 2)


if __name__ == "__main__":
    unittest.main()
