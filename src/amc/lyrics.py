"""Lyrics lookup via the lrclib.net public API.

Apple Music exposes no lyrics through SMTC, so we match the current
track (title / artist / duration) against lrclib's community database.
Lookups run on background threads and results are cached per track;
`poll` never blocks the GUI.
"""

from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request

_API = "https://lrclib.net/api"
_USER_AGENT = ("AppleMusicController/0.1 "
               "(+https://github.com/frogmagical/applemusic-controller)")
_TIMESTAMP = re.compile(r"^\s*\[[0-9:.]+\]\s*", re.MULTILINE)
_DURATION_TOLERANCE_S = 5


class _Loading:
    """Sentinel: a lookup for this track is still in flight."""


LOADING = _Loading()


class LyricsClient:
    """Non-blocking, cached lyrics lookups keyed by (title, artist)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: dict[tuple[str, str], str | None | _Loading] = {}

    def poll(self, title: str, artist: str,
             duration_s: float = 0.0) -> str | None | _Loading:
        """Returns lyrics text, None (not found), or LOADING.
        Starts a background fetch on first sight of a track."""
        key = (title, artist)
        with self._lock:
            if key in self._cache:
                return self._cache[key]
            self._cache[key] = LOADING
        threading.Thread(target=self._fetch, args=(key, duration_s),
                         daemon=True, name="lyrics").start()
        return LOADING

    # -- background thread -------------------------------------------------

    def _fetch(self, key: tuple[str, str], duration_s: float) -> None:
        title, artist = key
        try:
            text = (self._try_get(title, artist, duration_s)
                    or self._try_search(title, artist, duration_s))
        except Exception:
            text = None
        with self._lock:
            self._cache[key] = text

    def _request(self, path: str, params: dict):
        url = f"{_API}/{path}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _extract(item) -> str | None:
        if not item:
            return None
        plain = (item.get("plainLyrics") or "").strip()
        if plain:
            return plain
        synced = (item.get("syncedLyrics") or "").strip()
        if synced:
            return _TIMESTAMP.sub("", synced).strip()
        if item.get("instrumental"):
            return "(Instrumental)"
        return None

    def _try_get(self, title: str, artist: str, duration_s: float) -> str | None:
        params = {"track_name": title, "artist_name": artist}
        if duration_s > 0:
            params["duration"] = int(round(duration_s))
        try:
            return self._extract(self._request("get", params))
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise

    def _try_search(self, title: str, artist: str,
                    duration_s: float) -> str | None:
        results = self._request(
            "search", {"track_name": title, "artist_name": artist}) or []
        if duration_s > 0:
            results.sort(key=lambda r: abs((r.get("duration") or 0) - duration_s))
            results = [r for r in results
                       if abs((r.get("duration") or 0) - duration_s)
                       <= _DURATION_TOLERANCE_S] or results
        for item in results:
            text = self._extract(item)
            if text:
                return text
        return None


if __name__ == "__main__":
    # Manual check against the track currently playing in Apple Music.
    import time

    from .smtc import SmtcClient

    smtc = SmtcClient()
    smtc.start()
    time.sleep(2)
    now = smtc.now_playing
    smtc.stop()
    if not now.found:
        print("Apple Music session not found")
    else:
        print(f"track: {now.title} / {now.artist}")
        client = LyricsClient()
        client.poll(now.title, now.artist, now.duration.total_seconds())
        for _ in range(100):
            result = client.poll(now.title, now.artist)
            if not isinstance(result, _Loading):
                break
            time.sleep(0.2)
        if isinstance(result, str):
            lines = result.splitlines()
            print(f"found ({len(lines)} lines):")
            print("\n".join(lines[:8]))
            print("...")
        else:
            print("no lyrics found")
