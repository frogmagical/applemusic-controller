"""Capture -> DSP -> playback streaming pipeline.

A single full-duplex PortAudio stream captures from the virtual cable
(where Apple Music is routed) and plays the processed audio on the real
output device. Because time-stretching changes the sample count, ring
buffers sit on both sides of the engine:

    input callback data -> inbuf -> StretchEngine.process -> outbuf -> output

Live-source tempo caveats (documented in README):
  * speed > 1.0 consumes input faster than Apple Music produces it, so
    playback runs ahead until the input buffer drains, then briefly gaps.
  * speed < 1.0 makes the input buffer grow; it is capped, and the oldest
    audio is dropped (a skip) once the cap is exceeded.
"""

from __future__ import annotations

import threading
from collections import deque

import numpy as np
import sounddevice as sd

from .dsp import StretchEngine


class _Fifo:
    """Sample FIFO over (channels, N) float32 chunks. Single-thread use."""

    def __init__(self, channels: int) -> None:
        self._channels = channels
        self._chunks: deque[np.ndarray] = deque()
        self.length = 0  # samples currently queued

    def push(self, chunk: np.ndarray) -> None:
        if chunk.shape[1] == 0:
            return
        self._chunks.append(chunk)
        self.length += chunk.shape[1]

    def pop(self, n: int) -> np.ndarray:
        """Pop exactly n samples, zero-padded when underrunning."""
        out = np.zeros((self._channels, n), dtype=np.float32)
        filled = 0
        while filled < n and self._chunks:
            chunk = self._chunks[0]
            take = min(n - filled, chunk.shape[1])
            out[:, filled:filled + take] = chunk[:, :take]
            filled += take
            if take == chunk.shape[1]:
                self._chunks.popleft()
            else:
                self._chunks[0] = chunk[:, take:]
            self.length -= take
        return out

    def drop_oldest(self, n: int) -> None:
        n = min(n, self.length)
        if n > 0:
            self.pop(n)

    def clear(self) -> None:
        self._chunks.clear()
        self.length = 0


class AudioPipeline:
    def __init__(
        self,
        engine: StretchEngine,
        input_device: int,
        output_device: int,
        samplerate: int = 48000,
        blocksize: int = 512,
        channels: int = 2,
        max_input_buffer_seconds: float = 5.0,
    ) -> None:
        self.engine = engine
        self.samplerate = samplerate
        self.blocksize = blocksize
        self.channels = channels
        self._max_inbuf = int(max_input_buffer_seconds * samplerate)
        self._inbuf = _Fifo(channels)
        self._outbuf = _Fifo(channels)
        self._underruns = 0
        self._skips = 0
        self._lock = threading.Lock()

        extra = sd.WasapiSettings(auto_convert=True)
        self._stream = sd.Stream(
            device=(input_device, output_device),
            samplerate=samplerate,
            blocksize=blocksize,
            channels=channels,
            dtype="float32",
            callback=self._callback,
            extra_settings=extra,
        )

    # -- audio thread ------------------------------------------------------

    def _callback(self, indata, outdata, frames, _time, status) -> None:
        if status.input_overflow or status.output_underflow:
            with self._lock:
                self._underruns += 1

        self._inbuf.push(np.ascontiguousarray(indata.T, dtype=np.float32))

        # Bound latency/memory when speed < 1 makes the input pile up.
        if self._inbuf.length > self._max_inbuf:
            self._inbuf.drop_oldest(self._inbuf.length - self._max_inbuf // 2)
            self.engine.flush()
            with self._lock:
                self._skips += 1

        # Feed the engine until we have enough output for this callback.
        # (Right after start the engine buffers input and returns None.)
        while self._outbuf.length < frames and self._inbuf.length >= self.blocksize:
            chunk = self._inbuf.pop(self.blocksize)
            processed = self.engine.process(chunk)
            if processed is not None:
                self._outbuf.push(processed)

        outdata[:] = self._outbuf.pop(frames).T

    # -- control thread ----------------------------------------------------

    def start(self) -> None:
        self._stream.start()

    def stop(self) -> None:
        self._stream.stop()
        self._stream.close()
        self._inbuf.clear()
        self._outbuf.clear()
        self.engine.flush()

    @property
    def active(self) -> bool:
        return bool(self._stream.active)

    @property
    def stats(self) -> dict[str, float]:
        with self._lock:
            return {
                "underruns": self._underruns,
                "skips": self._skips,
                "buffered_seconds": self._inbuf.length / self.samplerate,
                "latency_seconds": (self._inbuf.length + self._outbuf.length)
                / self.samplerate,
            }
