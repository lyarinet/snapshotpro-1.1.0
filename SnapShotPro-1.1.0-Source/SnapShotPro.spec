# Portable default spec. Prefer python build_all.py for target-specific packaging.
from pathlib import Path
import sys
root = Path(SPECPATH)
a = Analysis([str(root / 'snapshot_pro.py')], pathex=[str(root)],
    datas=[(str(root / 'assets' / 'icon.png'), 'assets')],
    hiddenimports=[], excludes=['numpy','pandas','matplotlib','scipy','tkinter','pytesseract'],
    noarchive=False, optimize=1)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='SnapShotPro', console=False,
    icon=str(root / 'assets' / ('icon.ico' if sys.platform == 'win32' else 'icon.png')))
coll = COLLECT(exe, a.binaries, a.datas, name='SnapShotPro')
