"""SteelTemple YATMB — Yoshi and the Mysterious Book PC Launcher & Setup Hub."""

from __future__ import annotations

import argparse
import base64
import ctypes
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import urllib.request
import webbrowser
import zipfile
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from yatmb_dump import (
    DumpError,
    EXEFS_REQUIRED,
    discover_dump,
    extract_nup_overlay,
    find_extract_nup,
    load_expected_yatmb as load_expected_yatmb_dump,
    nro_to_nso,
    reuse_extracted_nup,
    rmtree_retry,
    sha256_file,
    verify_exefs_hashes,
)


APP_TITLE = "SteelTemple YATMB"
APP_SUBTITLE = "Yoshi and the Mysterious Book  ·  Native Windows PC Recompilation"
DEFAULT_VERSION = "0.1.2"
GITHUB_URL = "https://github.com/STS78721/YATMB"
RELEASES_URL = GITHUB_URL + "/releases"
RELEASES_API_URL = "https://api.github.com/repos/STS78721/YATMB/releases/latest"
RELEASES_LIST_API_URL = "https://api.github.com/repos/STS78721/YATMB/releases?per_page=10"
UPDATE_SKIP_TOP = {
    "exefs",
    "romfs",
    "romfs_packed",
    "generated",
    "spirv",
    "profile",
    "save",
    "logs",
    "shader-cache",
    "work",
    "mods",
}


# Storybook Meadow palette (matches runtime/ui/theme.h THEME_STORYBOOK): deep forest emerald, cream parchment, leaf green & gold.
C_BG_DEEP = "#07140B"
C_BG = "#0C1E12"
C_PANEL = "#152D1D"
C_RAISED = "#1E3E28"
C_RAISED_HOVER = "#2A5436"
C_LINE = "#3B6B44"
C_LINE_BRIGHT = "#5C9A64"
C_TEXT = "#FCF9EE"
C_TEXT_SOFT = "#CEE4C6"
C_TEXT_DIM = "#96B694"
C_NEON = "#60E244"
C_NEON_HOVER = "#84F466"
C_NEON_DOWN = "#48BC30"
C_NEON_TEXT = "#0A1A0E"
C_CYAN = "#FFE060"
C_OK = "#60E276"
C_WARN = "#FFA65C"
C_BAD = "#F67266"


def resource_base() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def read_app_version() -> str:
    # Frozen installs ship VERSION="0.1.0" beside YATMBLauncher.exe; unfrozen dev runs prefer yatmb_version.txt.
    names = ("VERSION", "yatmb_version.txt") if getattr(sys, "frozen", False) else ("yatmb_version.txt", "VERSION")
    for base in (app_dir(), resource_base(), resource_base().parent):
        for name in names:
            p = base / name
            if p.is_file():
                txt = p.read_text(encoding="utf-8-sig", errors="ignore").strip()
                if txt:
                    return txt.splitlines()[0].strip()
    return DEFAULT_VERSION


def version_tuple(ver: str) -> tuple[tuple[int, ...], str]:
    m = re.search(r"(\d+(?:\.\d+)+)(?:([a-z])(?![a-z]))?", str(ver or "").strip().lower())
    if not m:
        return ((), "")
    nums = tuple(int(x) for x in m.group(1).split("."))
    return (nums, m.group(2) or "")


def is_same_version(ver1: str, ver2: str) -> bool:
    def norm(v: str) -> str:
        v = re.sub(r"^v", "", str(v or "").strip().lower())
        return re.sub(r"[^a-z0-9]", "", v)

    return norm(ver1) == norm(ver2)


def is_up_to_date(local_ver: str, remote_tag: str) -> bool:
    if is_same_version(local_ver, remote_tag):
        return True
    lv, rv = version_tuple(local_ver), version_tuple(remote_tag)
    return bool(lv[0] and rv[0] and lv >= rv)


def _find_update_asset(release: dict) -> tuple[str | None, str | None]:
    tag = (release.get("tag_name") or "").strip()
    raw_assets = release.get("assets") or []
    assets = raw_assets.get("links") or [] if isinstance(raw_assets, dict) else raw_assets
    tag_clean = tag.replace("-", "").replace(".", "")
    candidates = [
        f"SteelTemple-YATMB-{tag}-Update.zip",
        f"SteelTemple-YATMB-{tag_clean}-Update.zip",
        f"SteelTemple-YATMB-Update-{tag}.zip",
    ]
    asset = next(
        (
            item
            for item in assets
            for cand in candidates
            if item.get("name", "").casefold() == cand.casefold()
        ),
        None,
    )
    if not asset:
        asset = next(
            (
                item
                for item in assets
                if "update" in item.get("name", "").lower() and item.get("name", "").lower().endswith(".zip")
            ),
            None,
        )
    if not asset:
        return (None, None)
    return (asset.get("name"), asset.get("browser_download_url") or asset.get("url"))


def select_latest_release(releases: list[dict]) -> dict | None:
    """Pick newest non-draft release across regular releases and pre-releases."""
    candidates = [r for r in (releases or []) if isinstance(r, dict) and not r.get("draft")]
    if not candidates:
        return None

    def rank(idx_rel: tuple[int, dict]) -> tuple:
        idx, rel = idx_rel
        tag = (rel.get("tag_name") or "").strip()
        name = (rel.get("name") or "").strip()
        ver = version_tuple(tag)
        if not ver[0]:
            ver = version_tuple(name)
        _, asset_url = _find_update_asset(rel)
        return (bool(ver[0]), ver, 1 if asset_url else 0, -idx)

    return max(enumerate(candidates), key=rank)[1]


def find_running_yatmb_processes(root: Path) -> list[dict]:
    if os.name != "nt":
        return []
    target = str((root / "yatmb.exe").resolve()).replace("'", "''")
    command = (
        f"$target = '{target}'; "
        "$items = @(Get-CimInstance Win32_Process -Filter \\\"Name='yatmb.exe'\\\" -ErrorAction SilentlyContinue | "
        "Where-Object { $_.ExecutablePath -and "
        "[String]::Equals([IO.Path]::GetFullPath($_.ExecutablePath), $target, "
        "[StringComparison]::OrdinalIgnoreCase) } | "
        "Select-Object ProcessId, ExecutablePath); "
        "if ($items.Count -eq 1) { $items[0] | ConvertTo-Json -Compress } "
        "else { $items | ConvertTo-Json -Compress }"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            return []
        output = result.stdout.strip()
        if not output or output == "null":
            return []
        parsed = json.loads(output)
        if isinstance(parsed, dict):
            return [{"pid": parsed.get("ProcessId"), "path": parsed.get("ExecutablePath")}]
        if isinstance(parsed, list):
            return [
                {"pid": item.get("ProcessId"), "path": item.get("ExecutablePath")}
                for item in parsed
                if isinstance(item, dict)
            ]
    except Exception:
        pass
    return []


def game_process_warning(root: Path, action: str) -> str | None:
    processes = find_running_yatmb_processes(root)
    if not processes:
        return None
    details = []
    for process in processes:
        label = []
        if process.get("pid") is not None:
            label.append(f"PID {process['pid']}")
        if process.get("path"):
            label.append(str(process["path"]))
        details.append(" - ".join(label) if label else "yatmb.exe")
    return "Yoshi and the Mysterious Book (yatmb.exe) is currently running:\n" + "\n".join(details) + f"\n\nClose the game before {action}."


def _win_long_path(path: Path) -> Path:
    """Prefix deep Windows paths with \\\\?\\ so file operations never hit the 260-char MAX_PATH limit."""
    p = Path(path)
    if os.name != "nt":
        return p
    raw = str(p.resolve(strict=False))
    if raw.startswith("\\\\?\\"):
        return Path(raw)
    if len(raw) < 240:
        return Path(raw)
    if raw.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + raw[2:])
    return Path("\\\\?\\" + raw)


def _is_updater_pid_alive(pid: int) -> bool:
    if pid <= 0 or os.name != "nt":
        return False
    try:
        r = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                f"$p = Get-Process -Id {int(pid)} -ErrorAction SilentlyContinue; if ($p -and $p.ProcessName -match 'powershell|pwsh') {{ 'ALIVE' }}",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return r.returncode == 0 and "ALIVE" in (r.stdout or "")
    except Exception:
        return False


def cleanup_stale_update_dirs(root: Path) -> int:
    """Remove leftover .yatmb-update-* staging folders and temp swap files when no updater is active."""
    root = Path(root)
    if not root.is_dir():
        return 0
    lock_file = root / "logs" / ".yatmb-update-active.pid"
    if lock_file.is_file():
        try:
            pid = int(lock_file.read_text(encoding="utf-8", errors="ignore").strip() or "0")
            if _is_updater_pid_alive(pid):
                return 0
        except Exception:
            pass
        try:
            lock_file.unlink(missing_ok=True)
        except OSError:
            pass

    removed = 0
    try:
        entries = list(root.iterdir())
    except OSError:
        return 0
    for entry in entries:
        name = entry.name
        if entry.is_dir() and name.startswith(".yatmb-update-"):
            try:
                rmtree_retry(_win_long_path(entry))
                removed += 1
            except Exception:
                shutil.rmtree(_win_long_path(entry), ignore_errors=True)
                if not entry.exists():
                    removed += 1
        elif entry.is_file() and (".update-old" in name or name.endswith(".update-new")):
            try:
                entry.unlink(missing_ok=True)
                removed += 1
            except OSError:
                pass
    return removed


