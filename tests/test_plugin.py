import http.server
import io
import json
import os
import threading
import sys
import tempfile
import unittest
import urllib.error
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hermes_config  # noqa: E402
import picker  # noqa: E402


def model(mid, free=True, tools=True, ctx=128_000):
    price = "0" if free else "0.000001"
    return {"id": mid, "pricing": {"prompt": price, "completion": price},
            "supported_parameters": ["tools"] if tools else [], "context_length": ctx}


class FakeHttp:
    """Routes by URL; `answers_tools` is the set of model ids that make a tool call."""

    def __init__(self, catalog, answers_tools=(), local=None):
        self.catalog, self.answers, self.local = catalog, set(answers_tools), local

    def __call__(self, url, body=None, key=None, timeout=30):
        if url == picker.OPENROUTER + "/models":
            return {"data": self.catalog}
        if url == picker.OPENROUTER + "/chat/completions":
            calls = [{"id": "1"}] if body["model"] in self.answers else None
            return {"choices": [{"message": {"content": "ok", "tool_calls": calls}}]}
        if self.local and url.startswith(self.local[0]):
            return {"data": [{"id": m} for m in self.local[1]]}
        raise urllib.error.URLError("refused")


class PickerTest(unittest.TestCase):
    def test_filters_paid_toolless_and_small_context(self):
        self.assertTrue(picker.is_candidate(model("a")))
        self.assertFalse(picker.is_candidate(model("b", free=False)))
        self.assertFalse(picker.is_candidate(model("c", tools=False)))
        self.assertFalse(picker.is_candidate(model("d", ctx=32_000)))

    def test_chat_only_model_fails_smoke_test(self):
        http = FakeHttp([model("qwen/q:free"), model("llama/l:free")], answers_tools={"llama/l:free"})
        pick = picker.plan("k", http=http, log=lambda *_: None)
        self.assertEqual(pick["primary"], {"provider": "openrouter", "model": "llama/l:free"})
        self.assertEqual(pick["fallbacks"], [])

    def test_runners_up_then_local_in_chain(self):
        ids = ["gemini/g:free", "qwen/q:free", "llama/l:free", "glm/x:free"]
        http = FakeHttp([model(i) for i in ids], answers_tools=ids,
                        local=("http://127.0.0.1:11434", ["nomic-embed", "qwen3:8b"]))
        pick = picker.plan("k", http=http, log=lambda *_: None)
        self.assertEqual(pick["primary"]["model"], "gemini/g:free")
        self.assertEqual([f["model"] for f in pick["fallbacks"]],
                         ["qwen/q:free", "llama/l:free", "qwen3:8b"])
        self.assertEqual(pick["fallbacks"][-1]["provider"], "custom")

    def test_no_key_uses_local_as_primary(self):
        http = FakeHttp([], local=("http://127.0.0.1:1234", ["phi-4"]))
        pick = picker.plan(None, http=http, log=lambda *_: None)
        self.assertEqual(pick["primary"],
                         {"provider": "lmstudio", "model": "phi-4", "base_url": "http://127.0.0.1:1234/v1"})

    def test_empty_ollama_falls_through_to_lm_studio(self):
        def http(url, body=None, key=None, timeout=30):
            if url.startswith("http://127.0.0.1:11434"):
                return {"data": []}
            if url.startswith("http://127.0.0.1:1234"):
                return {"data": [{"id": "phi-4"}]}
            raise urllib.error.URLError("refused")
        self.assertEqual(picker.find_local(http)["provider"], "lmstudio")

    def test_nothing_works_returns_none(self):
        self.assertIsNone(picker.plan("k", http=FakeHttp([]), log=lambda *_: None))


