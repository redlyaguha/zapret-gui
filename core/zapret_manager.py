import subprocess
import signal
from pathlib import Path


class ZapretManager:
    def __init__(self, zapret_path: Path):
        self.zapret_path = zapret_path
        self._process = None

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
        self.stop()
        self._process = subprocess.Popen(
            [str(bat_path)],
            cwd=self.zapret_path,
            shell=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    def stop(self):
        subprocess.run(
            ["taskkill", "/IM", "winws.exe", "/F"],
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
        if self._process:
            try:
                self._process.terminate()
            except Exception:
                pass
            self._process = None

    def is_running(self) -> bool:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq winws.exe"],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
        return "winws.exe" in result.stdout

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
