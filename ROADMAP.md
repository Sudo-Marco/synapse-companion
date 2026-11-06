# Roadmap

This roadmap distinguishes delivered code from goals that remain experimental.
Items listed as current were checked in this release's source/tests; offscreen
tests do not establish behavior on a physical desktop.

## Version 0.3.0 scope — delivered

- Expanded the approved Piu pixel-art package with new views, depth levels,
  thinking/rest/listening/fall/peek poses, and data-driven movement/dance routes.
- Added bounded scene and floating-pet movement, depth-aware rendering,
  stamina costs, and geometry-only active-window interaction with drag and
  full-screen suppression.
- Added separately opt-in microphone and system-loopback sensors. Voice/music
  detection is heuristic, runs on worker threads, and does not record,
  transcribe, or upload audio.
- Added a smooth offline local-time scene cycle with five periods, optional
  manual sunrise/sunset coordinates, moon phase, and decorative local weather.
- Re-audited the existing SNN experiments, habits, learning panel, and snapshot
  migration. The LIF topology and learning rules did not change in this release;
  experimental inhibition, replay, and migration remain off by default.
- Updated bilingual documentation, privacy guidance, release benchmarks, and
  headless Windows/Linux CI.

Physical Windows interaction, multiple monitors/mixed DPI, and actual
microphone/loopback devices remain unvalidated; see the remaining work below.

## Version 0.2.0 scope

- Piu pixel-art view is the default. Approved sprite art, animation metadata,
  JSON state routes, native 32/24/16 depth sprites, scene, pixel panel styling,
  floating mode, and generated previews are included.
- Scene motion supports easing, stride phase, jump height, depth, hysteretic LOD,
  view changes, and drag/proposal suppression. The sprite alpha drives the
  floating window mask.
- LIF dynamics and deterministic reference behavior remain unchanged when the
  experimental YAML flags are disabled.
- Typed tool parameter validation, permissions, proposal timeout, snapshot
  migration, local post-it templates, aggregate habits, and telemetry are
  implemented and documented.
- Sleep replay is opt-in and bounded. In the recorded scenario-e run it did not
  reach the >80% SNN-only retention target; the selector still carried the
  combined policy. Keep it disabled unless its behavior is deliberately tested.
- The optional output-competition experiment is also disabled. At strength
  `0.35` it reduced SNN-only accuracy in scenario c/X from 100% to 57.5%, so it
  is not a recommended policy setting.

## Remaining engineering

1. Improve the neural-only contextual classifier without degrading the
   combined selector, especially scenario c/Z and scenario e retention. Run
   repeated seeds and confidence intervals before changing defaults.
2. Rework or remove the experimental output-inhibition rule unless a future
   version passes the b/c acceptance thresholds with no >3-point regressions.
3. Evaluate alternate sleep replay sampling/consolidation until neural-only
   retention exceeds 80% while preserving the new-context score and keeping
   replay CPU bounded.
4. Expand sprite-authored animation variety and replace QPainter scene effects
   with editable pixel assets where practical. Keep the approved Piu design.
5. Persist hourly autonomy and teleport budgets across restarts if they are to
   be presented as cross-session anti-spam limits.
6. Complete interactive Windows checks: OpenGL and CPU fallback, transparent
   click-through, tray, taskbar placements, multiple monitors, mixed DPI,
   screen edges, return-to-pet behavior, and sleep animation timing.
7. Add confidence intervals and broader synthetic contexts to the learning
   report; current learning scores use one fixed seed and artificial actions.

## Longer-term directions

- A small skills layer for reusable, explicitly permitted local routines.
- Optional local-language narration, isolated from SNN learning and disabled
  unless deliberately configured.
- Optional MCP integrations with per-tool permissions and data-flow review.
- More animation routes and scene reactions backed by reproducible tests.

These are possible future directions, not current capabilities or delivery
dates.
