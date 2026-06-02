import subprocess
import re
import tempfile
from pathlib import Path
import requests


class ServiceController:
    def __init__(self, zapret_path: Path):
        self.zapret_path = zapret_path

    def service_status(self, name="zapret"):
        result = subprocess.run(
            ["sc", "query", name],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW
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
            capture_output=True, text=True, encoding="utf-8", errors="replace",
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
                if backup_file.exists():
                    backup_file.unlink()
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
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        for line in result.stdout.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                return parts[-1]
        return ""

    def update_ipset(self):
        url = "https://raw.githubusercontent.com/Flowseal/zapret-discord-youtube/refs/heads/main/.service/ipset-service.txt"
        out_file = self.zapret_path / "lists" / "ipset-all.txt"
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            content = response.text.strip()
            if not content:
                return False, "Downloaded IPSet list is empty"

            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(content + "\n", encoding="utf-8")
            entries = sum(1 for line in content.splitlines() if line.strip())
            return True, f"IPSet updated: {entries} entries"
        except Exception as e:
            return False, f"IPSet update failed: {e}"

    def update_hosts(self):
        url = "https://raw.githubusercontent.com/Flowseal/zapret-discord-youtube/refs/heads/main/.service/hosts"
        log_file = Path(tempfile.gettempdir()) / "zapret-gui-hosts-update.log"
        script = f"""
$url = '{url}'
$hosts = 'C:\\Windows\\System32\\drivers\\etc\\hosts'
$backup = 'C:\\Windows\\System32\\drivers\\etc\\hosts.zapret-gui.bak'
$begin = '# BEGIN zapret-gui'
$end = '# END zapret-gui'
Write-Output 'Downloading hosts data...'
$res = Invoke-WebRequest -Uri $url -TimeoutSec 10 -UseBasicParsing
if ($res.StatusCode -ne 200) {{ throw "Download failed with HTTP $($res.StatusCode)" }}
$block = ($res.Content -replace "`r`n", "`n").Trim()
if (-not $block) {{ throw 'Downloaded hosts data is empty' }}
Write-Output 'Creating backup...'
Copy-Item -LiteralPath $hosts -Destination $backup -Force
$current = ''
if (Test-Path -LiteralPath $hosts) {{
    $current = Get-Content -LiteralPath $hosts -Raw -Encoding UTF8
}}
$pattern = '(?s)\\r?\\n?# BEGIN zapret-gui\\r?\\n.*?\\r?\\n# END zapret-gui\\r?\\n?'
$managed = "$begin`r`n$block`r`n$end`r`n"
if ($current -match $pattern) {{
    $updated = [regex]::Replace($current, $pattern, "`r`n$managed", 1)
}} else {{
    $separator = if ($current.Trim().Length -gt 0) {{ "`r`n" }} else {{ "" }}
    $updated = $current.TrimEnd() + $separator + $managed
}}
Set-Content -LiteralPath $hosts -Value $updated -Encoding UTF8 -Force
Write-Output 'Hosts file updated successfully.'
"""
        return self._run_elevated_ps(script, log_file)

    def _ps_quote(self, value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    def _run_elevated_ps(self, script: str, log_file: Path):
        script_file = Path(tempfile.gettempdir()) / "zapret-gui-hosts-update.ps1"
        wrapped = (
            "$ErrorActionPreference = 'Stop'\n"
            f"try {{\n{script}\n}}\n"
            "catch {\n"
            "    Write-Output (\"ERROR: \" + $_.Exception.Message)\n"
            "    exit 1\n"
            "}\n"
        )
        script_file.write_text(wrapped, encoding="utf-8")
        command = (
            f'powershell -NoProfile -ExecutionPolicy Bypass -File "{script_file}" '
            f'> "{log_file}" 2>&1'
        )
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                f'$p = Start-Process -FilePath cmd.exe -ArgumentList @("/c", {self._ps_quote(command)}) -Verb RunAs -Wait -PassThru; exit $p.ExitCode'
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        details = ""
        if log_file.exists():
            details = log_file.read_text("utf-8", errors="ignore").strip()
        if result.returncode != 0:
            if not details:
                details = (result.stderr or result.stdout or "UAC was cancelled or hosts update failed").strip()
            return False, details
        return True, details or "Hosts file updated successfully."

    def _run_ps(self, script):
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", script],
            creationflags=subprocess.CREATE_NO_WINDOW
        )
