"""Per-app audio output routing for Apple Music.

Uses the undocumented AudioPolicyConfig factory (the same persisted store
behind Settings > System > Sound > Volume mixer) to point Apple Music's
render endpoint at the virtual cable, or back to the system default.

Interface layout ported from EarTrumpet's AudioPolicyConfigService:
IInspectable-based factory, 19 unrelated methods, then
SetPersistedDefaultAudioEndpoint / GetPersistedDefaultAudioEndpoint /
ClearAllPersistedApplicationDefaultEndpoints.
"""

from __future__ import annotations

import ctypes
from ctypes import POINTER, c_int32, c_uint32, c_void_p, c_wchar_p

import comtypes  # noqa: F401  - ensures CoInitialize on the importing thread
import psutil
from comtypes import GUID
from pycaw.pycaw import AudioUtilities

APPLE_MUSIC_PROCESS = "AppleMusic.exe"
# The Apple Music UI process never opens an audio session; the actual
# renderer is this background agent, so routing must target it.
AUDIO_AGENT_PROCESS = "AMPLibraryAgent.exe"

_IID_21H2 = GUID("{AB3D4648-E242-459F-B02F-541C70306324}")
_IID_LEGACY = GUID("{2A59116D-6C4F-45E0-A74F-707E3FEF9258}")
_CLASS_NAME = "Windows.Media.Internal.AudioPolicyConfig"
_DEVINTERFACE_AUDIO_RENDER = "{E6327CAD-DCEC-4949-AE8A-991E976A79D2}"

# vtable: IUnknown(3) + IInspectable(3) + 19 preceding methods
_SLOT_SET = 25
_SLOT_GET = 26

_E_RENDER = 0  # EDataFlow.eRender
_ROLES = (0, 1)  # eConsole, eMultimedia

_combase = ctypes.WinDLL("combase")
_combase.WindowsCreateString.argtypes = [c_wchar_p, c_uint32, POINTER(c_void_p)]
_combase.WindowsCreateString.restype = c_int32
_combase.WindowsDeleteString.argtypes = [c_void_p]
_combase.WindowsDeleteString.restype = c_int32
_combase.WindowsGetStringRawBuffer.argtypes = [c_void_p, POINTER(c_uint32)]
_combase.WindowsGetStringRawBuffer.restype = c_wchar_p
_combase.RoGetActivationFactory.argtypes = [c_void_p, POINTER(GUID), POINTER(c_void_p)]
_combase.RoGetActivationFactory.restype = c_int32

_PROTO_SET = ctypes.WINFUNCTYPE(c_int32, c_void_p, c_uint32, c_int32, c_int32, c_void_p)
_PROTO_GET = ctypes.WINFUNCTYPE(c_int32, c_void_p, c_uint32, c_int32, c_int32,
                                POINTER(c_void_p))


class RoutingError(RuntimeError):
    pass


def _check(hr: int, what: str) -> None:
    if hr != 0:
        raise RoutingError(f"{what} failed: HRESULT 0x{hr & 0xFFFFFFFF:08X}")


def _hstring(value: str) -> c_void_p:
    out = c_void_p()
    _check(_combase.WindowsCreateString(value, len(value), ctypes.byref(out)),
           "WindowsCreateString")
    return out


def _read_hstring(hstr: c_void_p) -> str:
    if not hstr:
        return ""
    length = c_uint32()
    buf = _combase.WindowsGetStringRawBuffer(hstr, ctypes.byref(length))
    return buf[:length.value] if buf else ""


