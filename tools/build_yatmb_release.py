"""Build the clean SteelTemple YATMB (Yoshi and the Mysterious Book PC) Windows release package.

Emits into build/release-yatmb/:
  1. SteelTemple-YATMB-<ver>-Full-Setup-Wizard.exe
  2. SteelTemple-YATMB-<ver>-Portable-StandAlone.zip
  3. SteelTemple-YATMB-<ver>-Update.zip

Follows strict allowlist staging:
  - Zero copyrighted game files (exefs/, romfs/, romfs_packed/, generated/, spirv/)
  - Zero developer INI/profile/logs/shader-cache state
  - Zero DKB, TotK, MTF, or FF icons, binaries, or release assets
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import check_content  # noqa: E402

MKW_CACHE = Path(r"C:\Games\MKW PC\upstream-mkw-recomp\build")
MSYS_UCRT = Path(r"C:\msys64\ucrt64")
YOSHI_BUILD = Path(r"C:\Games\Yoshi and the Mysterious Book PC\build\yoshi102")

LLVM_BIN = {
    "clang.exe", "clang++.exe", "clang-23.exe", "ld.lld.exe", "llvm-ar.exe", "llvm-ranlib.exe",
    "llvm-nm.exe", "llvm-objdump.exe", "llvm-objcopy.exe", "llvm-strip.exe", "llvm-readobj.exe",
    "llvm-dlltool.exe", "llvm-rc.exe", "llvm-cvtres.exe", "llvm-windres.exe", "llvm-wrapper.exe",
    "mingw32-common.cfg", "x86_64-w64-windows-gnu.cfg", "x86_64-pc-windows-gnu.cfg",
    "x86_64-w64-mingw32-clang.exe", "x86_64-w64-mingw32-clang++.exe",
    "libLLVM-23.dll", "libclang-cpp.dll", "libc++.dll", "libunwind.dll",
    "libwinpthread-1.dll", "libffi-8.dll",
}
LLVM_SKIP_DIRS = {"aarch64-w64-mingw32", "armv7-w64-mingw32", "i686-w64-mingw32", "busybox", "python", "share"}
LLVM_SKIP_SUFFIXES = {".idl", ".tlb"}

TOOLS_FILES = [
    "build_game.py",
    "build_shaders.py",
    "check_content.py",
    "extract_nup.py",
    "hostmem.py",
    "make_romfs_patches.py",
    "pack_romfs.py",
    "pack_shader_cache.py",
    "prepare_shaders.py",
    "romfs_index.py",
    "shader_census.py",
    "shader_list.py",
]

MAGIC = b"YATMBV01"


def read_version() -> str:
    p = ROOT / "launcher" / "yatmb_version.txt"
    if p.is_file():
        return p.read_text(encoding="utf-8-sig").strip().splitlines()[0].strip()
    return "0.1.0"


def version_slug(ver: str) -> str:
    return "-".join(ver.split())


def run(cmd: list[str | Path], **kw) -> None:
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def clean_env(*path_dirs: Path) -> dict[str, str]:
    sys_root = os.environ.get("SystemRoot", r"C:\Windows")
    keep = {
        "SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP", "USERPROFILE",
        "LOCALAPPDATA", "APPDATA", "COMSPEC", "PATHEXT", "NUMBER_OF_PROCESSORS",
    }
    env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    env["PATH"] = os.pathsep.join([*(str(p) for p in path_dirs), rf"{sys_root}\System32", sys_root])
    return env


def copy_tree(src: Path, dst: Path, skip=lambda _rel: False) -> None:
    for p in sorted(src.rglob("*")):
        rel = p.relative_to(src)
        if p.is_dir() or skip(rel.as_posix()):
            continue
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, out)


def build_launcher() -> Path:
    cands = [
        ROOT / ".venv" / "Scripts" / "pyinstaller.exe",
        ROOT.parent / "Universal-NS2-to-PC" / ".venv" / "Scripts" / "pyinstaller.exe",
    ]
    pyinstaller = next((c for c in cands if c.is_file()), None)
    if pyinstaller is None and shutil.which("pyinstaller"):
        pyinstaller = Path(shutil.which("pyinstaller"))
    if pyinstaller is None:
        sys.exit(f"Missing PyInstaller (looked in {', '.join(str(c) for c in cands)} and PATH)")
    run([pyinstaller, ROOT / "YATMBLauncher.spec", "--noconfirm"], cwd=ROOT)
    exe = ROOT / "dist" / "YATMBLauncher.exe"
    if not exe.is_file():
        sys.exit("PyInstaller did not produce dist/YATMBLauncher.exe")
    return exe


def stage_python(stage: Path) -> Path:
    dl = MKW_CACHE / "dist" / "dl"
    py_tar = next(iter(sorted(dl.glob("cpython-3.14*-x86_64-pc-windows-msvc-install_only_stripped.tar.gz"))), None)
    if not py_tar:
        sys.exit(f"Missing cached standalone Python 3.14 tarball in {dl}")
    py_dst = stage / "python"
    with tarfile.open(py_tar) as tf:
        tf.extractall(stage, filter="tar")
    if not (py_dst / "python.exe").is_file():
        sys.exit(f"Expected python.exe in {py_dst}")

    site_pkg = py_dst / "Lib" / "site-packages"
    site_pkg.mkdir(parents=True, exist_ok=True)
    for pattern in ("numpy-*.whl", "lz4-*.whl"):
        whls = sorted(dl.glob(pattern))
        if not whls:
            sys.exit(f"Missing cached wheel matching {pattern} in {dl}")
        with zipfile.ZipFile(whls[-1]) as zf:
            for member in zf.infolist():
                if member.filename.endswith("/") or member.filename.startswith("bin/"):
                    continue
                zf.extract(member, site_pkg)

    for junk in ("include", "libs", "Scripts", "tcl"):
        jdir = py_dst / junk
        if jdir.is_dir():
            shutil.rmtree(jdir, ignore_errors=True)
    for pycache in py_dst.rglob("__pycache__"):
        shutil.rmtree(pycache, ignore_errors=True)

    r = subprocess.run(
        [
            str(py_dst / "python.exe"),
            "-B",
            "-I",
            "-c",
            "from compression import zstd; import numpy, lz4.block; "
            "print('python OK:', numpy.__version__)",
        ],
        env=clean_env(py_dst),
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        sys.exit(f"Staged Python verification failed:\n{r.stderr}")
    print(" ", r.stdout.strip())
    return py_dst


def stage_llvm(stage: Path) -> Path:
    src = MKW_CACHE / "win" / "llvm-mingw"
    if not (src / "bin" / "clang.exe").is_file():
        sys.exit(f"Missing cached llvm-mingw in {src}")
    dst = stage / "llvm"

    def skip(rel: str) -> bool:
        top = rel.split("/")[0]
        if top in LLVM_SKIP_DIRS:
            return True
        if top == "bin":
            return rel not in {f"bin/{n}" for n in LLVM_BIN}
        if top == "lib":
            if rel.startswith("lib/clang/") and "/include/" in rel:
                return False
            return not rel.endswith("/lib/windows/libclang_rt.builtins-x86_64.a")
        return Path(rel).suffix.lower() in LLVM_SKIP_SUFFIXES or rel.startswith("include/ddk/")

    copy_tree(src, dst, skip)
    return dst


def ensure_standalone_ninja(dest_exe: Path) -> None:
    """Fetch pinned standalone ninja-win.zip (zero MSYS2 DLL dependencies) into toolchain/release-dl."""
    url = "https://github.com/ninja-build/ninja/releases/download/v1.13.2/ninja-win.zip"
    want_sha = "07fc8261b42b20e71d1720b39068c2e14ffcee6396b76fb7a795fb460b78dc65"
    dl = ROOT / "toolchain" / "release-dl"
    dl.mkdir(parents=True, exist_ok=True)
    zip_path = dl / "ninja-win.zip"
    if zip_path.is_file():
        got = hashlib.sha256(zip_path.read_bytes()).hexdigest()
        if got != want_sha:
            zip_path.unlink()
    if not zip_path.is_file():
        print(f"Downloading standalone ninja v1.13.2 -> {zip_path}", flush=True)
        data = urllib.request.urlopen(url, timeout=60).read()
        got = hashlib.sha256(data).hexdigest()
        if got != want_sha:
            sys.exit(f"ninja-win.zip sha256 mismatch: got {got}, expected {want_sha}")
        zip_path.write_bytes(data)
    with zipfile.ZipFile(zip_path) as zf:
        dest_exe.write_bytes(zf.read("ninja.exe"))
    r = subprocess.run([str(dest_exe), "--version"], env=clean_env(dest_exe.parent), capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"Standalone ninja.exe failed check:\n{r.stderr}")
    print("  ninja OK:", r.stdout.strip())


def stage_deps_and_bin(stage: Path) -> None:
    deps_src = MKW_CACHE / "win" / "deps"
    deps_dst = stage / "runtime" / "deps"
    if not (deps_src / "lib" / "libSDL3.dll.a").is_file():
        sys.exit(f"Missing cached Windows deps in {deps_src}")

    copy_tree(deps_src / "include", deps_dst / "include")
    (deps_dst / "lib").mkdir(parents=True, exist_ok=True)
    for lib_name in ("libSDL3.dll.a", "libopus.dll.a", "libvpx.a", "libvulkan-1.dll.a", "libzstd.a"):
        shutil.copy2(deps_src / "lib" / lib_name, deps_dst / "lib" / lib_name)

    dav_lib = MSYS_UCRT / "lib" / "libdav1d.a"
    dav_inc = MSYS_UCRT / "include" / "dav1d"
    if not dav_lib.is_file() or not dav_inc.is_dir():
        sys.exit(f"Missing MSYS2 dav1d static library/headers at {MSYS_UCRT}")
    shutil.copy2(dav_lib, deps_dst / "lib" / "libdav1d.a")
    copy_tree(dav_inc, deps_dst / "include" / "dav1d")

    (deps_dst / "bin").mkdir(parents=True, exist_ok=True)
    for dll in ("SDL3.dll", "libopus-0.dll"):
        shutil.copy2(deps_src / "bin" / dll, deps_dst / "bin" / dll)

    b = stage / "bin"
    b.mkdir(parents=True, exist_ok=True)
    ensure_standalone_ninja(b / "ninja.exe")
    for dll in ("SDL3.dll", "libopus-0.dll"):
        shutil.copy2(deps_src / "bin" / dll, b / dll)
    for font_name in ("Roboto-Medium.ttf", "LICENSE-Roboto.txt"):
        shutil.copy2(ROOT / "runtime" / "ui" / "fonts" / font_name, b / font_name)

    # Prefer this branch's 29-patch ns2_xlate.exe (including 0028 + 0029 Yoshi fixes)
    xlate_cand = [
        (ROOT / "build" / "xlate" / "ns2_xlate.exe", ROOT / "build" / "xlate" / "ns2_xlate.id"),
        (YOSHI_BUILD / "ns2_xlate.exe", YOSHI_BUILD / "ns2_xlate.id"),
    ]
    x_exe, x_id = next(((e, i) for e, i in xlate_cand if e.is_file()), (None, None))
    if not x_exe:
        sys.exit("Missing ns2_xlate.exe")
    shutil.copy2(x_exe, b / "ns2_xlate.exe")
    if x_id and x_id.is_file():
        shutil.copy2(x_id, b / "ns2_xlate.id")


def stage_sources_and_runtime_lib(stage: Path, llvm: Path, gen_dir: Path, lib_work: Path, ver: str) -> None:
    rt_src = ROOT / "runtime"
    rt_dst = stage / "runtime"

    # Build libyatmbrt.a cleanly using staged llvm & staged deps so ABI matches 100%
    if lib_work.exists():
        shutil.rmtree(lib_work)
    lib_work.mkdir(parents=True, exist_ok=True)
    run(
        [
            sys.executable,
            ROOT / "tools" / "build_game.py",
            "--make-runtime-lib",
            "--version",
            "yoshi102",
            "--expected",
            ROOT / "tools" / "data" / "expected-yoshi102.json",
            "--gen",
            gen_dir,
            "--out",
            lib_work,
            "--toolchain",
            llvm,
            "--deps",
            rt_dst / "deps",
            "--ninja",
            stage / "bin" / "ninja.exe",
        ]
    )
    built_lib = next(
        (p for p in (lib_work / "libyatmbrt.a", lib_work / "libtotkrt.a") if p.is_file()),
        None,
    )
    if built_lib is None:
        sys.exit(f"Expected libyatmbrt.a or libtotkrt.a in {lib_work} from --make-runtime-lib")
    shutil.copy2(built_lib, rt_dst / "libyatmbrt.a")

    # Stage runtime headers, INSTALL_SIDE C sources, Yoshi resources, fonts, and shaders (NO other games' icons/.rc!)
    keep_names = {
        "romfs.c", "patches.c", "ov_zstd.c",
        "yatmb.rc", "yatmb.manifest", "yatmb.ico", "yatmb.png", "yatmb_book.png",
        "Roboto-Medium.ttf", "LICENSE-Roboto.txt",
    }
    for p in sorted(rt_src.rglob("*")):
        if p.is_dir():
            continue
        rel = p.relative_to(rt_src)
        rel_posix = rel.as_posix()
        if rel_posix.startswith(("deps/", "__pycache__/")):
            continue
        if rel_posix.startswith("shaders/"):
            pass
        elif rel_posix.startswith("third_party/"):
            if p.suffix.lower() not in {".h", ".hpp", ".inc", ".txt", ".md"} and "LICENSE" not in p.name:
                continue
        elif p.suffix.lower() not in {".h", ".inc"} and p.name not in keep_names:
            continue
        out = rt_dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, out)

    # recomp/ (Yoshi patches only)
    recomp_dst = stage / "recomp"
    for p in sorted((ROOT / "recomp").rglob("*")):
        if p.is_dir() or "__pycache__" in p.parts:
            continue
        if p.name.startswith("patches-") and p.name != "patches-yoshi102.txt":
            continue
        if p.suffix.lower() not in {".py", ".txt", ".md"}:
            continue
        rel = p.relative_to(ROOT / "recomp")
        out = recomp_dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, out)

    # tools/ (Yoshi scripts & expected-yoshi102.json only)
    tools_dst = stage / "tools"
    tools_dst.mkdir(parents=True, exist_ok=True)
    for name in TOOLS_FILES:
        src = ROOT / "tools" / name
        if src.is_file():
            shutil.copy2(src, tools_dst / name)
    (tools_dst / "data").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "tools" / "data" / "expected-yoshi102.json", tools_dst / "data" / "expected-yoshi102.json")
    vendor_mng = ROOT / "tools" / "vendor" / "macnativegames"
    if vendor_mng.is_dir():
        copy_tree(vendor_mng, tools_dst / "vendor" / "macnativegames", lambda r: "__pycache__" in r)

    # Root docs/icons/config template (NEVER a personal yatmb.ini!)
    shutil.copy2(ROOT / "yatmb.ini.example", stage / "yatmb.ini.example")
    shutil.copy2(ROOT / "runtime" / "yatmb.ico", stage / "yatmb.ico")
    (stage / "VERSION").write_text(ver + "\n", encoding="utf-8")
    shutil.copy2(ROOT / "LICENSE", stage / "LICENSE")
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", stage / "THIRD_PARTY_NOTICES.md")

    lic_dst = stage / "licenses"
    lic_dst.mkdir(parents=True, exist_ok=True)
    llvm_lic = MKW_CACHE / "win" / "llvm-mingw" / "LICENSE.TXT"
    if llvm_lic.is_file():
        shutil.copy2(llvm_lic, lic_dst / "llvm-mingw-LICENSE.TXT")
    fsr_lic = ROOT / "runtime" / "shaders" / "ffx" / "LICENSE.txt"
    if fsr_lic.is_file():
        shutil.copy2(fsr_lic, lic_dst / "FidelityFX-FSR-LICENSE.txt")


def verify_clean_stage(stage: Path) -> None:
    forbidden_names = {
        "yatmb.ini", "ff.ini", "mtf.ini", "dkb.ini", "totk.ini", "mkw.ini",
        "yatmb.exe", "ff.exe", "mtf.exe", "dkb.exe", "totk.exe", "mkw.exe",
        "dkblauncher.exe", "mtflauncher.exe", "fflauncher.exe",
        "dkb.ico", "totk.ico", "mtf.ico", "ff.ico",
        "dkb.rc", "totk.rc", "mtf.rc", "ff.rc", "totk_xlate.exe",
    }
    forbidden_parts = {"exefs", "romfs", "romfs_packed", "generated", "spirv", "profile", "save", "logs", "shader-cache"}
    bad: list[str] = []
    file_count = 0
    for p in sorted(stage.rglob("*")):
        if not p.is_file():
            continue
        file_count += 1
        rel = p.relative_to(stage)
        rel_posix = rel.as_posix()
        parts_low = {part.lower() for part in rel.parts[:-1]}
        hit_dirs = parts_low & forbidden_parts
        if hit_dirs == {"profile"} and rel_posix.startswith("llvm/lib/clang/"):
            hit_dirs = set()
        if hit_dirs:
            bad.append(f"{rel_posix}: forbidden runtime/game directory segment ({sorted(hit_dirs)})")
        name_low = p.name.lower()
        if name_low in forbidden_names or name_low.endswith((".save", ".nsp", ".xci", ".nca", ".nup")):
            bad.append(f"{rel.as_posix()}: forbidden file name {p.name}")
        for prob in check_content.problems_for(p, allow_large=True):
            bad.append(f"{rel.as_posix()}: {prob}")
    if bad:
        sys.exit("Release stage validation FAILED:\n" + "\n".join(bad[:50]))
    print(f"verify_clean_stage: {file_count} files passed check_content + allowlist rules (zero dev INI/game files).")


def compile_setup_stub(work: Path, ver: str) -> Path:
    sdl_static = MKW_CACHE / "win" / "sdl-static"
    deps = MKW_CACHE / "win" / "deps"
    llvm_bin = MKW_CACHE / "win" / "llvm-mingw" / "bin"
    cxx = llvm_bin / "x86_64-w64-mingw32-clang++.exe"
    windres = llvm_bin / "x86_64-w64-mingw32-windres.exe"
    if not (sdl_static / "lib" / "libSDL3.a").is_file():
        sys.exit(f"Missing static SDL3 at {sdl_static}")

    nums = [int(x) for x in ver.split(".") if x.isdigit()]
    while len(nums) < 4:
        nums.append(0)
    ver_csv = ",".join(str(x) for x in nums[:4])

    rc_dir = work / "rc"
    rc_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "runtime" / "yatmb.ico", rc_dir / "yatmb.ico")
    shutil.copy2(ROOT / "runtime" / "yatmb.manifest", rc_dir / "yatmb.manifest")
    rc = rc_dir / "setup.rc"
    rc.write_text(
        '#include <winver.h>\n'
        '1 ICON "yatmb.ico"\n'
        '1 24 "yatmb.manifest"\n'
        'VS_VERSION_INFO VERSIONINFO\n'
        f' FILEVERSION {ver_csv}\n'
        f' PRODUCTVERSION {ver_csv}\n'
        ' FILEOS VOS_NT_WINDOWS32\n'
        ' FILETYPE VFT_APP\n'
        'BEGIN\n'
        '  BLOCK "StringFileInfo"\n'
        '  BEGIN\n'
        '    BLOCK "040904B0"\n'
        '    BEGIN\n'
        '      VALUE "CompanyName", "SteelTemple"\n'
        '      VALUE "FileDescription", "SteelTemple YATMB Setup Wizard"\n'
        '      VALUE "ProductName", "Yoshi and the Mysterious Book PC"\n'
        f'      VALUE "FileVersion", "{ver}"\n'
        f'      VALUE "ProductVersion", "{ver}"\n'
        '    END\n'
        '  END\n'
        '  BLOCK "VarFileInfo"\n'
        '  BEGIN\n'
        '    VALUE "Translation", 0x409, 1200\n'
        '  END\n'
        'END\n',
        encoding="utf-8",
    )
    res = work / "setup.res.o"
    run([windres, "-O", "coff", "-I", rc_dir, rc, "-o", res])

    imgui = ROOT / "runtime" / "third_party" / "imgui"
    mkw_imgui = MKW_CACHE.parent / "runtime" / "third_party" / "imgui"
    backends = imgui if (imgui / "backends" / "imgui_impl_sdl3.cpp").is_file() else mkw_imgui
    srcs = [
        ROOT / "tools" / "installer_yatmb" / "installer.cpp",
        imgui / "imgui.cpp",
        imgui / "imgui_draw.cpp",
        imgui / "imgui_tables.cpp",
        imgui / "imgui_widgets.cpp",
        backends / "backends" / "imgui_impl_sdl3.cpp",
        backends / "backends" / "imgui_impl_sdlrenderer3.cpp",
    ]
    stub = work / "setup-stub.exe"
    run(
        [
            cxx,
            "-std=c++20",
            "-O2",
            "-Wall",
            "-mwindows",
            "-static",
            "-DUNICODE",
            f"-I{sdl_static / 'include'}",
            f"-I{imgui}",
            f"-I{backends}",
            f"-I{deps / 'include'}",
            *srcs,
            res,
            "-o",
            stub,
            f"-L{sdl_static / 'lib'}",
            "-lSDL3",
            deps / "lib" / "libzstd.a",
            "-lsetupapi",
            "-lwinmm",
            "-limm32",
            "-lversion",
            "-lole32",
            "-loleaut32",
            "-luuid",
            "-lgdi32",
            "-luser32",
            "-lshell32",
            "-ladvapi32",
            "-lcfgmgr32",
        ]
    )
    return stub


def pack_setup_with_py314(py314: Path, stub: Path, stage: Path, out_exe: Path, ver: str, level: int) -> None:
    """Use staged Python 3.14's built-in compression.zstd module to pack YATMBV01 payload cleanly."""
    script = (
        "import struct, sys\n"
        "from pathlib import Path\n"
        "from compression import zstd\n"
        "stub, stage, out_exe, ver, lvl = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4].encode(), int(sys.argv[5])\n"
        "MAGIC = b'YATMBV01'\n"
        "files = sorted(p for p in stage.rglob('*') if p.is_file())\n"
        "total = sum(p.stat().st_size for p in files)\n"
        "out_exe.parent.mkdir(parents=True, exist_ok=True)\n"
        "with out_exe.open('wb') as f:\n"
        "    f.write(stub.read_bytes())\n"
        "    off = f.tell()\n"
        "    f.write(MAGIC + struct.pack('<IQI', len(files), total, len(ver)) + ver)\n"
        "    for i, p in enumerate(files):\n"
        "        rel = p.relative_to(stage).as_posix().encode()\n"
        "        comp = zstd.compress(p.read_bytes(), level=lvl)\n"
        "        f.write(struct.pack('<H', len(rel)) + rel + struct.pack('<QQ', p.stat().st_size, len(comp)) + comp)\n"
        "        if i % 300 == 0:\n"
        "            print(f'  pack {i}/{len(files)} {rel.decode()}', flush=True)\n"
        "    f.write(struct.pack('<Q', off) + MAGIC)\n"
        "print(f'{out_exe}: {len(files)} files ({total/2**20:.1f} MiB -> {out_exe.stat().st_size/2**20:.1f} MiB)')\n"
    )
    run([py314 / "python.exe", "-B", "-I", "-c", script, stub, stage, out_exe, ver, str(level)], env=clean_env(py314))


