from __future__ import annotations

import numpy as np

from synapse_pet.sensors.audio_analysis import (AudioFeatureAnalyzer,
                                               playback_states_active)
from synapse_pet.sensors.audio_service import AudioMonitorService


def process_signal(analyzer, signal, sample_rate, chunk_size=512):
    latest = None
    for start in range(0, len(signal), chunk_size):
        chunk = signal[start:start + chunk_size]
        latest = analyzer.process(chunk, start / sample_rate)
    return latest


def test_silence_and_unmodulated_tone_do_not_trigger_voice_or_music():
    sample_rate = 11025
    silence = AudioFeatureAnalyzer(sample_rate)
    result = process_signal(silence, np.zeros(sample_rate), sample_rate)
    assert not result.voice_active and not result.music_active

    t = np.arange(sample_rate * 2, dtype=np.float32) / sample_rate
    tone = 0.06 * np.sin(2 * np.pi * 440 * t)
    analyzer = AudioFeatureAnalyzer(sample_rate)
    result = process_signal(analyzer, tone, sample_rate)
    assert not result.voice_active


def test_voice_band_with_syllabic_modulation_is_detected_without_transcription():
    sample_rate = 11025
    t = np.arange(sample_rate * 2, dtype=np.float32) / sample_rate
    envelope = 0.06 * (1.0 + 0.75 * np.sin(2 * np.pi * 4.0 * t))
    voice_like = envelope * np.sin(2 * np.pi * 520 * t)
    result = process_signal(AudioFeatureAnalyzer(sample_rate), voice_like, sample_rate)
    assert result.voice_active
    assert not hasattr(result, "text")
    assert not hasattr(result, "samples")


def click_track(sample_rate: int, bpm: int, seconds: int = 8) -> np.ndarray:
    signal = np.zeros(sample_rate * seconds, dtype=np.float32)
    period = round(sample_rate * 60.0 / bpm)
    click = np.hanning(160).astype(np.float32) * 0.7
    for start in range(0, len(signal) - len(click), period):
        signal[start:start + len(click)] += click
    return signal


def test_click_tracks_estimate_90_and_120_bpm_within_tolerance():
    sample_rate = 11025
    for expected in (90, 120):
        result = process_signal(
            AudioFeatureAnalyzer(sample_rate),
            click_track(sample_rate, expected), sample_rate)
        assert result.music_active
        assert abs(result.bpm - expected) <= 6
        assert 0.0 <= result.beat_phase < 1.0


def test_playback_fallback_reduces_session_states_to_a_boolean():
    assert playback_states_active([0, 0, 1, 2])
    assert not playback_states_active([0, 2])


def test_audio_service_opens_no_device_until_a_source_is_explicitly_started():
    service = AudioMonitorService()
    assert service.active_sources == ()
    assert service.status_snapshot() == {}
    service.stop_all()
    assert service.active_sources == ()


def test_audio_metrics_keep_only_aggregates_not_samples_or_transcripts():
    from dataclasses import fields

    names = {field.name for field in fields(AudioFeatureAnalyzer(11025).process(
        np.zeros(512, dtype=np.float32), 0.0))}
    assert names == {"level", "voice_active", "music_active", "bpm",
                     "beat_phase", "fallback_playback_state"}
