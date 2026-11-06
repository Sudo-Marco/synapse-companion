from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math

import numpy as np


@dataclass(frozen=True, slots=True)
class AudioMetrics:
    """Small aggregate result; deliberately contains no waveform or transcript."""

    level: float = 0.0
    voice_active: bool = False
    music_active: bool = False
    bpm: float = 0.0
    beat_phase: float = 0.0
    fallback_playback_state: bool = False


def playback_states_active(states) -> bool:
    """Reduce Windows Core Audio session states to one boolean, then discard them."""
    return any(int(state) == 1 for state in states)


class AudioFeatureAnalyzer:
    """Heuristic voice/music features using bounded windows and NumPy only."""

    def __init__(self, sample_rate: int = 11025, *,
                 voice_rms_min: float = 0.012,
                 music_rms_min: float = 0.008,
                 band_ratio_min: float = 0.35,
                 modulation_min: float = 0.045,
                 flux_min: float = 0.035,
                 history_seconds: float = 8.0) -> None:
        self.sample_rate = max(4000, int(sample_rate))
        self.voice_rms_min = max(0.0, float(voice_rms_min))
        self.music_rms_min = max(0.0, float(music_rms_min))
        self.band_ratio_min = max(0.0, min(1.0, float(band_ratio_min)))
        self.modulation_min = max(0.0, float(modulation_min))
        self.flux_min = max(0.0, float(flux_min))
        self._rms_history: deque[float] = deque(maxlen=24)
        self._voice_ratio_history: deque[float] = deque(maxlen=24)
        self._onsets: deque[float] = deque()
        self._previous_spectrum: np.ndarray | None = None
        self._last_onset = -math.inf
        self._history_s = max(3.0, float(history_seconds))

    @staticmethod
    def _mono(samples) -> np.ndarray:
        values = np.asarray(samples, dtype=np.float32)
        if values.ndim == 2:
            values = values.mean(axis=1)
        values = values.reshape(-1)
        if not values.size:
            return np.zeros(0, dtype=np.float32)
        return np.nan_to_num(values, copy=False, nan=0.0, posinf=0.0, neginf=0.0)

    def process(self, samples, now: float) -> AudioMetrics:
        values = self._mono(samples)
        if not values.size:
            return AudioMetrics()
        level = float(np.sqrt(np.mean(values * values, dtype=np.float64)))
        window = np.hanning(values.size).astype(np.float32, copy=False)
        magnitude = np.abs(np.fft.rfft(values * window, n=512))
        frequencies = np.fft.rfftfreq(512, 1.0 / self.sample_rate)
        energy = magnitude * magnitude
        total_energy = float(energy.sum()) + 1e-12
        band_mask = (frequencies >= 300.0) & (frequencies <= 3400.0)
        band_ratio = float(energy[band_mask].sum() / total_energy)
        self._rms_history.append(level)
        self._voice_ratio_history.append(band_ratio)

        modulation = 0.0
        if len(self._rms_history) >= 10:
            envelope = np.asarray(self._rms_history, dtype=np.float32)
            mean = float(envelope.mean()) + 1e-8
            modulation = float(np.quantile(envelope, 0.9)
                               - np.quantile(envelope, 0.1)) / mean
        voice_active = (level >= self.voice_rms_min
                        and band_ratio >= self.band_ratio_min
                        and len(self._voice_ratio_history) >= 10
                        and sum(value >= self.band_ratio_min
                                for value in self._voice_ratio_history) >= 8
                        and modulation >= self.modulation_min)

        normalized = magnitude / (float(magnitude.sum()) + 1e-12)
        if self._previous_spectrum is None:
            flux = float(normalized.sum())
        else:
            flux = float(np.maximum(0.0, normalized - self._previous_spectrum).sum())
        self._previous_spectrum = normalized
        timestamp = float(now)
        if (level >= self.music_rms_min and flux >= self.flux_min
                and timestamp - self._last_onset >= 0.20):
            self._onsets.append(timestamp)
            self._last_onset = timestamp
        while self._onsets and timestamp - self._onsets[0] > self._history_s:
            self._onsets.popleft()
        bpm, regularity = self._estimate_bpm()
        recent_count = sum(timestamp - onset <= 3.5 for onset in self._onsets)
        music_active = (recent_count >= 3
                        and bool(self._onsets)
                        and timestamp - self._onsets[-1] <= 1.5
                        and regularity <= 0.32 and 60.0 <= bpm <= 180.0)
        beat_phase = 0.0
        if self._onsets and bpm > 0.0:
            beat_period = 60.0 / bpm
            beat_phase = ((timestamp - self._onsets[-1]) / beat_period) % 1.0
        return AudioMetrics(level=level, voice_active=voice_active,
                            music_active=music_active, bpm=bpm,
                            beat_phase=beat_phase)

    def _estimate_bpm(self) -> tuple[float, float]:
        if len(self._onsets) < 3:
            return 0.0, 1.0
        intervals = np.diff(np.asarray(self._onsets, dtype=np.float64))
        intervals = intervals[(intervals >= 1.0 / 3.0) & (intervals <= 1.0)]
        if intervals.size < 2:
            return 0.0, 1.0
        median = float(np.median(intervals))
        if median <= 0:
            return 0.0, 1.0
        bpm = 60.0 / median
        if bpm < 60.0:
            bpm *= 2.0
        elif bpm > 180.0:
            bpm *= 0.5
        regularity = float(np.std(intervals) / (np.mean(intervals) + 1e-9))
        return max(0.0, min(240.0, bpm)), regularity


__all__ = ["AudioFeatureAnalyzer", "AudioMetrics", "playback_states_active"]
