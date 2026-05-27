import subprocess
import signal
import re
from pathlib import Path
from typing import Optional
from core.strategy_parser import find_strategies, parse_strategy


class ZapretManager:
    def __init__(self, zapret_path: Path):
        self.zapret_path = zapret_path
        self._process = None
        self._current_strategy: Optional[str] = None
        self._is_service_mode: bool = False

    @property
    def current_strategy(self) -> Optional[str]:
        return self._current_strategy

    @property
    def is_service_mode(self) -> bool:
        return self._is_service_mode

    @is_service_mode.setter
    def is_service_mode(self, value: bool):
        self._is_service_mode = value

    def _is_winws_running(self) -> bool:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq winws.exe"],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
        return "winws.exe" in result.stdout

    def find_installation(self) -> bool:
        return (
            (self.zapret_path / "service.bat").exists()
            and (self.zapret_path / "bin" / "winws.exe").exists()
        )

    def get_local_version(self) -> str:
        svc = self.zapret_path / "service.bat"
        if not svc.exists():
            return "0.0.0"
        with open(svc, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "LOCAL_VERSION" in line:
                    m = line.split("=")
                    if len(m) > 1:
                        return m[1].strip().strip('"').strip()
        return "0.0.0"

    def start_strategy(self, bat_path: Path):
        if not bat_path.exists():
            raise FileNotFoundError(f"Strategy file not found: {bat_path}")

        self.stop()
        if self._is_service_mode:
            info = parse_strategy(bat_path)
            args_str = " ".join(info["args"]) if info["args"] else ""
            winws = str(self.zapret_path / "bin" / "winws.exe")
            svc_script = f'sc stop zapret >nul 2>&1 & sc delete zapret >nul 2>&1 & sc create zapret binPath= "\"{winws}\" {args_str}" DisplayName= "zapret" start= auto >nul & sc start zapret >nul'
            self._run_elevated(svc_script)
        else:
            try:
                self._process = subprocess.Popen(
                    [str(bat_path)],
                    cwd=self.zapret_path,
                    shell=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            except OSError as e:
                raise RuntimeError(f"Could not start strategy process: {e}") from e
        self._current_strategy = bat_path.stem

    def _run_elevated(self, command: str, check: bool = True):
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f'$p = Start-Process cmd -ArgumentList "/c {command}" -Verb RunAs -Wait -PassThru; exit $p.ExitCode'],
                capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=30
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError("Elevated command timed out") from e
        except OSError as e:
            raise RuntimeError(f"Could not run elevated command: {e}") from e

        if check and result.returncode != 0:
            details = (result.stderr or result.stdout or "").strip()
            if details:
                raise RuntimeError(f"Elevated command failed: {details}")
            raise RuntimeError(f"Elevated command failed with exit code {result.returncode}")

    def _kill_taskkill(self) -> bool:
        result = subprocess.run(
            ["taskkill", "/IM", "winws.exe", "/F"],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
        return result.returncode == 0

    def _kill_powershell(self) -> bool:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Stop-Process -Name winws -Force -ErrorAction SilentlyContinue"],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
        return result.returncode == 0

    def _is_service_installed(self) -> bool:
        result = subprocess.run(
            ["sc", "query", "zapret"],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
        return "FAILED" not in result.stdout and result.stdout.strip() != ""

    def stop(self):
        if self._is_service_installed():
            self._run_elevated("net stop zapret & sc delete zapret & taskkill /IM winws.exe /F", check=False)
        self._kill_taskkill()
        self._kill_powershell()
        if self._process:
            try:
                self._process.terminate()
            except Exception:
                pass
            self._process = None
        self._current_strategy = None

    def _get_strategy_from_service(self) -> Optional[str]:
        result = subprocess.run(
            ["reg", "query", r"HKLM\System\CurrentControlSet\Services\zapret",
             "/v", "zapret-discord-youtube"],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
        for line in result.stdout.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                name = parts[-1].strip()
                if name:
                    return name
        return None

    def _is_service_running(self) -> bool:
        result = subprocess.run(
            ["sc", "query", "zapret"],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
        for line in result.stdout.splitlines():
            if "STATE" in line and "RUNNING" in line:
                return True
        return False

    def _norm_args(self, args):
        return [a.replace('"', '').replace("'", "").strip().lower() for a in args]

    def _match_strategy(self, cmdline: str) -> Optional[str]:
        norm = cmdline.replace('"', '').replace("'", "").strip().lower()
        for bat in find_strategies(self.zapret_path):
            info = parse_strategy(bat)
            if info["args"]:
                norm_args = self._norm_args(info["args"])
                if all(a in norm for a in norm_args):
                    return bat.stem
        return None

    def _get_service_binpath(self) -> Optional[str]:
        result = subprocess.run(
            ["sc", "qc", "zapret"],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
        for line in result.stdout.splitlines():
            if "BINARY_PATH_NAME" in line:
                parts = line.split(":", 1)
                if len(parts) > 1:
                    return parts[1].strip()
        return None

    def _get_winws_cmdline(self) -> Optional[str]:
        for attempt in [
            ["wmic", "process", "where", "name='winws.exe'", "get", "commandline", "/format:csv"],
            ["powershell", "-NoProfile", "-Command",
             'Get-CimInstance Win32_Process -Filter "Name=\'winws.exe\'" | Select-Object -ExpandProperty CommandLine'],
            ["powershell", "-NoProfile", "-Command",
             "Get-WmiObject Win32_Process -Filter \"Name='winws.exe'\" | Select-Object -ExpandProperty CommandLine"],
        ]:
            try:
                result = subprocess.run(
                    attempt, capture_output=True, text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW, timeout=5
                )
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if line and "winws.exe" in line.lower() and not line.startswith("Node"):
                        return line
            except Exception:
                continue
        return None

    def is_running(self) -> bool:
        return self._is_winws_running()

    def detect_strategy(self) -> Optional[str]:
        if not self._is_winws_running():
            self._current_strategy = None
            return None
        svc_bin = self._get_service_binpath()
        if svc_bin:
            name = self._match_strategy(svc_bin)
            if name:
                self._current_strategy = name
                return name
        srv_reg = self._get_strategy_from_service()
        if srv_reg:
            self._current_strategy = srv_reg
            return srv_reg
        if self._is_service_running():
            self._current_strategy = "__service__"
            return self._current_strategy
        cmdline = self._get_winws_cmdline()
        if cmdline:
            name = self._match_strategy(cmdline)
            if name:
                self._current_strategy = name
                return name
        self._current_strategy = None
        return None

    def run_bat_admin(self, bat_name: str, args: str = ""):
        full_path = self.zapret_path / bat_name
        subprocess.Popen(
            f'cmd.exe /c "{full_path}" {args}',
            shell=True, creationflags=subprocess.CREATE_NO_WINDOW
        )

    def run_powershell(self, script: str):
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
