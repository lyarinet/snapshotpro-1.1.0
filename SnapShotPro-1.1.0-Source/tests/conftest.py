import os
import sys
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ['SNAPSHOT_DISABLE_HOTKEYS'] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

@pytest.fixture(scope='session')
def app(tmp_path_factory):
    instance = QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                      str(tmp_path_factory.mktemp('settings')))
    return instance

@pytest.fixture
def config(app, tmp_path):
    from snapshot_pro import AppConfig
    config = AppConfig()
    config.settings = QSettings(str(tmp_path / 'test.ini'), QSettings.Format.IniFormat)
    config.save_directory = str(tmp_path / 'saved')
    return config
