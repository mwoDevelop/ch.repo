# -*- coding: utf-8 -*-
"""Privacy-bounded playback identity notification for Profile Sync."""

import hashlib
import json
import os
import sqlite3
from urllib import parse as urllib_parse


NAMESPACE = "watchnixtoons2.playback.v1"
SOURCE_ADDON = "plugin.video.watchnixtoons2.mwodevelop"
PROFILE_SYNC_ADDON = "service.mwodevelop.profilesync"


def playback_identity(page_url):
    if not isinstance(page_url, str) or not page_url:
        raise ValueError("invalid playback page")
    parsed = urllib_parse.urlsplit(page_url)
    path = urllib_parse.unquote(parsed.path or "")
    path = "/" + "/".join(part for part in path.split("/") if part)
    if path == "/" or len(path) > 2048:
        raise ValueError("invalid playback page")
    query = urllib_parse.parse_qs(parsed.query, keep_blank_values=False)
    language = query.get("lang", [""])[0]
    if language not in {"", "dub", "sub"}:
        language = ""
    identity = {
        "schema": 1,
        "path": path.lower(),
        "language": language,
    }
    encoded = json.dumps(
        identity, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _notify(method, page_url, kodi_path):
    if (
        not isinstance(kodi_path, str)
        or not kodi_path.startswith("plugin://" + SOURCE_ADDON + "/")
        or len(kodi_path) > 4096
    ):
        raise ValueError("invalid Kodi playback path")
    document = {
        "namespace": NAMESPACE,
        "content_key": playback_identity(page_url),
        "kodi_path": kodi_path,
    }
    import xbmc

    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "JSONRPC.NotifyAll",
        "params": {
            "sender": SOURCE_ADDON,
            "message": method,
            "data": document,
        },
    }
    response = json.loads(
        xbmc.executeJSONRPC(
            json.dumps(request, sort_keys=True, separators=(",", ":"))
        )
    )
    if response.get("result") != "OK":
        raise ValueError("Profile Sync notification was rejected")
    return document


def notify_profile_identity(page_url, kodi_path):
    """Register a visible item without treating it as active playback."""
    return _notify("playback-identity-v1", page_url, kodi_path)


def notify_profile_sync(page_url, kodi_path):
    """Register the item selected for playback and arm progress sampling."""
    return _notify("playback-register-v1", page_url, kodi_path)


def cached_playback_state(page_url, database_path=None):
    """Read one redacted LWW record from Profile Sync's local cache."""

    if database_path is None:
        import xbmcvfs

        database_path = xbmcvfs.translatePath(
            "special://profile/addon_data/"
            + PROFILE_SYNC_ADDON
            + "/playback-state.sqlite"
        )
    database_path = str(database_path)
    if not os.path.isfile(database_path):
        return None
    uri = "file:%s?mode=ro" % urllib_parse.quote(database_path, safe="/")
    database = sqlite3.connect(uri, uri=True, timeout=0.2)
    try:
        row = database.execute(
            """
            SELECT document FROM records
            WHERE namespace=? AND content_key=?
            """,
            (NAMESPACE, playback_identity(page_url)),
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        database.close()
    if row is None:
        return None
    try:
        record = json.loads(row[0])
    except (TypeError, ValueError):
        return None
    required = {
        "namespace",
        "content_key",
        "state",
        "playcount",
        "resume_seconds",
        "duration_seconds",
        "lastplayed_utc",
        "server_revision",
    }
    if (
        not isinstance(record, dict)
        or set(record) != required
        or record.get("namespace") != NAMESPACE
        or record.get("content_key") != playback_identity(page_url)
        or record.get("state") not in {"unwatched", "in_progress", "watched"}
        or any(
            not isinstance(record.get(key), int)
            or isinstance(record.get(key), bool)
            or record.get(key) < 0
            for key in (
                "playcount",
                "resume_seconds",
                "duration_seconds",
                "server_revision",
            )
        )
    ):
        return None
    return record


def apply_cached_playback(item, page_url, database_path=None):
    """Decorate a WNT2 ListItem with the latest whole cached record."""

    record = cached_playback_state(page_url, database_path)
    if record is None:
        return None
    playcount = record["playcount"]
    resume = record["resume_seconds"]
    duration = record["duration_seconds"]
    tag = item.getVideoInfoTag() if hasattr(item, "getVideoInfoTag") else None
    if tag is not None and hasattr(tag, "setPlaycount"):
        tag.setPlaycount(playcount)
        if hasattr(tag, "setResumePoint") and duration > 0:
            tag.setResumePoint(resume, duration)
    elif hasattr(item, "setInfo"):
        item.setInfo("video", {"playcount": playcount})
    if hasattr(item, "setProperty"):
        item.setProperty("ResumeTime", str(resume))
        item.setProperty("TotalTime", str(duration))
    return record
