# Learning protocol and measurements

This document reports offline simulator runs with artificial numeric contexts
and actions. It does not validate usefulness in the desktop application.
Experiments use seed `20261102`, 600 requested neurons, and three simulated
tools (`eval_a`–`eval_c`); no real tool is run.

## Learning channels

- Numeric sensor and coarse-context features are encoded as spikes for sparse
  leaky integrate-and-fire populations.
- Bounded eligibility traces record spike timing. `learning_rpe` applies
  reward-modulated STDP to synaptic weights.
- `affect_impulse` changes the simulated affect state separately and is not a
  weight-update channel.
- Context output projections share a sparse topology but hold lazy,
  context-specific readout weights.
- The action selector combines normalized neural firing rates with contextual
  action preferences. An ablation with either term removed is useful for
  describing the decision policy, but it is evaluated after the same training
  history rather than separate SNN-only training.

## Scenarios

| Scenario | Protocol | Acceptance criterion |
| --- | --- | --- |
| a | 150 training and 100 evaluation episodes in X | Combined accuracy >85% |
| b | 120 episodes, reverse mapping, up to 120 more; 100 eval | Readapt ≤60 episodes and final >85% |
| c | 100 examples/context interleaved; 40 eval/context | Combined >80% for X, Y, Z |
| d | 500 episodes with 10% inverted feedback; 100 eval | Combined >70% |
| e | 120 episodes in X, 1,000 in Y, 100 retained-context eval in X | Combined >70%; replay target SNN-only >80% |

Training uses 20% exploration. Evaluation is greedy, does not update the
state, and uses only artificial actions. The offline simulator also reports
`action_gate_eligible` and `production_action_available`; these describe
separate thresholds and are not the primary accuracy metric.

## Feature-off baseline

The full baseline CSV, JSON, and scenario curves are in
[`learning/piu-snn-baseline/`](learning/piu-snn-baseline/). Combined accuracy
reached 100% in each scenario. Neural-only performance remained below the
target in c/Z and e; contextual preferences explain much of the combined
result.

| Scenario | Combined | SNN-only | Preference-only | Mean absolute score share: SNN / selector |
| --- | ---: | ---: | ---: | ---: |
| a — association | 100% | 100% | 100% | 41% / 59% |
| b — reversal | 100%; readapt 44 episodes | 100% | 100% | 17% / 83% |
| c — X | 100% | 100% | 100% | 19% / 81% |
| c — Y | 100% | 97.5% | 100% | 37% / 63% |
| c — Z | 100% | 77.5% | 100% | 27% / 73% |
| d — 10% feedback noise | 100% | 100% | 100% | 26% / 74% |
| e — interference | 100% | 67% | 100% | 22% / 78% |

The score-share column is the average magnitude share of the normalized SNN
term and contextual-preference term for the combined policy's selected
candidate. It is descriptive score composition, not causal attribution.

## Optional sleep replay

Replay is controlled by `sleep.replay_enabled`, `false` by default. When
enabled, sleep consolidation takes at most 120 events by default: mostly
high-absolute-RPE events plus a small recent slice. It creates a low-noise
synthetic sensor input from a hashed coarse context; it does not retain or
replay raw sensor sequences. Replay runs once at consolidation rather than on
every active simulation tick.

The enabled run is in
[`learning/piu-snn-enabled/`](learning/piu-snn-enabled/). Scenario e retained
100% combined accuracy and reached 79% in the SNN-only evaluation, compared
with the 67% feature-off baseline. This remains below the >80% SNN-only target
by one percentage point; preference-only remained 100%. Therefore replay is
still opt-in, and its measured improvement should not be interpreted as
independent neural retention. The test used one seed and should be repeated
with more seeds before changing defaults.

## Optional output competition

`network.tool_output_inhibition` is disabled by default. Sampling competition
every 10 LIF steps kept the same-seed b and c ablations equal to the baseline:
b reached 100% with 44-episode readaptation, and c reached X=100%, Y=97.5%,
Z=77.5%. It did not meet the >80% target for Z, so it is not enabled by
default. At this configured interval the short benchmark measured +1.08% tick
cost at 600 neurons and +1.03% at 1,000; see [PERFORMANCE.md](PERFORMANCE.md).
An earlier every-step sample was substantially slower and was discarded.

## Curves and CSVs

Each output folder contains `results.json`, `scenario_[a-e].csv`, and
`scenario_[a-e].png`. The CSV records combined, neural-only and
preference-only choices, RPE, rates, action eligibility and weight drift.
Curves show rolling combined/neural accuracy, target probability, RPE, and
weight change. They use one fixed seed and are descriptive rather than
statistical evidence.

## Reproduce

```powershell
.\.venv\Scripts\python.exe -m synapse_pet.sim.learning_eval --output docs\learning\piu-snn-baseline --seed 20261102 --neurons 600
.\.venv\Scripts\python.exe -m synapse_pet.sim.learning_eval --output docs\learning\piu-snn-enabled --seed 20261102 --neurons 600 --sleep-replay
```

For full parameter context and limitations, also see [Architecture](ARCHITECTURE.md),
[Privacy](PRIVACY.md), and [Roadmap](../ROADMAP.md).

## v0.3 release audit

The v0.3 visual, autonomy, audio, and day-cycle work did not change the LIF
topology or learning update rules. The default YAML keeps
`network.tool_output_inhibition`, `sleep.replay_enabled`, and
`network.allow_neuron_growth_migration` disabled. Existing determinism,
projection-persistence, habit, replay-flag, and migration tests were rerun in
the full suite. The frozen spike/state hashes are unchanged; this confirms the
tested reference path, not every possible runtime input or desktop session.
The full values are recorded in the paired
[v0.2.0 baseline](../benchmarks/results/snn_baseline_v02_1000tick_matched.json)
and [v0.3.0 run](../benchmarks/results/snn_baseline_v03.json).
