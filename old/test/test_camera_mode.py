import importlib
import sys
import types


def test_normalize_camera_mode_supports_aliases():
    sys.modules.pop("camera_config", None)

    sounddevice_stub = types.ModuleType("sounddevice")
    sounddevice_stub.rec = lambda *args, **kwargs: None
    sounddevice_stub.wait = lambda: None
    sys.modules["sounddevice"] = sounddevice_stub

    numpy_stub = types.ModuleType("numpy")
    numpy_stub.sqrt = lambda x: x
    numpy_stub.mean = lambda x: x
    numpy_stub.log10 = lambda x: x
    sys.modules["numpy"] = numpy_stub

    alsaaudio_stub = types.ModuleType("alsaaudio")
    sys.modules["alsaaudio"] = alsaaudio_stub

    module = importlib.import_module("camera_config")

    assert module.normalize_camera_mode("Photo") == "Foto"
    assert module.normalize_camera_mode("Record") == "Grabar"
    assert module.normalize_camera_mode("Foto") == "Foto"
    assert module.normalize_camera_mode("Stream") == "Stream"


def test_normalize_camera_config_assigns_camera_number_default():
    sys.modules.pop("camera_config", None)

    sounddevice_stub = types.ModuleType("sounddevice")
    sounddevice_stub.rec = lambda *args, **kwargs: None
    sounddevice_stub.wait = lambda: None
    sys.modules["sounddevice"] = sounddevice_stub

    numpy_stub = types.ModuleType("numpy")
    numpy_stub.sqrt = lambda x: x
    numpy_stub.mean = lambda x: x
    numpy_stub.log10 = lambda x: x
    sys.modules["numpy"] = numpy_stub

    alsaaudio_stub = types.ModuleType("alsaaudio")
    sys.modules["alsaaudio"] = alsaaudio_stub

    module = importlib.import_module("camera_config")

    normalized = module.normalize_camera_config({"resolution": "1920x1080", "fps": "30"})

    assert normalized["camera_number"] == "1"