class FailureReasonTest(unittest.TestCase):
    def test_bad_key_stops_early_and_says_so(self):
        tried, logs = [], []

        def http(url, body=None, key=None, timeout=30):
            if url.endswith("/models") and url.startswith(picker.OPENROUTER):
                return {"data": [model("qwen/a:free"), model("qwen/b:free")]}
            if body:
                tried.append(body["model"])
                raise urllib.error.HTTPError(url, 401, "Unauthorized", {},
                                             io.BytesIO(b'{"error":{"message":"No auth"}}'))
            raise urllib.error.URLError("refused")
        self.assertIsNone(picker.plan("bad", http=http, log=logs.append))
        self.assertEqual(tried, ["qwen/a:free"])
        self.assertTrue(any("HTTP 401: No auth" in line for line in logs))
        self.assertTrue(any("rejected the key" in line for line in logs))

    def test_all_free_failing_points_at_privacy_setting(self):
        logs = []
        picker.plan("k", http=FakeHttp([model("qwen/a:free")]), log=logs.append)
        self.assertTrue(any("settings/privacy" in line for line in logs))

    def test_local_lookup_ignores_http_proxy(self):
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"data":[{"id":"m"}]}')

            def log_message(self, *a):
                pass
        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        old = {k: os.environ.get(k) for k in ("http_proxy", "HTTP_PROXY", "no_proxy", "NO_PROXY")}
        os.environ.update(http_proxy="http://10.255.255.1:9", HTTP_PROXY="http://10.255.255.1:9")
        for k in ("no_proxy", "NO_PROXY"):
            os.environ.pop(k, None)
        try:
            url = "http://127.0.0.1:%d/v1/models" % srv.server_port
            self.assertEqual(picker.http_json(url, timeout=3), {"data": [{"id": "m"}]})
        finally:
            srv.shutdown()
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def run(*args):
            self.calls.append(args)
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        self.run = run

    def test_apply_openrouter_clears_local_base_url(self):
        pick = {"primary": {"provider": "openrouter", "model": "m"},
                "fallbacks": [{"provider": "custom", "model": "l", "base_url": "u"}]}
        hermes_config.apply(pick, run=self.run)
        self.assertIn(("config", "set", "model.default", "m"), self.calls)
        fb = [c for c in self.calls if c[2] == "fallback_providers"][0]
        self.assertEqual(json.loads(fb[3]), pick["fallbacks"])
        self.assertEqual(self.calls[-1], ("config", "unset", "model.base_url"))

    def test_apply_local_sets_base_url(self):
        pick = {"primary": {"provider": "custom", "model": "l", "base_url": "u"}, "fallbacks": []}
        hermes_config.apply(pick, run=self.run)
        self.assertIn(("config", "set", "model.base_url", "u"), self.calls)
        self.assertNotIn(("config", "unset", "model.base_url"), self.calls)

    def test_keeps_fallbacks_the_user_added(self):
        mine_before = [{"provider": "openrouter", "model": "old:free"}]
        users = {"provider": "anthropic", "model": "claude"}
        current = mine_before + [users, {"provider": "custom", "model": "l", "base_url": "u"}]

        def run(*args):
            return SimpleNamespace(returncode=0, stdout=json.dumps(current), stderr="")
        pick = {"primary": {"provider": "openrouter", "model": "new:free"},
                "fallbacks": [{"provider": "custom", "model": "l", "base_url": "u"}]}
        self.assertEqual(hermes_config.users_own_fallbacks(mine_before, pick, run), [users])

    def test_no_fallbacks_configured_yet(self):
        def run(*args):
            return SimpleNamespace(returncode=1, stdout="", stderr="Config key not set")
        pick = {"primary": {"provider": "openrouter", "model": "m"}, "fallbacks": []}
        self.assertEqual(hermes_config.users_own_fallbacks([], pick, run), [])

    def test_child_is_pinned_to_profile_home(self):
        self.assertEqual(hermes_config.child_env("/p/work")["HERMES_HOME"], "/p/work")
        argv = hermes_config.hermes_argv("config", "get", "x")
        self.assertEqual(argv[:3], [sys.executable, "-m", "hermes_cli.main"])

    def test_failed_write_raises(self):
        def run(*args):
            return SimpleNamespace(returncode=1, stdout="", stderr="nope")
        with self.assertRaises(RuntimeError):
            hermes_config.apply({"primary": {"provider": "openrouter", "model": "m"},
                                 "fallbacks": []}, run=run)


class StateTest(unittest.TestCase):
    def setUp(self):
        self.state = hermes_config.State(os.path.join(tempfile.mkdtemp(), "s.json"))

    def test_not_due_until_opted_in(self):
        self.assertFalse(self.state.due())
        self.state.save(model="m", checked_at=0)
        self.assertTrue(self.state.due())
        self.state.save(checked_at=1_000_000)
        self.assertFalse(self.state.due(now=1_000_000 + 3600))

    def test_hand_edit_means_hands_off(self):
        self.state.save(model="ours")
        self.assertFalse(self.state.user_took_over("ours"))
        self.assertTrue(self.state.user_took_over("theirs"))
        self.assertFalse(self.state.user_took_over(None))


if __name__ == "__main__":
    unittest.main()
