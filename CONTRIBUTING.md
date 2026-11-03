# Contributing

Thank you for helping improve Synapse Pet. The project is experimental, local-first, and careful about what its SNN results claim.

## Before opening a change

1. Search existing issues and discussions for the same problem.
2. For a substantial change, open an issue first so the scope and expected behavior are clear.
3. Keep pull requests focused and explain the user-visible effect, data flow, and limits.
4. Do not include private snapshots, SQLite databases, logs, screenshots of personal content, credentials, or absolute user paths.

## Development setup

Windows PowerShell:

```powershell
.\scripts\install.ps1
```

Manual setup:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,windows]"
```

For headless Qt tests:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m pytest
```

Linux CI uses the same `QT_QPA_PLATFORM=offscreen` setting. Linux desktop behavior is not a supported release claim.

## Engineering guidelines

- Preserve deterministic SNN behavior unless a change explicitly documents and tests the impact.
- Do not change LIF topology by default. New experimental topology behavior must have an explicit YAML flag, defaulting off.
- Keep UI, disk I/O, and external tool execution out of the simulation's critical tick path.
- Preserve coarse, privacy-safe sensor inputs. Never collect typed text or active-window titles for learning or logging.
- Add typed schemas and permission checks for new tools. Tool code executes with the user's OS privileges; never describe the app's permission manager as an OS sandbox.
- Bound autonomous actions with configurable cooldowns and budgets. Avoid doing anything outside the app without explicit user approval.
- Describe synthetic results as synthetic. Separate the SNN-only ablation from the combined contextual selector.
- Record what was tested. Offscreen Qt checks are not real desktop validation.

## Tests and benchmarks

Run the smallest relevant test files while developing, then the complete suite before a release:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_autonomy.py tests\test_teleport.py
.\.venv\Scripts\python.exe -m pytest
```

Short benchmark example:

```powershell
.\.venv\Scripts\python.exe benchmarks\snn_baseline.py --ticks 60 --profile-steps 40 --idle-seconds 2
```

Use longer samples for comparisons where runtime budget allows. Do not check in `_smoke` output, live databases, or hardware logs containing local paths.

## Pull requests

Include:

- Summary and motivation.
- Important design or privacy decisions.
- Tests and benchmarks run, including whether they were headless.
- Any unimplemented portion in `ROADMAP.md`.
- Screenshots only when they contain no private desktop content; clearly label generated/offscreen renders.

Use the project's code of conduct. By participating, you agree to uphold it.
