# Packaging

Scrolly Polly Notely can be packaged as a portable Windows folder with PyInstaller.

The build keeps user notes outside the app folder. Packaged builds still store data in:

```text
%APPDATA%\ScrollyPollyNotely
```

## Build A Portable App

From the repository root on Windows:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m PyInstaller scrolly-polly-notely.spec --clean --noconfirm
```

The portable app is created at:

```text
dist\ScrollyPollyNotely\ScrollyPollyNotely.exe
```

Zip the `dist\ScrollyPollyNotely` folder if you want to share a downloadable build.

## Verify Before Sharing

Run the test suite before packaging:

```powershell
python -m pytest -q
```

Then smoke test the packaged app:

1. Launch `dist\ScrollyPollyNotely\ScrollyPollyNotely.exe`.
2. Create a note from the hub.
3. Edit text, right-click inside edit mode, and paste text.
4. Toggle light mode, dark mode, and transparent background.
5. Minimize a note with the titlebar `-` control and confirm it appears in `Saved notes...`.
6. Restore the minimized note from `Saved notes...` and confirm it opens beside any notes already on screen.
7. Save multiple open notes from the hub right-click `Minimized` submenu, then restore and delete that group.
8. Toggle `Show window controls` on a note and confirm the titlebar controls hide and reappear.
9. Pin or update a Windows shortcut, right-click it, and restore a saved group from the Jump List.
10. Restart the packaged app and confirm the current notes are restored.

## Clean Generated Files

Generated packaging output is ignored by Git:

```text
build\
dist\
dist-*\
```
