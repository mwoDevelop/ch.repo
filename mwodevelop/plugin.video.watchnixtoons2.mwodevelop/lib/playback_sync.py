# -*- coding: utf-8 -*-
"""Privacy-bounded playback identity notification for Profile Sync."""

import hashlib
import json
from urllib import parse as urllib_parse


NAMESPACE = "watchnixtoons2.playback.v1"
SOURCE_ADDON = "plugin.video.watchnixtoons2.mwodevelop"


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
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":"))
    import xbmc

    xbmc.executebuiltin(
        "NotifyAll({0},{1},{2})".format(SOURCE_ADDON, method, encoded)
    )
    return document


def notify_profile_identity(page_url, kodi_path):
    """Register a visible item without treating it as active playback."""
    return _notify("playback-identity-v1", page_url, kodi_path)


def notify_profile_sync(page_url, kodi_path):
    """Register the item selected for playback and arm progress sampling."""
    return _notify("playback-register-v1", page_url, kodi_path)
