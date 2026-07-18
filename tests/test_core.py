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

    def test_corrupt_file_returns_empty(self):
        self.settings._PATH.parent.mkdir(parents=True, exist_ok=True)
        self.settings._PATH.write_text("{not json", encoding="utf-8")
        self.assertEqual(self.settings.load(), {})


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
