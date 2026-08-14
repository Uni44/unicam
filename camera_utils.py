import time


def release_camera_resources(camera, wait_seconds=0.2):
    """Cierra preview, detiene la cámara y libera recursos de forma defensiva."""
    if camera is None:
        return

    try:
        if hasattr(camera, "stop_preview"):
            camera.stop_preview()
    except Exception:
        pass

    try:
        if hasattr(camera, "stop"):
            camera.stop()
    except Exception:
        pass

    try:
        if hasattr(camera, "close"):
            camera.close()
    except Exception:
        pass

    if wait_seconds:
        time.sleep(wait_seconds)
