import subprocess
import re


def check_bfe():
    result = subprocess.run(
        ["sc", "query", "BFE"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    return "RUNNING" in result.stdout


def check_proxy():
    import winreg
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        )
        enabled, _ = winreg.QueryValueEx(key, "ProxyEnable")
        if enabled:
            server, _ = winreg.QueryValueEx(key, "ProxyServer")
            winreg.CloseKey(key)
            return ("enabled", server)
        winreg.CloseKey(key)
        return ("disabled", None)
    except Exception:
        return ("unknown", None)


def check_tcp_timestamps():
    result = subprocess.run(
        ["netsh", "interface", "tcp", "show", "global"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    return "timestamps" in result.stdout and "enabled" in result.stdout


def check_adguard():
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq AdguardSvc.exe"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    return "AdguardSvc.exe" in result.stdout


def check_killer():
    result = subprocess.run(
        ["sc", "query"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    return bool(re.search(r"Killer", result.stdout, re.I))


def check_intel_connectivity():
    result = subprocess.run(
        ["sc", "query"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    return bool(re.search(r"Intel.*Connectivity.*Network", result.stdout, re.I))


def check_checkpoint():
    result = subprocess.run(
        ["sc", "query"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    return ("TracSrvWrapper" in result.stdout) or ("EPWD" in result.stdout)


def check_smartbyte():
    result = subprocess.run(
        ["sc", "query"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    return "SmartByte" in result.stdout


def check_windivert_file(zapret_path):
    import glob
    return len(glob.glob(str(zapret_path / "bin" / "*.sys"))) > 0


def check_vpn():
    result = subprocess.run(
        ["sc", "query"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    services = re.findall(r"SERVICE_NAME:\s+(\S+)", result.stdout)
    vpn_services = [s for s in services if "vpn" in s.lower()]
    return vpn_services


def check_doh():
    result = subprocess.run(
        [
            "powershell", "-NoProfile", "-Command",
            "Get-ChildItem -Recurse -Path 'HKLM:System\\CurrentControlSet\\Services\\Dnscache\\InterfaceSpecificParameters\\' "
            "| Get-ItemProperty | Where-Object { $_.DohFlags -gt 0 } | Measure-Object | Select-Object -ExpandProperty Count"
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    try:
        return int(result.stdout.strip()) > 0
    except (ValueError, TypeError):
        return False


def run_diagnostics(zapret_path):
    results = []
    results.append(("Base Filtering Engine", "pass" if check_bfe() else "fail"))
    proxy_status, proxy_server = check_proxy()
    if proxy_status == "enabled":
        results.append(("Proxy", f"warn: enabled ({proxy_server})"))
    else:
        results.append(("Proxy", "pass"))
    results.append(("TCP Timestamps", "pass" if check_tcp_timestamps() else "fail"))
    results.append(("Adguard", "fail" if check_adguard() else "pass"))
    results.append(("Killer", "fail" if check_killer() else "pass"))
    results.append(("Intel Connectivity", "fail" if check_intel_connectivity() else "pass"))
    results.append(("Check Point", "fail" if check_checkpoint() else "pass"))
    results.append(("SmartByte", "fail" if check_smartbyte() else "pass"))
    results.append(("WinDivert64.sys", "pass" if check_windivert_file(zapret_path) else "fail"))
    vpn = check_vpn()
    if vpn:
        results.append(("VPN Services", f"warn: {', '.join(vpn)}"))
    else:
        results.append(("VPN Services", "pass"))
    results.append(("Secure DNS", "pass" if check_doh() else "warn: not configured"))
    return results
