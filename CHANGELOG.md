# Changelog

Notable changes are recorded here. This project follows a simple Keep a Changelog structure and Semantic Versioning from the first tagged release.

## [Unreleased]

### Added

- Adaptive, rounded ASCII eye LOD with a configurable minimum glyph size, stable features at small sizes, and a six-background/six-size contrast review with native and enlarged captures.
- Bounded personality mapping for action initiative and contextual preference learning; defaults are configurable and the mapping can be disabled.
- Focus-safe post-it UI and RPE/habit regression tests.
- Floating-eye grid and geometry reflow after display/DPI changes, with offscreen regression coverage.
- Safe SNN snapshot migration (600→800 neurons) gated by explicit YAML configuration flag `network.allow_neuron_growth_migration` (default `false`).
- Verifiable pre-migration backup creation with SHA-256 checksum validation and atomic file replacement/rollback safety.
- Full semantic preservation of synaptic weights, LIF neuronal states, context-dependent output projections, and dynamic tool groups.
- Network reduction guard that preserves larger existing snapshots and logs a clear warning when configured with fewer neurons.
- Comprehensive migration test suite (`tests/test_neuron_growth_migration.py`) validating population scaling, determinism, idempotency, failure rollback, and tool edge persistence.

### Changed

- Tool dispatch now reports missing/invalid required parameters safely and enforces cooldown notices before proposals or execution.
- Documentation now describes the delivered features, limits, contrast metrics, and current benchmark sample without claiming live desktop validation.

## [0.1.0] - 2026-11-03

### Added

- Typed parameter schemas for built-in tools, validation before proposal/dispatch, safer configured folder defaults, short UI failures, and per-tool cooldowns.
- Transparent floating ASCII eye, on-demand panel, tray actions, optional global shortcut and Windows autostart, saved position, and click-through mask.
- Emotion-dependent teleport motion with ASCII particle trails, monitor-aware placement, hourly/session budget, cooldown, and drag/proposal guards.
- Bounded local post-it windows driven by coarse state, local YAML templates, expiry and position persistence, and small user-response feedback.
- Aggregate habit counts and an on-demand learning view.
- Opt-in sleep replay flag, disabled by default, with bounded high-RPE episode selection and coarse synthetic input reconstruction.
- English and Brazilian Portuguese documentation, privacy/architecture/performance/learning notes, contributor guidance, issue templates, and Windows/Linux headless CI.

### Changed

- Added an `rpe` field to the local episode database with an in-place migration for existing SQLite files.
- Updated package metadata and documented the synthetic learning results and benchmark limits.

### Limitations

- The project is not a language model or coding assistant.
- Learning curves are synthetic and the action policy combines neural output with contextual preferences.
- Sleep replay has not been evaluated against the scenario-e goal and remains disabled by default.
- Floating pet and post-it UI checks were offscreen; physical Windows desktop and multi-monitor validation remains outstanding.
- Hourly autonomy/teleport caps reset when the process restarts.