def write_release_zips(stage: Path, out_dir: Path, slug: str) -> None:
    files = sorted(p for p in stage.rglob("*") if p.is_file())
    now = time.gmtime()
    zip_time = (max(now.tm_year, 1980), now.tm_mon, now.tm_mday, now.tm_hour, now.tm_min, now.tm_sec)
    for kind in ("Portable-StandAlone", "Update"):
        out_zip = out_dir / f"SteelTemple-YATMB-{slug}-{kind}.zip"
        with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for p in files:
                info = zipfile.ZipInfo("YATMB/" + p.relative_to(stage).as_posix(), zip_time)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                z.writestr(info, p.read_bytes(), compresslevel=6)
        digest = hashlib.sha256(out_zip.read_bytes()).hexdigest()
        print(f"{out_zip}: {out_zip.stat().st_size / 2**20:.1f} MiB  sha256 {digest}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ROOT / "build" / "release-yatmb")
    ap.add_argument("--gen", type=Path, default=Path(r"C:\Games\Yoshi and the Mysterious Book PC\generated\yoshi102"),
                    help="Lifted Yoshi 1.0.2 layout directory used solely to compile libyatmbrt.a headers (not bundled)")
    ap.add_argument("--version", default="", help="Override release version string (default: launcher/yatmb_version.txt)")
    ap.add_argument("--level", type=int, default=19, help="zstd compression level for Full-Setup-Wizard (default 19)")
    ap.add_argument("--skip-launcher-build", action="store_true", help="Reuse existing dist/YATMBLauncher.exe")
    args = ap.parse_args()

    t0 = time.time()
    ver = args.version.strip() or read_version()
    slug = version_slug(ver)
    out_dir = args.out.resolve()
    stage = out_dir / "stage" / "YATMB"
    work = out_dir / "work"
    shutil.rmtree(stage, ignore_errors=True)
    shutil.rmtree(work, ignore_errors=True)
    stage.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)

    launcher_exe = (ROOT / "dist" / "YATMBLauncher.exe") if args.skip_launcher_build else build_launcher()
    if not launcher_exe.is_file():
        launcher_exe = build_launcher()
    shutil.copy2(launcher_exe, stage / "YATMBLauncher.exe")

    py314 = stage_python(stage)
    llvm = stage_llvm(stage)
    stage_deps_and_bin(stage)
    stage_sources_and_runtime_lib(stage, llvm, args.gen.resolve(), work / "libbuild", ver)
    verify_clean_stage(stage)

    stub = compile_setup_stub(work / "stubbuild", ver)
    setup_exe = out_dir / f"SteelTemple-YATMB-{slug}-Full-Setup-Wizard.exe"
    pack_setup_with_py314(py314, stub, stage, setup_exe, ver, args.level)
    setup_sha = hashlib.sha256(setup_exe.read_bytes()).hexdigest()
    print(f"{setup_exe}: {setup_exe.stat().st_size / 2**20:.1f} MiB  sha256 {setup_sha}")
    write_release_zips(stage, out_dir, slug)
    print(f"Done in {time.time() - t0:.1f} s -> {out_dir}")


if __name__ == "__main__":
    main()
