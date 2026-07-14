# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

datas = [
    ('altirra/sio2sd.atdevice', 'altirra'),
    ('altirra/xexboot.bin', 'altirra'),
    ('assets/sio2sd_gui_icon.ico', 'assets'),
    ('assets/sio2sd_gui_icon.png', 'assets'),
    ('Configurator_35/Sio2SDBootLoaderCfgTools.atr', 'Configurator_35'),
]

a = Analysis(
    ['altirra/sio2sd_gui.py'],
    pathex=['altirra'],
    binaries=[],
    datas=datas,
    hiddenimports=[],
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SIO2SD-GUI',
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
    icon='assets/sio2sd_gui_icon.ico',
)
