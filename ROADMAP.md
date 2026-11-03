# Roadmap

This roadmap records incomplete work and possible directions. An item is not a delivered feature until implemented, tested, and described as such in the release notes.

## Current release scope

- P0 tool parameter validation, safe defaults, failure cooldowns, and configuration-required response: implemented.
- P1 transparent floating eye, on-demand panel/tray, move/affection behavior, and emotion-aware teleport: implemented; UI verification is headless/offscreen only.
- P2 budgeted template post-its, local metadata persistence, feedback, and aggregate habits: initial slice implemented.
- P3 opt-in sleep replay and an aggregate learning view: implemented; replay is disabled by default and its scenario performance has not been evaluated.
- P4 bilingual documentation and repository release setup: implementation and local validation complete; hosted CI starts with the release push.

## Remaining engineering

1. **Autonomy coverage:** implement remaining state-driven actions from the original plan: more glance paths, yawns, hiding, cursor chasing, time-of-day response, affection particles, repeated-punishment sulking, and break invitations. Add per-behavior deterministic tests and user-facing controls.
2. **Durable action budgets:** current autonomy and teleport hourly caps/cooldowns reset when the process restarts. Persist and test these counters before treating them as anti-spam guarantees across sessions.
3. **Post-it lifecycle:** test click, drag, expiry, restart restoration, geometry on mixed-DPI monitors, and feedback thresholds in interactive Windows runs. Add stable IDs and consider reconciliation when users change templates.
4. **Sleep replay evaluation:** run the same synthetic scenarios with replay off/on, especially scenario e and a new-context retention check. Keep it disabled unless it improves a measured goal without regressions.
5. **Snapshot migration:** support an explicit 600→800 neuron migration that copies old state, initializes only the new neurons, backs up first, and never shrinks silently. Add compatibility and determinism tests.
6. **Personality controls:** define and evaluate how traits change dopamine gain, initiative threshold, and exploration without changing the default deterministic topology.
7. **Profiling:** investigate lazy traces and per-tick allocations only after a repeatable profile shows a measurable opportunity under the ≤3% regression budget.
8. **Release validation:** run interactive tests on Windows with OpenGL and CPU fallback, multiple monitors/DPI scales, taskbar placements, and tray behavior. The current release's Qt checks are offscreen.

## Longer-term directions

- A small skills layer for reusable local routines.
- Optional local `NarratorProvider` integration for natural-language phrasing. It must be disabled by default, clearly isolated from SNN learning, and remain local unless configured otherwise.
- Optional MCP integration with per-tool permission and data-flow review.
- Browser workflows only with explicit user confirmation, bounded permissions, and privacy tests.
- Broader synthetic scenarios, confidence intervals, repeated seeds, and ablation reports before making stronger claims about learning.

These are ideas, not current capabilities or delivery dates.
