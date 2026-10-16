from types import SimpleNamespace
from snapshot_native import GlobalHotkeyManager

def test_windows_native_hotkeys_register_report_conflict_and_unregister(app, config, monkeypatch):
    calls=[]
    class User32:
        def RegisterHotKey(self, window, identifier, modifiers, key):
            calls.append(('register',identifier,modifiers,key))
            return key != 0x2C  # PrintScreen is reserved by another app.
        def UnregisterHotKey(self,window,identifier):
            calls.append(('unregister',identifier))
            return True
    monkeypatch.delenv('SNAPSHOT_DISABLE_HOTKEYS')
    monkeypatch.setattr('snapshot_native.platform.system',lambda:'Windows')
    monkeypatch.setattr('snapshot_native.ctypes.windll',SimpleNamespace(user32=User32()),raising=False)
    manager=GlobalHotkeyManager(config)
    assert manager.available
    assert len(manager._registered)==3
    assert 'already in use' in manager.failures[0]
    assert all(call[2]&0x4000 for call in calls if call[0]=='register')
    manager.stop()
    assert len([c for c in calls if c[0]=='unregister'])==3
    assert not manager.available
