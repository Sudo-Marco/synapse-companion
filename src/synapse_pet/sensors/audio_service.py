from __future__ import annotations

from collections import deque
import os
import threading
import time

from .audio_analysis import AudioFeatureAnalyzer, AudioMetrics, playback_states_active


class AudioMonitorService:
    """Opt-in audio capture. Only aggregate metrics cross the worker boundary."""

    SOURCES = {"microphone", "loopback"}

    def __init__(self, *, sample_rate: int = 11025, block_size: int = 512,
                 config: dict[str, object] | None = None) -> None:
        self.sample_rate = max(4000, int(sample_rate))
        self.block_size = max(256, int(block_size))
        self.config = config or {}
        self._lock = threading.Lock()
        self._threads: dict[str, threading.Thread] = {}
        self._stops: dict[str, threading.Event] = {}
        self._statuses: dict[str, str] = {}
        self._latest: dict[str, AudioMetrics] = {}
        self._events: deque[tuple[str, str]] = deque(maxlen=64)

    @property
    def active_sources(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(name for name, thread in self._threads.items()
                                if thread.is_alive()
                                and not self._stops[name].is_set()))

    def status_snapshot(self) -> dict[str, str]:
        with self._lock:
            return dict(self._statuses)

    def metrics_snapshot(self) -> dict[str, AudioMetrics]:
        with self._lock:
            return dict(self._latest)

    def drain_events(self) -> list[tuple[str, str]]:
        with self._lock:
            result = list(self._events)
            self._events.clear()
            return result

    def start(self, source: str) -> bool:
        source = str(source)
        if source not in self.SOURCES:
            raise ValueError(f"unknown audio source: {source}")
        with self._lock:
            existing = self._threads.get(source)
            if existing is not None and existing.is_alive():
                return False
            stop = threading.Event()
            thread = threading.Thread(
                target=self._run, args=(source, stop),
                name=f"synapse-audio-{source}", daemon=True)
            self._threads[source] = thread
            self._stops[source] = stop
            self._statuses[source] = "starting"
            self._events.append((source, "starting"))
        thread.start()
        return True

    def stop(self, source: str, *, wait_s: float = 0.20) -> None:
        source = str(source)
        with self._lock:
            stop = self._stops.get(source)
            thread = self._threads.get(source)
            if stop is None or thread is None:
                self._statuses[source] = "disabled"
                self._latest.pop(source, None)
                return
            stop.set()
        if thread is not threading.current_thread():
            thread.join(max(0.0, min(0.5, float(wait_s))))
        if not thread.is_alive():
            with self._lock:
                self._threads.pop(source, None)
                self._stops.pop(source, None)
                self._statuses[source] = "disabled"
                self._latest.pop(source, None)
                self._events.append((source, "disabled"))

    def stop_all(self) -> None:
        for source in tuple(self.SOURCES):
            self.stop(source, wait_s=0.15)

    def _status(self, source: str, value: str) -> None:
        with self._lock:
            self._statuses[source] = value
            self._events.append((source, value))

    def _metrics(self, source: str, metrics: AudioMetrics) -> None:
        # Only bounded aggregate values are retained; the samples are not copied.
        with self._lock:
            self._latest[source] = metrics

    def _run(self, source: str, stop: threading.Event) -> None:
        analyzer = AudioFeatureAnalyzer(
            self.sample_rate,
            voice_rms_min=float(self.config.get("voice_rms_min", 0.012)),
            music_rms_min=float(self.config.get("music_rms_min", 0.008)),
            band_ratio_min=float(self.config.get("band_ratio_min", 0.35)),
            modulation_min=float(self.config.get("modulation_min", 0.045)),
            flux_min=float(self.config.get("flux_min", 0.035)))
        recorder = None
        try:
            try:
                import soundcard

                if source == "microphone":
                    device = soundcard.default_microphone()
                else:
                    speaker = soundcard.default_speaker()
                    if speaker is None:
                        raise RuntimeError("no output device")
                    device = soundcard.get_microphone(
                        speaker.name, include_loopback=True)
                if device is None:
                    raise RuntimeError("no input device")
                recorder = device.recorder(
                    samplerate=self.sample_rate, channels=1,
                    blocksize=self.block_size)
            except Exception:
                if source == "loopback" and self._run_playback_state_fallback(stop):
                    return
                self._status(source, "unavailable")
                return
            with recorder:
                self._status(source, "active")
                while not stop.is_set():
                    samples = recorder.record(numframes=self.block_size)
                    metrics = analyzer.process(samples, time.monotonic())
                    self._metrics(source, metrics)
        except Exception:
            # Device failures are reported as a generic status; audio and
            # device identifiers are never written to logs.
            if source == "loopback" and self._run_playback_state_fallback(stop):
                return
            self._status(source, "unavailable")
        finally:
            with self._lock:
                current = self._threads.get(source)
                if current is threading.current_thread():
                    self._threads.pop(source, None)
                    self._stops.pop(source, None)
                if stop.is_set():
                    self._statuses[source] = "disabled"
                    self._events.append((source, "disabled"))
                    self._latest.pop(source, None)
                elif self._statuses.get(source) == "starting":
                    self._statuses[source] = "unavailable"
                    self._events.append((source, "unavailable"))

    def _run_playback_state_fallback(self, stop: threading.Event) -> bool:
        """Windows fallback: active/inactive Core Audio state only, without titles."""
        if os.name != "nt":
            return False
        try:
            from pycaw.pycaw import AudioUtilities
        except Exception:
            return False
        self._status("loopback", "fallback_active")
        while not stop.wait(0.5):
            try:
                states = [int(session.State)
                          for session in AudioUtilities.GetAllSessions()]
                active = playback_states_active(states)
            except Exception:
                active = False
            self._metrics("loopback", AudioMetrics(
                music_active=active, bpm=0.0,
                fallback_playback_state=True))
        self._status("loopback", "disabled")
        return True


__all__ = ["AudioMonitorService"]
