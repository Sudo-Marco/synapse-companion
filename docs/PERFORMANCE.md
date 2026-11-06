# Performance measurements

These are short measurements from the development environment. The Qt runs
use an offscreen CPU renderer; they do not measure physical desktop
composition, GPU drivers, or mixed-DPI behavior. Treat the values as regression
checks, not hardware guarantees.

## SNN tick cost — v0.3 release sample

The paired comparison used the v0.2.0 commit and the v0.3 branch on the same
development host, Python 3.14.10, NumPy 2.5.4, seed 20261102, and 1,000 active
ticks per requested network size. The measured SNN topology and update code
were not changed by v0.3. Since this harness is sensitive to host load, this
is a development comparison, not a machine-independent performance claim.

| Requested network size | v0.2.0 baseline | v0.3.0 branch | Difference |
| ---: | ---: | ---: | ---: |
| 600 neurons | 9.1563 ms/tick | 9.0000 ms/tick | −1.71% |
| 1,000 neurons | 18.8125 ms/tick | 18.7188 ms/tick | −0.50% |

The paired sample is within the 3% ceiling. A separate v0.2.0 run on this host
measured 11.8594 and 25.6875 ms/tick, then a repeat returned 9.1563 and
18.8125 ms/tick. That spread shows substantial run-to-run noise; the paired
values are provisional rather than evidence of a speedup. The runtime appends
tool-output neurons: the measured populations were 712 and 1,112 total. RSS in
the paired current run was 54.91 MiB at 600 requested and 55.98 MiB at 1,000.
Idle CPU readings at this short probe duration are below useful resolution and
are not claims of zero idle cost.

The optional lateral competition path was measured separately with an
inhibition sample every 10 LIF steps (20 ms at `dt_ms: 2`). Against the same
feature-off sample, measured active cost was +1.08% at 600 neurons and +1.03%
at 1,000 neurons. It remains disabled by default because it did not improve
scenario-c/Z accuracy. A one-step sampling interval was substantially more
expensive and is not the configured experiment.

Raw reports: [`snn_piu_after.json`](../benchmarks/results/snn_piu_after.json),
[`snn_piu_wta.json`](../benchmarks/results/snn_piu_wta.json), and
[`snn_baseline_phase2.json`](../benchmarks/results/snn_baseline_phase2.json).

## Pixel renderer CPU and FPS — v0.3 release sample

Both samples used an 800×450 Qt widget, QPainter CPU backend, offscreen display,
and 10 seconds per phase. “Scene” is the pixel-art scene shown under Piu;
“HUD” adds the telemetry card. Both views are under the 6% active and 3% idle
CPU targets in this environment.

| View | Phase | Target FPS | v0.2.0 FPS / CPU | v0.3.0 FPS / CPU | CPU change |
| --- | --- | ---: | ---: | ---: | ---: |
| Scene | active | 30 | 30.3 / 5.50% | 29.9 / 4.56% | −17.1% |
| Scene | idle | 5 | 4.9 / 2.52% | 4.7 / 2.12% | −15.9% |
| HUD | active | 30 | 30.3 / 6.30% | 30.3 / 5.66% | −10.2% |
| HUD | idle | 5 | 4.9 / 1.10% | 5.0 / 1.42% | +29.1% |

The scene's 4.7 FPS idle reading is slightly below the 5 FPS target in this
short sample; HUD reached 5 FPS. The HUD idle CPU change is a small absolute
increase of 0.32 percentage points. These measurements use Qt's offscreen
event loop and do not include physical desktop composition or GPU drivers.
VRAM is not applicable to the CPU-only renderer and was not measured.

The renderer reports are [piu_render_after.json](../benchmarks/results/piu_render_after.json)
and [piu_render_v03_after.json](../benchmarks/results/piu_render_v03_after.json).
The paired SNN source and current reports are
[snn_baseline_v02_1000tick_matched.json](../benchmarks/results/snn_baseline_v02_1000tick_matched.json),
[snn_baseline_v03.json](../benchmarks/results/snn_baseline_v03.json), and
[snn_profile_v03.md](../benchmarks/results/snn_profile_v03.md).

## Sleep replay

Replay occurs once during sleep consolidation rather than on every ordinary
simulation tick. It uses up to 120 high-absolute-RPE and recent events when
explicitly enabled; its one-shot CPU cost appears in the `sleep` phase of the
SNN report. Replay is off by default. See [LEARNING.md](LEARNING.md) for its
scenario accuracy and remaining target gap.

## Reproduce

```powershell
.\.venv\Scripts\python.exe benchmarks\snn_baseline.py --ticks 1000 --profile-steps 40 --idle-seconds 2
.\.venv\Scripts\python.exe benchmarks\render_benchmark.py --renderer cpu --render-style pixel --size 800x450 --seconds 10
```

Use several hundred ticks for a more stable SNN comparison. Record Python,
NumPy, hardware, renderer, resolution, and sample duration when comparing
different systems. Do not infer desktop GPU behavior from an offscreen CPU
renderer.
