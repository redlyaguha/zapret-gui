import requests
import zipfile
import io
from pathlib import Path
from datetime import datetime


GITHUB_API = "https://api.github.com/repos/Flowseal/zapret-discord-youtube"
VERSION_URL = "https://raw.githubusercontent.com/Flowseal/zapret-discord-youtube/main/.service/version.txt"


def get_latest_version() -> str:
    resp = requests.get(VERSION_URL, timeout=10)
    resp.raise_for_status()
    return resp.text.strip()


def get_release_info():
    resp = requests.get(f"{GITHUB_API}/releases/latest", timeout=10)
    resp.raise_for_status()
    data = resp.json()
    zip_asset = None
    for asset in data["assets"]:
        if asset["name"].endswith(".zip"):
            zip_asset = asset
            break
    return {
        "tag_name": data["tag_name"],
        "body": data.get("body", ""),
        "zip_url": zip_asset["browser_download_url"] if zip_asset else None,
        "zip_name": zip_asset["name"] if zip_asset else None,
    }


def download_release(zip_url: str, progress_callback=None) -> bytes:
    resp = requests.get(zip_url, stream=True, timeout=30)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    chunks = []
    downloaded = 0
    for chunk in resp.iter_content(chunk_size=8192):
        if chunk:
            chunks.append(chunk)
            downloaded += len(chunk)
            if progress_callback and total:
                progress_callback(int(downloaded / total * 100))
    return b"".join(chunks)


def _get_common_prefix(members):
    prefixes = set()
    for m in members:
        if "/" in m.rstrip("/"):
            prefixes.add(m.split("/", 1)[0])
    return prefixes.pop() if len(prefixes) == 1 else None


def _extract_zip(data, install_path, progress_callback=None, log_callback=None):
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        members = zf.namelist()
        prefix = _get_common_prefix(members)
        total = len(members)
        for i, member in enumerate(members):
            rel = member[len(prefix) + 1:] if prefix and member.startswith(prefix + "/") else member
            if not rel or rel.endswith("/"):
                if rel and rel.endswith("/"):
                    (install_path / rel).mkdir(parents=True, exist_ok=True)
                continue
            target = install_path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src:
                target.write_bytes(src.read())
            if progress_callback and total:
                progress_callback(int((i + 1) / total * 100))
            if log_callback:
                log_callback(f"Extracted: {rel}")


def install_update(
    data: bytes,
    install_path: Path,
    progress_callback=None,
    log_callback=None,
):
    user_files = [
        "lists/ipset-exclude-user.txt",
        "lists/list-general-user.txt",
        "lists/list-exclude-user.txt",
        "utils/game_filter.enabled",
        "utils/check_updates.enabled",
    ]

    backup = {}
    for rel_path in user_files:
        full = install_path / rel_path
        if full.exists():
            backup[rel_path] = full.read_bytes()

    _extract_zip(data, install_path, progress_callback, log_callback)

    for rel_path, content in backup.items():
        target = install_path / rel_path
        target.write_bytes(content)
        if log_callback:
            log_callback(f"Restored user file: {rel_path}")

    version_file = install_path / ".version"
    version_file.write_text(datetime.now().strftime("%Y-%m-%d"), encoding="utf-8")

    if log_callback:
        log_callback("Update complete!")
