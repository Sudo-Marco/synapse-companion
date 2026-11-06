# Privacy and local data inventory

Synapse Pet is local-first. The engine, SNN, UI, episode memory, snapshots, and logs run on the user's computer. No remote inference or telemetry service is part of the current runtime. Installing dependencies requires network access; explicitly opening a URL or using a user-installed plugin can also access external resources.

The pixel-art pet renderer draws from packaged sprite assets and UI state. It does not sample or capture desktop/background pixels. The floating mode uses window geometry for placement and the current sprite alpha for its click-through mask; it does not inspect other windows' titles or contents.

## Sensors

All optional sensors are disabled by default in `configs/default.yaml`.

| Sensor | Data sampled | What is emitted or retained |
| --- | --- | --- |
| `input_activity` | Keyboard and mouse event count | Events per second. Key identity, coordinates, and typed text are not recorded. |
| `active_window` | Foreground process executable name on Windows | A configured coarse category such as `codigo` or `navegador`; window titles and contents are not read. |
| `file_events` | Names and modification times inside the explicitly selected folder | The sensor emits a changed-file count. The separate explicit file-summary tool can return changed filenames. |
| `clipboard` | Clipboard text while the counter sensor is enabled | A length/count signal and an in-memory digest used for change detection; it does not return or persist clipboard contents. |
| `system_stats` | CPU and memory metrics | Numeric resource measurements. |
| `clock` | Local time | A normalized hour feature. |
| `microphone` | Short microphone audio windows, only while explicitly enabled | Temporary level/voice-activity features for a listening gesture; no waveform, speech text, or recording is stored. |
| `system_loopback` | Short system-output audio windows, only while explicitly enabled | Temporary level/music/BPM features for a dance cue. If loopback capture is unavailable, a coarse Windows playback-active boolean may be used; title and artist are not read. |

The `historico_clipboard` tool is different from the clipboard counter sensor. When explicitly called with `capture: true` and accepted, it stores up to 4,000 characters in local SQLite. This action has medium risk; do not enable or accept it unless storing that clipboard material is intended.

## Local files

On Windows, runtime data is under `%APPDATA%\synapse_pet` (typically `%APPDATA%` resolves to the user's roaming application-data directory).

| File or directory | Contents |
| --- | --- |
| `creature/` | SNN weights, neural state, and persisted mind/action-preference state. |
| `episodes.sqlite3` | Coarse context/action, target reward, emotion-state serialization, RPE, and timestamps used for learning/replay. Context values should remain categories; raw sensor payloads must not be added. |
| `actions.sqlite3` | Tool/action identifier, outcome, reward, coarse category, and timestamp; no typed text or window title. |
| `postits.sqlite3` | Template ID, emotion category, creation/expiry times, and window position; the rendered text is not stored. |
| `notes.sqlite3` | Notes deliberately created or searched through the local note tools. Note contents are stored locally. |
| `clipboard.sqlite3` | Clipboard contents only if the explicit history tool captures them. |
| `logs/synapse_pet.log` | Rotating runtime diagnostics and exception tracebacks. Logs should be reviewed before sharing. |

The exact set of optional databases depends on which features have been used. The repository does not include a user's live creature snapshot, SQLite database, or application log.

## Tools and plugins

Tool manifests validate parameters, and the permission manager restricts file paths and risk-sensitive operations. These are application-level controls, not a Windows security sandbox. Third-party Python plugins execute with the current user's operating-system permissions. Review plugin code before loading it.

The URL-opening tool can access a URL only as an explicit user action. The app does not send runtime state to a remote language model. No language-model integration is currently implemented.

## Privacy invariants

- Never capture keyboard text or active-window titles for curiosity, logging, autonomy, or training.
- Keep sensor-derived inputs numeric or coarse category labels.
- Keep microphone and loopback sensors off until the user enables each one. Analyze audio in worker memory, then discard the sample; never record, transcribe, upload, or add raw audio to logs.
- Do not attach recordings or transcripts to issue reports. Synthetic audio tests use generated arrays and do not open hardware devices.
- Keep post-it templates in local configuration; persist template IDs and metadata only.
- Do not commit live databases, snapshots, logs, or personal absolute file paths.
- Review runtime logs and benchmark output before posting them publicly.
