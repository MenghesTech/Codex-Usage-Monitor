from __future__ import annotations
import os, re, shutil
from pathlib import Path


class CodexNotFoundError(FileNotFoundError):
    """No compatible Codex executable exists in a supported location."""


def _version_key(path: Path):
    m = re.search(r'openai\.chatgpt-([0-9.]+)', str(path), re.I)
    if m:
        try: return tuple(int(x) for x in m.group(1).split('.'))
        except ValueError: pass
    try: return (0, int(path.stat().st_mtime))
    except OSError: return (0, 0)


def find_codex() -> Path:
    env = os.getenv('CODEX_EXE')
    if env and Path(env).is_file():
        return Path(env)
    p = shutil.which('codex') or shutil.which('codex.exe')
    if p:
        return Path(p)

    home = Path.home()
    roots = [home/'.vscode'/'extensions', home/'.vscode-insiders'/'extensions']
    local = os.getenv('LOCALAPPDATA')
    if local:
        roots += [Path(local)/'Programs'/'Microsoft VS Code'/'resources'/'app'/'extensions']

    candidates: list[Path] = []
    arches = ('windows-x86_64', 'windows-arm64')
    for root in roots:
        if not root.exists(): continue
        for arch in arches:
            candidates.extend(root.glob(f'openai.chatgpt-*/bin/{arch}/codex.exe'))
    if candidates:
        return max(candidates, key=_version_key)
    raise CodexNotFoundError("No compatible codex.exe was found")
