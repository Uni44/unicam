import unittest
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TalkbackLockTests(unittest.TestCase):
    def setUp(self):
        self.talkback = importlib.import_module("talkback")
        self.talkback.talk_state["holder_id"] = None
        self.talkback.talk_state["last_audio_at"] = 0

    def test_acquire_and_release(self):
        self.assertTrue(self.talkback.try_acquire("client-a"))
        self.assertFalse(self.talkback.try_acquire("client-b"))
        self.talkback.release("client-a")
        self.assertTrue(self.talkback.try_acquire("client-b"))

    def test_timeout_releases_holder(self):
        self.assertTrue(self.talkback.try_acquire("client-a"))
        self.talkback.talk_state["last_audio_at"] = 0.0
        self.assertTrue(self.talkback.try_acquire("client-b"))


if __name__ == "__main__":
    unittest.main()
