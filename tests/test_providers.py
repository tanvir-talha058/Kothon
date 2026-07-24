import io
import json
import unittest
from urllib import error

import providers


class RewriteDispatchTests(unittest.TestCase):
    """Verify each provider builds the right request and parses its response.
    Network is mocked by replacing providers._request."""

    def setUp(self):
        self.calls = []
        self._orig = providers._request

        def fake_request(url, *, data, headers, timeout, method="POST"):
            try:
                body = json.loads(data.decode()) if data else None
            except (json.JSONDecodeError, UnicodeDecodeError):
                body = data  # multipart upload — keep raw bytes
            self.calls.append({"url": url, "headers": headers, "body": body, "method": method})
            return self._response
        providers._request = fake_request

    def tearDown(self):
        providers._request = self._orig

    def test_openai_rewrite(self):
        self._response = {"choices": [{"message": {"content": "Cleaned up."}}]}
        out = providers.rewrite("openai", "sk-x", "", "PROMPT", "messy text")
        self.assertEqual(out, "Cleaned up.")
        call = self.calls[0]
        self.assertTrue(call["url"].endswith("/chat/completions"))
        self.assertIn("api.openai.com", call["url"])
        self.assertEqual(call["headers"]["Authorization"], "Bearer sk-x")
        self.assertEqual(call["body"]["model"], "gpt-4o-mini")  # default model
        self.assertEqual(call["body"]["messages"][0]["content"], "PROMPT")
        self.assertEqual(call["body"]["messages"][1]["content"], "messy text")

    def test_openrouter_uses_its_base_url(self):
        self._response = {"choices": [{"message": {"content": "ok"}}]}
        providers.rewrite("openrouter", "sk-x", "some/model", "P", "t")
        self.assertIn("openrouter.ai", self.calls[0]["url"])
        self.assertEqual(self.calls[0]["body"]["model"], "some/model")

    def test_gemini_rewrite(self):
        self._response = {"candidates": [{"content": {"parts": [{"text": "fixed"}]}}]}
        out = providers.rewrite("gemini", "KEY", "", "P", "t")
        self.assertEqual(out, "fixed")
        self.assertIn("generativelanguage.googleapis.com", self.calls[0]["url"])
        self.assertIn("key=KEY", self.calls[0]["url"])
        self.assertIn("gemini-2.0-flash", self.calls[0]["url"])

    def test_anthropic_rewrite(self):
        self._response = {"stop_reason": "end_turn",
                          "content": [{"type": "text", "text": "clean"}]}
        out = providers.rewrite("anthropic", "sk-ant", "", "P", "t")
        self.assertEqual(out, "clean")
        self.assertEqual(self.calls[0]["headers"]["x-api-key"], "sk-ant")
        self.assertEqual(self.calls[0]["headers"]["anthropic-version"], "2023-06-01")
        self.assertEqual(self.calls[0]["body"]["model"], "claude-haiku-4-5")

    def test_anthropic_refusal_raises(self):
        self._response = {"stop_reason": "refusal", "content": []}
        with self.assertRaises(providers.ProviderError):
            providers.rewrite("anthropic", "sk-ant", "", "P", "t")

    def test_empty_text_skips_network(self):
        self._response = {"choices": [{"message": {"content": "should not be used"}}]}
        self.assertEqual(providers.rewrite("openai", "k", "", "P", "   "), "   ")
        self.assertEqual(self.calls, [])

    def test_openai_transcribe(self):
        self._response = {"text": "hello world"}
        out = providers.transcribe("openai", "sk-x", "", b"RIFFxxxx")
        self.assertEqual(out, "hello world")
        call = self.calls[0]
        self.assertTrue(call["url"].endswith("/audio/transcriptions"))
        self.assertIn("multipart/form-data", call["headers"]["Content-Type"])

    def test_gemini_transcribe_uses_inline_audio(self):
        self._response = {"candidates": [{"content": {"parts": [{"text": "spoken"}]}}]}
        out = providers.transcribe("gemini", "KEY", "", b"RIFFxxxx")
        self.assertEqual(out, "spoken")
        parts = self.calls[0]["body"]["contents"][0]["parts"]
        self.assertTrue(any("inline_data" in p for p in parts))

    def test_transcribe_unsupported_provider(self):
        with self.assertRaises(providers.ProviderError):
            providers.transcribe("anthropic", "k", "", b"x")

    def test_unknown_provider(self):
        with self.assertRaises(providers.ProviderError):
            providers.rewrite("nope", "k", "", "P", "t")


class RequestErrorTests(unittest.TestCase):
    """_request maps HTTP/network failures to friendly ProviderError text."""

    def setUp(self):
        self._orig = providers.request.urlopen

    def tearDown(self):
        providers.request.urlopen = self._orig

    def test_http_error_includes_status_and_detail(self):
        payload = json.dumps({"error": {"message": "Invalid API key"}}).encode()

        def boom(req, timeout=None):
            raise error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(payload))
        providers.request.urlopen = boom
        # A raw rewrite call raises ProviderError...
        with self.assertRaises(providers.ProviderError) as ctx:
            providers.rewrite("openai", "bad-key", "", "P", "text")
        self.assertIn("401", str(ctx.exception))
        # ...while test_connection swallows it into a (False, message) tuple.
        ok, msg = providers.test_connection("openai", "bad-key")
        self.assertFalse(ok)
        self.assertIn("401", msg)

    def test_network_error(self):
        def boom(req, timeout=None):
            raise error.URLError("no route to host")
        providers.request.urlopen = boom
        ok, msg = providers.test_connection("gemini", "KEY")
        self.assertFalse(ok)
        self.assertIn("Network error", msg)


class TestConnectionTests(unittest.TestCase):
    def setUp(self):
        self._orig = providers._request

    def tearDown(self):
        providers._request = self._orig

    def test_ok(self):
        providers._request = lambda *a, **k: {"data": []}
        ok, msg = providers.test_connection("openai", "sk-x")
        self.assertTrue(ok)

    def test_no_key(self):
        ok, msg = providers.test_connection("openai", "")
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
