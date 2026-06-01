import json
import sys
from pathlib import Path


DEFAULT_CONFIG = {
    "zapret_path": "",
    "theme": "system",
    "stay_open_on_close": True,
    "launch_on_startup": False,
    "advanced_logs": True,
    "deferred_app_update": None,
}


def get_config_file() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "config.json"
    return Path(__file__).resolve().parent.parent / "config.json"


def load_config() -> dict:
    path = get_config_file()
    data = DEFAULT_CONFIG.copy()
    if path.exists():
        try:
            loaded = json.loads(path.read_text("utf-8"))
            if isinstance(loaded, dict):
                data.update(loaded)
        except Exception:
            pass
    return data


def save_config(data: dict):
    merged = DEFAULT_CONFIG.copy()
    merged.update(data)
    get_config_file().write_text(
        json.dumps(merged, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