def extract_update_archive(
    archive_path: Path,
    stage_dir: Path,
    existing_root: Path | None = None,
) -> list[str]:
    """Stage safe files from the official SteelTemple YATMB Update.zip (flat or YATMB/ nested).

    When existing_root is provided, validates the full archive (including CRC and required YATMBLauncher.exe)
    and only stages files that are missing or differ from existing_root so updates apply in seconds.
    """
    archive_path, stage_dir = Path(archive_path), Path(stage_dir)
    existing_base = Path(existing_root).resolve() if existing_root is not None else None
    selected: dict[str, tuple[tuple[str, ...], zipfile.ZipInfo]] = {}
    with zipfile.ZipFile(archive_path) as archive:
        bad_member = archive.testzip()
        if bad_member:
            raise ValueError(f"Update archive CRC check failed for {bad_member}.")
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            path = Path(name)
            parts = path.parts
            if parts and parts[0].casefold() == "yatmb":
                parts = parts[1:]
            if not parts or path.is_absolute() or ".." in parts:
                raise ValueError(f"Unexpected path in update archive: {info.filename}")
            top = parts[0].casefold()
            if top in UPDATE_SKIP_TOP or top.startswith("."):
                continue
            if parts[-1].casefold() in {"yatmb.ini", ".ds_store"}:
                continue
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise ValueError(f"Symbolic links are not allowed in updates: {info.filename}")
            # Empty files (e.g. Python package markers) are allowed.
            key = "/".join(parts).casefold()
            if key in selected:
                raise ValueError(f"Duplicate update file: {info.filename}")
            selected[key] = (parts, info)

        launcher_keys = [k for k in selected if k.endswith("yatmblauncher.exe")]
        if not launcher_keys:
            raise ValueError("Update archive is missing required binary: YATMBLauncher.exe.")
        if selected[launcher_keys[0]][1].file_size < 1024 * 1024:
            raise ValueError("Update launcher executable is unexpectedly small.")

        written: list[str] = []
        for _key, (parts, info) in selected.items():
            rel = Path(*parts)
            data = archive.read(info)
            if existing_base is not None:
                cur = _win_long_path(existing_base / rel)
                try:
                    if cur.is_file() and cur.stat().st_size == len(data) and cur.read_bytes() == data:
                        continue
                except OSError:
                    pass
            target = _win_long_path(stage_dir / rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            written.append(rel.as_posix())
        return written


def build_update_relauncher_script(
    game_dir: Path,
    stage_dir: Path,
    title: str,
    pid: int = 0,
    restart: bool = True,
    silent: bool = False,
    tag: str = "",
) -> str:
    def ps_quote(value: object) -> str:
        return "'" + str(value).replace("'", "''") + "'"

    game_path = ps_quote(Path(game_dir).resolve())
    stage_path = ps_quote(Path(stage_dir).resolve())
    title_text = ps_quote(title)
    tag_text = ps_quote(tag or title)
    wait_pid_line = f"Wait-Process -Id {int(pid)} -Timeout 20 -ErrorAction SilentlyContinue" if pid and pid > 0 else ""
    msg_err = (
        ""
        if silent
        else (
            "try {\n"
            "        Add-Type -AssemblyName System.Windows.Forms\n"
            "        [System.Windows.Forms.MessageBox]::Show(\n"
            "            ('Update failed and changes were rolled back:' + [Environment]::NewLine + $errMsg + [Environment]::NewLine + [Environment]::NewLine + 'See logs\\update.log for details.'),\n"
            "            'SteelTemple YATMB — Update Failed',\n"
            "            [System.Windows.Forms.MessageBoxButtons]::OK,\n"
            "            [System.Windows.Forms.MessageBoxIcon]::Error,\n"
            "            [System.Windows.Forms.MessageBoxDefaultButton]::Button1,\n"
            "            [System.Windows.Forms.MessageBoxOptions]::DefaultDesktopOnly\n"
            "        ) | Out-Null\n"
            "    } catch {}\n"
        )
    )
    restart_block = (
        "    if ([System.IO.File]::Exists($targetLauncherLP)) {\n"
        "        Start-Process -FilePath $targetLauncher -WorkingDirectory $game\n"
        "    }\n"
        if restart
        else ""
    )
    return f"""$ErrorActionPreference = 'Stop'
$tStart = Get-Date
$game = {game_path}
$stage = {stage_path}
$title = {title_text}
$tag = {tag_text}

function ConvertTo-LongPath([string]$p) {{
    $full = [System.IO.Path]::GetFullPath($p)
    if ($full.StartsWith('\\\\?\\')) {{ return $full }}
    if ($full.StartsWith('\\\\')) {{ return '\\\\?\\UNC\\' + $full.Substring(2) }}
    return '\\\\?\\' + $full
}}

$gameLP = (ConvertTo-LongPath $game).TrimEnd('\\')
$stageLP = (ConvertTo-LongPath $stage).TrimEnd('\\')
$rollbackLP = $stageLP + '\\_rollback'
$targetLauncher = Join-Path $game 'YATMBLauncher.exe'
$targetLauncherFull = [System.IO.Path]::GetFullPath($targetLauncher)
$targetLauncherLP = ConvertTo-LongPath $targetLauncher
$logDirLP = $gameLP + '\\logs'
$logFileLP = $logDirLP + '\\update.log'
$doneFileLP = $logDirLP + '\\update_done.json'
$failFileLP = $logDirLP + '\\update_failed.json'
$lockFileLP = $logDirLP + '\\.yatmb-update-active.pid'
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)

function Write-UpdateLog([string]$msg) {{
    try {{
        [System.IO.Directory]::CreateDirectory($logDirLP) | Out-Null
        $line = '[' + (Get-Date -Format 's') + '] ' + $msg + [Environment]::NewLine
        [System.IO.File]::AppendAllText($logFileLP, $line, $utf8NoBom)
    }} catch {{}}
}}

function Remove-StageDir {{
    for ($try = 1; $try -le 8; $try++) {{
        try {{
            if ([System.IO.Directory]::Exists($stageLP)) {{
                [System.IO.Directory]::Delete($stageLP, $true)
            }}
            break
        }} catch {{
            Start-Sleep -Milliseconds 250
        }}
    }}
}}

Write-UpdateLog ('Updater started (PID ' + $PID + '): ' + $title)
try {{
    [System.IO.Directory]::CreateDirectory($logDirLP) | Out-Null
    [System.IO.File]::WriteAllText($lockFileLP, [string]$PID, $utf8NoBom)
}} catch {{}}

$changed = [System.Collections.Generic.List[string]]::new()
$appliedCount = 0
$failed = $false
$errMsg = ''

try {{
    [System.IO.Directory]::CreateDirectory($rollbackLP) | Out-Null
    {wait_pid_line}
    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $deadline) {{
        $stillRunning = $false
        foreach ($proc in @([System.Diagnostics.Process]::GetProcessesByName('YATMBLauncher'))) {{
            try {{
                $pPath = $proc.MainModule.FileName
                if ($pPath -and [String]::Equals([System.IO.Path]::GetFullPath($pPath), $targetLauncherFull, [StringComparison]::OrdinalIgnoreCase)) {{
                    $stillRunning = $true
                    break
                }}
            }} catch {{
                try {{
                    $cim = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $proc.Id) -ErrorAction SilentlyContinue
                    if ($cim -and $cim.ExecutablePath -and [String]::Equals([System.IO.Path]::GetFullPath($cim.ExecutablePath), $targetLauncherFull, [StringComparison]::OrdinalIgnoreCase)) {{
                        $stillRunning = $true
                        break
                    }}
                }} catch {{}}
            }} finally {{
                try {{ $proc.Dispose() }} catch {{}}
            }}
        }}
        if (-not $stillRunning) {{ break }}
        Start-Sleep -Milliseconds 200
    }}
    Start-Sleep -Milliseconds 200

    $prefixLen = $stageLP.Length + 1
    foreach ($src in [System.IO.Directory]::EnumerateFiles($stageLP, '*', [System.IO.SearchOption]::AllDirectories)) {{
        $rel = $src.Substring($prefixLen)
        if ($rel.StartsWith('_rollback\\', [System.StringComparison]::OrdinalIgnoreCase)) {{ continue }}
        $name = [System.IO.Path]::GetFileName($src)
        if ($name.EndsWith('.tmp') -or $name.EndsWith('.update-new') -or $name.Contains('.update-old')) {{ continue }}
        if (-not $rel.Contains('\\') -and $name.EndsWith('.zip', [System.StringComparison]::OrdinalIgnoreCase)) {{ continue }}

        $dst = $gameLP + '\\' + $rel
        $bak = $rollbackLP + '\\' + $rel
        $dstDir = [System.IO.Path]::GetDirectoryName($dst)
        $bakDir = [System.IO.Path]::GetDirectoryName($bak)
        if ($bakDir) {{ [System.IO.Directory]::CreateDirectory($bakDir) | Out-Null }}
        if ($dstDir) {{ [System.IO.Directory]::CreateDirectory($dstDir) | Out-Null }}

        $newFile = $dst + '.update-new'
        $backedUp = $false
        $tracked = $false
        for ($attempt = 1; $attempt -le 20; $attempt++) {{
            $oldFile = $dst + '.update-old'
            $movedOld = $false
            try {{
                if (-not $backedUp -and [System.IO.File]::Exists($dst)) {{
                    [System.IO.File]::Copy($dst, $bak, $true)
                    $backedUp = $true
                }}
                if (-not $tracked) {{
                    $changed.Add($rel)
                    $tracked = $true
                }}
                if ([System.IO.File]::Exists($newFile)) {{ [System.IO.File]::Delete($newFile) }}
                [System.IO.File]::Copy($src, $newFile, $true)
                if ([System.IO.File]::Exists($oldFile)) {{
                    try {{ [System.IO.File]::Delete($oldFile) }} catch {{ $oldFile = $dst + '.update-old-' + $attempt }}
                }}
                if ([System.IO.File]::Exists($dst)) {{
                    [System.IO.File]::Move($dst, $oldFile)
                    $movedOld = $true
                }}
                [System.IO.File]::Move($newFile, $dst)
                if ($movedOld -and [System.IO.File]::Exists($oldFile)) {{
                    try {{ [System.IO.File]::Delete($oldFile) }} catch {{}}
                }}
                break
            }} catch {{
                if ($movedOld -and -not [System.IO.File]::Exists($dst) -and [System.IO.File]::Exists($oldFile)) {{
                    try {{ [System.IO.File]::Move($oldFile, $dst) }} catch {{}}
                }}
                if ([System.IO.File]::Exists($newFile)) {{
                    try {{ [System.IO.File]::Delete($newFile) }} catch {{}}
                }}
                if ($attempt -ge 20) {{ throw }}
                Start-Sleep -Milliseconds 250
            }}
        }}
        $appliedCount++
    }}

    $elapsed = [Math]::Round(((Get-Date) - $tStart).TotalSeconds, 2)
    Write-UpdateLog ('Applied ' + $appliedCount + ' files cleanly in ' + $elapsed + 's.')
    try {{ if ([System.IO.File]::Exists($failFileLP)) {{ [System.IO.File]::Delete($failFileLP) }} }} catch {{}}
    try {{
        $doneJson = (@{{ title = $title; tag = $tag; applied = $appliedCount; ts = (Get-Date -Format 's') }} | ConvertTo-Json -Compress)
        [System.IO.File]::WriteAllText($doneFileLP, $doneJson, $utf8NoBom)
    }} catch {{}}
    Remove-StageDir
{restart_block}}} catch {{
    $failed = $true
    $errMsg = $_.Exception.Message
    Write-UpdateLog ('ERROR: ' + $errMsg + ' (rolling back ' + $changed.Count + ' files)')
    for ($i = $changed.Count - 1; $i -ge 0; $i--) {{
        $rel = $changed[$i]
        $dst = $gameLP + '\\' + $rel
        $bak = $rollbackLP + '\\' + $rel
        try {{
            if ([System.IO.File]::Exists($bak)) {{ [System.IO.File]::Copy($bak, $dst, $true) }}
            elseif ([System.IO.File]::Exists($dst)) {{ [System.IO.File]::Delete($dst) }}
        }} catch {{}}
        foreach ($suf in @('.update-new', '.update-old')) {{
            try {{ if ([System.IO.File]::Exists($dst + $suf)) {{ [System.IO.File]::Delete($dst + $suf) }} }} catch {{}}
        }}
    }}
    try {{
        $failJson = (@{{ title = $title; tag = $tag; error = $errMsg; ts = (Get-Date -Format 's') }} | ConvertTo-Json -Compress)
        [System.IO.File]::WriteAllText($failFileLP, $failJson, $utf8NoBom)
    }} catch {{}}
    Remove-StageDir
    {msg_err}}} finally {{
    try {{ if ([System.IO.File]::Exists($lockFileLP)) {{ [System.IO.File]::Delete($lockFileLP) }} }} catch {{}}
    if ($PSCommandPath -and [System.IO.File]::Exists($PSCommandPath)) {{
        try {{ [System.IO.File]::Delete($PSCommandPath) }} catch {{}}
    }}
}}
if ($failed) {{ exit 1 }}
"""


def find_icon_ico() -> Path | None:
    for p in (
        app_dir() / "yatmb.ico",
        app_dir() / "assets" / "yatmb.ico",
        app_dir() / "runtime" / "yatmb.ico",
        resource_base() / "assets" / "yatmb.ico",
        resource_base() / "yatmb.ico",
        app_dir().parent / "runtime" / "yatmb.ico",
    ):
        if p.is_file():
            return p
    return None


def find_icon_png() -> Path | None:
    for p in (
        app_dir() / "runtime" / "yatmb.png",
        resource_base() / "assets" / "yatmb.png",
        resource_base() / "yatmb.png",
        app_dir().parent / "runtime" / "yatmb.png",
    ):
        if p.is_file():
            return p
    return None


def find_book_png() -> Path | None:
    for p in (
        app_dir() / "runtime" / "yatmb_book.png",
        resource_base() / "assets" / "yatmb_book.png",
        resource_base() / "yatmb_book.png",
        app_dir().parent / "runtime" / "yatmb_book.png",
    ):
        if p.is_file():
            return p
    return None


def set_windows_app_id() -> None:
    if os.name == "nt":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SteelTemple.YATMB.Launcher")
        except Exception:
            pass


def _shorten_path(path: Path | str, max_len: int = 56) -> str:
    s = str(path)
    if len(s) <= max_len:
        return s
    parts = Path(s).parts
    if len(parts) >= 3:
        head = parts[0]
        tail = str(Path(*parts[-2:]))
        cand = f"{head}...\\{tail}" if os.name == "nt" else f"{head}.../{tail}"
        if len(cand) <= max_len:
            return cand
    keep = max(12, max_len - 4)
    return "..." + s[-keep:]


def parse_ini(path: Path | None) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path or not path.is_file():
        return values
    try:
        for raw in path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
            s = raw.strip()
            if not s or s.startswith(("#", ";", "[")) or "=" not in s:
                continue
            k, v = s.split("=", 1)
            values[k.strip().lower()] = v.split("#", 1)[0].split(";", 1)[0].strip()
    except OSError:
        pass
    return values


INI_SECTIONS: list[tuple[str, set[str]]] = [
    ("graphics", {"resolution", "aniso"}),
    (
        "display",
        {
            "fullscreen",
            "window_size",
            "output_res",
            "vk_present",
            "upscaler",
            "sharpness",
            "fg_mode",
            "perf_overlay",
            "color_preset",
        },
    ),
    ("frame rate", {"fps_limit"}),
    ("input", {"pad_layout", "stick_deadzone"}),
    ("audio", {"volume"}),
    ("language", {"lang", "menu_theme"}),
    ("performance", {"pipe_skip", "pipe_prebuild"}),
]


def save_ini_settings(path: Path, updates: dict[str, str]) -> None:
    path = Path(path)
    lines = path.read_text(encoding="utf-8-sig", errors="ignore").splitlines(keepends=True) if path.is_file() else []
    for key, value in updates.items():
        k_low = key.casefold()
        sec = next((s for s, keys in INI_SECTIONS if k_low in keys), "")
        replaced = False
        if not value:
            # Remove key when reset to automatic/unset so clean auto detection runs
            new_lines: list[str] = []
            for line in lines:
                s = line.strip()
                if not s.startswith(("#", ";", "[")) and "=" in line:
                    if line.split("=", 1)[0].strip().casefold() == k_low:
                        continue
                new_lines.append(line)
            lines = new_lines
            continue
        if sec:
            active = ""
            for i, line in enumerate(lines):
                s = line.strip()
                if s.startswith("[") and s.endswith("]"):
                    active = s[1:-1].casefold()
                    continue
                if active != sec or s.startswith(("#", ";")) or "=" not in line:
                    continue
                if line.split("=", 1)[0].strip().casefold() == k_low:
                    lines[i] = f"{key} = {value}\n"
                    replaced = True
                    break
            if not replaced:
                sec_idx = next(
                    (i for i, l in enumerate(lines) if l.strip().casefold() == f"[{sec}]"),
                    -1,
                )
                if sec_idx >= 0:
                    lines.insert(sec_idx + 1, f"{key} = {value}\n")
                else:
                    if lines and lines[-1].strip():
                        lines.append("\n")
                    lines.append(f"[{sec}]\n")
                    lines.append(f"{key} = {value}\n")
        else:
            for i, line in enumerate(lines):
                s = line.lstrip()
                if s.startswith(("#", ";", "[")) or "=" not in line:
                    continue
                if line.split("=", 1)[0].strip().casefold() == k_low:
                    lines[i] = f"{key} = {value}\n"
                    replaced = True
                    break
            if not replaced:
                lines.append(f"{key} = {value}\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".ini.tmp")
    tmp.write_text("".join(lines), encoding="utf-8")
    tmp.replace(path)


def clean_default_settings() -> dict[str, str]:
    """Safe, hardware-agnostic baseline defaults matching runtime/cfg.c."""
    return {
        "resolution": "original",
        "output_res": "1920x1080",
        "window_size": "1920x1080",
        "fullscreen": "0",
        "upscaler": "fsr",
        "sharpness": "80",
        "fg_mode": "off",
        "vk_present": "mailbox",
        "fps_limit": "60",
        "perf_overlay": "off",
        "aniso": "16",
        "color_preset": "default",
        "pad_layout": "auto",
        "stick_deadzone": "8",
        "volume": "100",
        "lang": "auto",
        "pipe_skip": "any",
        "pipe_prebuild": "1",
    }


def detect_gpu_name() -> str:
    if os.name != "nt":
        return "Vulkan Host GPU"
    try:
        r = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name | ConvertTo-Json -Compress",
            ],
            capture_output=True,
            text=True,
            timeout=6,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if r.returncode == 0 and r.stdout.strip():
            data = json.loads(r.stdout.strip())
            names = [data] if isinstance(data, str) else list(data)
            names = [n for n in names if n]
            if names:
                names.sort(key=lambda n: (not any(k in n.lower() for k in ("nvidia", "geforce", "amd", "radeon")), n))
                return names[0]
    except Exception:
        pass
    return "Vulkan GPU (Auto)"


def resolve_root_dir() -> Path:
    root = app_dir()
    if (root / "yatmb.exe").is_file() or (root / "tools" / "build_game.py").is_file():
        return root
    if (root.parent / "tools" / "build_game.py").is_file():
        return root.parent
    return root


def load_expected_yatmb(root: Path) -> dict[str, str]:
    return load_expected_yatmb_dump(root, resource_bases=[resource_base(), resource_base().parent])


def open_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]


