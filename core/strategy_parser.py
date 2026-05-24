import re
from pathlib import Path


def find_strategies(zapret_path: Path):
    strategies = []
    for f in sorted(zapret_path.glob("general*.bat"), key=lambda p: p.stem.lower()):
        strategies.append(f)
    return strategies


def parse_strategy(filepath: Path):
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    args_line = ""
    for line in content.splitlines():
        if "winws.exe" in line and not line.strip().startswith("rem") and not line.strip().startswith("::"):
            args_line = line.strip()
            break

    args_list = []
    if args_line:
        parts = re.findall(r'(?:--\w+(?:-\w+)*)(?:=(?:"[^"]*"|\S+))?|(?:"[^"]*"|\S+)', args_line)
        capture = False
        for p in parts:
            if "winws.exe" in p:
                capture = True
                continue
            if capture:
                args_list.append(p.strip('"'))

    params = {}
    for a in args_list:
        if a.startswith("--"):
            if "=" in a:
                key, val = a.split("=", 1)
                params[key] = val.strip('"')
            else:
                params[a] = True

    return {
        "name": filepath.stem,
        "filename": filepath.name,
        "args": args_list,
        "params": params,
    }
