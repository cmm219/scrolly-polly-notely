# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
win32com_hiddenimports = collect_submodules("win32com")

a = Analysis(
    ["labels.py"],
    pathex=[],
    binaries=[],
    datas=[("assets", "assets")] + collect_data_files("win32com"),
    hiddenimports=[
        "PIL.ImageGrab",
        "PIL.ImageTk",
        "pythoncom",
        "pywintypes",
        "win32com.shell.shell",
        "win32com.propsys.propsys",
        "win32com.propsys.pscon",
    ] + win32com_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ScrollyPollyNotely",
    debug=False,
    icon="assets/black-paper.ico",
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ScrollyPollyNotely",
)
