from pathlib import Path
from .auto_updater import get_release_info, download_release, _extract_zip


def install_zapret(target_path: Path, progress_callback=None, log_callback=None):
    if log_callback:
        log_callback("Fetching latest release info...")

    info = get_release_info()
    if not info["zip_url"]:
        raise Exception("No .zip asset found in latest release")

    if log_callback:
        log_callback(f"Downloading {info['zip_name']} ({info['tag_name']})...")

    data = download_release(info["zip_url"], progress_callback)

    if log_callback:
        log_callback("Extracting...")

    _extract_zip(data, target_path, progress_callback, log_callback)

    version_file = target_path / ".version"
    version_file.write_text(info["tag_name"], encoding="utf-8")

    if log_callback:
        log_callback(f"zapret {info['tag_name']} installed to {target_path}")
        log_callback("Done!")

    return info["tag_name"]
