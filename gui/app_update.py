import re
import webbrowser
from dataclasses import dataclass

import requests

from core.app_info import APP_VERSION, GITHUB_REPO


@dataclass
class AppUpdateInfo:
    current_version: str
    latest_version: str
    release_url: str
    body: str = ""

    @property
    def is_newer(self) -> bool:
        return _version_tuple(self.latest_version) > _version_tuple(self.current_version)


def _version_tuple(value: str) -> tuple:
    parts = re.findall(r"\d+", value or "")
    return tuple(int(part) for part in parts[:3]) or (0,)


def check_app_update() -> AppUpdateInfo:
    response = requests.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
        timeout=8,
    )
    response.raise_for_status()
    data = response.json()
    latest = str(data.get("tag_name") or "").lstrip("v")
    return AppUpdateInfo(
        current_version=APP_VERSION.lstrip("v"),
        latest_version=latest,
        release_url=data.get("html_url") or f"https://github.com/{GITHUB_REPO}/releases",
        body=data.get("body") or "",
    )


def open_releases():
    webbrowser.open(f"https://github.com/{GITHUB_REPO}/releases")
