import json
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QSettings

from core.app_info import APP_NAME


DATA_DIR_NAME = "zapret-gui-config"
CONFIG_FILE_NAME = "config.json"
LOG_DIR_NAME = "logs"
LOG_DPI_DIR_NAME = "dpi"
LOG_TELEGRAM_DIR_NAME = "telegram"
LOG_GUI_DIR_NAME = "gui"

DEFAULT_CONFIG = {
    "zapret_path": "",
    "theme": "system",
    "stay_open_on_close": True,
    "launch_on_startup": False,
    "startup_mode": "window",
    "always_run_as_admin": False,
    "deferred_app_update": None,
    "last_strategy": "",
    "last_strategy_mode": "process",
    "app_auto_update_enabled": True,
    "app_update_include_prerelease": False,
    "last_app_update_check": "",
    "skipped_app_version": "",
}


def _settings() -> QSettings:
    return QSettings(APP_NAME, APP_NAME)


def default_parent_dir() -> Path:
    return Path.home() / "Documents"


def data_dir_from_parent(parent: Path) -> Path:
    parent = Path(parent)
    if parent.name == DATA_DIR_NAME:
        return parent
    return parent / DATA_DIR_NAME


def legacy_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def legacy_config_file() -> Path:
    return legacy_app_dir() / CONFIG_FILE_NAME


def legacy_logs_dir() -> Path:
    return legacy_app_dir() / LOG_DIR_NAME


def has_configured_data_dir() -> bool:
    return bool(_settings().value("data_dir", "", str))


def get_data_dir() -> Path:
    stored = _settings().value("data_dir", "", str)
    return Path(stored) if stored else data_dir_from_parent(default_parent_dir())


def get_logs_dir() -> Path:
    return get_data_dir() / LOG_DIR_NAME


def get_dpi_logs_dir() -> Path:
    return get_logs_dir() / LOG_DPI_DIR_NAME


def get_telegram_logs_dir() -> Path:
    return get_logs_dir() / LOG_TELEGRAM_DIR_NAME


def get_gui_logs_dir() -> Path:
    return get_logs_dir() / LOG_GUI_DIR_NAME


def ensure_log_dirs():
    for path in (get_dpi_logs_dir(), get_telegram_logs_dir(), get_gui_logs_dir()):
        path.mkdir(parents=True, exist_ok=True)


def get_config_file() -> Path:
    return get_data_dir() / CONFIG_FILE_NAME


def _copy_file_if_exists(src: Path, dst: Path):
    if src.exists() and src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _copy_tree_contents(src: Path, dst: Path):
    if not src.exists() or not src.is_dir():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def configure_data_dir(data_dir: Path, migrate_legacy: bool = True):
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / LOG_DIR_NAME).mkdir(parents=True, exist_ok=True)

    if migrate_legacy:
        old_config = legacy_config_file()
        old_logs = legacy_logs_dir()
        _copy_file_if_exists(old_config, data_dir / CONFIG_FILE_NAME)
        _copy_tree_contents(old_logs, data_dir / LOG_DIR_NAME)
        try:
            if old_config.exists():
                old_config.unlink()
        except OSError:
            pass
        if old_logs.exists():
            shutil.rmtree(old_logs, ignore_errors=True)

    _settings().setValue("data_dir", str(data_dir))
    ensure_log_dirs()


def change_data_parent(parent: Path):
    old_dir = get_data_dir()
    new_dir = data_dir_from_parent(parent)
    if old_dir.resolve() == new_dir.resolve():
        new_dir.mkdir(parents=True, exist_ok=True)
        (new_dir / LOG_DIR_NAME).mkdir(parents=True, exist_ok=True)
        _settings().setValue("data_dir", str(new_dir))
        ensure_log_dirs()
        return new_dir

    new_dir.mkdir(parents=True, exist_ok=True)
    _copy_file_if_exists(old_dir / CONFIG_FILE_NAME, new_dir / CONFIG_FILE_NAME)
    _copy_tree_contents(old_dir / LOG_DIR_NAME, new_dir / LOG_DIR_NAME)
    (new_dir / LOG_DIR_NAME).mkdir(parents=True, exist_ok=True)
    _settings().setValue("data_dir", str(new_dir))
    ensure_log_dirs()

    if old_dir.name == DATA_DIR_NAME and old_dir.exists():
        shutil.rmtree(old_dir, ignore_errors=True)

    return new_dir


def logs_size_bytes() -> int:
    logs_dir = get_logs_dir()
    if not logs_dir.exists():
        return 0
    return sum(path.stat().st_size for path in logs_dir.rglob("*") if path.is_file())


def format_size(size: int) -> str:
    units = ("B", "KB", "MB", "GB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
        value /= 1024


def clear_logs():
    logs_dir = get_logs_dir()
    if logs_dir.exists():
        shutil.rmtree(logs_dir, ignore_errors=True)
    ensure_log_dirs()


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
    data.pop("advanced_logs", None)
    return data


def save_config(data: dict):
    merged = DEFAULT_CONFIG.copy()
    merged.update(data)
    merged.pop("advanced_logs", None)
    path = get_config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
