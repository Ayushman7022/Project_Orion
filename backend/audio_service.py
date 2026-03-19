from __future__ import annotations

from ctypes import POINTER, cast


def _require_pycaw() -> tuple[object, object, object]:
    """
    Imports pycaw/comtypes at runtime.
    We keep imports local so the rest of the backend can run even if audio deps are missing.
    """
    try:
        from comtypes import CLSCTX_ALL  # type: ignore
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "Audio control dependencies are missing. Install with: pip install pycaw comtypes"
        ) from e

    return AudioUtilities, IAudioEndpointVolume, CLSCTX_ALL


def set_speaker_volume_scalar(volume_scalar: float) -> None:
    """
    Set default speaker volume.
    volume_scalar: 0.0 to 1.0
    """
    volume_scalar = max(0.0, min(1.0, float(volume_scalar)))

    AudioUtilities, IAudioEndpointVolume, CLSCTX_ALL = _require_pycaw()

    speakers = AudioUtilities.GetSpeakers()
    interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    volume = cast(interface, POINTER(IAudioEndpointVolume))
    volume.SetMasterVolumeLevelScalar(volume_scalar, None)


def mute_speaker(mute: bool) -> None:
    """Mute/unmute default speaker output."""
    AudioUtilities, IAudioEndpointVolume, CLSCTX_ALL = _require_pycaw()

    speakers = AudioUtilities.GetSpeakers()
    interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    volume = cast(interface, POINTER(IAudioEndpointVolume))
    volume.SetMute(bool(mute), None)


def mute_microphone(mute: bool) -> None:
    """Mute/unmute default microphone (capture endpoint)."""
    AudioUtilities, IAudioEndpointVolume, CLSCTX_ALL = _require_pycaw()

    mic = None
    # pycaw may expose either GetMicrophone() or GetMicrophones().
    try:
        mic = AudioUtilities.GetMicrophone()
    except Exception:
        mic = None

    if mic is None:
        try:
            mics = AudioUtilities.GetMicrophones()
            if mics:
                mic = mics[0]
        except Exception as e:
            raise RuntimeError("Could not locate a microphone capture device") from e

    if mic is None:
        raise RuntimeError("Could not locate a microphone capture device")

    interface = mic.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    volume = cast(interface, POINTER(IAudioEndpointVolume))
    volume.SetMute(bool(mute), None)

