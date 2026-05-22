# Scrolly Polly Notely

[![CI](https://github.com/cmm219/scrolly-polly-notely/actions/workflows/ci.yml/badge.svg)](https://github.com/cmm219/scrolly-polly-notely/actions/workflows/ci.yml)

Scrolly Polly Notely is a small Windows-friendly floating notes app built with Python and Tkinter. It keeps quick notes on top of your desktop with no installer, no account, no cloud sync, and no telemetry.

Use it for:

- Floating always-on-top notes.
- Saving open notes into named groups and restoring them later from the app.
- Quickly reopening saved note groups from the Windows taskbar Jump List.
- Optional clipboard capture via `send_label.ps1`; you run it when you want to send the current clipboard to a new note.
- Checklists, colors, fonts, opacity, resizing, stash, presets, and pasted images.
- Local-only note storage under `%APPDATA%\ScrollyPollyNotely`.

## Status

Current release: [latest](https://github.com/cmm219/scrolly-polly-notely/releases/latest). The app is intentionally small and local-first.

## Screenshots

![Animated demo of hub and floating notes](docs/screenshots/demo.gif)

![Floating notes in light and dark mode](docs/screenshots/note.png)

![Small always-on-top hub](docs/screenshots/hub.png)

## Install

### Run From Source

1. Install Python 3.11 or newer from [python.org](https://www.python.org/downloads/).
2. Download this project from GitHub as a ZIP, or clone it with Git.
3. Open PowerShell in the project folder.
4. Install the image dependency:

```powershell
python -m pip install -r requirements.txt
```

### Build A Portable Windows App

For a portable `.exe` build, see [docs/PACKAGING.md](docs/PACKAGING.md).

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

Some tests use Tkinter windows and may need a normal desktop session.

CI runs the same test command on Windows for pushes and pull requests. See [CHANGELOG.md](CHANGELOG.md) for release notes.
