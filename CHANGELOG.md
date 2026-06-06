# Changelog

## Unreleased

- Fixed multi-photo notes so pasted images stay distinct after edit cycles, restart, and reload.
- Changed the `+` action to open a blank note directly in edit mode, and made empty notes close without a save prompt.
- Added a Saved notes library from the hub gear menu with search, preview, restore, and delete actions for minimized groups, stash entries, and presets.
- Added named minimized note groups so open notes can be saved, closed from the desktop, and restored later without replacing notes that are already open.
- Added note titlebar controls for minimize, maximize/restore, and close, with a setting to hide those controls for cleaner label-style notes.
- Added automatic minimize naming from the note text and smarter close behavior that skips the save prompt when a restored saved note has not changed.
- Added Windows taskbar Jump List support for restoring saved note groups from the pinned app menu.
- Added black paper app icon assets and PyInstaller packaging support for Windows shortcut and Jump List metadata.

## v1.1.5 - 2026-05-16

- Added a Windows global `Ctrl+Alt+Shift+T` recovery hotkey for disabling click-through when the hub is not focused.
- Added a hub-menu toggle for the global recovery hotkey and documented what the shortcut does.

## v1.1.4 - 2026-05-16

- Added an animated README demo GIF.
- Added PyInstaller packaging docs and a portable Windows app spec.
- Added a first-time click-through warning plus `Ctrl+Shift+T` recovery to disable click-through on all notes.
- Made the hub draggable from the `+`, gear, and `x` controls without stealing normal short clicks.
- Added a persisted hub `Always on top` toggle in the hub right-click menu.

## v1.1.3 - 2026-05-14

- Improved transparent background rendering by moving the transparency key away from black and white text colors.
- Reworked click-through on Windows to use the window click-through style when available, with a hub-menu action to disable click-through on all notes.
- Reasserted topmost state when click-through fallback restores a note.
- Added appearance/click-through regression tests.

## v1.1.2 - 2026-05-11

- Fixed edit-mode `Select all` so it clears the existing selection before selecting note text.

## v1.1.1 - 2026-05-11

- Added an edit-mode right-click text menu with cut, copy, paste, and select-all actions.
- Clamped the font family picker popup to the visible screen.
- Added tests for font family persistence through duplicate, stash, and preset flows.

## v1.1.0 - 2026-05-11

- Added a searchable font family picker for individual notes.
- Added a default font family picker for new notes.
- Persisted note font family in saved sessions, stash, presets, and duplicates.

## v1.0.0 - 2026-05-11

Initial public release.

- Floating always-on-top notes built with Python and Tkinter.
- Quick note creation from the hub or `send_label.ps1`.
- Local-only socket listener bound to `127.0.0.1`.
- Per-note colors, opacity, resize, stash, presets, and pasted images.
- Light and dark mode actions for existing notes and new-note defaults.
- Plain-text checklist syntax with click-to-toggle behavior.
- Notes stored outside the project folder in `%APPDATA%\ScrollyPollyNotely`.
- Public test suite and GitHub Actions CI.
