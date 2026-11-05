# Performance measurements

Measurements in this file are diagnostics from the recorded development environment. They are not guarantees for other machines or a live desktop session.

## SNN tick cost

The latest short feature-branch sample (40 active ticks, seed `20261102`) compared the B4 code with the recorded B1 baseline. It is a local diagnostic; the small sample is useful for checking the regression budget, not for claiming a precise speedup.

| Requested SNN size | B1 baseline CPU ms/tick | B4 sample CPU ms/tick | Difference |
| ---: | ---: | ---: | ---: |
| 600 neurons | 9.2188 | 9.3750 | +1.69% |
| 1,000 neurons | 19.0625 | 19.1406 | +0.41% |

The raw comparison and profile are [`snn_b4_personality_after.json`](../benchmarks/results/snn_b4_personality_after.json) and its adjacent Markdown report. The measured change is within the 3% tick-cost budget. The personality mapping runs on action/reward events and does not execute in the SNN tick loop.

A short launch comparison ran 60 active ticks on the current code and compared them with a previously recorded 300-tick benchmark. The current file is [`benchmarks/results/snn_launch_comparison.json`](../benchmarks/results/snn_launch_comparison.json); the prior reference is [`snn_runtime_resilience_after.json`](../benchmarks/results/snn_runtime_resilience_after.json).

| Requested SNN size | Prior active CPU ms/tick | Current sample | Difference |
| ---: | ---: | ---: | ---: |
| 600 neurons | 9.1146 | 9.1146 | 0.00% |
| 1,000 neurons | 18.9063 | 18.7500 | −0.83% |

The requested sizes become 712 and 1,112 runtime neurons after built-in tool output groups are added. Current process RSS was 55.30 MiB and 55.87 MiB, respectively. The short idle engine CPU probe measured 0.78% of one logical core. Tick deltas compare a 60-sample run with a 300-sample baseline and are within the measurement noise; the negative delta at 1,000 neurons is not evidence of a speedup.

The older context-projection comparison used 300 ticks and reported 9.0104 ms/tick at 600 neurons and 18.9063 ms/tick at 1,000. Later samples recorded about 9.11 ms/tick and 18.91 ms/tick. Differences at 600 were at or near the timer's quantization step. See the JSON/Markdown reports in `benchmarks/results/` for methodology.

## Floating UI idle sample

A 4-second offscreen Qt event-loop sample, after 4 seconds of warm-up, measured **0.39% of one logical core** with a 200 ms timer interval (5 FPS). This measures the offscreen renderer and does not include a physical Windows desktop compositor. It does not prove the target `<3%` on all hardware.

## Renderer sample (historical)

The tracked renderer reports were generated before the current small floating-pet default and measure a full panel at 800×450. They are not measurements of the new floating mode.

| Mode | GPU-enabled panel idle CPU | CPU-only panel idle CPU | Measured FPS target |
| --- | ---: | ---: | ---: |
| Shader | 4.03% | 9.77% | 5 |
| ASCII | 22.47% | 17.13% | 5 |
| HUD | 11.07% | 6.32% | 5 |

The brief active full-panel samples reported ASCII CPU above one logical core. The main panel's ASCII renderer is therefore substantially heavier than the compact floating eye; full-screen use can increase cost. VRAM readings are GPU/driver-specific and not directly comparable with process RSS.

## Reproduction

```powershell
.\.venv\Scripts\python.exe benchmarks\snn_baseline.py --ticks 60 --profile-steps 40 --idle-seconds 2
.\.venv\Scripts\python.exe benchmarks\render_benchmark.py --seconds 3
```

Use at least a few hundred ticks for a more stable SNN comparison. Record Python, NumPy, hardware, renderer, resolution, and run duration when comparing results. Avoid interpreting a short CPU-timer sample as a precise regression or speedup.
