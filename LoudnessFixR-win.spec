# -*- mode: python ; coding: utf-8 -*-
# Spec SOLO para Windows: ONEFILE → un único dist/LoudnessFixR.exe.
# El auto-updater compartido (core/updater_core._apply_windows) intercambia UN SOLO .exe
# (descarga LoudnessFixR.new.exe y lo renombra a LoudnessFixR.exe), así que el build de
# Windows tiene que ser onefile, no onedir. NO tocar el LoudnessFixR.spec (macOS, onedir).
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []
datas += collect_data_files('imageio_ffmpeg')
datas += collect_data_files('soundfile')
tmp_ret = collect_all('sounddevice')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# ONEFILE: metemos binaries y datas DENTRO del EXE (exclude_binaries=False), sin COLLECT ni BUNDLE.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='LoudnessFixR',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='design/loudnessfixr.ico',
)
