"""Core unit tests for Kothon — run with: python -m unittest discover tests -v"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from banglish_fix import apply_punctuation, normalize_text
from recorder import _rms


class TestApplyPunctuation(unittest.TestCase):
    def test_basic_commands(self):
        self.assertEqual(apply_punctuation("hello comma world"), "hello, world")
        self.assertEqual(apply_punctuation("done full stop"), "done.")
        self.assertEqual(apply_punctuation("really question mark"), "really?")

    def test_no_space_before_punctuation(self):
        # Substituted symbols must attach to the preceding word
        self.assertEqual(apply_punctuation("hi comma how are you question mark"),
                         "hi, how are you?")

    def test_parentheses_hug_content(self):
        self.assertEqual(apply_punctuation("open bracket note close bracket"), "(note)")

    def test_new_line_survives(self):
        self.assertEqual(apply_punctuation("first new line second"), "first\nsecond")

    def test_case_insensitive(self):
        self.assertEqual(apply_punctuation("wait Comma go"), "wait, go")

    def test_plain_text_untouched(self):
        self.assertEqual(apply_punctuation("just a normal sentence"), "just a normal sentence")

    def test_empty(self):
        self.assertEqual(apply_punctuation(""), "")
        self.assertEqual(apply_punctuation("   "), "")

    def test_dash_keeps_single_spaces(self):
        # " — " replacement must not leave doubled spaces around the dash
        self.assertEqual(apply_punctuation("wait dash go"), "wait — go")


class TestNormalizeText(unittest.TestCase):
    def test_word_replacement(self):
        self.assertEqual(normalize_text("ami"), "আমি")

    def test_phrase_beats_words(self):
        self.assertEqual(normalize_text("ami bhalo achi"), "আমি ভালো আছি")

    def test_mixed_banglish_english(self):
        self.assertEqual(normalize_text("ami office jabo"), "আমি office যাবো")

    def test_punctuation_in_banglish(self):
        self.assertEqual(normalize_text("ami jabo full stop"), "আমি যাবো.")

    def test_partial_skips_phrases_and_punctuation(self):
        # Partial results only get single-word swaps, never phrase/punct commands
        out = normalize_text("thik ache full stop", is_partial=True)
        self.assertIn("full stop", out)
        self.assertNotIn(".", out)

    def test_partial_still_swaps_words(self):
        self.assertEqual(normalize_text("ami", is_partial=True), "আমি")

    def test_empty(self):
        self.assertEqual(normalize_text(""), "")


class TestCleanupText(unittest.TestCase):
    def setUp(self):
        # VoiceTyperApp.__init__ needs a Vosk model; test _cleanup_text unbound
        from main import VoiceTyperApp
        self.cleanup = lambda text, lang: VoiceTyperApp._cleanup_text(
            type("A", (), {"language": lang})(), text
        )

    def test_capitalizes_english(self):
        self.assertEqual(self.cleanup("hello world", "English"), "Hello world")

    def test_lone_i(self):
        self.assertEqual(self.cleanup("i", "English"), "I")

    def test_whitespace_collapsed(self):
        self.assertEqual(self.cleanup("a   b\t c", "English"), "A b c")

    def test_newline_preserved(self):
        # "new line" voice command must survive cleanup all the way to typing
        self.assertEqual(self.cleanup("first\nsecond", "English"), "First\nsecond")

    def test_bangla_not_capitalized(self):
        self.assertEqual(self.cleanup("আমি ভালো", "Bangla"), "আমি ভালো")

    def test_empty(self):
        self.assertEqual(self.cleanup("   ", "English"), "")


class TestRms(unittest.TestCase):
    def test_silence(self):
        self.assertEqual(_rms(b"\x00\x00" * 100), 0.0)

    def test_empty(self):
        self.assertEqual(_rms(b""), 0.0)

    def test_odd_length_is_safe(self):
        self.assertEqual(_rms(b"\x01\x02\x03"), 0.0)

    def test_full_scale(self):
        # int16 max ≈ 32767 → RMS ≈ 1.0
        self.assertAlmostEqual(_rms(b"\xff\x7f" * 100), 1.0, places=2)


class TestSettings(unittest.TestCase):
    def setUp(self):
        import settings
        self.settings = settings
        self._orig = settings._PATH
        self.tmp = tempfile.TemporaryDirectory()
        settings._PATH = Path(self.tmp.name) / "settings.json"

    def tearDown(self):
        self.settings._PATH = self._orig
        self.tmp.cleanup()

    def test_load_missing_file(self):
        self.assertEqual(self.settings.load(), {})

    def test_round_trip(self):
        self.settings.save({"language": "Bangla"})
        self.assertEqual(self.settings.load()["language"], "Bangla")

    def test_save_merges_existing_keys(self):
        # A partial save (e.g. language switch) must not wipe other keys (e.g. theme)
        self.settings.save({"theme": "day"})
        self.settings.save({"language": "English"})
        data = self.settings.load()
        self.assertEqual(data.get("theme"), "day")
        self.assertEqual(data.get("language"), "English")

    def test_save_leaves_no_temp_file(self):
        # save() writes via a temp file + atomic replace; the temp must not linger
        self.settings.save({"language": "Bangla"})
        leftovers = [p for p in self.settings._PATH.parent.iterdir() if p.suffix == ".tmp"]
        self.assertEqual(leftovers, [])
        self.assertEqual(self.settings.load()["language"], "Bangla")

    def test_corrupt_file_returns_empty(self):
        self.settings._PATH.parent.mkdir(parents=True, exist_ok=True)
        self.settings._PATH.write_text("{not json", encoding="utf-8")
        self.assertEqual(self.settings.load(), {})


_MODELS = Path(__file__).resolve().parent.parent / "models"


@unittest.skipUnless(_MODELS.exists(), "models/ not present (CI)")
class TestModelResolution(unittest.TestCase):
    def test_english_resolves(self):
        import main
        self.assertIn("en-us", main.resolve_model_path("English").name)

    def test_bangla_resolves_to_bn_model(self):
        import main
        self.assertIn("bn", main.resolve_model_path("Bangla").name)

    def test_banglish_stays_on_english_model(self):
        # Banglish = romanized speech: must use English STT + transliteration,
        # not the Bangla acoustic model
        import main
        self.assertIn("en-us", main.resolve_model_path("Banglish").name)

    def test_unknown_language_falls_back(self):
        import main
        # Any language string should still resolve to some available model
        self.assertTrue(main.resolve_model_path("Klingon").exists())


class TestTransliteration(unittest.TestCase):
    def test_common_words(self):
        from banglish_fix import transliterate
        self.assertEqual(transliterate("ami"), "আমি")
        self.assertEqual(transliterate("tumi"), "তুমি")
        self.assertEqual(transliterate("kore"), "করে")

    def test_aggressive_mode_converts_unknown_words(self):
        out = normalize_text("amar computer kharap", aggressive=True)
        self.assertNotIn("computer", out)     # transliterated, not left roman

    def test_default_mode_keeps_unknown_words_roman(self):
        self.assertEqual(normalize_text("ami office jabo"), "আমি office যাবো")


class TestBanglaPunctuation(unittest.TestCase):
    def test_dari_command(self):
        # \b fails after Bangla vowel signs — the whitespace-boundary patterns must match
        self.assertEqual(normalize_text("আমি ভালো আছি দাঁড়ি"), "আমি ভালো আছি।")

    def test_bangla_question_mark(self):
        self.assertEqual(normalize_text("তুমি কেমন প্রশ্নবোধক"), "তুমি কেমন?")

    def test_bangla_new_line(self):
        self.assertEqual(normalize_text("এক নতুন লাইন দুই"), "এক\nদুই")


class TestCustomizationOptions(unittest.TestCase):
    def test_punctuation_commands_can_be_disabled(self):
        out = normalize_text("ami jabo full stop", punctuation=False)
        self.assertIn("full stop", out)
        self.assertNotIn(".", out)

    def test_phrases_still_apply_without_punctuation(self):
        self.assertEqual(normalize_text("thik ache", punctuation=False), "ঠিক আছে")

    def test_capitalization_can_be_disabled(self):
        from main import DEFAULT_CONFIG, VoiceTyperApp
        fake = type("A", (), {
            "language": "English",
            "config": {**DEFAULT_CONFIG, "auto_capitalize": False},
        })()
        self.assertEqual(VoiceTyperApp._cleanup_text(fake, "hello world"), "hello world")

    def test_new_options_have_defaults(self):
        from main import DEFAULT_CONFIG
        for key in ("auto_stop", "trailing_space", "auto_capitalize",
                    "punctuation_commands", "sounds", "always_on_top", "minimize_to"):
            self.assertIn(key, DEFAULT_CONFIG)


class TestConfig(unittest.TestCase):
    def test_defaults_when_settings_empty(self):
        from main import DEFAULT_CONFIG, config_from_settings
        self.assertEqual(config_from_settings({}), DEFAULT_CONFIG)

    def test_saved_values_override_defaults(self):
        from main import config_from_settings
        cfg = config_from_settings({"silence_seconds": 4.0, "unrelated": 1})
        self.assertEqual(cfg["silence_seconds"], 4.0)
        self.assertNotIn("unrelated", cfg)


class TestUserDict(unittest.TestCase):
    def _write(self, tmp, payload):
        p = Path(tmp) / "custom_words.json"
        p.write_text(payload, encoding="utf-8")
        return p

    def test_loads_words_and_phrases(self):
        import json

        from banglish_fix import load_user_dict
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, json.dumps(
                {"words": {"Tanvir": "তানভীর"}, "phrases": {"ki obostha": "কি অবস্থা"}}
            ))
            words, phrases = load_user_dict(p)
            self.assertEqual(words, {"tanvir": "তানভীর"})   # keys lowercased
            self.assertEqual(phrases, {"ki obostha": "কি অবস্থা"})

    def test_missing_file_is_empty(self):
        from banglish_fix import load_user_dict
        self.assertEqual(load_user_dict(Path("does/not/exist.json")), ({}, {}))

    def test_malformed_file_is_ignored(self):
        from banglish_fix import load_user_dict
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, "{broken json")
            self.assertEqual(load_user_dict(p), ({}, {}))


class TestWindowsIntegration(unittest.TestCase):
    def test_hotkey_label(self):
        from main import hotkey_label
        self.assertEqual(hotkey_label("ctrl+shift+v"), "Ctrl+Shift+V")
        self.assertEqual(hotkey_label("ctrl + alt + k"), "Ctrl+Alt+K")

    def test_single_instance_mutex(self):
        # First acquire wins; acquiring the same named mutex again reports taken.
        # Uses a test-only name so a running Kothon doesn't affect the result.
        import os

        from main import acquire_single_instance
        name = f"Kothon.Test.Mutex.{os.getpid()}"
        self.assertTrue(acquire_single_instance(name))
        self.assertFalse(acquire_single_instance(name))

    def test_autostart_command_quotes_paths(self):
        from main import _autostart_command
        cmd = _autostart_command()
        self.assertTrue(cmd.startswith('"'))
        self.assertIn("python", cmd.lower())


class TestTyperStructs(unittest.TestCase):
    def test_input_struct_matches_windows_abi(self):
        # SendInput silently rejects every event if cbSize is wrong; the union
        # must include MOUSEINPUT (largest member) to reach 40 bytes on x64
        import ctypes

        from typer import INPUT
        expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
        self.assertEqual(ctypes.sizeof(INPUT), expected)


class TestEngineSelection(unittest.TestCase):
    def test_detects_sherpa_layout(self):
        import stt
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "am-onnx").mkdir()
            (Path(tmp) / "am-onnx" / "encoder.onnx").touch()
            self.assertTrue(stt.is_sherpa_model(tmp))

    def test_detects_vosk_layout(self):
        import stt
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "am").mkdir()
            self.assertFalse(stt.is_sherpa_model(tmp))

    def test_incomplete_sherpa_model_raises(self):
        import stt
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "am-onnx").mkdir()
            (Path(tmp) / "am-onnx" / "encoder.onnx").touch()
            with self.assertRaises(FileNotFoundError):
                stt.SherpaRecognizer(tmp)


if __name__ == "__main__":
    unittest.main()
