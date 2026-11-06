# Performance measurements

These are short measurements from the development environment. The Qt runs
use an offscreen CPU renderer; they do not measure physical desktop
composition, GPU drivers, or mixed-DPI behavior. Treat the values as regression
checks, not hardware guarantees.

## SNN tick cost

The baseline used 120 active ticks and the post-change sample used 160 active
ticks, with the same seed/configuration and 600 or 1,000 requested neurons.
The small sample is sensitive to timer quantization. Changes are below the 3%
regression ceiling; negative values are not claimed as speedups.

| Requested network size | Prior baseline active CPU | Current feature-off sample | Difference |
| ---: | ---: | ---: | ---: |
| 600 neurons | 9.2188 ms/tick | 9.0820 ms/tick | −1.48% |
| 1,000 neurons | 19.2188 ms/tick | 19.0430 ms/tick | −0.91% |

The runtime appends tool-output neurons, so the live populations are larger than
the requested base sizes. The current 600-neuron process used about 55.37 MiB
RSS and the 1,000-neuron process about 55.99 MiB in the probe. The sampled idle
engine CPU was 0.00% at this short duration; that reading is below the useful
resolution of the probe and is not a claim of zero idle cost.

The optional lateral competition path was measured separately with an
inhibition sample every 10 LIF steps (20 ms at `dt_ms: 2`). Against the same
feature-off sample, measured active cost was +1.08% at 600 neurons and +1.03%
at 1,000 neurons. It remains disabled by default because it did not improve
scenario-c/Z accuracy. A one-step sampling interval was substantially more
expensive and is not the configured experiment.

Raw reports: [`snn_piu_after.json`](../benchmarks/results/snn_piu_after.json),
[`snn_piu_wta.json`](../benchmarks/results/snn_piu_wta.json), and
[`snn_baseline_phase2.json`](../benchmarks/results/snn_baseline_phase2.json).

## Pixel renderer CPU and FPS

The renderer benchmark used an 800×450 Qt widget, CPU/QPainter backend, and
offscreen display. “Scene” is the pixel-art scene shown under Piu; “HUD” adds
the cached telemetry card. The prior run lasted 5 seconds per phase and the
current run 10 seconds per phase, so compare only as an approximate check.

| View | Phase | FPS target / measured | CPU before | CPU after | Change |
| --- | --- | ---: | ---: | ---: | ---: |
| Scene | active | 30 / 30.39 → 30 / 30.30 | 5.53% | 5.50% | −0.5% |
| Scene | idle | 5 / 5.00 → 5 / 5.00 | 2.59% | 2.52% | −2.7% |
| HUD | active | 30 / 29.99 → 30 / 30.30 | 7.14% | 6.30% | −11.8% |
| HUD | idle | 5 / 5.00 → 5 / 5.00 | 2.60% | 1.10% | −57.7% |

The scene view is about 0.5 percentage points above the `<5%` active target in
this sample; the HUD active view is 1.3 points above it. Both idle views stayed
under 3%. The cached HUD and half-resolution nearest-neighbor buffer reduced
work, and measured FPS stayed at target. These CPU values depend on Qt's
offscreen event loop and should not be transferred to physical hardware.

The report files are [`piu_render_before_after.json`](../benchmarks/results/piu_render_before_after.json)
and [`piu_render_after.json`](../benchmarks/results/piu_render_after.json). The
first file contains the captured prior sample; the second is the current
10-second sample. Both use the CPU renderer, so VRAM is not applicable.

## Sleep replay

Replay occurs once during sleep consolidation rather than on every ordinary
simulation tick. It uses up to 120 high-absolute-RPE and recent events when
explicitly enabled; its one-shot CPU cost appears in the `sleep` phase of the
SNN report. Replay is off by default. See [LEARNING.md](LEARNING.md) for its
scenario accuracy and remaining target gap.

## Reproduce

```powershell
.\.venv\Scripts\python.exe benchmarks\snn_baseline.py --ticks 160 --profile-steps 40 --idle-seconds 2
.\.venv\Scripts\python.exe benchmarks\snn_baseline.py --ticks 160 --profile-steps 40 --idle-seconds 2 --tool-output-inhibition
.\.venv\Scripts\python.exe benchmarks\render_benchmark.py --renderer ascii --render-style pixel --size 800x450 --seconds 10
```

Use several hundred ticks for a more stable SNN comparison. Record Python,
NumPy, hardware, renderer, resolution, and sample duration when comparing
different systems. Do not infer desktop GPU behavior from an offscreen CPU
renderer.
