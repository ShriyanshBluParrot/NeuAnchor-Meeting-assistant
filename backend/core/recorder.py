"""Offline microphone recording.

Captures the local microphone (the laptop placed between participants) into a
mono 16 kHz WAV file. Recording is stateful: callers start a session, then stop
it later, so active streams are tracked in a module-level registry keyed by
session_id.
"""
import os
import tempfile
import threading

SAMPLE_RATE = 16_000
CHANNELS = 1


def _audio_libs():
    """Import the audio stack lazily so the backend boots on hosts without
    PortAudio (e.g. a cloud server that only handles online meetings)."""
    import numpy as np
    import sounddevice as sd
    import soundfile as sf

    return np, sd, sf


class _Recording:
    def __init__(self, session_id: str):
        np, sd, _ = _audio_libs()
        self._np = np
        self.session_id = session_id
        self._frames: list = []
        self._lock = threading.Lock()
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            callback=self._callback,
        )

    def _callback(self, indata, frames, time_info, status):  # noqa: ARG002
        with self._lock:
            self._frames.append(indata.copy())

    def start(self) -> None:
        self._stream.start()

    def stop_and_save(self) -> str:
        np, _, sf = _audio_libs()
        self._stream.stop()
        self._stream.close()
        with self._lock:
            audio = (
                np.concatenate(self._frames, axis=0)
                if self._frames
                else np.zeros((0, CHANNELS), dtype="int16")
            )
        path = os.path.join(tempfile.gettempdir(), f"{self.session_id}.wav")
        sf.write(path, audio, SAMPLE_RATE, subtype="PCM_16")
        return path


_active: dict[str, _Recording] = {}


def start_recording(session_id: str) -> None:
    if session_id in _active:
        raise ValueError(f"Recording already active for {session_id}")
    rec = _Recording(session_id)
    rec.start()
    _active[session_id] = rec


def stop_recording(session_id: str) -> str:
    """Stop the recording and return the path to the saved WAV file."""
    rec = _active.pop(session_id, None)
    if rec is None:
        raise ValueError(f"No active recording for {session_id}")
    return rec.stop_and_save()


def is_recording(session_id: str) -> bool:
    return session_id in _active
