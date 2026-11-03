# Autonomy and behavior budgets

Autonomous visual behavior is separate from the SNN simulation loop. It receives immutable visual state and rate summaries, then decides whether to request a UI effect. It does not run tools directly.

## Current behavior

| State or trigger | Current effect | Control |
| --- | --- | --- |
| SNN initiative plus an emotional state | Short ASCII particle teleport; style follows curiosity, happiness, stress, energy, or attention. | `teleport.enabled`, `initiative_rate_hz`, `cooldown_s`, `max_per_hour`, `targets`. |
| High stress | Local alert/pause post-it template. | `autonomy.behaviors.postits`, `postits.stress_threshold`, template `alerta`. |
| Repeated output attention | Conversation invitation template. | `postits.attention_rate_hz`, template `conversa`. |
| High boredom | Break reminder template. | `postits.boredom_threshold`, template `pausa`. |
| High curiosity | Explore invitation template. | `postits.curiosity_threshold`, template `curiosidade`. |
| Repeated positive habit | One-time informational post-it saying a pattern was recorded. | `habits.*`, `behaviors.habit_notice`. |
| Low energy / sleep | Existing eye animation closes its eye and shows sleep cues. | `runtime.sleep_after_s`; `sleep.replay_enabled` affects optional replay only. |
| Hover, mouse, idle | Gaze, brief curiosity, glances, blink, and existing visual effects. | `interaction.*`, `curiosity_novelty.*`, `visual.*`. |

All template strings are local YAML configuration. The app does not create files on the desktop. Post-it windows are frameless, topmost, non-activating, draggable, dismissible, and capped at four by default. They expire after ten minutes. SQLite stores template ID, emotion category, timestamps, and position, not the rendered text.

## Budgets and suppression

- `autonomy.max_actions_per_hour` caps post-it/notice actions per process. Template cooldowns are configured under `autonomy.cooldowns_s`.
- `teleport.max_per_hour` and `teleport.cooldown_s` independently cap teleports.
- Teleports do not run during a drag, recent interaction, a pending proposal, pause, or runtime stall.
- Post-it creation is suppressed during a drag, recent interaction, pending proposal, detected full-screen window, or while the visible-note cap is reached.
- Tray action **Silenciar autonomia** disables autonomous proposals and effects while leaving the SNN running. Configuration `autonomy.enabled: false` starts with it silenced.
- Full-screen detection on Windows compares foreground-window bounds to screen bounds. It does not inspect the foreground title or content. On platforms without that geometry probe, the extra full-screen suppression is unavailable.

The hourly counters are currently in-memory and reset when the application restarts. This is a known limitation; persistent cross-session autonomy budgets are tracked in [ROADMAP.md](../ROADMAP.md).

## User response feedback

Clicking **Entendi** sends a small positive feedback event. Quickly closing a new note (within `postits.quick_dismiss_s`) sends a small negative feedback event. Dragging a note only saves its new position. Expiry and application exit are not treated as feedback. These UI signals enter the normal learning reward channel; they do not execute tools.

## Planned behavior

The broader behavior map includes more glance patterns, yawns, hiding, cursor chasing, time-of-day reactions, affection particles, repeated-punishment sulking, break invitations, and template dialogue. These are not all implemented. See [ROADMAP.md](../ROADMAP.md).
