import subprocess
import re
from pathlib import Path


class ServiceController:
    def __init__(self, zapret_path: Path):
        self.zapret_path = zapret_path

    def service_status(self, name="zapret"):
        result = subprocess.run(
            ["sc", "query", name],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
        for line in result.stdout.splitlines():
            if "STATE" in line:
                if "RUNNING" in line:
                    return "running"
                if "STOP_PENDING" in line:
                    return "stop_pending"
                return "stopped"
        return "not_installed"

    def install_service(self, strategy_name: str):
        strategy_path = self.zapret_path / f"{strategy_name}.bat"
        if not strategy_path.exists():
            return False, f"Strategy {strategy_name}.bat not found"

        svc = self.zapret_path / "service.bat"
        subprocess.Popen(
            f'cmd.exe /c "{svc}" admin',
            shell=True, creationflags=subprocess.CREATE_NO_WINDOW
        )

        result = subprocess.run(
            [str(svc), "admin"],
            capture_output=True, text=True,
            cwd=self.zapret_path, creationflags=subprocess.CREATE_NO_WINDOW
        )
        return True, "Service installation launched"

    def remove_services(self):
        for srv in ["zapret", "WinDivert", "WinDivert14"]:
            subprocess.run(
                ["net", "stop", srv],
                capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
            subprocess.run(
                ["sc", "delete", srv],
                capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
        subprocess.run(
            ["taskkill", "/IM", "winws.exe", "/F"],
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
        return True

    def game_filter_status(self) -> str:
        flag_file = self.zapret_path / "utils" / "game_filter.enabled"
        if not flag_file.exists():
            return "disabled"
        mode = flag_file.read_text("utf-8", errors="ignore").strip()
        if mode.lower() == "all":
            return "enabled (TCP and UDP)"
        elif mode.lower() == "tcp":
            return "enabled (TCP)"
        elif mode.lower() == "udp":
            return "enabled (UDP)"
        return "disabled"

    def set_game_filter(self, mode: str):
        flag_file = self.zapret_path / "utils" / "game_filter.enabled"
        if mode == "disabled":
            if flag_file.exists():
                flag_file.unlink()
        else:
            flag_file.parent.mkdir(parents=True, exist_ok=True)
            flag_file.write_text(mode, encoding="utf-8")
        return True

    def ipset_filter_status(self) -> str:
        list_file = self.zapret_path / "lists" / "ipset-all.txt"
        if not list_file.exists():
            return "none"
        content = list_file.read_text("utf-8", errors="ignore").strip()
        if not content:
            return "any"
        if "203.0.113.113/32" in content:
            return "none"
        return "loaded"

    def set_ipset_filter(self, mode: str):
        list_file = self.zapret_path / "lists" / "ipset-all.txt"
        backup_file = list_file.with_suffix(".txt.backup")

        if mode == "loaded":
            if backup_file.exists():
                if list_file.exists():
                    list_file.unlink()
                backup_file.rename(list_file)
        elif mode == "none":
            if list_file.exists() and self.ipset_filter_status() == "loaded":
                list_file.rename(backup_file)
            list_file.write_text("203.0.113.113/32\n", encoding="utf-8")
        elif mode == "any":
            list_file.write_text("", encoding="utf-8")
        return True

    def auto_update_status(self) -> bool:
        flag = self.zapret_path / "utils" / "check_updates.enabled"
        return flag.exists()

    def set_auto_update(self, enabled: bool):
        flag = self.zapret_path / "utils" / "check_updates.enabled"
        if enabled:
            flag.parent.mkdir(parents=True, exist_ok=True)
            flag.write_text("ENABLED\n", encoding="utf-8")
        else:
            if flag.exists():
                flag.unlink()
        return True

    def get_installed_strategy(self) -> str:
        result = subprocess.run(
            [
                "reg", "query",
                r"HKLM\System\CurrentControlSet\Services\zapret",
                "/v", "zapret-discord-youtube"
            ],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
        for line in result.stdout.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                return parts[-1]
        return ""

    def update_ipset(self):
        url = "https://raw.githubusercontent.com/Flowseal/zapret-discord-youtube/refs/heads/main/.service/ipset-service.txt"
        out_file = self.zapret_path / "lists" / "ipset-all.txt"
        script = f"""
$url = '{url}'
$out = '{out_file}'
$dir = Split-Path -Parent $out
if (-not (Test-Path $dir)) {{ New-Item -ItemType Directory -Path $dir | Out-Null }}
$res = Invoke-WebRequest -Uri $url -TimeoutSec 10 -UseBasicParsing
if ($res.StatusCode -eq 200) {{ $res.Content | Out-File -FilePath $out -Encoding UTF8 }}
"""
        self._run_ps(script)

    def update_hosts(self):
        url = "https://raw.githubusercontent.com/Flowseal/zapret-discord-youtube/refs/heads/main/.service/hosts"
        temp = self.zapret_path / "temp_hosts.txt"
        hosts = Path(r"C:\Windows\System32\drivers\etc\hosts")
        script = f"""
$url = '{url}'
$out = '{temp}'
$res = Invoke-WebRequest -Uri $url -TimeoutSec 10 -UseBasicParsing
if ($res.StatusCode -eq 200) {{ $res.Content | Out-File -FilePath $out -Encoding UTF8 }}
Write-Host "Downloaded to {temp}. Open and copy to {hosts} manually."
start notepad '{temp}'
start explorer /select,'{hosts}'
"""
        self._run_ps(script)

    def _run_ps(self, script):
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", script],
            creationflags=subprocess.CREATE_NO_WINDOW
        )
