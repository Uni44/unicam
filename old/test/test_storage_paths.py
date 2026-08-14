import importlib
import os
import sys
import types

# Stub external dependencies that may not be installed in this environment.
sounddevice = types.ModuleType("sounddevice")
sounddevice.rec = lambda *args, **kwargs: None
sounddevice.wait = lambda *args, **kwargs: None
sys.modules.setdefault("sounddevice", sounddevice)

numpy = types.ModuleType("numpy")
numpy.sqrt = lambda x: x
numpy.mean = lambda x: 0
numpy.log10 = lambda x: 0
sys.modules.setdefault("numpy", numpy)

alsaaudio = types.ModuleType("alsaaudio")
sys.modules.setdefault("alsaaudio", alsaaudio)

import camera_config


def test_resolve_storage_dir_uses_custom_path(tmp_path):
    custom_root = tmp_path / "custom_storage"
    custom_root.mkdir()

    cfg = {
        "storage_mode": "custom",
        "storage_path": str(custom_root),
        "storage_usb_path": "",
    }

    result = camera_config.resolve_storage_dir("fotos", cfg)

    assert result == os.path.join(str(custom_root), "fotos")
    assert os.path.isdir(result)


def test_config_file_is_relative_to_module_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    reloaded = importlib.reload(camera_config)

    expected = os.path.join(os.path.dirname(os.path.abspath(camera_config.__file__)), "camera_config.json")
    assert os.path.abspath(reloaded.CONFIG_FILE) == expected


def test_resolve_storage_dir_uses_usb_path_when_usb_field_empty(tmp_path):
    usb_root = tmp_path / "usb_storage"
    usb_root.mkdir()

    cfg = {
        "storage_mode": "usb",
        "storage_path": str(usb_root),
        "storage_usb_path": "",
    }

    result = camera_config.resolve_storage_dir("fotos", cfg)

    assert result == str(usb_root)
