import importlib.util
import json
import sys
import types
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

    def test_visible_item_and_playback_use_distinct_notifications(self):
        calls = []
        previous = sys.modules.get("xbmc")
        sys.modules["xbmc"] = types.SimpleNamespace(
            executebuiltin=lambda value: calls.append(value)
        )
        try:
            page = "/my-little-pony-episode-2"
            path = (
                "plugin://plugin.video.watchnixtoons2.mwodevelop/"
                "?action=actionResolve&url=%2Fmy-little-pony-episode-2"
            )
            playback_sync.notify_profile_identity(page, path)
            playback_sync.notify_profile_sync(page, path)
        finally:
            if previous is None:
                sys.modules.pop("xbmc", None)
            else:
                sys.modules["xbmc"] = previous

        self.assertEqual(len(calls), 2)
        self.assertIn(",playback-identity-v1,", calls[0])
        self.assertIn(",playback-register-v1,", calls[1])
        for call in calls:
            payload = call.split(",", 2)[2][:-1]
            document = json.loads(payload)
            self.assertEqual(document["namespace"], playback_sync.NAMESPACE)
            self.assertEqual(document["kodi_path"], path)
