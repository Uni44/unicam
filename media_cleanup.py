import os
import shutil
from typing import Iterable, List, Dict, Any


def cleanup_media_directories(media_dirs: Iterable[str], base_dir: str | None = None) -> Dict[str, Any]:
    """Delete only media files inside the provided media directories.

    This function is intentionally conservative: it never deletes the root directories,
    never traverses outside the supplied base path, and only removes known media files.
    """
    if media_dirs is None:
        media_dirs = []

    normalized_dirs: List[str] = []
    for raw_dir in media_dirs:
        if not raw_dir:
            continue
        expanded = os.path.expanduser(str(raw_dir))
        if not expanded:
            continue
        normalized_dirs.append(os.path.abspath(expanded))

    if not normalized_dirs:
        return {"removed_files": 0, "removed_dirs": 0, "paths": []}

    if base_dir is not None:
        base_real = os.path.abspath(os.path.expanduser(str(base_dir)))
    else:
        base_real = os.path.commonpath(normalized_dirs) if len(normalized_dirs) > 1 else normalized_dirs[0]

    removed_files = 0
    removed_dirs = 0
    removed_paths = []

    media_extensions = {
        ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff", ".webp",
        ".mp4", ".mov", ".mkv", ".avi", ".m4v", ".mpg", ".mpeg", ".ts", ".mts", ".m2ts",
        ".h264", ".h265", ".hevc"
    }

    for directory in normalized_dirs:
        if not os.path.isdir(directory):
            continue

        real_dir = os.path.realpath(directory)
        if not real_dir.startswith(base_real + os.sep) and real_dir != base_real:
            continue

        for root, dirs, files in os.walk(real_dir, topdown=True):
            dirs[:] = [d for d in dirs if not d.startswith(".") or d in {""}]
            for filename in files:
                full_path = os.path.join(root, filename)
                if not os.path.isfile(full_path):
                    continue
                ext = os.path.splitext(filename)[1].lower()
                if ext not in media_extensions:
                    continue
                os.remove(full_path)
                removed_files += 1
                removed_paths.append(full_path)

        for root, dirs, files in os.walk(real_dir, topdown=False):
            for dirname in dirs:
                full_dir = os.path.join(root, dirname)
                try:
                    if os.path.isdir(full_dir) and not os.listdir(full_dir):
                        os.rmdir(full_dir)
                        removed_dirs += 1
                except Exception:
                    continue

    return {
        "removed_files": removed_files,
        "removed_dirs": removed_dirs,
        "paths": removed_paths,
    }
