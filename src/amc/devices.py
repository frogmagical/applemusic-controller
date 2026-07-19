"""Audio device discovery helpers (WASAPI-focused)."""

from __future__ import annotations

from dataclasses import dataclass

import sounddevice as sd

# Substrings that identify the capture side of known virtual audio cables.
VIRTUAL_CAPTURE_HINTS = (
    "cable output",          # VB-CABLE
    "voicemeeter out",       # Voicemeeter
    "virtual audio",         # generic (e.g. "Voice Changer Virtual Audio Device")
    "virtual cable",
)


@dataclass(frozen=True)
class Device:
    index: int
    name: str
    hostapi: str
    max_input_channels: int
    max_output_channels: int

    def __str__(self) -> str:
        return f"[{self.index}] {self.name}"


def _wasapi_hostapi_index() -> int | None:
    for i, api in enumerate(sd.query_hostapis()):
        if "WASAPI" in api["name"]:
            return i
    return None


def _query(kind: str) -> list[Device]:
    """kind: 'input' or 'output'. Prefers WASAPI devices."""
    wasapi = _wasapi_hostapi_index()
    devices: list[Device] = []
    for i, d in enumerate(sd.query_devices()):
        if wasapi is not None and d["hostapi"] != wasapi:
            continue
        channels = d["max_input_channels"] if kind == "input" else d["max_output_channels"]
        if channels <= 0:
            continue
        devices.append(Device(
            index=i,
            name=d["name"],
            hostapi=sd.query_hostapis(d["hostapi"])["name"],
            max_input_channels=d["max_input_channels"],
            max_output_channels=d["max_output_channels"],
        ))
    return devices


def list_capture_devices() -> list[Device]:
    return _query("input")


def list_output_devices() -> list[Device]:
    return _query("output")


def guess_capture_device() -> Device | None:
    """Pick the device that most likely is a virtual cable's capture side."""
    candidates = list_capture_devices()
    for hint in VIRTUAL_CAPTURE_HINTS:
        for dev in candidates:
            if hint in dev.name.lower():
                return dev
    return None


def _device_from_index(index: int) -> Device:
    d = sd.query_devices(index)
    return Device(
        index=index,
        name=d["name"],
        hostapi=sd.query_hostapis(d["hostapi"])["name"],
        max_input_channels=d["max_input_channels"],
        max_output_channels=d["max_output_channels"],
    )


def default_output_device() -> Device | None:
    """The WASAPI host API's own default output device.

    PortAudio keeps a per-host-API default; asking WASAPI directly avoids
    the fragile name-matching between MME's truncated names and WASAPI's
    full names, and works the same on any machine.
    """
    wasapi = _wasapi_hostapi_index()
    if wasapi is not None:
        index = sd.query_hostapis(wasapi)["default_output_device"]
        if index is not None and index >= 0:
            return _device_from_index(index)
    try:
        index = sd.default.device[1]
    except Exception:
        return None
    if index is None or index < 0:
        return None
    return _device_from_index(index)
