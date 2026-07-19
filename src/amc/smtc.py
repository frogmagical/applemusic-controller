"""Now-playing info and transport control for Apple Music via Windows SMTC.

Runs a dedicated thread with its own asyncio event loop so that the
(blocking-averse) WinRT async APIs can be used from a tkinter app.

Quirk: the Apple Music Windows app does not fill the SMTC album field.
Instead it reports the artist field as "<artist> — <album>" (em dash).
`_split_artist_album` untangles that.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as _SessionManager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
)

APPLE_MUSIC_APP_ID_PREFIX = "AppleInc.AppleMusic"

_ARTIST_ALBUM_SEP = " — "  # " — "


@dataclass
class NowPlaying:
    found: bool = False
    app_id: str = ""
    title: str = ""
    artist: str = ""
    album: str = ""
    status: str = "CLOSED"
    position: timedelta = field(default_factory=timedelta)
    duration: timedelta = field(default_factory=timedelta)

    @property
    def is_playing(self) -> bool:
        return self.status == "PLAYING"


def _split_artist_album(artist_raw: str, album_raw: str) -> tuple[str, str]:
    if album_raw:
        return artist_raw, album_raw
    if _ARTIST_ALBUM_SEP in artist_raw:
        artist, album = artist_raw.split(_ARTIST_ALBUM_SEP, 1)
        return artist.strip(), album.strip()
    return artist_raw, ""


class SmtcClient:
    """Background SMTC poller + transport commands, safe to use from any thread."""

    def __init__(self, app_id_prefix: str = APPLE_MUSIC_APP_ID_PREFIX,
                 poll_interval: float = 0.5) -> None:
        self._app_id_prefix = app_id_prefix
        self._poll_interval = poll_interval
        self._lock = threading.Lock()
        self._now_playing = NowPlaying()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="smtc", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._loop is not None:
            self._loop.call_soon_threadsafe(lambda: None)  # wake the loop

    # -- public API --------------------------------------------------------

    @property
    def now_playing(self) -> NowPlaying:
        with self._lock:
            return self._now_playing

    def toggle_play_pause(self) -> None:
        self._submit(self._transport("try_toggle_play_pause_async"))

    def skip_next(self) -> None:
        self._submit(self._transport("try_skip_next_async"))

    def skip_previous(self) -> None:
        self._submit(self._transport("try_skip_previous_async"))

    # -- internals ---------------------------------------------------------

    def _submit(self, coro) -> None:
        if self._loop is not None:
            asyncio.run_coroutine_threadsafe(coro, self._loop)

    def _run(self) -> None:
        asyncio.run(self._main())

    async def _main(self) -> None:
        self._loop = asyncio.get_running_loop()
        manager = await _SessionManager.request_async()
        while not self._stop.is_set():
            try:
                np_ = await self._snapshot(manager)
            except Exception:
                np_ = NowPlaying()
            with self._lock:
                self._now_playing = np_
            await asyncio.sleep(self._poll_interval)

    async def _find_session(self, manager):
        for session in manager.get_sessions():
            if (session.source_app_user_model_id or "").startswith(self._app_id_prefix):
                return session
        return None

    async def _snapshot(self, manager) -> NowPlaying:
        session = await self._find_session(manager)
        if session is None:
            return NowPlaying()
        props = await session.try_get_media_properties_async()
        info = session.get_playback_info()
        timeline = session.get_timeline_properties()

        artist, album = _split_artist_album(props.artist or "", props.album_title or "")
        status = PlaybackStatus(info.playback_status).name

        position = timeline.position
        if status == "PLAYING" and timeline.last_updated_time is not None:
            # SMTC only pushes timeline updates sparsely; extrapolate.
            elapsed = datetime.now(timezone.utc) - timeline.last_updated_time
            if timedelta() < elapsed < timedelta(minutes=30):
                position = position + elapsed
        duration = timeline.end_time
        if duration > timedelta() and position > duration:
            position = duration

        return NowPlaying(
            found=True,
            app_id=session.source_app_user_model_id or "",
            title=props.title or "",
            artist=artist,
            album=album,
            status=status,
            position=position,
            duration=duration,
        )

    async def _transport(self, method_name: str) -> None:
        manager = await _SessionManager.request_async()
        session = await self._find_session(manager)
        if session is not None:
            await getattr(session, method_name)()


def format_timedelta(td: timedelta) -> str:
    total = max(0, int(td.total_seconds()))
    minutes, seconds = divmod(total, 60)
    return f"{minutes}:{seconds:02d}"


if __name__ == "__main__":
    # Quick manual check: python -m amc.smtc
    import time

    client = SmtcClient()
    client.start()
    time.sleep(2)
    np_ = client.now_playing
    if not np_.found:
        print("Apple Music session not found")
    else:
        print(f"[{np_.status}] {np_.title} / {np_.artist} ({np_.album})")
        print(f"  {format_timedelta(np_.position)} / {format_timedelta(np_.duration)}")
    client.stop()
