import types
import unittest

import main
import providers
import secrets_store
from stt import CloudRecognizer


def _fake_app(**config):
    """A minimal stand-in for VoiceTyperApp so we can exercise its cloud hooks
    without loading a real STT model."""
    cfg = dict(main.DEFAULT_CONFIG)
    cfg.update(config)
    return types.SimpleNamespace(
        config=cfg,
        language="Bangla",
        model_path=main.Path("models/dummy"),
        on_error=None,
        _forward_error=lambda message: None,
    )


class RewriteHookTests(unittest.TestCase):
    def setUp(self):
        self._get_key = secrets_store.get_key
        self._rewrite = providers.rewrite

    def tearDown(self):
        secrets_store.get_key = self._get_key
        providers.rewrite = self._rewrite

    def test_disabled_returns_original(self):
        app = _fake_app(online_enabled=False, rewrite_enabled=True)
        providers.rewrite = lambda *a, **k: "SHOULD NOT RUN"
        self.assertEqual(main.VoiceTyperApp._rewrite(app, "raw"), "raw")

    def test_no_key_returns_original(self):
        app = _fake_app(online_enabled=True, rewrite_enabled=True)
        secrets_store.get_key = lambda provider: None
        providers.rewrite = lambda *a, **k: "SHOULD NOT RUN"
        self.assertEqual(main.VoiceTyperApp._rewrite(app, "raw"), "raw")

    def test_success_returns_rewritten(self):
        app = _fake_app(online_enabled=True, rewrite_enabled=True, rewrite_provider="openai")
        secrets_store.get_key = lambda provider: "sk-x"
        providers.rewrite = lambda *a, **k: "polished"
        self.assertEqual(main.VoiceTyperApp._rewrite(app, "raw"), "polished")

    def test_provider_error_falls_back_to_original(self):
        app = _fake_app(online_enabled=True, rewrite_enabled=True)
        secrets_store.get_key = lambda provider: "sk-x"

        def boom(*a, **k):
            raise providers.ProviderError("HTTP 500")
        providers.rewrite = boom
        self.assertEqual(main.VoiceTyperApp._rewrite(app, "my words"), "my words")


class RecognizerSelectionTests(unittest.TestCase):
    def setUp(self):
        self._get_recognizer = main.get_recognizer
        self._get_key = secrets_store.get_key
        main.get_recognizer = lambda path: "OFFLINE"

    def tearDown(self):
        main.get_recognizer = self._get_recognizer
        secrets_store.get_key = self._get_key

    def test_offline_by_default(self):
        app = _fake_app()
        self.assertEqual(main.VoiceTyperApp._select_recognizer(app), "OFFLINE")

    def test_cloud_when_online_with_key(self):
        app = _fake_app(online_enabled=True, stt_provider="openai")
        secrets_store.get_key = lambda provider: "sk-x"
        rec = main.VoiceTyperApp._select_recognizer(app)
        self.assertIsInstance(rec, CloudRecognizer)
        self.assertEqual(rec.provider, "openai")

    def test_falls_back_to_offline_without_key(self):
        app = _fake_app(online_enabled=True, stt_provider="openai")
        secrets_store.get_key = lambda provider: None
        self.assertEqual(main.VoiceTyperApp._select_recognizer(app), "OFFLINE")


if __name__ == "__main__":
    unittest.main()
