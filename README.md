# Scrolly Polly Notely

[![CI](https://github.com/cmm219/scrolly-polly-notely/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/cmm219/scrolly-polly-notely/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/cmm219/scrolly-polly-notely)](https://github.com/cmm219/scrolly-polly-notely/releases/latest)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![Platform: Windows](https://img.shields.io/badge/platform-windows-lightgrey)](#install)

Scrolly Polly Notely is a small Windows floating notes app built with Python and Tkinter. It keeps quick notes on top of your desktop with no installer, no account, no cloud sync, and no telemetry.

Use it for:

- Floating always-on-top notes.
- Saving open notes into named groups and restoring them later from the app.
- Quickly reopening saved note groups from the Windows taskbar Jump List.
- Optional clipboard capture via `send_label.ps1`; you run it when you want to send the current clipboard to a new note.
- Checklists, colors, fonts, opacity, resizing, stash, presets, and pasted images.
- Local-only note storage under `%APPDATA%\ScrollyPollyNotely`.

## Status

Shipped and maintained. Eight tagged releases to date; see [the latest release](https://github.com/cmm219/scrolly-polly-notely/releases/latest) and [CHANGELOG.md](CHANGELOG.md). The test suite is **99 tests**, run on Windows in CI for every push and pull request. The app is intentionally small and local-first.

## Screenshots

![Animated demo of hub and floating notes](docs/screenshots/demo.gif)

![Floating notes in light and dark mode](docs/screenshots/note.png)

![Small always-on-top hub](docs/screenshots/hub.png)

## Install

Windows only. Requires **Python 3.11 or newer** from [python.org](https://www.python.org/downloads/). Releases are tagged source snapshots; there is no prebuilt installer to download.

### From a tagged release (recommended)

1. Download the source ZIP for the [latest release](https://github.com/cmm219/scrolly-polly-notely/releases/latest) and unpack it.
2. Open PowerShell in the unpacked folder.
3. Install the image dependency:

```powershell
python -m pip install -r requirements.txt
```

### From the main branch

```powershell
git clone https://github.com/cmm219/scrolly-polly-notely.git
cd scrolly-polly-notely
python -m pip install -r requirements.txt
```

### Build A Portable Windows App

A PyInstaller spec (`scrolly-polly-notely.spec`) is included so you can build your own portable `.exe`. See [docs/PACKAGING.md](docs/PACKAGING.md).

## Run

```powershell
python labels.py
```

The small hub appears near the top-left of the screen. Use `+` to create a note, the gear for defaults, and `x` to save the current session and quit.
You can drag the hub from the blank strip or from the `+`, gear, and `x` controls; a short click still runs the button action.

## Basic Use

- Drag a note to move it.
- Drag the bottom-right corner of a note to make it bigger or smaller.
- Use the note titlebar controls to minimize a note into saved notes, maximize or restore the note size, or close the note.
- Double-click a note to edit its text.
- While editing a note, right-click the text area for `Cut`, `Copy`, `Paste`, and `Select all`.
- Right-click a pasted image for image resize and delete actions.
- Use the hub gear menu's `Saved notes...` action to search, preview, restore, or delete saved notes, minimized groups, stash entries, and presets.
- Use the hub right-click menu's `Minimized` submenu to save all currently open notes as a named group or restore/delete existing minimized groups.
- If click-through is enabled on a note, use the hub right-click menu to disable click-through on all notes.
- While the app is focused, `Ctrl+Shift+T` also disables click-through on all notes.
- On Windows, `Ctrl+Alt+Shift+T` is registered as a global recovery hotkey while the app is running. It only disables click-through on all notes and lifts the hub; it does not read keys or send data anywhere.
- The hub right-click menu also has an `Always on top` toggle for the hub itself.
- The hub right-click menu can disable the Windows global recovery hotkey if another app needs that shortcut.

## Note Appearance

Right-click any note to change its appearance:

- `Light mode` sets a white background and black text.
- `Dark mode` sets a black background and white text.
- Both light and dark mode turn transparent background off for that note.
- The note's colors are saved and restored on restart.

The gear menu includes `Default light mode` and `Default dark mode`. These defaults apply to new notes; existing notes keep their own colors unless changed from the note's right-click menu.

Use `Font family...` on a note to pick from installed system fonts. Use `Default font family...` from the gear menu to set the font for new notes.

`Transparent background` uses Windows color-key transparency. It works best with high-contrast text over simple backgrounds; busy pages can still make transparent text harder to read.

`Click-through` makes a note ignore mouse clicks so you can interact with windows behind it. The app shows a first-time warning before enabling it because a click-through note cannot be dragged or closed directly until click-through is disabled from the hub or keyboard shortcut.

`Show window controls` can be turned off from a note's right-click menu when you want a cleaner label with no minimize, maximize, or close controls. The gear menu also includes `Default: show window controls` for new notes.

## Saved Notes

The app has two saved-note flows:

- `Minimized` saves open notes as a restorable work group and removes them from the desktop.
- `Saved notes...` opens a library view where saved groups, stash entries, and presets can be searched, previewed, restored, or deleted.

Restoring a saved group adds those notes beside whatever is already open. It does not delete the saved group, so the same group can be restored again later.

On Windows, pinned app Jump Lists can show saved note groups under `Saved notes`. Choosing one starts the app if needed and restores that group.

## Checklists

Checklist lines use plain text syntax:

```text
- [ ] unchecked item
- [x] checked item
```

Click a checklist line to toggle it. Checked items are struck through, dimmed, and sorted below unchecked items. Numbered lists are plain text.

## Data Storage

Your notes and pasted images are stored outside the project folder:

```text
%APPDATA%\ScrollyPollyNotely\notes-and-settings.json
%APPDATA%\ScrollyPollyNotely\pasted-images\
```

That keeps downloaded code separate from each user's private notes. Saved groups, minimized notes, stash entries, presets, and note settings all stay in the same local settings file; the app does not add cloud storage or telemetry.

For testing or portable use, set `SCROLLY_POLLY_NOTELY_DATA_DIR` before launching:

```powershell
$env:SCROLLY_POLLY_NOTELY_DATA_DIR = "C:\path\to\my-note-data"
python labels.py
```

## Send Clipboard Text

When the app is running, `send_label.ps1` sends the current clipboard text into a new note through the local socket listener:

```powershell
.\send_label.ps1
```

The default local port is `47210`. The socket binds to `127.0.0.1` only and does not accept remote network connections. The app does not make outbound network calls or send telemetry.

Advanced users can change `socket_port` in their config file.

If PowerShell blocks the helper script on a fresh Windows install, run it for the current process with:

```powershell
powershell -ExecutionPolicy Bypass -File .\send_label.ps1
```

## Start With Windows

One simple option is to create a shortcut in the Windows Startup folder:

```text
shell:startup
```

Point the shortcut at:

```text
pythonw.exe C:\path\to\ScrollyPollyNotely\labels.py
```

Use the full path to your installed Python `pythonw.exe` if Windows does not find it automatically.

## Uninstall

Delete the downloaded project folder. To remove your notes too, delete:

```text
%APPDATA%\ScrollyPollyNotely
```

## Development

Install test tooling if needed:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The suite is 99 tests. Some of them create real Tkinter windows and need a normal interactive desktop session, so a headless or service context will fail.

CI runs the same test command on Windows for pushes and pull requests. See [CHANGELOG.md](CHANGELOG.md) for release notes and [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

## Stack

Python 3.11+ with the Tkinter standard-library toolkit, Pillow for pasted images, `pywin32` for the Windows Jump List, and pytest for the suite. Notes are plain JSON on disk. No database, no web service, no third-party accounts.

## Limitations

- **Windows only.** Transparency, click-through, the Jump List, and the global recovery hotkey all use Windows APIs; the app is not tested or supported on macOS or Linux.
- Single-user and single-device. There is no sync, sharing, or multi-device merge, and adding one is out of scope.
- No packaged installer or signed binary. You run it from source with your own Python, or build the `.exe` yourself.
- Notes are stored unencrypted in `%APPDATA%`. Treat it as a scratchpad, not a secrets store.
- Click-through notes cannot be dragged or closed directly. Recovery is through the hub menu or `Ctrl+Alt+Shift+T`.
- The clipboard helper listens on `127.0.0.1` only, but any local process can reach that port while the app is running.

## Case study

Design decisions and the wider desktop-tools story: [chris-portfolio-97r.pages.dev/case-studies/desktop-tools](https://chris-portfolio-97r.pages.dev/case-studies/desktop-tools/)

## License

MIT — see [LICENSE](LICENSE).