def create_shortcut(game_dir: Path, name: str = "SteelTemple YATMB") -> tuple[bool, str]:
    if os.name != "nt":
        return False, "Windows shortcuts are only available on Windows."
    try:
        desktop = Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop"
        lnk = desktop / f"{name}.lnk"
        target = game_dir / ("YATMBLauncher.exe" if (game_dir / "YATMBLauncher.exe").is_file() else "yatmb.exe")
        ico = find_icon_ico() or target
        ps = (
            "$ws = New-Object -ComObject WScript.Shell; "
            f"$s = $ws.CreateShortcut('{str(lnk).replace(chr(39), chr(39)*2)}'); "
            f"$s.TargetPath = '{str(target).replace(chr(39), chr(39)*2)}'; "
            f"$s.WorkingDirectory = '{str(game_dir).replace(chr(39), chr(39)*2)}'; "
            f"$s.IconLocation = '{str(ico).replace(chr(39), chr(39)*2)},0'; "
            "$s.Description = 'Play Yoshi and the Mysterious Book PC (SteelTemple YATMB)'; "
            "$s.Save()"
        )
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if r.returncode == 0 and lnk.is_file():
            return True, str(lnk)
        return False, r.stderr.strip() or "Could not create desktop shortcut."
    except Exception as exc:
        return False, str(exc)


