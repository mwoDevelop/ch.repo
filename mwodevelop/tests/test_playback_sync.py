import importlib.util
import json
import sqlite3
import sys
import tempfile
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
    def test_cached_record_decorates_never_played_list_item(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "playback-state.sqlite"
            page = "/my-little-pony-episode-2"
            record = {
                "namespace": playback_sync.NAMESPACE,
                "content_key": playback_sync.playback_identity(page),
                "state": "in_progress",
                "playcount": 0,
                "resume_seconds": 11,
                "duration_seconds": 1327,
                "lastplayed_utc": "2026-08-31T12:00:00Z",
                "server_revision": 1,
            }
            with sqlite3.connect(database_path) as database:
                database.execute(
                    "CREATE TABLE records(namespace TEXT, content_key TEXT, document TEXT)"
                )
                database.execute(
                    "INSERT INTO records VALUES (?, ?, ?)",
                    (
                        playback_sync.NAMESPACE,
                        record["content_key"],
                        json.dumps(record),
                    ),
                )

            class Tag:
                def __init__(self):
                    self.playcount = None
                    self.resume = None

                def setPlaycount(self, value):
                    self.playcount = value

                def setResumePoint(self, position, total):
                    self.resume = (position, total)

            class Item:
                def __init__(self):
                    self.tag = Tag()
                    self.properties = {}

                def getVideoInfoTag(self):
                    return self.tag

                def setProperty(self, key, value):
                    self.properties[key] = value

            item = Item()
            result = playback_sync.apply_cached_playback(
                item, page, database_path
            )

            self.assertEqual(result, record)
            self.assertEqual(item.tag.playcount, 0)
            self.assertEqual(item.tag.resume, (11, 1327))
            self.assertEqual(item.properties["ResumeTime"], "11")

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
            executeJSONRPC=lambda value: (
                calls.append(json.loads(value)) or '{"result":"OK"}'
            )
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
        self.assertEqual(calls[0]["method"], "JSONRPC.NotifyAll")
        self.assertEqual(calls[0]["params"]["message"], "playback-identity-v1")
        self.assertEqual(calls[1]["params"]["message"], "playback-register-v1")
        for call in calls:
            document = call["params"]["data"]
            self.assertEqual(call["params"]["sender"], playback_sync.SOURCE_ADDON)
            self.assertEqual(document["namespace"], playback_sync.NAMESPACE)
            self.assertEqual(document["kodi_path"], path)

    def test_notification_rejection_is_fail_closed(self):
        previous = sys.modules.get("xbmc")
        sys.modules["xbmc"] = types.SimpleNamespace(
            executeJSONRPC=lambda _value: '{"error":{"code":-32601}}'
        )
        try:
            with self.assertRaises(ValueError):
                playback_sync.notify_profile_identity(
                    "/my-little-pony-episode-2",
                    "plugin://plugin.video.watchnixtoons2.mwodevelop/"
                    "?action=actionResolve&url=%2Fmy-little-pony-episode-2",
                )
        finally:
            if previous is None:
                sys.modules.pop("xbmc", None)
            else:
                sys.modules["xbmc"] = previous
