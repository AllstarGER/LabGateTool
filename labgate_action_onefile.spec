# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

project_dir = Path.cwd()

mysql_connector_datas = collect_data_files('mysql.connector', includes=['locales/**/*.py'])
hiddenimports = []
hiddenimports += collect_submodules('mysql.connector.locales')
hiddenimports += collect_submodules('mysql.connector.plugins')

a = Analysis(
    ['labgate_action_main.py'],
    pathex=[],
    binaries=[],
    datas=mysql_connector_datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'pytest',
        '_pytest',
        'py',
        '_mysql_connector',
        'torch',
        'torchvision',
        'ultralytics',
        'ultralytics_thop',
        'qreader',
        'qrdet',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='labgate_action_onefile',
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
)