class _PolicyConfig:
    def __init__(self) -> None:
        class_h = _hstring(_CLASS_NAME)
        self._ptr = c_void_p()
        try:
            for iid in (_IID_21H2, _IID_LEGACY):
                hr = _combase.RoGetActivationFactory(
                    class_h, ctypes.byref(iid), ctypes.byref(self._ptr))
                if hr == 0 and self._ptr:
                    return
            raise RoutingError(f"AudioPolicyConfig activation failed: 0x{hr & 0xFFFFFFFF:08X}")
        finally:
            _combase.WindowsDeleteString(class_h)

    def _call(self, slot: int, proto, *args) -> int:
        vtbl = ctypes.cast(self._ptr,
                           POINTER(POINTER(c_void_p))).contents
        fn = proto(vtbl[slot])
        return fn(self._ptr, *args)

    def set_endpoint(self, pid: int, device_path: str | None) -> None:
        """device_path None resets the app to the system default."""
        hstr = _hstring(device_path) if device_path else c_void_p(None)
        try:
            for role in _ROLES:
                _check(self._call(_SLOT_SET, _PROTO_SET, pid, _E_RENDER, role, hstr),
                       "SetPersistedDefaultAudioEndpoint")
        finally:
            if device_path:
                _combase.WindowsDeleteString(hstr)

    def get_endpoint(self, pid: int) -> str:
        out = c_void_p()
        _check(self._call(_SLOT_GET, _PROTO_GET, pid, _E_RENDER, _ROLES[0],
                          ctypes.byref(out)),
               "GetPersistedDefaultAudioEndpoint")
        try:
            return _read_hstring(out)
        finally:
            if out:
                _combase.WindowsDeleteString(out)


def _device_path(mmdevice_id: str) -> str:
    return f"\\\\?\\SWD#MMDEVAPI#{mmdevice_id}#{_DEVINTERFACE_AUDIO_RENDER}"


def _pid_of(process_name: str) -> int | None:
    for proc in psutil.process_iter(["name"]):
        if proc.info["name"] == process_name:
            return proc.pid
    return None


def apple_music_pid() -> int | None:
    return _pid_of(APPLE_MUSIC_PROCESS)


def audio_agent_pid() -> int | None:
    return _pid_of(AUDIO_AGENT_PROCESS)


def list_render_endpoints() -> list[tuple[str, str]]:
    """[(mmdevice_id, friendly_name)] of active render endpoints."""
    result = []
    for device in AudioUtilities.GetAllDevices():
        if device.id and device.id.startswith("{0.0.0."):
            result.append((device.id, device.FriendlyName or device.id))
    return result


def find_render_endpoint_by_driver(driver_hint: str) -> tuple[str, str] | None:
    """Find the render endpoint whose name contains `driver_hint`.

    Used to map a capture device like 'CABLE Output (VB-Audio Virtual
    Cable)' to its render twin 'CABLE Input (VB-Audio Virtual Cable)'.
    """
    hint = driver_hint.lower()
    for mmdevice_id, name in list_render_endpoints():
        if hint in name.lower():
            return mmdevice_id, name
    return None


def capture_driver_hint(capture_name: str) -> str:
    """Extract the driver portion: 'CABLE Output (VB-Audio Virtual Cable)'
    -> 'VB-Audio Virtual Cable'."""
    start = capture_name.find("(")
    if start >= 0 and capture_name.rstrip().endswith(")"):
        return capture_name[start + 1:capture_name.rstrip().rfind(")")].strip()
    return capture_name.strip()


class AppleMusicRouter:
    """On/off routing of Apple Music's output to a chosen render endpoint.

    Targets AMPLibraryAgent.exe (the process that actually renders the
    audio). Streams are recreated on every track change, so a change
    takes effect from the next track - no Apple Music restart needed.
    """

    def __init__(self) -> None:
        self._config = _PolicyConfig()

    def _agent_pid(self) -> int:
        pid = audio_agent_pid()
        if pid is None:
            raise RoutingError(
                "AMPLibraryAgent.exe is not running (start Apple Music first)")
        return pid

    def _clear_frontend(self) -> None:
        """Remove any endpoint pinned on the UI process: it is not the
        renderer, and routing it can break the app's playback engine."""
        pid = apple_music_pid()
        if pid is not None:
            try:
                self._config.set_endpoint(pid, None)
            except RoutingError:
                pass

    def current_endpoint(self) -> str:
        return self._config.get_endpoint(self._agent_pid())

    def route_to(self, mmdevice_id: str) -> None:
        self._config.set_endpoint(self._agent_pid(), _device_path(mmdevice_id))
        self._clear_frontend()

    def reset(self) -> None:
        self._config.set_endpoint(self._agent_pid(), None)
        self._clear_frontend()


if __name__ == "__main__":
    router = AppleMusicRouter()
    print("Apple Music pid:", apple_music_pid())
    print("current:", router.current_endpoint() or "(default)")
    print("render endpoints:")
    for mmdevice_id, name in list_render_endpoints():
        print(" ", mmdevice_id, name)
