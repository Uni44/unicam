import sys
import types

# Stubs para que la importación no dependa de hardware real
sounddevice_stub = types.ModuleType("sounddevice")
sounddevice_stub.rec = lambda *args, **kwargs: None
sounddevice_stub.wait = lambda *args, **kwargs: None
sys.modules.setdefault("sounddevice", sounddevice_stub)

numpy_stub = types.ModuleType("numpy")
numpy_stub.sqrt = lambda x: x
numpy_stub.mean = lambda x: 0
numpy_stub.interp = lambda value, xp, fp: value
numpy_stub.clip = lambda value, a, b: value
sys.modules.setdefault("numpy", numpy_stub)

alsaaudio_stub = types.ModuleType("alsaaudio")
sys.modules.setdefault("alsaaudio", alsaaudio_stub)

import camera_config as cc


def test_audio_monitor_plan_disabled_by_default():
    cfg = {"mic": "", "audio_monitor_enabled": False, "audio_monitor_output": ""}
    plan = cc.build_audio_monitor_plan(cfg)
    assert plan["enabled"] is False
    assert plan["monitor_output"] == ""


def test_audio_monitor_plan_enabled_with_output_device():
    cfg = {
        "mic": "plughw:1,0",
        "audio_monitor_enabled": True,
        "audio_monitor_output": "hw:1,0",
    }
    plan = cc.build_audio_monitor_plan(cfg)
    assert plan["enabled"] is True
    assert plan["input_device"] == "plughw:1,0"
    assert plan["monitor_output"] == "hw:1,0"
    assert plan["monitor_source"] == "dsnoop:plughw:1,0"
