from picamera2 import Picamera2
import time
import subprocess

def video_record_test(output_file="test_2k.mp4"):
    print("🎥 Grabación iniciada. Pulsa Ctrl+C para detener.")
    global picam2

    WIDTH, HEIGHT = 2560, 1440
    TARGET_FPS = 30

    picam2 = Picamera2()
    config = picam2.create_video_configuration(
        main={"format": "YUV420", "size": (WIDTH, HEIGHT)}
    )
    picam2.configure(config)

    frame_time_us = int(1_000_000 / TARGET_FPS)
    picam2.set_controls({
        "AfMode": 2,
        "LensPosition": 0,
        "FrameDurationLimits": (frame_time_us, frame_time_us)
    })

    picam2.start()

    cmd = [
        "ffmpeg",
        "-y",
        "-f", "rawvideo",
        "-pix_fmt", "yuv420p",
        "-s", f"{WIDTH}x{HEIGHT}",
        "-r", str(TARGET_FPS),
        "-i", "-",
        "-c:v", "libx264",
        "-preset", "ultrafast",     
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-fps_mode", "passthrough",
        output_file
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    try:
        while True:
            frame = picam2.capture_array("main")
            proc.stdin.write(memoryview(frame))
    except KeyboardInterrupt:
        print("\n⏹ Grabación detenida por usuario.")
    except Exception as e:
        print("❌ Error en grabación:", e)
    finally:
        proc.stdin.close()
        proc.wait()
        picam2.close()
        print("✅ Grabación terminada y guardada en", output_file)

# test
video_record_test()