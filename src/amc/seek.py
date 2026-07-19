"""Seek control for Apple Music via UI Automation.

Apple Music accepts SMTC TryChangePlaybackPositionAsync and returns
success, but never actually moves the position (and reports
is_playback_position_enabled = False). The app's own seek slider
(AutomationId "LCDScrubber", range = track length in seconds) does work
through UIA RangeValuePattern, so we drive that instead.

UIA calls run on a dedicated worker thread with its own COM apartment.
"""

from __future__ import annotations

import threading

import psutil

APPLE_MUSIC_PROCESS = "AppleMusic.exe"
_SCRUBBER_AUTOMATION_ID = "LCDScrubber"


def _apple_music_pids() -> set[int]:
    return {p.pid for p in psutil.process_iter(["name"])
            if p.info["name"] == APPLE_MUSIC_PROCESS}


class AppleMusicSeeker:
    """Fire-and-forget seek requests; drops requests while one is running."""

    def __init__(self) -> None:
        self._busy = threading.Lock()
        self.last_error: str | None = None

    def seek(self, seconds: float) -> None:
        if not self._busy.acquire(blocking=False):
            return  # a seek is already in flight
        thread = threading.Thread(target=self._seek_worker, args=(seconds,),
                                  daemon=True, name="am-seek")
        thread.start()

    def _seek_worker(self, seconds: float) -> None:
        try:
            import uiautomation as auto

            with auto.UIAutomationInitializerInThread():
                pids = _apple_music_pids()
                if not pids:
                    self.last_error = "Apple Music is not running"
                    return
                for window in auto.GetRootControl().GetChildren():
                    if window.ProcessId not in pids:
                        continue
                    slider = window.SliderControl(
                        searchDepth=10, AutomationId=_SCRUBBER_AUTOMATION_ID)
                    if not slider.Exists(1, 0.2):
                        continue
                    pattern = slider.GetRangeValuePattern()
                    target = max(pattern.Minimum,
                                 min(float(seconds), pattern.Maximum))
                    pattern.SetValue(target)
                    self.last_error = None
                    return
                self.last_error = "Apple Music seek slider not found"
        except Exception as exc:  # UIA is flaky by nature; never crash the GUI
            self.last_error = str(exc)
        finally:
            self._busy.release()
