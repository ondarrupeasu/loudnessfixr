# -*- mode: python ; coding: utf-8 -*-
import sys
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

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LoudnessFixR',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Icono del .exe en Windows (ignorado en macOS: allí manda el .icns del BUNDLE).
    icon='design/loudnessfixr.ico' if sys.platform == 'win32' else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='LoudnessFixR',
)
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='LoudnessFixR.app',
        icon='design/LoudnessFixR.icns',
        # NO cambiar: de este id cuelgan las preferencias del usuario
        # (~/Library/Preferences/es.cinemafilmak.audioloudnesstoolkit.plist).
        # El rebrand a LoudnessFixR es solo visible; el id interno se mantiene.
        bundle_identifier='es.cinemafilmak.audioloudnesstoolkit',
        info_plist={
            'NSHighResolutionCapable': True,
        },
    )
