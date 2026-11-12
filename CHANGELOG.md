# Changelog

Notable changes are recorded here. This project follows a simple Keep a Changelog structure and Semantic Versioning from the first tagged release.

## [Unreleased]

### Added

- Optional Cython LIF kernel with NumPy fallback, bitwise trajectory tests, and
  Windows/Ubuntu full-network tick benchmarks; NumPy remains the default.
- Optional Cython CSR propagation with destination-row and active-source
  traversal, lazy source indexing, bitwise tests, and Windows/Ubuntu benchmarks;
  NumPy remains the default.

### Planned

- Improve neural-only retention and evaluate the renderer on physical Windows
  desktops with mixed-DPI displays.

## [0.3.0] - 2026-11-06

### Added

- Expanded Piu's approved pixel-art poses and views, including bounded movement,
  depth, stamina-aware jumps, listening, and data-driven dance cycles.
- Added opt-in microphone and system-loopback features with worker-thread
  analysis, synthetic signal coverage, and no recording or transcription.
- Added a smooth five-period local day cycle, offline sunrise/sunset estimates,
  moon phases, layered scene depth, and optional decorative weather.
- Updated English and Brazilian Portuguese READMEs, architecture, autonomy,
  privacy, art, learning, performance, contributor, and release documentation.

### Changed

- Updated the package release metadata and project documentation to v0.3.0.
- Made CI's offscreen Windows/Linux test setup explicit about not requiring
  audio extras or physical audio devices.
- Rechecked the existing SNN experiment defaults; inhibition, sleep replay, and
  neuron-growth migration remain opt-in.

### Validation limits

- The headless suite passed all 136 tests locally and on GitHub Actions for
  Windows and Linux after a font-independent renderer assertion fix.
- Automated tests and renderer benchmarks are headless/offscreen. Physical
  Windows desktop behavior, GPU composition, monitor/DPI edge cases, and real
  audio devices were not validated.
- Voice/music recognition is heuristic; it does not understand speech. SNN
  scenario results remain synthetic and the hybrid policy can rely heavily on
  the contextual selector.

## [0.2.0] - 2026-11-06

### Added

- Approved Piu pixel-art atlases with front/back/turn, run, jump, approach and
  depth views; JSON frame metadata and emotion/action-to-pose routes.
- Pixel-art day/dusk/night scene, segmented panel styling, bundled Silkscreen
  OFL font, preview screenshots, and a generated Piu animation.
- Scene motion controller with easing, stride phase, jump height, depth,
  hysteretic native LOD, and drag/proposal guards.
- Transparent floating Piu view with the current sprite's alpha mask and
  return-to-pet controls.
- Bounded, optional sleep replay that can mix high-RPE and recent events; the
  experiment and its remaining retention gap are documented in `docs/LEARNING.md`.
- Optional tool-output current competition behind a disabled-by-default YAML
  flag; the configured 10-step interval measured about +1.1% tick cost but did
  not improve the scenario-c/Z SNN-only result, which remains below its target.
- Pixel-art guide and updated bilingual project documentation for version 0.2.0.

### Changed

- The default visual is now the Piu pixel-art style. Spectral, ASCII, and vector
  eye renderers remain selectable.
- The pixel renderer paints through a half-resolution nearest-neighbor buffer,
  caches HUD elements, and can resolve emotion poses from JSON routes.
- Snapshot schema, LIF topology, tools, and default deterministic dynamics are
  unchanged by the new optional experiments.

### Validation limits

- Automated Qt tests and screenshots are offscreen. Physical desktop,
  multi-monitor, mixed-DPI, and real OpenGL behavior are not validated here.
- The SNN-only replay target and the output-competition accuracy target were
  not reached; the features remain off by default.

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
