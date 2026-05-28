import re
from pathlib import Path


def find_strategies(zapret_path: Path):
    strategies = []
    for f in sorted(zapret_path.glob("general*.bat"), key=lambda p: p.stem.lower()):
        strategies.append(f)
    return strategies


def _is_comment(line: str) -> bool:
    stripped = line.strip().lower()
    return stripped.startswith("rem") or stripped.startswith("::")


def _strip_line_continuation(line: str):
    stripped = line.strip()
    if stripped.endswith("^"):
        return stripped[:-1].rstrip(), True
    return stripped, False


def _extract_winws_command(content: str) -> str:
    lines = content.splitlines()
    command_parts = []
    capturing = False

    for line in lines:
        if not capturing:
            if _is_comment(line) or "winws.exe" not in line.lower():
                continue
            capturing = True

        part, continues = _strip_line_continuation(line)
        if part:
            command_parts.append(part)

        if capturing and not continues:
            break

    return " ".join(command_parts)


def _split_batch_command(command: str):
    return re.findall(r'"[^"]*"|\S+', command)


def _strip_outer_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def _unescape_batch_arg(value: str) -> str:
    return value.replace("^!", "!")


def parse_strategy(filepath: Path):
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    command = _extract_winws_command(content)

    args_list = []
    if command:
        parts = _split_batch_command(command)
        capture = False
        for p in parts:
            if "winws.exe" in p.lower():
                capture = True
                continue
            if capture:
                args_list.append(_unescape_batch_arg(_strip_outer_quotes(p)))

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
