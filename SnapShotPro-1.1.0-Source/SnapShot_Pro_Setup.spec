from pathlib import Path

ROOT = Path.cwd()
payload_datas = [('assets', 'assets')]
onedir_path = ROOT / 'dist' / 'SnapShotPro'
onefile_path = ROOT / 'dist' / 'SnapShotPro.exe'

if onedir_path.is_dir() and (onedir_path / 'SnapShotPro.exe').exists():
    payload_datas.append(('dist/SnapShotPro', 'SnapShotPro'))
elif onefile_path.is_file():
    payload_datas.append(('dist/SnapShotPro.exe', '.'))

a = Analysis(
    ['installer_gui.py'],
    pathex=[],
    binaries=[],
    datas=payload_datas,
    hiddenimports=[],
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
    a.binaries,
    a.datas,
    [],
    name='SnapShot_Pro_Setup',
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
    icon=['assets/icon.ico'],
)
