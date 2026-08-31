import importlib.util
import unittest
from pathlib import Path


MODULE = (
    Path(__file__).parents[1]
    / "overlays"
    / "lib"
    / "playback_sync.py"
)
SPEC = importlib.util.spec_from_file_location("wnt2_playback_sync", MODULE)
playback_sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(playback_sync)


class PlaybackSyncTests(unittest.TestCase):
    def test_identity_ignores_domain_and_unrelated_query(self):
        first = playback_sync.playback_identity(
            "https://www.wcostream.tv/my-little-pony-episode-2?lang=dub&token=secret"
        )
        second = playback_sync.playback_identity(
            "https://www.wcoflix.tv/My-Little-Pony-Episode-2/?lang=dub"
        )
        subbed = playback_sync.playback_identity(
            "/my-little-pony-episode-2?lang=sub"
        )

        self.assertEqual(first, second)
        self.assertTrue(first.startswith("sha256:"))
        self.assertNotEqual(first, subbed)
        self.assertNotIn("secret", first)

    def test_identity_rejects_missing_page(self):
        for value in ("", "/", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                playback_sync.playback_identity(value)
