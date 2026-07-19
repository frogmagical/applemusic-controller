"""Pitch / tempo engine built on Signalsmith Stretch.

Parameters are set from the GUI thread and applied inside `process`,
which is called from the audio thread; a lock plus a "dirty" flag keeps
the underlying Stretch object single-threaded.

Conventions:
    semitones : key change in semitones (+/-12)
    cents     : fine pitch offset in cents (+/-100)
    speed     : playback speed factor (1.0 = original tempo).
                Values != 1.0 change tempo WITHOUT changing pitch.
"""

from __future__ import annotations

import threading

import numpy as np
from python_stretch import Signalsmith


class StretchEngine:
    def __init__(self, channels: int = 2, samplerate: int = 48000) -> None:
        self._stretch = Signalsmith.Stretch()
        self._stretch.preset(channels, samplerate)
        self._lock = threading.Lock()
        self._semitones = 0.0
        self._cents = 0.0
        self._speed = 1.0
        self._dirty = False

    # -- parameter setters (GUI thread) -----------------------------------

    def set_semitones(self, semitones: float) -> None:
        with self._lock:
            self._semitones = float(semitones)
            self._dirty = True

    def set_cents(self, cents: float) -> None:
        with self._lock:
            self._cents = float(cents)
            self._dirty = True

    def set_speed(self, speed: float) -> None:
        with self._lock:
            self._speed = max(0.25, min(4.0, float(speed)))
            self._dirty = True

    def reset_all(self) -> None:
        with self._lock:
            self._semitones = 0.0
            self._cents = 0.0
            self._speed = 1.0
            self._dirty = True

    @property
    def params(self) -> tuple[float, float, float]:
        with self._lock:
            return self._semitones, self._cents, self._speed

    @property
    def is_neutral(self) -> bool:
        semitones, cents, speed = self.params
        return semitones == 0.0 and cents == 0.0 and speed == 1.0

    @property
    def speed(self) -> float:
        with self._lock:
            return self._speed

    # -- audio thread ------------------------------------------------------

    def _apply_pending(self) -> None:
        with self._lock:
            if not self._dirty:
                return
            total_semitones = self._semitones + self._cents / 100.0
            self._stretch.setTransposeFactor(2.0 ** (total_semitones / 12.0))
            # Signalsmith timeFactor: output_len = input_len / timeFactor,
            # i.e. factor > 1 plays the content faster.
            self._stretch.setTimeFactor(self._speed)
            self._dirty = False

    def process(self, block: np.ndarray) -> np.ndarray:
        """block: float32 array shaped (channels, frames). Returns same layout."""
        self._apply_pending()
        return self._stretch.process(block)

    def flush(self) -> None:
        self._stretch.reset()
