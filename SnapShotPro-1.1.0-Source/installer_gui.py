#!/usr/bin/env python3
"""
SnapShot Pro — Windows Setup & Installer Wizard
Self-contained 1-click graphical installer for Windows.
Installs SnapShot Pro, creates Start Menu and Desktop shortcuts with custom icon,
and registers uninstaller.
"""

import os
import pathlib
import platform
import shutil
import subprocess
import sys

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class InstallWorker(QThread):
    progress = pyqtSignal(int, str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, target_dir: pathlib.Path, desktop_sc: bool, startmenu_sc: bool, launch_after: bool, autostart: bool = True):
        super().__init__()
        self.target_dir = target_dir
        self.desktop_sc = desktop_sc
        self.startmenu_sc = startmenu_sc
        self.launch_after = launch_after
        self.autostart = autostart

    def run(self):
        try:
            self.progress.emit(10, "Preparing target installation directory...")
            self.target_dir.mkdir(parents=True, exist_ok=True)

            # Determine payload location
            base_dir = getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parent)
            base_path = pathlib.Path(base_dir)

            source_exe = base_path / "SnapShotPro.exe"
            if not source_exe.exists():
                source_exe = base_path / "dist" / "SnapShotPro.exe"

            if not source_exe.exists():
                raise FileNotFoundError(f"SnapShotPro.exe payload not found in {base_path}")

            self.progress.emit(30, "Copying application binaries...")
            dest_exe = self.target_dir / "SnapShotPro.exe"
            shutil.copy2(source_exe, dest_exe)

            self.progress.emit(50, "Installing application icons and assets...")
            dest_assets = self.target_dir / "assets"
            dest_assets.mkdir(parents=True, exist_ok=True)
            source_assets = base_path / "assets"
            if source_assets.exists():
                for item in source_assets.glob("*"):
                    shutil.copy2(item, dest_assets / item.name)

            ico_file = dest_assets / "icon.ico"

            self.progress.emit(70, "Creating Windows shortcuts...")
            # Desktop Shortcut
            if self.desktop_sc:
                desktop_dir = pathlib.Path.home() / "Desktop"
                if desktop_dir.exists():
                    lnk = desktop_dir / "SnapShot Pro.lnk"
                    self._create_shortcut(lnk, dest_exe, ico_file)

            # Start Menu Shortcut
            if self.startmenu_sc:
                appdata = os.environ.get("APPDATA")
                if appdata:
                    start_dir = pathlib.Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "SnapShot Pro"
                    start_dir.mkdir(parents=True, exist_ok=True)
                    lnk = start_dir / "SnapShot Pro.lnk"
                    self._create_shortcut(lnk, dest_exe, ico_file)

            # Windows Startup (Auto start on PC restart)
            if self.autostart:
                self.progress.emit(80, "Configuring auto-start on Windows startup...")
                appdata = os.environ.get("APPDATA")
                if appdata:
                    startup_dir = pathlib.Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
                    startup_dir.mkdir(parents=True, exist_ok=True)
                    lnk = startup_dir / "SnapShot Pro.lnk"
                    self._create_shortcut(lnk, dest_exe, ico_file)
                try:
                    import winreg
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE) as key:
                        winreg.SetValueEx(key, "SnapShot Pro", 0, winreg.REG_SZ, f'"{dest_exe}"')
                except Exception:
                    pass

            self.progress.emit(90, "Creating uninstaller...")
            self._create_uninstaller(dest_exe)

            self.progress.emit(100, "Installation complete!")
            if self.launch_after and dest_exe.exists():
                subprocess.Popen([str(dest_exe)], cwd=str(self.target_dir))

            self.finished_signal.emit(True, "SnapShot Pro installed successfully!")
        except Exception as exc:
            self.finished_signal.emit(False, str(exc))

    def _create_shortcut(self, lnk_path: pathlib.Path, target_exe: pathlib.Path, ico_path: pathlib.Path) -> None:
        lnk_path = str(lnk_path).replace("'", "''")
        working_dir = str(target_exe.parent).replace("'", "''")
        target_exe = str(target_exe).replace("'", "''")
        ico_path = str(ico_path).replace("'", "''")
        ps_cmd = (
            f"$ws = New-Object -ComObject WScript.Shell; "
            f"$s = $ws.CreateShortcut('{lnk_path}'); "
            f"$s.TargetPath = '{target_exe}'; "
            f"$s.WorkingDirectory = '{working_dir}'; "
            f"if (Test-Path -LiteralPath '{ico_path}') {{ $s.IconLocation = '{ico_path},0' }} else {{ $s.IconLocation = '{target_exe},0' }}; "
            f"$s.Save()"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], check=True)

    def _create_uninstaller(self, dest_exe: pathlib.Path) -> None:
        uninst_bat = self.target_dir / "uninstall.bat"
        uninst_content = f"""@echo off
title SnapShot Pro Uninstaller
echo Uninstalling SnapShot Pro...
taskkill /f /im SnapShotPro.exe >nul 2>&1
timeout /t 1 >nul
del /q "%USERPROFILE%\\Desktop\\SnapShot Pro.lnk" >nul 2>&1
del /q "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\SnapShot Pro.lnk" >nul 2>&1
reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" /v "SnapShot Pro" /f >nul 2>&1
rd /s /q "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\SnapShot Pro" >nul 2>&1
echo Removing application directory...
cd /d "%TEMP%"
rd /s /q "{self.target_dir}" >nul 2>&1
echo SnapShot Pro has been successfully removed.
pause
"""
        uninst_bat.write_text(uninst_content, encoding="utf-8")


class InstallerWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SnapShot Pro — Setup & Installation")
        self.setFixedSize(520, 475)

        # Set Window Icon
        base_dir = getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parent)
        ico_file = pathlib.Path(base_dir) / "assets" / "icon.ico"
        if ico_file.exists():
            self.setWindowIcon(QIcon(str(ico_file)))

        self.setStyleSheet("""
            QWidget {
                background-color: #0F172A;
                color: #F8FAFC;
                font-family: 'Segoe UI', Tahoma, sans-serif;
            }
            QLabel {
                color: #E2E8F0;
                font-size: 13px;
            }
            QLineEdit {
                background-color: #1E293B;
                color: #F8FAFC;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QCheckBox {
                color: #E2E8F0;
                font-size: 13px;
                spacing: 8px;
            }
            QPushButton {
                background-color: #4F46E5;
                color: #FFFFFF;
                border: 1px solid #6366F1;
                border-radius: 6px;
                padding: 10px 20px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #4338CA;
            }
            QPushButton#SecondaryBtn {
                background-color: #1E293B;
                border-color: #475569;
                color: #E2E8F0;
            }
            QPushButton#SecondaryBtn:hover {
                background-color: #334155;
            }
            QProgressBar {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 6px;
                text-align: center;
                color: #FFFFFF;
                font-weight: bold;
                height: 22px;
            }
            QProgressBar::chunk {
                background-color: #06B6D4;
                border-radius: 5px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        # Header Title
        title = QLabel("⚡ SnapShot Pro Setup Wizard")
        title.setStyleSheet("font-size: 20px; font-weight: 800; color: #38BDF8;")
        layout.addWidget(title)

        desc = QLabel("Welcome! This wizard will install SnapShot Pro on your computer.")
        desc.setStyleSheet("color: #94A3B8; font-size: 13px;")
        layout.addWidget(desc)

        layout.addSpacing(6)

        # Installation Directory
        lbl_dir = QLabel("Install Location:")
        lbl_dir.setStyleSheet("font-weight: 600;")
        layout.addWidget(lbl_dir)

        row_dir = QHBoxLayout()
        default_dir = os.path.expandvars(r"%LocalAppData%\Programs\SnapShotPro")
        self.edit_dir = QLineEdit(default_dir)
        row_dir.addWidget(self.edit_dir, 1)

        btn_browse = QPushButton("Browse...")
        btn_browse.setObjectName("SecondaryBtn")
        btn_browse.clicked.connect(self._browse)
        row_dir.addWidget(btn_browse)
        layout.addLayout(row_dir)

        layout.addSpacing(6)

        # Shortcuts Options
        self.chk_desktop = QCheckBox("Create Desktop Shortcut (with SnapShot Pro icon)")
        self.chk_desktop.setChecked(True)
        layout.addWidget(self.chk_desktop)

        self.chk_startmenu = QCheckBox("Create Start Menu Shortcut")
        self.chk_startmenu.setChecked(True)
        layout.addWidget(self.chk_startmenu)

        self.chk_autostart = QCheckBox("Start SnapShot Pro automatically on Windows startup (PC restart)")
        self.chk_autostart.setChecked(True)
        layout.addWidget(self.chk_autostart)

        self.chk_launch = QCheckBox("Launch SnapShot Pro after setup")
        self.chk_launch.setChecked(True)
        layout.addWidget(self.chk_launch)

        layout.addSpacing(8)

        # Progress Bar & Status
        self.status_lbl = QLabel("Ready to install.")
        self.status_lbl.setStyleSheet("color: #94A3B8; font-size: 12px;")
        layout.addWidget(self.status_lbl)

        self.prog_bar = QProgressBar()
        self.prog_bar.setValue(0)
        layout.addWidget(self.prog_bar)

        layout.addStretch()

        # Action Buttons
        row_btn = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("SecondaryBtn")
        self.btn_cancel.clicked.connect(self.close)
        row_btn.addWidget(self.btn_cancel)

        row_btn.addStretch()

        self.btn_install = QPushButton("Install Now")
        self.btn_install.clicked.connect(self._start_install)
        row_btn.addWidget(self.btn_install)

        layout.addLayout(row_btn)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Select Install Directory", self.edit_dir.text())
        if d:
            self.edit_dir.setText(d)

    def _start_install(self):
        target = pathlib.Path(self.edit_dir.text().strip())
        self.btn_install.setEnabled(False)
        self.btn_cancel.setEnabled(False)

        self.worker = InstallWorker(
            target_dir=target,
            desktop_sc=self.chk_desktop.isChecked(),
            startmenu_sc=self.chk_startmenu.isChecked(),
            launch_after=self.chk_launch.isChecked(),
            autostart=self.chk_autostart.isChecked(),
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.start()

    def _on_progress(self, val: int, msg: str):
        self.prog_bar.setValue(val)
        self.status_lbl.setText(msg)

    def _on_finished(self, success: bool, msg: str):
        if success:
            QMessageBox.information(self, "Setup Completed", msg)
            self.close()
        else:
            QMessageBox.critical(self, "Setup Error", f"Installation failed:\n{msg}")
            self.btn_install.setEnabled(True)
            self.btn_cancel.setEnabled(True)


def main():
    app = QApplication(sys.argv)
    win = InstallerWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