class YATMBLauncherApp(tk.Tk):
    def __init__(self, initial_tab: str = "play", shot_path: str = "", skip_update_check: bool = False) -> None:
        super().__init__()
        self.root_dir = resolve_root_dir()
        self.version = read_app_version()
        self.shot_path = shot_path
        self._skip_update_check = skip_update_check
        self.gpu_name = "Checking GPU..."

        self.title(f"{APP_TITLE} {self.version} — Yoshi and the Mysterious Book PC")
        self.geometry("1060x750")
        self.minsize(940, 690)
        self.configure(bg=C_BG)

        self._icon_photo = None
        self._hero_photo = None
        self._book_photo = None
        self._apply_window_icon()
        self._configure_ttk_styles()

        self.vars: dict[str, tk.StringVar] = {}
        defaults = clean_default_settings()
        for k, v in defaults.items():
            self.vars[k] = tk.StringVar(value=v)

        self.dump_root_var = tk.StringVar()
        self.exefs_var = tk.StringVar()
        self.romfs_var = tk.StringVar()
        self.shortcut_var = tk.BooleanVar(value=True)
        self.setup_status_var = tk.StringVar(value="Select your Yoshi and the Mysterious Book 1.0.2 ExeFS & RomFS folders to build yatmb.exe locally.")
        self.setup_running = False
        self.refresh_running = False
        self._last_refresh_error: str | None = None
        self._launch_after_refresh = False
        self._runtime_stamp_cache: tuple[tuple, str] | None = None
        self._last_nup_extract: tuple[Path, Path, Path] | None = None
        self.current_tab = initial_tab
        self.latest_release: dict | None = None
        self.release_check_active = False
        self.update_in_progress = False
        self._auto_installing = False
        self.auto_install_updates = True

        self._build_layout()
        self._load_ini_into_vars()
        self._refresh_status_cards()
        self.select_tab(initial_tab)
        self._recent_update_done = self._consume_update_done_marker()
        if self._recent_update_done:
            done_title = self._recent_update_done.get("title") or self.version
            self.update_status.config(text=f"Updated to {done_title} cleanly.", fg=C_OK)

        self._gpu_done = threading.Event()
        threading.Thread(target=self._probe_gpu_async, daemon=True).start()
        if self.shot_path:
            self._shot_deadline = time.monotonic() + 2.0
            self.after(250, self._wait_then_capture_shot)
        else:
            self.after(50, self._auto_refresh_existing_build)
            self.after(1500, lambda: threading.Thread(target=cleanup_stale_update_dirs, args=(self.root_dir,), daemon=True).start())
            if not getattr(self, "_skip_update_check", False):
                self.after(700, self.check_for_updates)

    def _apply_window_icon(self) -> None:
        ico = find_icon_ico()
        if ico and os.name == "nt":
            try:
                self.iconbitmap(default=str(ico))
            except Exception:
                pass
        png = find_icon_png() or ico
        if png and png.is_file():
            try:
                im = Image.open(png).convert("RGBA")
                self._icon_photo = ImageTk.PhotoImage(im.resize((48, 48), Image.Resampling.LANCZOS))
                self._hero_photo = ImageTk.PhotoImage(im.resize((72, 72), Image.Resampling.LANCZOS))
                self.iconphoto(True, self._icon_photo)
            except Exception:
                pass
        book = find_book_png()
        if book and book.is_file():
            try:
                bim = Image.open(book).convert("RGBA")
                self._book_photo = ImageTk.PhotoImage(bim.resize((82, 82), Image.Resampling.LANCZOS))
            except Exception:
                pass

    def _configure_ttk_styles(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("YATMB.TCombobox", fieldbackground=C_RAISED, background=C_RAISED, foreground=C_TEXT,
                        bordercolor=C_LINE, arrowcolor=C_NEON, selectbackground=C_RAISED_HOVER,
                        selectforeground=C_NEON, padding=5)
        style.map("YATMB.TCombobox", fieldbackground=[("readonly", C_RAISED)], foreground=[("readonly", C_TEXT)])
        style.configure("YATMB.Horizontal.TProgressbar", troughcolor=C_BG_DEEP, background=C_NEON,
                        bordercolor=C_LINE, lightcolor=C_NEON, darkcolor=C_NEON_DOWN, thickness=12)

    def _probe_gpu_async(self) -> None:
        try:
            name = detect_gpu_name()
            self.after(0, lambda: self._set_gpu_label(name))
        finally:
            self._gpu_done.set()

    def _wait_then_capture_shot(self) -> None:
        if not self._gpu_done.is_set() and time.monotonic() < getattr(self, "_shot_deadline", 0.0):
            self.after(100, self._wait_then_capture_shot)
            return
        self.after(120, self._capture_shot_and_exit)

    def _set_gpu_label(self, name: str) -> None:
        self.gpu_name = name
        if hasattr(self, "gpu_label"):
            self.gpu_label.configure(text=name)

    def _ini_path(self) -> Path:
        return self.root_dir / "yatmb.ini"

    def _exe_path(self) -> Path:
        return self.root_dir / ("yatmb.exe" if os.name == "nt" else "yatmb")

    def _mods_dir(self) -> Path:
        return self.root_dir / "mods"

    def _profile_dir(self) -> Path:
        return self.root_dir / "profile"

    def _logs_dir(self) -> Path:
        return self.root_dir / "logs"

    def _load_ini_into_vars(self) -> None:
        defaults = clean_default_settings()
        ini = parse_ini(self._ini_path())
        for k, d in defaults.items():
            val = ini.get(k, d)
            self.vars[k].set(val if val else d)

    def _build_layout(self) -> None:
        # Top Storybook Meadow banner
        banner = tk.Canvas(self, height=116, bg=C_BG_DEEP, highlightthickness=0)
        banner.pack(fill=tk.X, side=tk.TOP)
        self.banner = banner
        banner.bind("<Configure>", self._draw_banner)

        # Navigation strip
        nav = tk.Frame(self, bg=C_PANEL, height=46, highlightbackground=C_LINE, highlightthickness=1)
        nav.pack(fill=tk.X, side=tk.TOP)
        nav.pack_propagate(False)
        self.nav_buttons: dict[str, tk.Button] = {}
        tabs = [
            ("play", "PLAY"),
            ("setup", "SETUP FROM DUMP"),
            ("settings", "GRAPHICS & INPUT"),
            ("mods", "MODS & SAVES"),
        ]
        for key, label in tabs:
            btn = tk.Button(
                nav,
                text=label,
                command=lambda k=key: self.select_tab(k),
                font=("Segoe UI", 9, "bold"),
                bg=C_PANEL,
                fg=C_TEXT_SOFT,
                activebackground=C_RAISED_HOVER,
                activeforeground=C_NEON,
                bd=0,
                padx=18,
                pady=10,
                cursor="hand2",
            )
            btn.pack(side=tk.LEFT)
            self.nav_buttons[key] = btn

        self.profile_badge = tk.Label(
            nav,
            text="",
            font=("Segoe UI", 8, "bold"),
            bg=C_RAISED,
            fg=C_NEON,
            padx=10,
            pady=4,
        )
        self.profile_badge.pack(side=tk.RIGHT, padx=14, pady=9)

        # Footer strip — packed BEFORE body so it always stays pinned at the bottom of the window.
        foot = tk.Frame(self, bg=C_BG_DEEP, height=34)
        foot.pack(fill=tk.X, side=tk.BOTTOM)
        foot.pack_propagate(False)
        tk.Label(
            foot,
            text=f"SteelTemple YATMB  ·  {self.version}  ·  No copyrighted game assets included",
            font=("Segoe UI", 8),
            fg=C_TEXT_DIM,
            bg=C_BG_DEEP,
        ).pack(side=tk.LEFT, padx=16)
        tk.Label(
            foot,
            text=f"Folder: {_shorten_path(self.root_dir, 56)}",
            font=("Segoe UI", 8),
            fg=C_TEXT_DIM,
            bg=C_BG_DEEP,
        ).pack(side=tk.RIGHT, padx=16)

        # Content container
        self.body = tk.Frame(self, bg=C_BG)
        self.body.pack(fill=tk.BOTH, expand=True, padx=22, pady=14)

        self.pages: dict[str, tk.Frame] = {
            "play": self._build_play_page(),
            "setup": self._build_setup_page(),
            "settings": self._build_settings_page(),
            "mods": self._build_mods_page(),
        }

    def _draw_banner(self, _event=None) -> None:
        c = self.banner
        c.delete("all")
        w = max(900, c.winfo_width())
        h = c.winfo_height()
        # Sunlit emerald-forest gradient bands
        top, bot = (24, 58, 34), (8, 20, 12)
        bands = 12
        for i in range(bands):
            t = i / (bands - 1)
            col = "#%02X%02X%02X" % tuple(int(top[k] + (bot[k] - top[k]) * t) for k in range(3))
            c.create_rectangle(0, h * i / bands, w, h * (i + 1) / bands + 1, fill=col, outline="")
        # Soft rolling storybook meadow hill curves on the right
        c.create_oval(w - 360, h - 46, w + 40, h + 150, fill="#14321E", outline="")
        c.create_oval(w - 220, h - 32, w + 120, h + 130, fill="#193D24", outline="")
        # Four-point golden storybook stars scattered softly across the right half
        def _star(cx: float, cy: float, r: float, col: str) -> None:
            pts = []
            for k in range(8):
                ang = k * math.pi / 4.0
                rad = r if k % 2 == 0 else r * 0.28
                pts.extend([cx + math.cos(ang) * rad, cy + math.sin(ang) * rad])
            c.create_polygon(*pts, fill=col, outline="")

        for sx, sy, sr, scol in (
            (w - 295, 28, 7, C_CYAN),
            (w - 235, 76, 5, C_NEON),
            (w - 190, 24, 5, C_CYAN),
            (w - 42, 26, 6, C_CYAN),
            (w - 36, 82, 4, C_NEON),
        ):
            _star(sx, sy, sr, scol)
        # Golden storybook trim line at bottom edge (leaf green into warm gold)
        c.create_line(0, h - 2, w * 0.55, h - 2, fill=C_NEON, width=3)
        c.create_line(w * 0.55, h - 2, w, h - 2, fill=C_CYAN, width=3)

        # Open storybook + spotted egg emblem on the right
        bx, by = w - 110, 58
        if self._book_photo is not None:
            c.create_oval(bx - 38, by + 32, bx + 38, by + 44, fill="#051109", outline="")
            c.create_image(bx, by, image=self._book_photo)

        x_text = 26
        if self._hero_photo is not None:
            c.create_image(62, 58, image=self._hero_photo)
            x_text = 116
        c.create_text(x_text, 38, anchor="w", text=APP_TITLE, font=("Segoe UI", 22, "bold"), fill=C_TEXT)
        c.create_text(
            x_text + 2,
            70,
            anchor="w",
            text=f"{APP_SUBTITLE}  ·  {self.version}",
            font=("Segoe UI", 10),
            fill=C_CYAN,
        )

    def select_tab(self, key: str) -> None:
        self.current_tab = key
        for k, page in self.pages.items():
            if k == key:
                page.pack(fill=tk.BOTH, expand=True)
            else:
                page.pack_forget()
        for k, btn in self.nav_buttons.items():
            if k == key:
                btn.configure(bg=C_RAISED_HOVER, fg=C_NEON)
            else:
                btn.configure(bg=C_PANEL, fg=C_TEXT_SOFT)

    def _card(self, parent: tk.Misc, title: str, padx: int = 16, pady: int = 14) -> tk.Frame:
        outer = tk.Frame(parent, bg=C_PANEL, highlightbackground=C_LINE, highlightthickness=1, padx=padx, pady=pady)
        if title:
            tk.Label(outer, text=title, font=("Segoe UI", 10, "bold"), fg=C_NEON, bg=C_PANEL).pack(anchor="w", pady=(0, 8))
        return outer

    def _accent_btn(self, parent: tk.Misc, text: str, cmd, width: int = 18) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=cmd,
            font=("Segoe UI", 10, "bold"),
            bg=C_NEON,
            fg=C_NEON_TEXT,
            activebackground=C_NEON_HOVER,
            activeforeground=C_NEON_TEXT,
            bd=0,
            padx=16,
            pady=9,
            width=width,
            cursor="hand2",
        )

    def _plain_btn(self, parent: tk.Misc, text: str, cmd, width: int = 16) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=cmd,
            font=("Segoe UI", 9, "bold"),
            bg=C_RAISED,
            fg=C_TEXT,
            activebackground=C_RAISED_HOVER,
            activeforeground=C_NEON,
            bd=0,
            padx=14,
            pady=8,
            width=width,
            cursor="hand2",
        )

    def _build_play_page(self) -> tk.Frame:
        page = tk.Frame(self.body, bg=C_BG)

        top = self._card(page, "STORYBOOK READINESS")
        top.pack(fill=tk.X, pady=(0, 12))
        self.build_state_lbl = tk.Label(top, text="", font=("Segoe UI", 11, "bold"), fg=C_TEXT, bg=C_PANEL)
        self.build_state_lbl.pack(anchor="w")
        self.build_hint_lbl = tk.Label(top, text="", font=("Segoe UI", 9), fg=C_TEXT_SOFT, bg=C_PANEL, wraplength=880, justify="left")
        self.build_hint_lbl.pack(anchor="w", pady=(4, 10))

        cta_row = tk.Frame(top, bg=C_PANEL)
        cta_row.pack(fill=tk.X)
        self.play_btn = self._accent_btn(cta_row, "PLAY YOSHI PC", self.launch_game, width=26)
        self.play_btn.pack(side=tk.LEFT)
        self.goto_setup_btn = self._plain_btn(cta_row, "OPEN DUMP SETUP", lambda: self.select_tab("setup"), width=20)
        self.goto_setup_btn.pack(side=tk.LEFT, padx=(10, 0))
        self._plain_btn(cta_row, "CREATE DESKTOP SHORTCUT", self.on_create_shortcut, width=24).pack(side=tk.RIGHT)

        upd = tk.Frame(top, bg=C_PANEL)
        upd.pack(fill=tk.X, pady=(12, 0))
        self.update_status = tk.Label(
            upd,
            text="Checking GitHub Releases…",
            font=("Segoe UI", 9),
            fg=C_TEXT_DIM,
            bg=C_PANEL,
            wraplength=880,
            justify="left",
        )
        self.update_status.pack(anchor="w")
        btn_row = tk.Frame(upd, bg=C_PANEL)
        btn_row.pack(fill=tk.X, pady=(6, 0))
        self.update_action_btn = self._accent_btn(btn_row, "INSTALL UPDATE", self.apply_latest_update, width=18)
        self.release_btn = self._plain_btn(btn_row, "VIEW RELEASE NOTES", self.open_latest_release, width=20)
        self._plain_btn(btn_row, "CHECK FOR UPDATES", self.check_for_updates, width=18).pack(side=tk.LEFT)
        # Hidden until an update is available / notes needed
        self.update_action_btn.pack_forget()
        self.release_btn.pack_forget()

        grid = tk.Frame(page, bg=C_BG)
        grid.pack(fill=tk.BOTH, expand=True)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        c1 = self._card(grid, "ACTIVE HARDWARE & PROFILE")
        c1.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        self._kv_row(c1, "Graphics Adapter", self.gpu_name, attr="gpu_label")
        self._kv_row(c1, "Config File", "", attr="ini_state_label")
        self._kv_row(c1, "Internal Resolution", "", attr="res_summary_label")
        self._kv_row(c1, "Display / Upscaler", "", attr="upscaler_summary_label")
        self._kv_row(c1, "Frame Generation", "", attr="fg_summary_label")

        c2 = self._card(grid, "CLEAN CLIENT DEFAULTS")
        c2.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        notes = [
            ("Zero-Config Baseline", "Starts cleanly at 1920x1080 Windowed, Original internal, Storybook Meadow F1 menu, Aniso 16x, Frame Gen Off, 60 FPS."),
            ("Native 720p–4K & Locked 60 FPS", "Supports Original, 720p, 900p, 1080p, 1440p, and native 4K (2160p) with linear UI scaling. Pick it here or in-game (F1)."),
            ("No Personal Settings Bundled", "Your yatmb.ini and saves stay strictly local on your PC; updates never overwrite them."),
            ("Controls", "Supports Xbox, DualSense, Nintendo Switch / Switch 2 Pro controllers, plus Keyboard."),
        ]
        for head, body in notes:
            tk.Label(c2, text=head, font=("Segoe UI", 9, "bold"), fg=C_TEXT, bg=C_PANEL).pack(anchor="w", pady=(1, 0))
            tk.Label(c2, text=body, font=("Segoe UI", 8), fg=C_TEXT_DIM, bg=C_PANEL, wraplength=430, justify="left").pack(anchor="w", pady=(1, 4))

        return page

    def _kv_row(self, parent: tk.Misc, key: str, value: str, attr: str) -> None:
        row = tk.Frame(parent, bg=C_PANEL)
        row.pack(fill=tk.X, pady=4)
        tk.Label(row, text=key, font=("Segoe UI", 9), fg=C_TEXT_DIM, bg=C_PANEL).pack(side=tk.LEFT)
        lbl = tk.Label(row, text=value, font=("Segoe UI", 9, "bold"), fg=C_TEXT, bg=C_PANEL)
        lbl.pack(side=tk.RIGHT)
        setattr(self, attr, lbl)

    def _build_setup_page(self) -> tk.Frame:
        page = tk.Frame(self.body, bg=C_BG)

        card = self._card(page, "ONE-STEP SETUP FROM YOUR YOSHI AND THE MYSTERIOUS BOOK 1.0.2 DUMP")
        card.pack(fill=tk.X, pady=(0, 12))
        tk.Label(
            card,
            text="No copyrighted game data is shipped with SteelTemple YATMB. Select your dumped Switch 2 ExeFS and RomFS folders, "
            "a NUP-extracted dump tree (update alone or base + updates\\<ver>), or a .nup container. Setup verifies Yoshi and the Mysterious Book 1.0.2 "
            "SHA-256 hashes, packs RomFS, lifts ARM64 modules, compiles yatmb.exe locally, then pre-warms every shader so the first launch runs smoothly.",
            font=("Segoe UI", 9),
            fg=C_TEXT_SOFT,
            bg=C_PANEL,
            wraplength=920,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        dump_row = tk.Frame(card, bg=C_PANEL)
        dump_row.pack(fill=tk.X, pady=3)
        tk.Label(
            dump_row,
            text="Dump Folder / .NUP (auto-detect):",
            width=38,
            anchor="w",
            font=("Segoe UI", 9),
            fg=C_TEXT_DIM,
            bg=C_PANEL,
        ).pack(side=tk.LEFT)
        tk.Entry(
            dump_row,
            textvariable=self.dump_root_var,
            bg=C_BG_DEEP,
            fg=C_TEXT,
            insertbackground=C_NEON,
            relief=tk.FLAT,
            font=("Segoe UI", 9),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8), ipady=5)
        self.folder_btn = self._plain_btn(dump_row, "Folder...", self._pick_dump_root, width=9)
        self.folder_btn.pack(side=tk.RIGHT, padx=(4, 0))
        self.nup_btn = self._plain_btn(dump_row, ".NUP...", self._pick_nup_file, width=8)
        self.nup_btn.pack(side=tk.RIGHT)
        self.exefs_browse_btn = self._path_picker(card, "ExeFS Folder (all seven files, main … subsdk2):", self.exefs_var, self._pick_exefs)
        self.romfs_browse_btn = self._path_picker(card, "RomFS Folder (raw dump or romfs_packed):", self.romfs_var, self._pick_romfs)

        opt_row = tk.Frame(card, bg=C_PANEL)
        opt_row.pack(fill=tk.X, pady=(8, 6))
        tk.Checkbutton(
            opt_row,
            text="Create 'SteelTemple YATMB' Desktop shortcut after build",
            variable=self.shortcut_var,
            bg=C_PANEL,
            fg=C_TEXT,
            activebackground=C_PANEL,
            activeforeground=C_NEON,
            selectcolor=C_BG_DEEP,
            font=("Segoe UI", 9),
        ).pack(side=tk.LEFT)
        self.build_btn = self._accent_btn(opt_row, "VERIFY & BUILD YATMB.EXE", self.start_dump_setup, width=24)
        self.build_btn.pack(side=tk.RIGHT)

        prog_card = self._card(page, "BUILD PROGRESS & LOG")
        prog_card.pack(fill=tk.BOTH, expand=True)
        tk.Label(prog_card, textvariable=self.setup_status_var, font=("Segoe UI", 9, "bold"), fg=C_TEXT, bg=C_PANEL).pack(anchor="w", pady=(0, 6))
        self.setup_prog = ttk.Progressbar(prog_card, style="YATMB.Horizontal.TProgressbar", maximum=100, value=0)
        self.setup_prog.pack(fill=tk.X, pady=(0, 8))
        self.setup_log = tk.Text(
            prog_card,
            height=11,
            bg=C_BG_DEEP,
            fg=C_TEXT_SOFT,
            insertbackground=C_NEON,
            relief=tk.FLAT,
            font=("Consolas", 9),
        )
        self.setup_log.pack(fill=tk.BOTH, expand=True)
        return page

    def _path_picker(self, parent: tk.Misc, label: str, var: tk.StringVar, cmd) -> tk.Button:
        row = tk.Frame(parent, bg=C_PANEL)
        row.pack(fill=tk.X, pady=3)
        tk.Label(row, text=label, width=38, anchor="w", font=("Segoe UI", 9), fg=C_TEXT_DIM, bg=C_PANEL).pack(side=tk.LEFT)
        tk.Entry(row, textvariable=var, bg=C_BG_DEEP, fg=C_TEXT, insertbackground=C_NEON, relief=tk.FLAT,
                 font=("Segoe UI", 9)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8), ipady=5)
        btn = self._plain_btn(row, "Browse...", cmd, width=10)
        btn.pack(side=tk.RIGHT)
        return btn

    def _set_setup_busy(self, busy: bool) -> None:
        self.setup_running = busy
        state = tk.DISABLED if busy else tk.NORMAL
        for attr in ("folder_btn", "nup_btn", "exefs_browse_btn", "romfs_browse_btn", "build_btn"):
            btn = getattr(self, attr, None)
            if btn is not None:
                btn.configure(state=state)

    def _apply_dump_resolve(self, resolved, *, log: bool = True, update_status: bool = True) -> None:
        self.exefs_var.set(str(resolved.exefs))
        self.romfs_var.set(str(resolved.romfs))
        if log:
            for note in resolved.notes:
                self._log_setup(note)
        if update_status:
            self.setup_status_var.set("Dump paths resolved. Click VERIFY & BUILD YATMB.EXE when ready.")

    def _pick_dump_root(self) -> None:
        if self.setup_running:
            return
        d = filedialog.askdirectory(title="Select Yoshi and the Mysterious Book Dump Root / NUP-extracted Folder")
        if not d:
            return
        self.dump_root_var.set(d)
        try:
            work = self.root_dir / "work" / "dump-resolve"
            work.mkdir(parents=True, exist_ok=True)
            resolved = discover_dump(Path(d), work)
            self.setup_log.delete("1.0", tk.END)
            self._apply_dump_resolve(resolved)
        except DumpError as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Could not auto-detect dump folders:\n{exc}", parent=self)

    def _resolve_or_extract_nup(
        self,
        nup: Path,
        *,
        exefs_hint: str = "",
        pct_lo: int = 2,
        pct_hi: int = 99,
    ):
        nup_out = self.root_dir / "work" / "nup-extract"
        resolved = reuse_extracted_nup(nup, nup_out)
        if resolved is None and exefs_hint:
            cand_parent = Path(exefs_hint).parent
            if cand_parent.name.startswith("nup-extract"):
                resolved = reuse_extracted_nup(nup, cand_parent)
        if resolved is not None:
            self.after(0, lambda: self._log_setup("Reusing extracted NUP tree (no re-extract needed)."))
            return resolved

        self.after(
            0,
            lambda name=nup.name: self.setup_status_var.set(
                f"Extracting {name} (base+update if present, else update alone)…"
            ),
        )

        def on_progress(line: str, pct: int | None) -> None:
            def _ui() -> None:
                self._log_setup(line)
                if pct is not None:
                    p = pct_lo + int((pct_hi - pct_lo) * max(0, min(100, pct)) / 100)
                    self.setup_prog.configure(value=p)
                    self.setup_status_var.set(f"Extracting {nup.name}… {pct}%")

            self.after(0, _ui)

        script = find_extract_nup(self.root_dir, resource_bases=[resource_base(), resource_base().parent])
        return extract_nup_overlay(
            nup,
            nup_out,
            python=self._find_setup_python(),
            extract_script=script,
            root=self.root_dir,
            on_progress=on_progress,
        )

    def _pick_nup_file(self) -> None:
        if self.setup_running:
            return
        path = filedialog.askopenfilename(
            title="Select Yoshi and the Mysterious Book .NUP Container",
            filetypes=[("NX Package (NUP)", "*.nup"), ("All files", "*.*")],
        )
        if not path:
            return
        nup = Path(path)
        self.dump_root_var.set(str(nup))
        self.setup_log.delete("1.0", tk.END)
        self._set_setup_busy(True)
        self.setup_prog.configure(value=2)
        self.setup_status_var.set(f"Extracting {nup.name} (base+update if present, else update alone)…")
        self.update_idletasks()

        def worker() -> None:
            try:
                resolved = self._resolve_or_extract_nup(nup, pct_lo=2, pct_hi=99)
                self._last_nup_extract = (nup.resolve(), resolved.exefs.resolve(), resolved.romfs.resolve())
                self.after(
                    0,
                    lambda r=resolved: (
                        self.setup_prog.configure(value=100),
                        self._apply_dump_resolve(r),
                    ),
                )
            except Exception as exc:
                err = str(exc)
                self.after(
                    0,
                    lambda e=err: (
                        self.setup_prog.configure(value=0),
                        self.setup_status_var.set(f"NUP extract failed: {e}"),
                        self._log_setup(f"ERROR: {e}"),
                        messagebox.showerror(APP_TITLE, e, parent=self),
                    ),
                )
            finally:
                self.after(0, lambda: self._set_setup_busy(False))

        threading.Thread(target=worker, daemon=True).start()

    def _pick_exefs(self) -> None:
        if self.setup_running:
            return
        d = filedialog.askdirectory(title="Select ExeFS Folder (main, main.npdm, rtld, sdk)")
        if d:
            self.exefs_var.set(d)

    def _pick_romfs(self) -> None:
        if self.setup_running:
            return
        d = filedialog.askdirectory(title="Select RomFS or Packed RomFS Folder")
        if d:
            self.romfs_var.set(d)

    def _build_settings_page(self) -> tk.Frame:
        page = tk.Frame(self.body, bg=C_BG)

        cols = tk.Frame(page, bg=C_BG)
        cols.pack(fill=tk.BOTH, expand=True)
        cols.columnconfigure(0, weight=1)
        cols.columnconfigure(1, weight=1)

        left = self._card(cols, "DISPLAY & RESOLUTION")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        self._combo_row(left, "Internal Resolution", "resolution", ["original", "720", "900", "1080", "1440", "2160"],
                        hint="original = console tier. 1080 / 1440 / 2160 (4K) lock native UE5 resolution with crisp UI scaling.")
        self._combo_row(left, "Output / Window Size", "output_res",
                        ["1280x720", "1600x900", "1920x1080", "2560x1440", "3840x2160"])
        self._combo_row(left, "Window Mode", "fullscreen", ["0", "1"], hint="0 = Windowed, 1 = Fullscreen")
        self._combo_row(left, "Upscaler", "upscaler", ["fsr", "bilinear", "off", "smrs"])
        self._combo_row(left, "FSR Sharpness (0-100)", "sharpness", ["0", "40", "60", "80", "90", "100"])
        self._combo_row(left, "V-Sync / Present", "vk_present", ["mailbox", "fifo", "immediate"])

        right = self._card(cols, "PERFORMANCE, COLOR & INPUT")
        right.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        self._combo_row(right, "Frame Generation", "fg_mode", ["off", "msm_fg", "fsr3_fg", "xefg"])
        self._combo_row(right, "FPS Limit", "fps_limit", ["60", "120", "144", "30"])
        self._combo_row(right, "Color Preset", "color_preset", ["default", "vivid", "clarity"])
        self._combo_row(right, "Perf Overlay", "perf_overlay", ["off", "fps", "full"])
        self._combo_row(right, "Anisotropic Filtering", "aniso", ["game", "2", "4", "8", "16"])
        self._combo_row(right, "Controller Button Layout", "pad_layout", ["auto", "nintendo", "xbox", "xbox_prompts"])
        self._combo_row(
            right,
            "Game Language",
            "lang",
            ["auto", "en-US", "en-GB", "ja", "fr", "fr-CA", "de", "it", "es", "es-419", "nl", "pt-BR", "ko", "zh-Hans", "zh-Hant"],
            hint="auto = Windows locale (Russian -> en-US, Portuguese -> pt-BR).",
        )

        bar = tk.Frame(page, bg=C_PANEL, highlightbackground=C_LINE, highlightthickness=1, padx=16, pady=12)
        bar.pack(fill=tk.X, pady=(12, 0))
        self._plain_btn(bar, "RESET TO DEFAULT PROFILE", self.on_reset_defaults, width=25).pack(side=tk.LEFT)
        self._accent_btn(bar, "SAVE SETTINGS", self.on_save_settings, width=18).pack(side=tk.RIGHT)
        self._plain_btn(bar, "RELOAD", self._reload_settings_ui, width=12).pack(side=tk.RIGHT, padx=(0, 10))
        return page

    def _combo_row(self, parent: tk.Misc, label: str, key: str, values: list[str], hint: str = "") -> None:
        wrap = tk.Frame(parent, bg=C_PANEL)
        wrap.pack(fill=tk.X, pady=4)
        top = tk.Frame(wrap, bg=C_PANEL)
        top.pack(fill=tk.X)
        tk.Label(top, text=label, font=("Segoe UI", 9, "bold"), fg=C_TEXT, bg=C_PANEL).pack(side=tk.LEFT)
        cb = ttk.Combobox(top, textvariable=self.vars[key], values=values, state="readonly", style="YATMB.TCombobox", width=18)
        cb.pack(side=tk.RIGHT)
        if hint:
            tk.Label(wrap, text=hint, font=("Segoe UI", 8), fg=C_TEXT_DIM, bg=C_PANEL,
                     wraplength=420, justify="left").pack(anchor="w")

    def _build_mods_page(self) -> tk.Frame:
        page = tk.Frame(self.body, bg=C_BG)

        c_top = self._card(page, "GAME & DATA FOLDERS")
        c_top.pack(fill=tk.X, pady=(0, 12))
        row = tk.Frame(c_top, bg=C_PANEL)
        row.pack(fill=tk.X)
        self._plain_btn(row, "Game Folder", lambda: open_folder(self.root_dir), width=16).pack(side=tk.LEFT)
        self._plain_btn(row, "Saves / Profile", lambda: open_folder(self._profile_dir()), width=16).pack(side=tk.LEFT, padx=8)
        self._plain_btn(row, "Mods Folder", lambda: open_folder(self._mods_dir()), width=16).pack(side=tk.LEFT)
        self._plain_btn(row, "Logs Folder", lambda: open_folder(self._logs_dir()), width=16).pack(side=tk.LEFT, padx=8)

        c_bak = self._card(page, "SAVE BACKUP VAULT")
        c_bak.pack(fill=tk.BOTH, expand=True)
        tk.Label(
            c_bak,
            text="Create a timestamped snapshot of your profile/save folder before installing updates or testing mods.",
            font=("Segoe UI", 9),
            fg=C_TEXT_SOFT,
            bg=C_PANEL,
        ).pack(anchor="w", pady=(0, 8))
        self.bak_list = tk.Listbox(c_bak, bg=C_BG_DEEP, fg=C_TEXT, selectbackground=C_RAISED_HOVER,
                                   selectforeground=C_NEON, highlightthickness=1, highlightbackground=C_LINE,
                                   font=("Consolas", 9), activestyle="none")
        self.bak_list.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        brow = tk.Frame(c_bak, bg=C_PANEL)
        brow.pack(fill=tk.X)
        self._accent_btn(brow, "CREATE SAVE SNAPSHOT", self.on_create_backup, width=22).pack(side=tk.LEFT)
        self._plain_btn(brow, "REFRESH LIST", self._refresh_backups, width=14).pack(side=tk.RIGHT)
        self._refresh_backups()
        return page

    def _refresh_backups(self) -> None:
        self.bak_list.delete(0, tk.END)
        bdir = self._profile_dir() / "backups"
        if bdir.is_dir():
            snaps = sorted((p.name for p in bdir.iterdir() if p.is_dir()), reverse=True)
            for s in snaps:
                self.bak_list.insert(tk.END, s)
        if self.bak_list.size() == 0:
            self.bak_list.insert(tk.END, "No save snapshots yet.")

    def on_create_backup(self) -> None:
        save_dir = self._profile_dir() / "save"
        if not save_dir.is_dir() or not any(save_dir.iterdir()):
            messagebox.showinfo(APP_TITLE, "No save data found yet under profile/save.", parent=self)
            return
        stamp = datetime.now().strftime("save_%Y%m%d_%H%M%S")
        dst = self._profile_dir() / "backups" / stamp
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(save_dir, dst)
        self._refresh_backups()
        messagebox.showinfo(APP_TITLE, f"Created save backup:\n{dst}", parent=self)

    def _set_play_btn(self, text: str, enabled: bool) -> None:
        if enabled:
            self.play_btn.configure(
                text=text,
                state=tk.NORMAL,
                bg=C_NEON,
                fg=C_NEON_TEXT,
                activebackground=C_NEON_HOVER,
                activeforeground=C_NEON_TEXT,
                cursor="hand2",
            )
        else:
            self.play_btn.configure(
                text=text,
                state=tk.DISABLED,
                bg=C_RAISED,
                fg=C_TEXT_DIM,
                disabledforeground=C_TEXT_DIM,
                cursor="arrow",
            )

    def _refresh_status_cards(self) -> None:
        exe = self._exe_path()
        ready = exe.is_file()
        ini_exists = self._ini_path().is_file()

        if self.refresh_running:
            self.build_state_lbl.configure(text=f"Updating yatmb.exe for {self.version}…", fg=C_WARN)
            self.build_hint_lbl.configure(
                text="Relinking yatmb.exe with the updated runtime (usually 10–20 seconds). PLAY will unlock automatically.",
                fg=C_TEXT_SOFT,
            )
            self._set_play_btn("UPDATING yatmb.exe…", False)
        elif ready:
            stale, reason, refresh_args = self._stale_build_status()
            if self._last_refresh_error:
                first_line = self._last_refresh_error.splitlines()[0][:140]
                self.build_state_lbl.configure(text=f"yatmb.exe Update Failed ({self.version})", fg=C_BAD)
                self.build_hint_lbl.configure(
                    text=f"{first_line} — See logs\\refresh.log, or click RETRY UPDATE & PLAY.",
                    fg=C_BAD,
                )
                self._set_play_btn("RETRY UPDATE & PLAY", True)
            elif stale and refresh_args is not None:
                self.build_state_lbl.configure(text=f"Update Required  (relinking yatmb.exe for {self.version})", fg=C_WARN)
                self.build_hint_lbl.configure(
                    text=f"Installed yatmb.exe is from an older runtime. Click UPDATE & PLAY (or wait a moment) to apply {self.version}.",
                    fg=C_WARN,
                )
                self._set_play_btn("UPDATE & PLAY", True)
            elif stale:
                self.build_state_lbl.configure(text=f"Outdated yatmb.exe  (rebuild needed for {self.version})", fg=C_WARN)
                self.build_hint_lbl.configure(
                    text=f"Installed yatmb.exe does not match {self.version} ({reason}). Open SETUP FROM DUMP to rebuild yatmb.exe.",
                    fg=C_WARN,
                )
                self._set_play_btn("PLAY (OUTDATED yatmb.exe)", True)
            else:
                self.build_state_lbl.configure(text=f"Ready to Play  (yatmb.exe · {self.version})", fg=C_OK)
                self.build_hint_lbl.configure(
                    text=f"Executable: {exe}. Press PLAY below to launch Yoshi and the Mysterious Book natively.",
                    fg=C_TEXT_SOFT,
                )
                self._set_play_btn("PLAY YOSHI PC", True)
        else:
            self.build_state_lbl.configure(text="Setup Required  (no game files included)", fg=C_WARN)
            self.build_hint_lbl.configure(
                text="Open SETUP FROM DUMP to point SteelTemple YATMB at your dumped Yoshi and the Mysterious Book 1.0.2 ExeFS & RomFS folders.",
                fg=C_TEXT_SOFT,
            )
            self._set_play_btn("PLAY YOSHI PC", False)

        if ini_exists:
            self.profile_badge.configure(text="CUSTOM yatmb.ini ACTIVE")
            self.ini_state_label.configure(text="yatmb.ini (custom)", fg=C_NEON)
        else:
            self.profile_badge.configure(text="DEFAULT PROFILE ACTIVE")
            self.ini_state_label.configure(text="Clean Defaults (no yatmb.ini)", fg=C_OK)

        self.res_summary_label.configure(text=self.vars["resolution"].get())
        self.upscaler_summary_label.configure(text=f"{self.vars['output_res'].get()} · {self.vars['upscaler'].get().upper()}")
        fg_val = self.vars["fg_mode"].get()
        self.fg_summary_label.configure(text=fg_val)

    def _reload_settings_ui(self) -> None:
        self._load_ini_into_vars()
        self._refresh_status_cards()

    def on_save_settings(self) -> None:
        updates = {k: self.vars[k].get().strip() for k in clean_default_settings()}
        if updates.get("lang", "").casefold() == "auto":
            updates["lang"] = ""
        if updates["resolution"] == "original":
            # Ensure output window size also stays synchronized if left untouched
            updates["window_size"] = updates["output_res"]
        else:
            updates["window_size"] = updates["output_res"]
        save_ini_settings(self._ini_path(), updates)
        self._refresh_status_cards()
        messagebox.showinfo(APP_TITLE, f"Saved settings to {self._ini_path().name}.", parent=self)

    def on_reset_defaults(self) -> None:
        if self._ini_path().is_file():
            try:
                self._ini_path().unlink()
            except OSError as exc:
                messagebox.showerror(APP_TITLE, f"Could not delete yatmb.ini: {exc}", parent=self)
                return
        self._load_ini_into_vars()
        self._refresh_status_cards()
        messagebox.showinfo(
            APP_TITLE,
            "Restored the clean Zero-Config Default Profile (removed custom yatmb.ini).",
            parent=self,
        )

    def on_create_shortcut(self) -> None:
        ok, info = create_shortcut(self.root_dir)
        if ok:
            messagebox.showinfo(APP_TITLE, f"Created Desktop shortcut:\n{info}", parent=self)
        else:
            messagebox.showwarning(APP_TITLE, info, parent=self)

    def launch_game(self) -> None:
        exe = self._exe_path()
        if not exe.is_file():
            self.select_tab("setup")
            return
        if self.refresh_running:
            messagebox.showinfo(
                APP_TITLE,
                f"Updating yatmb.exe for {self.version} is still in progress.\nPlease wait a moment until it finishes.",
                parent=self,
            )
            return
        stale, reason, refresh_args = self._stale_build_status()
        if stale:
            if refresh_args is not None:
                self._auto_refresh_existing_build(launch_after=True)
                return
            if messagebox.askyesno(
                f"{APP_TITLE} — Outdated yatmb.exe",
                f"Your yatmb.exe was built with an older runtime than {self.version} ({reason}), "
                "so the latest fixes are not inside yatmb.exe yet.\n\n"
                "Open SETUP FROM DUMP to rebuild yatmb.exe now? (Click No to launch the older yatmb.exe anyway.)",
                parent=self,
            ):
                self.select_tab("setup")
                return
        try:
            subprocess.Popen([str(exe)], cwd=str(self.root_dir))
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"Failed to start {exe.name}:\n{exc}", parent=self)

    def _log_setup(self, msg: str) -> None:
        self.setup_log.insert(tk.END, msg.rstrip() + "\n")
        self.setup_log.see(tk.END)

    def start_dump_setup(self) -> None:
        if self.setup_running:
            return
        dump_root = self.dump_root_var.get().strip()
        exefs_txt = self.exefs_var.get().strip()
        romfs_txt = self.romfs_var.get().strip()

        has_root = bool(dump_root and Path(dump_root).exists())
        has_pair = bool(exefs_txt and romfs_txt and Path(exefs_txt).is_dir() and Path(romfs_txt).is_dir())
        if not has_root and not has_pair:
            messagebox.showwarning(
                APP_TITLE,
                "Please select a dump folder / .nup, or both ExeFS and RomFS folders first.",
                parent=self,
            )
            return

        self.setup_log.delete("1.0", tk.END)
        self._set_setup_busy(True)
        self.setup_prog.configure(value=2)
        self.setup_status_var.set("Resolving Yoshi and the Mysterious Book 1.0.2 dump...")
        threading.Thread(
            target=self._run_setup_worker,
            args=(dump_root, exefs_txt, romfs_txt),
            daemon=True,
        ).start()

    def _find_setup_python(self) -> Path:
        for cand in (
            self.root_dir / "python" / "python.exe",
            self.root_dir / "setup" / "python" / "python.exe",
            self.root_dir / ".venv" / "Scripts" / "python.exe",
        ):
            if cand.is_file():
                return cand
        return Path(sys.executable)

    def _run_step(self, cmd: list[str], env: dict[str, str], pct_start: int, pct_end: int) -> None:
        self.after(0, lambda: self._log_setup("+ " + " ".join(cmd)))
        proc = subprocess.Popen(
            cmd,
            cwd=str(self.root_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        assert proc.stdout is not None
        lines = 0
        for line in proc.stdout:
            lines += 1
            text = line.rstrip()
            prog = min(pct_end, pct_start + int((pct_end - pct_start) * min(1.0, lines / 60.0)))
            self.after(0, lambda t=text, p=prog: (self._log_setup(t), self.setup_prog.configure(value=p)))
        rc = proc.wait()
        if rc != 0:
            raise RuntimeError(f"Step failed with exit code {rc}: {' '.join(cmd[:3])}")

    def _build_game_cmd(
        self,
        py: Path,
        *,
        gen_dir: Path,
        build_out: Path,
        exefs: Path,
        packed_romfs: Path,
        expected_path: Path | None = None,
    ) -> list[str]:
        cmd = [
            str(py),
            str(self.root_dir / "tools" / "build_game.py"),
            "--version",
            "yoshi102",
            "--gen",
            str(gen_dir),
            "--out",
            str(build_out),
            "--exefs",
            str(exefs),
            "--romfs",
            str(packed_romfs),
            "--profile",
            str(self._profile_dir()),
        ]
        if expected_path is None:
            cand_exp = self.root_dir / "tools" / "data" / "expected-yoshi102.json"
            if cand_exp.is_file():
                expected_path = cand_exp
        if expected_path is not None:
            cmd += ["--expected", str(expected_path)]
        rt_lib = self.root_dir / "runtime" / "libyatmbrt.a"
        if rt_lib.is_file():
            cmd += ["--runtime", str(self.root_dir / "runtime"), "--runtime-lib", str(rt_lib)]
        llvm_dir = self.root_dir / "llvm"
        if llvm_dir.is_dir():
            cmd += ["--toolchain", str(llvm_dir), "--deps", str(self.root_dir / "runtime" / "deps")]
        ninja_bin = self.root_dir / "bin" / "ninja.exe"
        if ninja_bin.is_file():
            cmd += ["--ninja", str(ninja_bin)]
        return cmd

    def _run_setup_worker(self, dump_root: str, exefs_txt: str, romfs_txt: str) -> None:
        try:
            # Resolve dump root / .nup off the Tkinter UI thread.
            resolve_root: Path | None = None
            if dump_root:
                resolve_root = Path(dump_root)
            elif exefs_txt:
                exefs_path = Path(exefs_txt)
                if any(part.lower() == "updates" for part in exefs_path.parts):
                    for parent in exefs_path.parents:
                        if parent.name.lower() == "updates":
                            resolve_root = parent.parent
                            break

            if resolve_root is not None:
                resolved = None
                if resolve_root.is_file() and resolve_root.suffix.lower() == ".nup":
                    try:
                        resolved = self._resolve_or_extract_nup(
                            resolve_root,
                            exefs_hint=exefs_txt,
                            pct_lo=2,
                            pct_hi=16,
                        )
                    except DumpError as exc:
                        raise RuntimeError(str(exc)) from exc
                    self._last_nup_extract = (
                        resolve_root.resolve(),
                        resolved.exefs.resolve(),
                        resolved.romfs.resolve(),
                    )
                    self.after(0, lambda: self.setup_prog.configure(value=16))
                elif resolve_root.is_dir():
                    work = self.root_dir / "work" / "dump-resolve"
                    work.mkdir(parents=True, exist_ok=True)
                    try:
                        resolved = discover_dump(resolve_root, work)
                    except DumpError as exc:
                        raise RuntimeError(str(exc)) from exc

                if resolved is not None:
                    self.after(0, lambda r=resolved: self._apply_dump_resolve(r, log=True, update_status=False))
                    exefs_txt = str(resolved.exefs)
                    romfs_txt = str(resolved.romfs)

            exefs = Path(exefs_txt)
            romfs = Path(romfs_txt)
            if not exefs.is_dir() or not romfs.is_dir():
                raise RuntimeError("Please select a dump folder / .nup, or both ExeFS and RomFS folders first.")

            self.after(0, lambda: self.setup_status_var.set("1/5 Verifying Yoshi and the Mysterious Book 1.0.2 ExeFS hashes..."))
            expected = load_expected_yatmb(self.root_dir)
            try:
                lines = verify_exefs_hashes(exefs, expected)
            except DumpError as exc:
                raise RuntimeError(str(exc)) from exc
            for line in lines:
                self.after(0, lambda t=line: self._log_setup(t))
            verified_msg = f"ExeFS SHA-256 verification passed ({len(expected)}/{len(expected)} files matched)."
            self.after(0, lambda m=verified_msg: (self._log_setup(m), self.setup_prog.configure(value=18)))

            # Keep rt_default_exefs inside self.root_dir/exefs so portable installs stay self-contained.
            local_exefs = self.root_dir / "exefs"
            if exefs.resolve() != local_exefs.resolve():
                local_exefs.mkdir(parents=True, exist_ok=True)
                keep_files = {p.name for p in exefs.iterdir() if p.is_file()}
                for old in list(local_exefs.iterdir()):
                    if old.is_file() and old.name not in keep_files:
                        old.unlink(missing_ok=True)
                copied: set[str] = set()
                for name in EXEFS_REQUIRED:
                    src = exefs / name
                    if src.is_file():
                        shutil.copy2(src, local_exefs / name)
                        copied.add(name)
                for src in exefs.iterdir():
                    if src.is_file() and src.name not in copied:
                        shutil.copy2(src, local_exefs / src.name)
                exefs = local_exefs
                self.after(
                    0,
                    lambda p=str(exefs): (
                        self.exefs_var.set(p),
                        self._log_setup(f"Staged verified ExeFS into {p}"),
                    ),
                )

            py = self._find_setup_python()
            env = self._clean_tool_env()

            # Step 2: RomFS pack or use already packed folder
            packed_romfs = self.root_dir / "romfs_packed"
            if (romfs / "index.json").is_file() and (romfs / "romfs.bin").is_file():
                packed_romfs = romfs
                self.after(0, lambda: (self._log_setup(f"Using pre-packed RomFS at {romfs}"),
                                       self.setup_prog.configure(value=40)))
            elif (packed_romfs / "index.json").is_file() and (packed_romfs / "romfs.bin").is_file():
                self.after(0, lambda: (self._log_setup(f"Using existing packed RomFS at {packed_romfs}"),
                                       self.setup_prog.configure(value=40)))
            else:
                self.after(0, lambda: self.setup_status_var.set("2/5 Packing Yoshi and the Mysterious Book RomFS..."))
                packer = self.root_dir / "tools" / "pack_romfs.py"
                self._run_step([str(py), str(packer), "--dir", str(romfs), "--out", str(packed_romfs)], env, 20, 42)


            # Step 3: Lift ExeFS ARM64 -> C
            gen_dir = self.root_dir / "work" / "generated" / "yoshi102"
            gen_ready = (
                (gen_dir / "layout.json").is_file()
                and (gen_dir / "patches.h").is_file()
                and all(
                    (gen_dir / m / "manifest.json").is_file() and (gen_dir / m / f"{m}_table.c").is_file()
                    for m in ("main", "subsdk0", "subsdk1", "subsdk2", "sdk")
                )
            )
            if gen_ready:
                self.after(0, lambda: (self._log_setup(f"Reusing existing lifted C in {gen_dir}"),
                                       self.setup_prog.configure(value=66)))
            else:
                self.after(0, lambda: self.setup_status_var.set("3/5 Lifting ARM64 code to native C..."))
                gen_script = self.root_dir / "recomp" / "gen.py"
                patches = self.root_dir / "recomp" / "patches-yoshi102.txt"
                self._run_step(
                    [str(py), str(gen_script), "--exefs", str(exefs), "--out", str(gen_dir), "--patches", str(patches),
                     "--modules", "main,subsdk0,subsdk1,subsdk2,sdk"],   # Yoshi and the Mysterious Book links subsdk1 too (gen.py lifts 3 by default)
                    env,
                    56,
                    68,
                )

            # Step 4: Compile & link yatmb.exe into clean work/build/yoshi102 then place finished runtime files at root
            self.after(0, lambda: self.setup_status_var.set("4/5 Compiling & linking yatmb.exe..."))
            build_out = self.root_dir / "work" / "build" / "yoshi102"
            build_out.mkdir(parents=True, exist_ok=True)
            cmd = self._build_game_cmd(
                py,
                gen_dir=gen_dir,
                build_out=build_out,
                exefs=exefs,
                packed_romfs=packed_romfs,
            )
            self._run_step(cmd, env, 68, 88)

            for fname in (
                "yatmb.exe",
                "romfs-index.bin",
                "SDL3.dll",
                "libopus-0.dll",
                "libiconv-2.dll",
                "ns2_xlate.exe",
                "ns2_xlate.id",
                "Roboto-Medium.ttf",
                "LICENSE-Roboto.txt",
            ):
                src = build_out / fname
                if src.is_file():
                    shutil.copy2(src, self.root_dir / fname)
                elif fname in ("Roboto-Medium.ttf", "LICENSE-Roboto.txt"):
                    fallback = self.root_dir / "bin" / fname
                    if fallback.is_file() and not (self.root_dir / fname).is_file():
                        shutil.copy2(fallback, self.root_dir / fname)
            for patch_dir in ("romfs-patches", "romfs-patches-xbox"):
                src_dir = build_out / patch_dir
                dst_dir = self.root_dir / patch_dir
                if src_dir.is_dir():
                    shutil.rmtree(dst_dir, ignore_errors=True)
                    shutil.copytree(src_dir, dst_dir)

            # The shader translator ships in bin/; yatmb.exe looks for it beside itself (no translator = no shaders).
            self._sync_staged_bin_files()

            # Step 5: shader pre-warm. Runs a short muted boot pass on a scratch profile so the player's first start stays clean,
            # recording met shaders (shader-programs.bin, shader-answers.bin, pipeline-keys.bin), then builds their pipeline
            # libraries once so the GPU driver's own cache is warm before launch. Not fatal: the game translates on demand.
            self._prewarm_shaders(py, env, exefs, packed_romfs, 88, 99)

            if self.shortcut_var.get():
                create_shortcut(self.root_dir)
            self._write_runtime_stamp()

            self.after(
                0,
                lambda: (
                    self.setup_prog.configure(value=100),
                    self.setup_status_var.set("Setup complete! yatmb.exe is ready to play."),
                    self._refresh_status_cards(),
                    self.select_tab("play"),
                    messagebox.showinfo(APP_TITLE, "Yoshi and the Mysterious Book PC setup finished cleanly! Press PLAY to start.", parent=self),
                ),
            )
        except Exception as exc:
            err = str(exc)
            self.after(
                0,
                lambda e=err: (
                    self.setup_prog.configure(value=0),
                    self.setup_status_var.set(f"Setup failed: {e}"),
                    self._log_setup(f"ERROR: {e}"),
                    messagebox.showerror(APP_TITLE, e, parent=self),
                ),
            )
        finally:
            self.after(0, lambda: self._set_setup_busy(False))

    WARM_SECONDS = 30

    def _prewarm_shaders(self, py: Path, env: dict[str, str], exefs: Path, packed_romfs: Path,
                         pct_start: int = 88, pct_end: int = 99) -> bool:
        """Shader pre-warm pass for Yoshi and the Mysterious Book: runs yatmb.exe once (windowed, muted, on a scratch profile so
        the player's first start stays a first start) along tools/data/yatmb_warm_route.txt (when present) into the title screen,
        recording every shader it meets (shader-programs.bin, shader-answers.bin, pipeline-keys.bin). yatmb.exe --prepare-shaders
        then translates those into the shader cache and builds their pipeline libraries once, so the GPU driver's own
        cache is warm too. Not fatal: the game still translates on demand."""
        exe = self._exe_path()
        route = self.root_dir / "tools" / "data" / "yatmb_warm_route.txt"
        if not exe.is_file() or not (self.root_dir / "ns2_xlate.exe").is_file():
            self.after(0, lambda: self._log_setup("Shader pre-warm skipped (yatmb.exe or ns2_xlate.exe missing)."))
            return False
        self.after(0, lambda: self.setup_status_var.set("5/5 Pre-warming shaders (a short muted boot pass)..."))
        self.after(0, lambda: self._log_setup(f"Warm run: yatmb.exe for {self.WARM_SECONDS} s on a scratch profile..."))
        warm_profile = self.root_dir / "work" / "warm-profile"
        rmtree_retry(warm_profile)
        wenv = dict(env, YATMB_VOLUME="0", YATMB_FULLSCREEN="0", YATMB_WINDOW_SIZE="1280x720")
        if route.is_file():
            wenv["YATMB_INPUT_SCRIPT"] = str(route)
        mid = pct_start + (pct_end - pct_start) * 3 // 4
        try:
            proc = subprocess.Popen(
                [str(exe), "--seconds", str(self.WARM_SECONDS), "--profile", str(warm_profile)],
                cwd=str(self.root_dir), env=wenv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            t0 = time.time()
            while proc.poll() is None:
                frac = min(1.0, (time.time() - t0) / (self.WARM_SECONDS + 15))
                self.after(0, lambda v=pct_start + int((mid - pct_start) * frac): self.setup_prog.configure(value=v))
                if time.time() - t0 > self.WARM_SECONDS + 90:
                    proc.kill()
                    raise RuntimeError("the warm run did not end")
                time.sleep(1)
            if proc.returncode != 0:
                raise RuntimeError(f"the warm run ended with exit code {proc.returncode}; see logs\\yatmb.log")
            for name in ("seed-programs.bin", "seed-answers.bin"):   # --prepare-shaders prefers a seed when present
                (self.root_dir / name).unlink(missing_ok=True)
            self.after(0, lambda: self.setup_status_var.set("5/5 Building the recorded shaders' pipelines..."))
            self._run_step([str(exe), "--prepare-shaders"], env, mid, pct_end)
        except Exception as exc:
            self.after(0, lambda e=str(exc): self._log_setup(f"Shader pre-warm did not finish ({e}); "
                                                              "the game translates the rest while you play."))
            return False
        finally:
            try:
                rmtree_retry(warm_profile)
            except OSError:
                pass
        self.after(0, lambda: self._log_setup("Shader pre-warm complete: shader cache and pipeline libraries are ready."))
        return True

    def _clean_tool_env(self) -> dict[str, str]:
        env = dict(os.environ)
        # Isolate bundled python.exe from any host Python/PyInstaller environment variables.
        for k in ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONUSERBASE", "VIRTUAL_ENV"):
            env.pop(k, None)
        for d in (self.root_dir / "python", self.root_dir / "llvm" / "bin", self.root_dir / "bin"):
            if d.is_dir():
                env["PATH"] = str(d) + os.pathsep + env.get("PATH", "")
        return env

    def _runtime_stamp(self) -> str:
        rt_lib = self.root_dir / "runtime" / "libyatmbrt.a"
        if not rt_lib.is_file():
            return ""
        bg = self.root_dir / "tools" / "build_game.py"
        xlate_id = self.root_dir / "bin" / "ns2_xlate.id"
        st_lib = rt_lib.stat()
        st_bg = bg.stat() if bg.is_file() else None
        st_xl = xlate_id.stat() if xlate_id.is_file() else None
        key = (
            self.version,
            st_lib.st_size,
            st_lib.st_mtime_ns,
            st_bg.st_size if st_bg else 0,
            st_bg.st_mtime_ns if st_bg else 0,
            st_xl.st_size if st_xl else 0,
            st_xl.st_mtime_ns if st_xl else 0,
        )
        if self._runtime_stamp_cache and self._runtime_stamp_cache[0] == key:
            return self._runtime_stamp_cache[1]
        lib_hash = hashlib.sha256(rt_lib.read_bytes()).hexdigest()[:16]
        bg_hash = hashlib.sha256(bg.read_bytes()).hexdigest()[:12] if bg.is_file() else ""
        xlate_txt = xlate_id.read_text(encoding="utf-8", errors="ignore").strip() if xlate_id.is_file() else ""
        stamp = f"{self.version}|{st_lib.st_size}|{lib_hash}|{bg_hash}|{xlate_txt}"
        self._runtime_stamp_cache = (key, stamp)
        return stamp

    def _resolve_exefs(self) -> Path | None:
        direct = self.root_dir / "exefs"
        if (direct / "main").is_file():
            return direct
        mods_c = self.root_dir / "work" / "build" / "yoshi102" / "modules.c"
        if mods_c.is_file():
            txt = mods_c.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r'rt_default_exefs\[\]\s*=\s*"([^"]+)"', txt)
            if m:
                cand = Path(m.group(1).replace("\\\\", "\\"))
                if (cand / "main").is_file():
                    return cand
        return direct if direct.is_dir() else None

    def _resolve_packed_romfs(self) -> Path | None:
        direct = self.root_dir / "romfs_packed"
        if (direct / "romfs.bin").is_file():
            return direct
        mods_c = self.root_dir / "work" / "build" / "yoshi102" / "modules.c"
        if mods_c.is_file():
            txt = mods_c.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r'rt_default_romfs\[\]\s*=\s*"([^"]+)"', txt)
            if m:
                cand = Path(m.group(1).replace("\\\\", "\\"))
                if (cand / "romfs.bin").is_file():
                    return cand
        return None

    def _runtime_stamp_path(self) -> Path:
        return self.root_dir / "work" / "build" / "yoshi102" / ".yatmb_runtime_stamp"

    def _write_runtime_stamp(self, exe_size: int | None = None) -> None:
        stamp = self._runtime_stamp()
        if not stamp:
            return
        if exe_size is None:
            exe = self._exe_path()
            exe_size = exe.stat().st_size if exe.is_file() else 0
        sp = self._runtime_stamp_path()
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(f"{stamp}|exe:{exe_size}\n", encoding="utf-8")

    def _parse_stored_stamp(self, raw: str) -> tuple[str, int | None]:
        text = (raw or "").strip()
        if not text:
            return "", None
        m = re.search(r"\|exe:(\d+)$", text)
        if m:
            return text[: m.start()], int(m.group(1))
        return text, None

    def _stale_build_status(self) -> tuple[bool, str, tuple[Path, Path, Path, str, str] | None]:
        exe = self._exe_path()
        rt_lib = self.root_dir / "runtime" / "libyatmbrt.a"
        if not exe.is_file() or not rt_lib.is_file():
            return False, "", None
        want_stamp = self._runtime_stamp()
        if not want_stamp:
            return False, "", None
        stamp_path = self._runtime_stamp_path()
        raw_have = stamp_path.read_text(encoding="utf-8", errors="ignore").strip() if stamp_path.is_file() else ""
        have_stamp, rec_exe_size = self._parse_stored_stamp(raw_have)
        exe_size = exe.stat().st_size
        stale = (
            (have_stamp != want_stamp)
            or (rec_exe_size is not None and rec_exe_size != exe_size)
            or (rt_lib.stat().st_mtime > exe.stat().st_mtime + 1.0)
        )
        if not stale:
            return False, "", None
        exefs = self._resolve_exefs()
        packed_romfs = self._resolve_packed_romfs()
        gen_dir = self.root_dir / "work" / "generated" / "yoshi102"
        missing: list[str] = []
        if exefs is None or not exefs.is_dir():
            missing.append("exefs")
        if packed_romfs is None:
            missing.append("romfs_packed")
        if not (gen_dir / "layout.json").is_file():
            missing.append("work/generated/yoshi102")
        if missing:
            return True, "missing " + ", ".join(missing), None
        assert exefs is not None and packed_romfs is not None
        return True, "runtime updated", (exefs, packed_romfs, gen_dir, want_stamp, have_stamp)

    def _write_refresh_log(self, lines: list[str]) -> None:
        try:
            log_dir = self._logs_dir()
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "refresh.log"
            stamp = datetime.now().isoformat(timespec="seconds")
            body = f"=== [{stamp}] YATMBLauncher runtime refresh ({self.version}) ===\n" + "\n".join(lines) + "\n\n"
            with log_file.open("a", encoding="utf-8", errors="replace") as f:
                f.write(body)
        except OSError:
            pass

    def _sync_staged_bin_files(self) -> None:
        if not self._exe_path().is_file():
            return
        src_exe = self.root_dir / "bin" / "ns2_xlate.exe"
        src_id = self.root_dir / "bin" / "ns2_xlate.id"
        if not src_exe.is_file() or not src_id.is_file():
            return
        dst_exe = self.root_dir / "ns2_xlate.exe"
        dst_id = self.root_dir / "ns2_xlate.id"
        try:
            src_bytes = src_id.read_bytes()
            if not dst_id.is_file() or not dst_exe.is_file() or dst_id.read_bytes() != src_bytes:
                shutil.copy2(src_exe, dst_exe)
                shutil.copy2(src_id, dst_id)
        except OSError:
            pass

    def _auto_refresh_existing_build(self, launch_after: bool = False) -> None:
        # Read installed translator ID before _sync_staged_bin_files overwrites it, so upgrades from
        # older installs without .yatmb_runtime_stamp avoid unnecessary 50s shader re-warms.
        root_xlate_id = self.root_dir / "ns2_xlate.id"
        prev_root_xlate = (
            root_xlate_id.read_text(encoding="utf-8", errors="ignore").strip() if root_xlate_id.is_file() else ""
        )
        self._sync_staged_bin_files()
        if self.setup_running or self.refresh_running or self.update_in_progress:
            return
        stale, reason, refresh_args = self._stale_build_status()
        if not stale:
            return
        if refresh_args is None:
            self._write_refresh_log([f"Skipped auto-refresh: {reason}"])
            self._refresh_status_cards()
            return
        exefs, packed_romfs, gen_dir, want_stamp, have_stamp = refresh_args
        running_warn = game_process_warning(self.root_dir, "updating yatmb.exe")
        if running_warn is not None:
            self._last_refresh_error = "Close running yatmb.exe so the launcher can update it."
            self._write_refresh_log([f"Deferred auto-refresh: {running_warn}"])
            self._refresh_status_cards()
            if launch_after:
                messagebox.showwarning(APP_TITLE, running_warn, parent=self)
            return
        self._last_refresh_error = None
        self._launch_after_refresh = bool(launch_after)
        self.refresh_running = True
        self._refresh_status_cards()
        threading.Thread(
            target=self._run_refresh_worker,
            args=(exefs, packed_romfs, gen_dir, want_stamp, have_stamp, prev_root_xlate),
            daemon=True,
        ).start()

    def _run_refresh_worker(
        self,
        exefs: Path,
        packed_romfs: Path,
        gen_dir: Path,
        want_stamp: str,
        have_stamp: str = "",
        prev_root_xlate: str = "",
    ) -> None:
        err: str | None = None
        log_lines: list[str] = [
            f"exefs={exefs}",
            f"packed_romfs={packed_romfs}",
            f"gen_dir={gen_dir}",
            f"have_stamp={have_stamp or '<none>'}",
            f"want_stamp={want_stamp}",
        ]
        try:
            py = self._find_setup_python()
            env = self._clean_tool_env()
            build_out = self.root_dir / "work" / "build" / "yoshi102"
            build_out.mkdir(parents=True, exist_ok=True)
            # Always drop cached build_out/yatmb.exe before relinking so Ninja never skips relinking
            # when a manually extracted Update.zip preserves older timestamps on libyatmbrt.a.
            (build_out / "yatmb.exe").unlink(missing_ok=True)
            cmd = self._build_game_cmd(
                py,
                gen_dir=gen_dir,
                build_out=build_out,
                exefs=exefs,
                packed_romfs=packed_romfs,
            )
            log_lines.append("cmd=" + " ".join(cmd))
            proc = subprocess.run(
                cmd,
                cwd=str(self.root_dir),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if proc.stdout:
                log_lines.append(proc.stdout.rstrip())
            log_lines.append(f"build_game exit={proc.returncode}")
            if proc.returncode != 0:
                tail = "\n".join((proc.stdout or "").strip().splitlines()[-10:])
                raise RuntimeError(f"Runtime update build failed (exit {proc.returncode}):\n{tail}")
            src_exe = build_out / "yatmb.exe"
            if not src_exe.is_file():
                raise RuntimeError(f"Runtime update build did not produce {src_exe}")
            src_size = src_exe.stat().st_size
            src_sha = sha256_file(src_exe)
            dst_exe = self._exe_path()
            tmp_exe = self.root_dir / "yatmb.exe.update-new"
            shutil.copy2(src_exe, tmp_exe)
            os.replace(tmp_exe, dst_exe)
            dst_size = dst_exe.stat().st_size
            dst_sha = sha256_file(dst_exe)
            if dst_size != src_size or dst_sha != src_sha:
                raise RuntimeError(
                    f"Copied yatmb.exe verification mismatch (src={src_size}/{src_sha[:12]}, dst={dst_size}/{dst_sha[:12]})"
                )
            log_lines.append(f"verified yatmb.exe: size={dst_size} sha256={dst_sha[:16]}")
            for fname in ("ns2_xlate.exe", "ns2_xlate.id", "SDL3.dll", "libopus-0.dll"):
                src = build_out / fname
                if src.is_file():
                    shutil.copy2(src, self.root_dir / fname)
            self._sync_staged_bin_files()
            old_xlate = (have_stamp.rsplit("|", 1)[-1].strip() if "|" in have_stamp else "") or prev_root_xlate
            new_xlate = want_stamp.rsplit("|", 1)[-1].strip() if "|" in want_stamp else ""
            can_reuse_shaders = (
                bool(old_xlate)
                and old_xlate == new_xlate
                and (self.root_dir / "shader-programs.bin").is_file()
                and (self.root_dir / "pipeline-keys.bin").is_file()
            )
            log_lines.append(f"shaders: can_reuse={can_reuse_shaders} old_xlate={old_xlate[:12]} new_xlate={new_xlate[:12]}")
            if can_reuse_shaders:
                subprocess.run(
                    [str(dst_exe), "--prepare-shaders"],
                    cwd=str(self.root_dir),
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            else:
                # An update can bring a new shader translator, which starts a new cache: warm it again.
                self._prewarm_shaders(py, env, exefs, packed_romfs, 0, 100)
            self._write_runtime_stamp(exe_size=dst_size)
            log_lines.append("refresh complete: OK")
        except Exception as exc:
            err = str(exc)
            log_lines.append(f"ERROR: {err}")
        finally:
            self._write_refresh_log(log_lines)
            self.after(0, lambda e=err: self._finish_refresh_worker(e))

    def _finish_refresh_worker(self, err: str | None) -> None:
        self.refresh_running = False
        self._last_refresh_error = err
        launch_now = self._launch_after_refresh and err is None
        self._launch_after_refresh = False
        self._refresh_status_cards()
        if err:
            messagebox.showerror(
                f"{APP_TITLE} — yatmb.exe Update Failed",
                f"Could not relink yatmb.exe for {self.version}:\n\n{err[:500]}\n\nFull details were written to logs\\refresh.log.",
                parent=self,
            )
        else:
            self.build_hint_lbl.configure(
                text=f"Updated {self._exe_path().name} to {self.version}. Press PLAY to launch.",
                fg=C_OK,
            )
            if launch_now:
                self.launch_game()

    def check_for_updates(self) -> None:
        if getattr(self, "release_check_active", False) or getattr(self, "update_in_progress", False):
            return
        self.release_check_active = True
        self.update_action_btn.pack_forget()
        self.release_btn.pack_forget()
        self.update_status.config(text="Checking GitHub Releases…", fg=C_TEXT_DIM)
        threading.Thread(target=self._check_release_worker, daemon=True).start()

    def _check_release_worker(self) -> None:
        try:
            headers = {"Accept": "application/vnd.github+json", "User-Agent": "YATMBLauncher"}
            data: dict | None = None
            try:
                req = urllib.request.Request(RELEASES_LIST_API_URL, headers=headers)
                with urllib.request.urlopen(req, timeout=12) as r:
                    releases = json.loads(r.read().decode("utf-8"))
                if isinstance(releases, list):
                    if not releases:
                        self.after(
                            0,
                            lambda: self._show_release_result(
                                self.version, f"Your SteelTemple YATMB is up to date ({self.version}).", RELEASES_URL, None, None
                            ),
                        )
                        return
                    data = select_latest_release(releases)
                    if data is None:
                        self.after(
                            0,
                            lambda: self._show_release_result(
                                self.version, f"Your SteelTemple YATMB is up to date ({self.version}).", RELEASES_URL, None, None
                            ),
                        )
                        return
            except Exception:
                data = None
            if data is None:
                req = urllib.request.Request(RELEASES_API_URL, headers=headers)
                with urllib.request.urlopen(req, timeout=12) as r:
                    data = json.loads(r.read().decode("utf-8"))
            tag = (data.get("tag_name") or "").strip()
            title = (data.get("name") or tag or "Latest SteelTemple YATMB release").strip()
            page = data.get("html_url") or (f"{GITHUB_URL}/releases/tag/{tag}" if tag else RELEASES_URL)
            if not tag:
                raise ValueError("The latest release did not include a version tag.")
            asset_name, asset_url = _find_update_asset(data)
            self.after(0, lambda: self._show_release_result(tag, title, page, asset_url, asset_name))
        except Exception as exc:
            detail = str(exc)
            if "404" in detail or "Not Found" in detail:
                self.after(
                    0,
                    lambda: self._show_release_result(
                        self.version, f"Your SteelTemple YATMB is up to date ({self.version}).", RELEASES_URL, None, None
                    ),
                )
            else:
                self.after(0, lambda: self._show_release_error("Update check failed: " + detail))

    def _update_done_marker_path(self) -> Path:
        return self._logs_dir() / "update_done.json"

    def _update_failed_marker_path(self) -> Path:
        return self._logs_dir() / "update_failed.json"

    def _consume_update_done_marker(self) -> dict | None:
        p = self._update_done_marker_path()
        if not p.is_file():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig", errors="ignore"))
        except Exception:
            data = None
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass
        return data if isinstance(data, dict) else None

    def _read_update_failed_marker(self) -> dict | None:
        p = self._update_failed_marker_path()
        if not p.is_file():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig", errors="ignore"))
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _clear_update_failed_marker(self) -> None:
        try:
            self._update_failed_marker_path().unlink(missing_ok=True)
        except OSError:
            pass

    def _write_update_failed_marker(self, tag: str, title: str, error: str) -> None:
        try:
            p = self._update_failed_marker_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            payload = {"tag": tag, "title": title, "error": error, "ts": datetime.now().isoformat(timespec="seconds")}
            p.write_text(json.dumps(payload), encoding="utf-8")
        except OSError:
            pass

    def _show_release_error(self, message: str) -> None:
        self.release_check_active = False
        self.update_status.config(text=message, fg=C_BAD)

    def _show_release_result(
        self, tag: str, title: str, page: str, asset_url: str | None = None, asset_name: str | None = None
    ) -> None:
        self.release_check_active = False
        self.latest_release = {
            "tag": tag,
            "title": title,
            "page": page,
            "asset_url": asset_url,
            "asset_name": asset_name,
        }
        clean_title = title.split(":", 1)[0].strip()
        if (
            is_up_to_date(self.version, tag)
            or is_same_version(self.version, clean_title)
            or (not version_tuple(tag)[0] and is_up_to_date(self.version, clean_title))
        ):
            self._clear_update_failed_marker()
            if getattr(self, "_recent_update_done", None):
                self.update_status.config(
                    text=f"Updated cleanly — SteelTemple YATMB is up to date ({self.version})", fg=C_OK
                )
            else:
                self.update_status.config(text=f"Your SteelTemple YATMB is up to date ({self.version})", fg=C_OK)
            self.update_action_btn.pack_forget()
            self.release_btn.pack_forget()
            return
        if not asset_url:
            self.update_status.config(text=f"Update found ({clean_title}), but Update.zip is missing.", fg=C_WARN)
            self.update_action_btn.pack_forget()
            self.release_btn.config(text="VIEW RELEASE NOTES")
            self.release_btn.pack(side=tk.LEFT, padx=(10, 0))
            return
        failed = self._read_update_failed_marker()
        if failed and (failed.get("tag") or "").casefold() == tag.casefold():
            err_preview = str(failed.get("error") or "see logs\\update.log").splitlines()[0][:120]
            self.update_status.config(
                text=f"Previous auto-update to {clean_title} failed ({err_preview}) — click INSTALL UPDATE to retry.",
                fg=C_BAD,
            )
            self.update_action_btn.config(state=tk.NORMAL, text="INSTALL UPDATE")
            self.update_action_btn.pack(side=tk.LEFT, padx=(10, 0))
            self.release_btn.config(text="VIEW RELEASE NOTES")
            self.release_btn.pack(side=tk.LEFT, padx=(10, 0))
            return
        if self.auto_install_updates:
            self.update_status.config(text=f"Update available: {clean_title} — installing…", fg=C_WARN)
            self.update_action_btn.config(state=tk.DISABLED, text="AUTO-INSTALLING…")
            self.update_action_btn.pack(side=tk.LEFT, padx=(10, 0))
            self.release_btn.config(text="VIEW RELEASE NOTES")
            self.release_btn.pack(side=tk.LEFT, padx=(10, 0))
            self.after(400, lambda: self.apply_latest_update(auto=True))
        else:
            self.update_status.config(text=f"Update available: {clean_title}", fg=C_WARN)
            self.update_action_btn.config(state=tk.NORMAL, text="INSTALL UPDATE")
            self.update_action_btn.pack(side=tk.LEFT, padx=(10, 0))
            self.release_btn.config(text="VIEW RELEASE NOTES")
            self.release_btn.pack(side=tk.LEFT, padx=(10, 0))

    def open_latest_release(self) -> None:
        url = self.latest_release["page"] if (self.latest_release and self.latest_release.get("page")) else RELEASES_URL
        webbrowser.open(url)

    def apply_latest_update(self, auto: bool = False) -> None:
        if (
            getattr(self, "update_in_progress", False)
            or getattr(self, "refresh_running", False)
            or getattr(self, "setup_running", False)
            or not self.latest_release
        ):
            return
        warning = game_process_warning(self.root_dir, "applying a launcher/game update")
        if warning:
            self.update_action_btn.config(state=tk.NORMAL, text="INSTALL UPDATE")
            self.update_status.config(text="Close Yoshi and the Mysterious Book (yatmb.exe) before installing the update.", fg=C_WARN)
            if not auto:
                messagebox.showwarning("Close the Game First", warning, parent=self)
            return
        title = self.latest_release.get("title", "SteelTemple YATMB Update")
        if not auto and not messagebox.askyesno(
            "Install SteelTemple YATMB Update",
            f"Download and install {title} now?\n\nThis updates YATMBLauncher and toolchain files. "
            "Your dump, saves, and personal yatmb.ini stay local.",
            parent=self,
        ):
            return
        if not self.latest_release.get("asset_url") or not self.latest_release.get("asset_name"):
            self.update_status.config(text="Update.zip download URL is missing.", fg=C_BAD)
            return
        if not auto:
            self._clear_update_failed_marker()
        self.update_in_progress = True
        self._auto_installing = bool(auto)
        self.update_action_btn.config(state=tk.DISABLED, text="DOWNLOADING UPDATE…")
        self.update_status.config(text="Connecting to GitHub Releases…", fg=C_TEXT_DIM)
        threading.Thread(target=self._download_update_worker, args=(self.latest_release.copy(),), daemon=True).start()

    def _download_update_worker(self, release: dict) -> None:
        stage = None
        try:
            target = self.root_dir
            target.mkdir(parents=True, exist_ok=True)
            stage = Path(tempfile.mkdtemp(prefix=".yatmb-update-", dir=str(target)))
            archive_path = stage / release["asset_name"]
            request = urllib.request.Request(
                release["asset_url"],
                headers={"User-Agent": "YATMBLauncher", "Accept": "application/octet-stream"},
            )
            with urllib.request.urlopen(request, timeout=120) as response, archive_path.open("wb") as output:
                total = int(response.headers.get("Content-Length", "0") or 0)
                downloaded = 0
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    output.write(block)
                    downloaded += len(block)
                    if total:
                        percent = min(100, downloaded * 100 // total)
                        self._set_update_status(f"Downloading update… {percent}%", C_TEXT_DIM)
            self._set_update_status("Validating & staging update files…", C_TEXT_DIM)
            files = extract_update_archive(archive_path, stage, existing_root=target)
            archive_path.unlink(missing_ok=True)
            if not files:
                shutil.rmtree(_win_long_path(stage), ignore_errors=True)
                self.after(0, lambda: self._update_already_applied(release))
                return
            self.after(0, lambda: self._update_ready(release, stage, files))
        except Exception as exc:
            if stage:
                shutil.rmtree(_win_long_path(stage), ignore_errors=True)
            detail = str(exc)
            if getattr(self, "_auto_installing", False):
                self._write_update_failed_marker(
                    release.get("tag", ""),
                    release.get("title", "SteelTemple YATMB Update"),
                    detail,
                )
            self.after(0, lambda: self._update_failed(detail))

    def _update_already_applied(self, release: dict) -> None:
        self.update_in_progress = False
        self._clear_update_failed_marker()
        self.version = read_app_version()
        self.update_status.config(text=f"Your SteelTemple YATMB is up to date ({self.version})", fg=C_OK)
        self.update_action_btn.pack_forget()
        self.release_btn.pack_forget()

    def _set_update_status(self, text: str, color: str) -> None:
        try:
            self.after(0, lambda: self.update_status.config(text=text, fg=color))
        except tk.TclError:
            pass

    def _update_failed(self, detail: str) -> None:
        self.update_in_progress = False
        self.update_action_btn.config(state=tk.NORMAL, text="INSTALL UPDATE")
        self.update_status.config(text=f"Update failed:\n{detail[:160]}", fg=C_BAD)

    def _update_ready(self, release: dict, stage: Path, files: list[str]) -> None:
        title = release.get("title", "SteelTemple YATMB Update")
        tag = release.get("tag", "")
        auto = getattr(self, "_auto_installing", False)
        if not auto and not messagebox.askyesno(
            "Update Ready",
            f"{title} is downloaded and verified ({len(files)} updated file(s)).\n\n"
            "Install it now? The launcher will close, apply the files, and restart automatically.",
            parent=self,
        ):
            shutil.rmtree(_win_long_path(stage), ignore_errors=True)
            self.update_in_progress = False
            self.update_action_btn.config(state=tk.NORMAL, text="INSTALL UPDATE")
            self.update_status.config(text="Update downloaded; installation cancelled.", fg=C_TEXT_DIM)
            return
        try:
            self.update_status.config(text=f"Applying {title}… restarting launcher.", fg=C_WARN)
            self.update_idletasks()
            self.withdraw()
            self._start_update_relauncher(stage, title, tag=tag)
            os._exit(0)
        except Exception as exc:
            try:
                self.deiconify()
            except Exception:
                pass
            shutil.rmtree(_win_long_path(stage), ignore_errors=True)
            if auto:
                self._write_update_failed_marker(tag, title, str(exc))
            self._update_failed(str(exc))

    def _start_update_relauncher(self, stage: Path, title: str, tag: str = "") -> None:
        script = build_update_relauncher_script(
            self.root_dir, stage, title, pid=os.getpid(), restart=True, silent=False, tag=tag
        )
        temp_dir = Path(tempfile.gettempdir())
        script_path = temp_dir / f"yatmb-update-{stage.name}.ps1"
        # UTF-8 with BOM ensures Windows PowerShell 5.1 parses non-ASCII/accented paths reliably.
        script_path.write_text(script, encoding="utf-8-sig")
        # IMPORTANT: Do NOT use DETACHED_PROCESS with powershell.exe — Windows PowerShell 5.1
        # silently exits with code 0 without running the script when no console is attached.
        # CREATE_NO_WINDOW allocates a hidden console so the script runs reliably with no popup window.
        flags = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        proc = subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-WindowStyle",
                "Hidden",
                "-File",
                str(script_path),
            ],
            cwd=str(temp_dir),
            creationflags=flags,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.05)
        rc = proc.poll()
        if rc is not None and rc != 0:
            raise RuntimeError(f"Updater helper exited immediately with code {rc}.")

    def _capture_shot_and_exit(self) -> None:
        try:
            self.update_idletasks()
            self.update()
            out_path = Path(self.shot_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                hwnd = self.winfo_id()
                # Parent top-level HWND for decorated frame
                parent_hwnd = ctypes.windll.user32.GetParent(hwnd) or hwnd
                rect = (ctypes.c_long * 4)()
                ctypes.windll.user32.GetWindowRect(parent_hwnd, rect)
                w = max(1, int(rect[2] - rect[0]))
                h = max(1, int(rect[3] - rect[1]))
                hdc_win = ctypes.windll.user32.GetWindowDC(parent_hwnd)
                hdc_mem = ctypes.windll.gdi32.CreateCompatibleDC(hdc_win)
                hbmp = ctypes.windll.gdi32.CreateCompatibleBitmap(hdc_win, w, h)
                old = ctypes.windll.gdi32.SelectObject(hdc_mem, hbmp)
                ctypes.windll.user32.PrintWindow(parent_hwnd, hdc_mem, 2)  # PW_RENDERFULLCONTENT
                class BITMAPINFOHEADER(ctypes.Structure):
                    _fields_ = [
                        ("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32), ("biHeight", ctypes.c_int32),
                        ("biPlanes", ctypes.c_uint16), ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                        ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32), ("biYPelsPerMeter", ctypes.c_int32),
                        ("biClrUsed", ctypes.c_uint32), ("biClrImportant", ctypes.c_uint32),
                    ]
                bmi = BITMAPINFOHEADER()
                bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                bmi.biWidth = w
                bmi.biHeight = -h
                bmi.biPlanes = 1
                bmi.biBitCount = 32
                bmi.biCompression = 0
                buf = (ctypes.c_ubyte * (w * h * 4))()
                ctypes.windll.gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bmi), 0)
                ctypes.windll.gdi32.SelectObject(hdc_mem, old)
                ctypes.windll.gdi32.DeleteObject(hbmp)
                ctypes.windll.gdi32.DeleteDC(hdc_mem)
                ctypes.windll.user32.ReleaseDC(parent_hwnd, hdc_win)
                img = Image.frombuffer("RGBA", (w, h), bytes(buf), "raw", "BGRA", 0, 1)
                img.save(out_path)
            else:
                from PIL import ImageGrab
                x, y, w, h = self.winfo_rootx(), self.winfo_rooty(), self.winfo_width(), self.winfo_height()
                ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(out_path)
        finally:
            self.after(40, self.destroy)


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--tab", default="play", choices=["play", "setup", "settings", "mods"])
    ap.add_argument("--shot", default="", help="Capture launcher window screenshot and exit")
    ap.add_argument("--check", action="store_true", help="Verify clean startup & exit")
    args = ap.parse_args()

    set_windows_app_id()
    app = YATMBLauncherApp(initial_tab=args.tab, shot_path=args.shot, skip_update_check=args.check)
    if args.check:
        app.update_idletasks()
        app.destroy()
        print("YATMBLauncher check: OK")
        return 0
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
