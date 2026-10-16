#!/usr/bin/env python3
"""Build on the target OS. Default folder bundles start without extracting a runtime."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import zipfile
from snapshot_core import VERSION

ROOT = Path(__file__).resolve().parent
EXCLUDES = ['numpy', 'pandas', 'matplotlib', 'scipy', 'cv2', 'torch', 'tensorflow',
            'IPython', 'pytest', 'tkinter', 'PySide6', 'PyQt5', 'pytesseract',
            'PyQt6.QtWebEngineCore', 'PyQt6.QtWebEngineWidgets', 'PyQt6.QtQml',
            'PyQt6.QtQuick', 'PyQt6.QtMultimedia', 'PyQt6.QtSql', 'PyQt6.QtTest']


def build_command(target, onefile=False):
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
               '--windowed', '--onefile' if onefile and target != 'Darwin' else '--onedir',
               '--name', 'SnapShotPro', '--specpath', str(ROOT / 'build' / 'spec'),
               '--distpath', str(ROOT / 'dist'), '--workpath', str(ROOT / 'build' / 'pyinstaller'),
               '--optimize', '1']
    if target == 'Linux':
        command.append('--strip')
    separator = ';' if os.name == 'nt' else ':'
    for name in ('icon.png', 'icon.ico', 'icon.icns'):
        path = ROOT / 'assets' / name
        if path.exists():
            command.extend(['--add-data', f'{path}{separator}assets'])
    icon = ROOT / 'assets' / ('icon.ico' if target == 'Windows' else 'icon.icns' if target == 'Darwin' else 'icon.png')
    command.extend(['--icon', str(icon)])
    for module in EXCLUDES + (['pynput'] if target == 'Windows' else []):
        command.extend(['--exclude-module', module])
    if target in {'Linux', 'Darwin'}:
        backend = '_xorg' if target == 'Linux' else '_darwin'
        for device in ('keyboard', 'mouse'):
            command.extend(['--hidden-import', f'pynput.{device}.{backend}'])
    if target == 'Darwin':
        command.extend(['--osx-bundle-identifier', 'com.lyaritech.snapshotpro'])
    command.append(str(ROOT / 'snapshot_pro.py'))
    return command


def linux_installers(folder):
    (folder / 'install.sh').write_text('''#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")"
install_root="${XDG_DATA_HOME:-$HOME/.local/share}/snapshotpro"
if [ "$PWD" != "$install_root" ]; then
    mkdir -p "$install_root"
    cp -a . "$install_root/"
fi
chmod +x "$install_root/SnapShotPro"
mkdir -p "${XDG_DATA_HOME:-$HOME/.local/share}/applications"
cat > "${XDG_DATA_HOME:-$HOME/.local/share}/applications/snapshotpro.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=SnapShot Pro
Comment=Screenshot and annotation tool
Exec="$install_root/SnapShotPro"
Icon=$install_root/_internal/assets/icon.png
Terminal=false
Categories=Utility;Graphics;
EOF
printf 'Installed. Open SnapShot Pro from your applications menu.\\n'
''', encoding='utf-8')
    (folder / 'uninstall.sh').write_text('''#!/usr/bin/env bash
set -eu
install_root="${XDG_DATA_HOME:-$HOME/.local/share}/snapshotpro"
rm -f "${XDG_DATA_HOME:-$HOME/.local/share}/applications/snapshotpro.desktop"
rm -rf -- "$install_root"
printf 'Application removed. Your saved images and settings are preserved.\\n'
''', encoding='utf-8')
    (folder / 'install.sh').chmod(0o755)
    (folder / 'uninstall.sh').chmod(0o755)


def copy_runtime_licenses(folder):
    for package in ('PyQt6', 'PyQt6-Qt6', 'PyQt6-sip', 'mss', 'Pillow', 'pynput'):
        try:
            distribution = importlib.metadata.distribution(package)
        except importlib.metadata.PackageNotFoundError:
            continue
        for entry in distribution.files or []:
            if '.dist-info/' in str(entry) and any(token in str(entry).lower() for token in ('license', 'copying')):
                source = Path(distribution.locate_file(entry))
                if source.is_file():
                    destination = folder / 'licenses' / package / source.name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)


def archive_folder(folder, name):
    archive = ROOT / 'dist' / (name + '.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=8) as bundle:
        for path in sorted(folder.rglob('*')):
            if path.is_symlink():
                info = zipfile.ZipInfo(str(path.relative_to(folder.parent)))
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                bundle.writestr(info, os.readlink(path))
            elif path.is_file():
                bundle.write(path, path.relative_to(folder.parent))
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    targets = parser.add_mutually_exclusive_group()
    targets.add_argument('--windows', action='store_true')
    targets.add_argument('--linux', action='store_true')
    targets.add_argument('--mac', action='store_true')
    targets.add_argument('--all', action='store_true', help='Explains native-build requirement')
    parser.add_argument('--onefile', action='store_true', help='Optional portable single file; slower cold startup')
    parser.add_argument('--skip-installer', action='store_true', help='Windows: only create portable output')
    args = parser.parse_args()
    target = 'Windows' if args.windows else 'Darwin' if args.mac else 'Linux' if args.linux else platform.system()
    if args.all or target != platform.system():
        parser.error('PyInstaller builds for the current OS only. Use the included GitHub Actions matrix for all platforms.')
    if target not in {'Windows', 'Darwin', 'Linux'}:
        parser.error('Unsupported OS.')
    subprocess.run(build_command(target, args.onefile), cwd=ROOT, check=True)
    dist = ROOT / 'dist'
    is_file = args.onefile and target != 'Darwin'
    folder = dist / ('SnapShotPro.app' if target == 'Darwin' else 'SnapShotPro')
    if not is_file:
        if target == 'Linux':
            linux_installers(folder)
        copy_runtime_licenses(folder)
        shutil.copy2(ROOT / 'README.md', folder / 'README.md')
        for name in ('BUILD_VERIFICATION.md', 'REPOSITORY_ANALYSIS.md'):
            if (ROOT / name).exists():
                shutil.copy2(ROOT / name, folder / name)
        if target == 'Darwin':
            # Screen Recording / Accessibility permission prompts belong to macOS.
            import plistlib
            plist = folder / 'Contents' / 'Info.plist'
            data = plistlib.loads(plist.read_bytes())
            data.update({'NSHighResolutionCapable': True, 'CFBundleShortVersionString': VERSION,
                         'NSScreenCaptureUsageDescription': 'Capture screen regions you select.',
                         'NSAppleEventsUsageDescription': 'Optional user-started scrolling capture.'})
            plist.write_bytes(plistlib.dumps(data))
        archive = archive_folder(folder, f'SnapShotPro-{VERSION}-{target}-{platform.machine()}')
        print(f'Portable package: {archive} ({archive.stat().st_size/1048576:.1f} MiB)')
    if target == 'Windows' and not args.skip_installer:
        compiler = shutil.which('ISCC') or next((str(p) for p in (
            Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Inno Setup 6' / 'ISCC.exe',
            Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Inno Setup 6' / 'ISCC.exe') if p.exists()), None)
        if compiler:
            command = [compiler, f'/DAppVersion={VERSION}']
            if is_file:
                command.append('/DOneFile')
            command.append(str(ROOT / 'installer_inno.iss'))
            subprocess.run(command, cwd=ROOT, check=True)
        else:
            print('Portable app is ready. To also build Setup.exe, install Inno Setup 6 and rerun this command.')
    artifacts = [p for p in dist.iterdir() if p.is_file() and p.suffix in {'.zip', '.exe'}]
    if is_file and target == 'Linux':
        artifacts.append(folder)
    (dist / 'SHA256SUMS.txt').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in sorted(artifacts)), encoding='utf-8')
    (dist / 'build-info.json').write_text(json.dumps({'version': VERSION, 'platform': target,
        'architecture': platform.machine(), 'python': platform.python_version(),
        'bundle': 'onefile' if is_file else 'onedir',
        'dependencies': {p: importlib.metadata.version(p) for p in ('PyQt6','mss','Pillow','pyinstaller')}}, indent=2), encoding='utf-8')

if __name__ == '__main__':
    main()
