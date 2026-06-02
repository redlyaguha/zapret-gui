import hashlib
import os
import re
import shutil
import subprocess
import sys
import webbrowser
import zipfile
from dataclasses import dataclass
from pathlib import Path

import requests

from core.app_info import APP_VERSION, GITHUB_REPO


APP_ZIP_RE = re.compile(r"^zapret-gui-v.+-windows-x64\.zip$", re.IGNORECASE)


@dataclass
class AppUpdateInfo:
    current_version: str
    latest_version: str
    release_url: str
    body: str = ""
    asset_url: str = ""
    asset_name: str = ""
    sha256_url: str = ""
    sha256_name: str = ""
    is_prerelease: bool = False

    @property
    def is_newer(self) -> bool:
        return _version_tuple(self.latest_version) > _version_tuple(self.current_version)


def _version_tuple(value: str) -> tuple:
    parts = re.findall(r"\d+", value or "")
    return tuple(int(part) for part in parts[:3]) or (0,)


def _github_get(url: str):
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()


def _select_release(include_prerelease: bool):
    releases = _github_get(f"https://api.github.com/repos/{GITHUB_REPO}/releases")
    candidates = [
        rel for rel in releases
        if not rel.get("draft") and (include_prerelease or not rel.get("prerelease"))
    ]
    if not candidates:
        raise RuntimeError("Подходящие релизы zapret-gui не найдены")
    candidates.sort(key=lambda rel: _version_tuple(str(rel.get("tag_name") or "")), reverse=True)
    return candidates[0]


def _asset_url(asset: dict) -> str:
    return asset.get("browser_download_url") or asset.get("url") or ""


def _select_assets(release: dict) -> tuple[dict, dict]:
    assets = release.get("assets") or []
    zip_asset = next((asset for asset in assets if APP_ZIP_RE.match(asset.get("name") or "")), None)
    if not zip_asset:
        raise RuntimeError("В релизе не найден zip asset zapret-gui для Windows")

    expected_sha_name = f"{zip_asset.get('name')}.sha256"
    sha_asset = next((asset for asset in assets if (asset.get("name") or "").lower() == expected_sha_name.lower()), None)
    if not sha_asset:
        raise RuntimeError(f"В релизе не найден checksum asset {expected_sha_name}")
    return zip_asset, sha_asset


def check_app_update(include_prerelease: bool = False, require_assets: bool = True) -> AppUpdateInfo:
    release = _select_release(include_prerelease)
    latest = str(release.get("tag_name") or "").lstrip("v")
    info = AppUpdateInfo(
        current_version=APP_VERSION.lstrip("v"),
        latest_version=latest,
        release_url=release.get("html_url") or f"https://github.com/{GITHUB_REPO}/releases",
        body=release.get("body") or "",
        is_prerelease=bool(release.get("prerelease")),
    )
    if not info.is_newer or not require_assets:
        return info

    zip_asset, sha_asset = _select_assets(release)
    info.asset_url = _asset_url(zip_asset)
    info.asset_name = zip_asset.get("name") or ""
    info.sha256_url = _asset_url(sha_asset)
    info.sha256_name = sha_asset.get("name") or ""
    return info


def download_file(url: str, target: Path, progress_callback=None) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=30) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        downloaded = 0
        with target.open("wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 256):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback and total:
                    progress_callback(min(100, int(downloaded / total * 100)))
    if progress_callback:
        progress_callback(100)
    return target


def _parse_sha256(text: str) -> str:
    match = re.search(r"\b[a-fA-F0-9]{64}\b", text or "")
    if not match:
        raise RuntimeError("SHA256-файл не содержит корректный hash")
    return match.group(0).lower()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


def download_and_verify_update(info: AppUpdateInfo, updates_dir: Path, progress_callback=None) -> Path:
    if not info.asset_url or not info.sha256_url:
        raise RuntimeError("Релиз не содержит ссылок на zip и checksum")

    work_dir = updates_dir / f"zapret-gui-{info.latest_version}"
    if work_dir.exists():
        shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    zip_path = download_file(info.asset_url, work_dir / info.asset_name, progress_callback)
    sha_path = download_file(info.sha256_url, work_dir / info.sha256_name)
    expected = _parse_sha256(sha_path.read_text("utf-8", errors="ignore"))
    actual = _file_sha256(zip_path)
    if actual != expected:
        raise RuntimeError("SHA256 не совпал, обновление не будет установлено")
    return zip_path


def extract_app_exe(zip_path: Path, updates_dir: Path) -> Path:
    extract_dir = updates_dir / "extracted"
    if extract_dir.exists():
        shutil.rmtree(extract_dir, ignore_errors=True)
    extract_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as zf:
        exe_member = None
        for member in zf.infolist():
            name = Path(member.filename).name.lower()
            if not member.is_dir() and name == "zapret-gui.exe":
                exe_member = member
                break
        if not exe_member:
            raise RuntimeError("В архиве не найден zapret-gui.exe")

        target = extract_dir / "zapret-gui.exe"
        with zf.open(exe_member) as src, target.open("wb") as dst:
            shutil.copyfileobj(src, dst)
    return target


def launch_update_helper(new_exe: Path, logs_dir: Path):
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Автоустановка доступна только для portable .exe")

    current_exe = Path(sys.executable).resolve()
    pid = os.getpid()
    helper = new_exe.parent / "apply-zapret-gui-update.ps1"
    log_file = logs_dir / "app-update-helper.log"
    backup = current_exe.with_suffix(".exe.bak")

    script = f"""
$ErrorActionPreference = "Stop"
$CurrentExe = { _ps_quote(str(current_exe)) }
$NewExe = { _ps_quote(str(new_exe.resolve())) }
$Backup = { _ps_quote(str(backup)) }
$Log = { _ps_quote(str(log_file)) }
$PidToWait = {pid}
function Write-UpdateLog($Message) {{
  $dir = Split-Path -Parent $Log
  New-Item -ItemType Directory -Path $dir -Force | Out-Null
  Add-Content -Path $Log -Value ("[{{0}}] {{1}}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message) -Encoding UTF8
}}
try {{
  Write-UpdateLog "Waiting for zapret-gui process $PidToWait"
  try {{ Wait-Process -Id $PidToWait -Timeout 30 }} catch {{ Start-Sleep -Seconds 2 }}
  if (Test-Path $Backup) {{ Remove-Item -LiteralPath $Backup -Force }}
  Copy-Item -LiteralPath $CurrentExe -Destination $Backup -Force
  Copy-Item -LiteralPath $NewExe -Destination $CurrentExe -Force
  Write-UpdateLog "Executable replaced"
  Start-Process -FilePath $CurrentExe
  Start-Sleep -Seconds 2
  if (Test-Path $Backup) {{ Remove-Item -LiteralPath $Backup -Force }}
}} catch {{
  Write-UpdateLog ("Update failed: " + $_.Exception.Message)
  try {{
    if ((Test-Path $Backup) -and (Test-Path $CurrentExe)) {{
      Copy-Item -LiteralPath $Backup -Destination $CurrentExe -Force
      Write-UpdateLog "Backup restored"
    }}
  }} catch {{
    Write-UpdateLog ("Restore failed: " + $_.Exception.Message)
  }}
}}
"""
    helper.write_text(script, encoding="utf-8")
    subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(helper)],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def open_releases():
    webbrowser.open(f"https://github.com/{GITHUB_REPO}/releases")
