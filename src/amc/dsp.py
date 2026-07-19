"""Pitch / tempo engine built on Rubber Band (pylibrb, R3 "finer" engine).

Rubber Band's realtime mode keeps analysis state across arbitrarily sized
`process` calls, which is what a streaming pipeline needs. (The previous
Signalsmith python-stretch binding resets per call and produces severe
artifacts when fed 512-sample blocks.)

Parameters are set from the GUI thread and applied inside `process`,
which is called from the audio thread; a lock plus a "dirty" flag keeps
the underlying stretcher object single-threaded.

Conventions:
    semitones : key change in semitones (+/-12)
    cents     : fine pitch offset in cents (+/-100)
    speed     : playback speed factor (1.0 = original tempo).
                Values != 1.0 change tempo WITHOUT changing pitch.
"""

from __future__ import annotations

import threading

import numpy as np
from pylibrb import Option, RubberBandStretcher


class StretchEngine:
    def __init__(self, channels: int = 2, samplerate: int = 48000) -> None:
        self._rb = RubberBandStretcher(
            sample_rate=samplerate,
            channels=channels,
            options=(Option.PROCESS_REALTIME
                     | Option.ENGINE_FINER
                     | Option.PitchHighConsistency),
        )
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
            self._rb.pitch_scale = 2.0 ** (total_semitones / 12.0)
            # Rubber Band time_ratio: >1 = slower/longer output,
            # our speed: >1 = faster, hence the inverse.
            self._rb.time_ratio = 1.0 / self._speed
            self._dirty = False

    def process(self, block: np.ndarray) -> np.ndarray | None:
        """block: float32 (channels, frames). Returns whatever output is
        ready as (channels, N), or None while the engine is still priming."""
        self._apply_pending()
        self._rb.process(block, False)
        available = self._rb.available()
        if available > 0:
            return self._rb.retrieve(available)
        return None

    def flush(self) -> None:
        self._rb.reset()
