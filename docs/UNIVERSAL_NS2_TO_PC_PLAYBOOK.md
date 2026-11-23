# The Universal NS2 to PC Playbook & AI Guide

> **A complete engineering & AI prompting playbook for the "Universal NS2 to PC" Static Recompiler.**  
> **Workspace:** `C:\Games\DKB PC\Universal-NS2-to-PC`

This playbook replaces game-by-game repo forks with one unified, game-agnostic Switch 2 static recompilation engine (`Universal NS2 to PC`). It combines:
1. **TotK Recomp** (`valentderah`): Ahead-of-time ARM64-to-C lifter (`recomp/`), Horizon OS runtime, differential Unicorn testing, and Vulkan renderer.
2. **DKB / MTF / MKW Switch 2 Recomp**: NVN 2 front-end (`runtime/nvn_*.c`), Switch 2 6-core threading, `nn::codec` VP9 host decoder (`runtime/ov_codec.c`), and Ampere-to-Maxwell lowering (`runtime/nvn2_lower.cpp`).
3. **Pre-Flight Intelligence (`tools/universal_ns2_to_pc.py`)** inspired by **NotRexed's Hookshot (`nx2/`)**: Scans ExeFS + RomFS *before* lifting C so every AI model sees exact module relocations, `sdk -> app` imports, ARM64 opcode coverage, NVN 2 proc deltas, paired BNSH stages, SM86 shader opcodes, and Switch 2 `Ounc` texture hazards upfront.
4. **Cross-Emulator Breakthroughs**:
   - **Eglantine (`notsapinho/Eglantine`, commits `7dde4f15`, `77875bb6`, `a2042312`, `7ed597d6`):** Ampere SM86-to-Maxwell lowering, read-only SSBO/bindless fixes, `B10G11R11F` vertex attribute handling, and compute shared memory fixes.
   - **Fritchii (`Frizti/Fritchii` + `NX2_NOTES.md`, commits `724aede4`, `1ca9f7d5`, `2940d9fa`, `4f9b9624`):** Switch 2 `nvdrv` / `nvnflinger` display format behavior, SM86 `TEX`/`FSETP`/`SHFL` fixes, and NVN 2 service structure.
   - **Lichii & Lichii-fg (`zortos293/Lichii`, commits `bcb37c49`, `d2eaae4f`, `536853e7`, `314e1d94`, + `cirnoice9/Lichii-fg`):** `robustBufferAccess2`, `VK_PIPELINE_CREATE_DISABLE_OPTIMIZATION_BIT` (`NS2_VK_NOOPT`) safe shader compilation for driver-hanging SM86 shaders, sparse/buffer guards, and frame generation pacing.
   - **MacNativeGames (`ly05010419/MacNativeGames`):** Horizon OS runtime, NPDM/dynamic linking, and audio renderer hardening.

---

## 1. Architecture Overview (Why One Unified Engine Works)

Instead of cloning and hardcoding `dkb.*` / `mtf.*` / `mkw.*` across 20 files, **Universal NS2 to PC** separates game-specific rules from shared subsystems:

| Subsystem | Role in Universal NS2 to PC | Key Files |
| --- | --- | --- |
| **Pre-Flight Profiler & Builder** | Scans `exefs/` + `romfs/`, builds `expected-<ver>.json`, lifts C, invokes MSYS2 Clang build | `tools/universal_ns2_to_pc.py`, `tools/build_game.py` |
| **Game Profile Registry** | Detects `rt_application_id`, weak `rt_game_short_name[]`, `rt_game_display_name[]`, and quirk flags (`GAME_QUIRK_*`) | `runtime/game_profile.h`, `runtime/game_profile.c` |
| **Unified Config & Aliases** | Primary `NS2_*` settings stored in `<short>.ini`; accepts legacy `MTF_`, `MKW_`, `DKB_`, `OOT_`, `TOTK_` aliases | `runtime/cfg.c` |
| **Live Resolution & Mode Hooks** | Syncs live `NS2_OPERATION_MODE` (`docked`/`handheld`), Horizon events `0x1e`/`0x1f`, `ov_graphics_scale()`, `OUTPUT_RES`, and `RENDER_SCALE` | `runtime/resolution.c`, `runtime/ov_system.c`, `runtime/nvn_api_obj.c`, `runtime/gfx_present.c` |
| **Midnight Glass Overlay** | Built by default (`F1` / `Back+Y`). Live toggles, Inspector Card (`[LIVE]`/`[RESTART]`/`[ENV]`), `FPS_LIMIT` (`30..240\|display`), pipeline telemetry | `runtime/ui/menu.cpp`, `runtime/ui/option_rows.cpp`, `runtime/ui/option_rows.h` |
| **Safe Shader Pipeline** | `VK_PIPELINE_CREATE_DISABLE_OPTIMIZATION_BIT` toggle (`NS2_VK_NOOPT`) + NativeAOT Ryujinx SPIR-V translator (`*_xlate.exe/.id`) | `runtime/vk_crumbs.c`, `runtime/gfx_shader.c`, `tools/build_xlate.py` |

### Registered `GAME_QUIRK_*` Flags (`runtime/game_profile.h`)

Never scatter `if (strstr(game, "..."))` across the codebase. Add a clean flag in `runtime/game_profile.h` + `runtime/game_profile.c`:
- `GAME_QUIRK_PT_BR` — Localization / PT-BR profile handling
- `GAME_QUIRK_MTF_WORKER_ARGS` — Redirected guest worker args for Mario Tennis Fever (`0x0400D4201C6EA000`)
- `GAME_QUIRK_MKW_HEAP_FALLBACK` — Mario Kart World large heap fallback (`0x0400C3F00006E000`)
- `GAME_QUIRK_MKW_VTABLES` — Mario Kart World vtable patches
- `GAME_QUIRK_TOTK_PATCH_RES` — Switch 1 TotK-style resolution patch checks
- `GAME_QUIRK_RTLD_ORDER` — Load-order default-visibility symbol binding (`runtime/loader.c`) for duplicated SDK/subsdk singletons
- `GAME_QUIRK_GRAPHICS_SCALE_ZERO` — Return graphics scale `0` in `ov_graphics_scale()` (`runtime/ov_system.c`)
- `GAME_QUIRK_UE5_CVAR_RES` — Drive native `NS2_RESOLUTION` (`720p`–`2160p`) via UE5 `IConsoleManager` CVar hooks and linear UI DPI scaling (`runtime/resolution.c`)

---

## 2. Standard Bring-Up Workflow (Scan -> Init -> Build -> Probe -> Boot)

### One-Command Turnkey Port (`port` / `auto`)
Point directly at **any** Switch 2 game folder (containing `exefs`/`romfs`, loose NSOs, or SubSDKs) and let the engine discover layouts, pack loose RomFS if needed, stage metadata inside `build/<ver>/`, lift ARM64 -> C, compile & link with MSYS2 Clang + Ninja, deploy `ns2_xlate.exe` + fonts + `<short>.ini`, and run the repo content guard automatically:
```powershell
$env:PATH = "C:\msys64\ucrt64\bin;$env:PATH"
python tools\universal_ns2_to_pc.py port --folder "<GAME_FOLDER>"
```
(Pass `--save-expected` only if you want `tools/data/expected-<ver>.json` and `recomp/patches-<ver>.txt` persisted in git-tracked paths; by default `port` stages them inside gitignored `build/<ver>/` so your repo stays clean.)

### Manual Step-by-Step Pipeline (`scan` -> `init` -> `build`)
Every new Nintendo Switch 2 game can also be run step-by-step from `C:\Games\DKB PC\Universal-NS2-to-PC` (using `--folder "<GAME_FOLDER>"` or explicit `--exefs` / `--romfs`):

### Step 1: Build the NativeAOT Shader Translator (once per machine/update)
```powershell
python tools\build_xlate.py
```
Outputs `build\xlate\totk_xlate.exe` + `totk_xlate.id` (and `mkw_xlate.*`). `runtime/gfx_shader.c` searches `ns2_xlate`, `mtf_xlate`, `mkw_xlate`, `dkb_xlate`, `oot_xlate`, `totk_xlate`.

### Step 2: Run the Smart Pre-Flight Scanner (`scan`)
```powershell
python tools\universal_ns2_to_pc.py scan --exefs "<path>\exefs" --romfs "<path>\romfs" --max-textures 200
```
**What `scan` catches before you write 1 line of C:**
- **Title ID & Extra Modules:** Detects `subsdk0`, `subsdk1`, etc. (`rtld`, `main`, `main.npdm`, `sdk`).
- **ELF Relocations:** Reports `DT_RELR`, `R_AARCH64_ABS64`, `R_AARCH64_GLOB_DAT`, `R_AARCH64_JUMP_SLOT`, `R_AARCH64_TLSDESC`.
- **Exact `sdk -> app` Imports:** Counts hooked vs unhooked `nn::*` namespaces (`nn::audio`, `nn::os`, `nn::movie`, `nn::async`, `nn::codec`, `nn::socket`, etc.).
- **ARM64 Lifter Coverage:** Samples distinct `.text` words directly through `recomp/lifter.py` (`Lifter(...).lift(...)`) and flags unhandled encodings immediately.
- **NVN 2 Proc Coverage:** Cross-checks game NVN string table against `nvn_procs*.inc`.
- **Shader Census & Ampere SM86 Audit:** Walks RomFS (`.bfsha`, `.sharcb`, `.bnsh`, SARC+Zstd) to count all 9 BNSH shader slots, pipeline stage pairs (e.g. `vertex+pixel`, `compute`), `>5K`-insn stall shaders, and SM86 opcodes vs `lower_to_maxwell.h`.
- **Switch 2 `Ounc` Texture & Container Audit:** Detects Switch 2 `+4` byte `Ounc` `BRTI` headers (`SurfaceFormat` at `+0x1C`, dims `<4I` at `+0x24`), `>256M` texel sparse hazards, huge arrays (`layers=46`), media streams, and monolithic archives (`CRA.` magic).

### Step 3: Initialize Game Metadata & Patch Table (`init`)
```powershell
python tools\universal_ns2_to_pc.py init --ver mygame100 --short mygame --name "My NS2 Title" --display 1.0.0 --exefs "<path>\exefs" --romfs "<path>\romfs"
```
Creates:
- `tools/data/expected-mygame100.json` (hashes + `short_name` + `display_name` + `title_id` only; zero game bytes)
- `recomp/patches-mygame100.txt` (empty patch table)

### Step 4: Lift ARM64 -> C & Compile Native PC Executable (`build`)
```powershell
python tools\universal_ns2_to_pc.py build --ver mygame100 --exefs "<path>\exefs" --romfs "<path>\romfs_or_packed"
```
(Make sure `C:\msys64\ucrt64\bin` is first on `PATH` so MSYS2 UCRT64 Clang & Ninja are used — never `cl.exe`!)

To recompile runtime C/C++ changes fast against existing lifted C:
```powershell
$env:PATH = "C:\msys64\ucrt64\bin;$env:PATH"
python tools\build_game.py --version <ver> --gen "<gen_dir>" --exefs "<exefs_dir>" --romfs "<romfs_dir>" --out "build\<ver>"
```

### Step 5: Mandatory Baseline Smoke Checks (F0 -> F5 Order)
Always run in strict layer order so you never debug F4 Vulkan bugs caused by F0/F1 failures:
```powershell
.\build\<ver>\<short>.exe --selftest        # F0: dispatch table, memory map, heap/alias, CPU caps
.\build\<ver>\<short>.exe --probe-cfg       # Config parser + ImGui option_rows test_parse()
.\build\<ver>\<short>.exe --probe-gfx-abi   # F2: NVN2 struct layouts & ABI sizes
.\build\<ver>\<short>.exe --probe-window    # F4: Vulkan swapchain, ImGui overlay open/close, vsync
$env:TOTK_GPU="null"
.\build\<ver>\<short>.exe --seconds 4       # F1: Headless Horizon OS boot (threads, FS, audren, codec)
Remove-Item Env:TOTK_GPU -ErrorAction SilentlyContinue
.\build\<ver>\<short>.exe --seconds 4       # F2-F4: Full Vulkan GPU pipeline + present check
```
Inspect `build\<ver>\logs\<short>.log` after every run! Never skip `TOTK_SHARED_FONTS` if a title calls `nn::pl::GetSharedFontSize`.

---

## 3. Switch 2 Hardware & File-Format Gotchas (Verified)

1. **BNTX `Ounc` vs `NX  ` Header Offset (+4 Bytes):**
   - Switch 2 textures (`target = "Ounc"` at `b[0x20:0x24]`) store `BRTI` `SurfaceFormat` at `+0x1C` (vs `+0x18` on Switch 1 `NX  `) and `<4I` `(width, height, depth, arrayLayers)` at `+0x24` (vs `+0x20`).
   - Do **not** blindly fall back to uncompressed RGBA8 decoding for large arrays (`layers=46`, `8192x8192`): use native BCn/ASTC Vulkan paths or CompactLayers + sparse `MapVirtual`.
2. **Switch 2 `GetCurrentGraphicsScale` Enum:**
   - Switch 2 returns enum `0..2` (`0` = handheld/conservative, `1` = balanced, `2` = docked), **not** Switch 1 `10`/`20`. `runtime/ov_system.c` maps `ov_graphics_scale()` cleanly and fires OS messages `0x1e` / `0x1f` + display resolution change events when toggled live.
3. **MSVC `cl.exe` Cannot Compile Lifted C:**
   - Generated chunks rely on GNU C extensions. Always build with MSYS2 UCRT64 Clang (`C:\msys64\ucrt64\bin\clang.exe`).
4. **Driver Shader Stalls / Miscompiles:**
   - If a game hangs or crashes inside Vulkan `vkCreateGraphicsPipelines` on a giant (`>5K`-insn) SM86 shader, toggle **Safe Shader Compile (`NS2_VK_NOOPT=1`)** in the in-game menu (`F1`) to pass `VK_PIPELINE_CREATE_DISABLE_OPTIMIZATION_BIT` via `vk_pipeline_capture_flags()`.
5. **Repo Content Guard:**
   - Everything extracted or lifted must stay in `build/`, `generated/`, or external game folders. Always run `python tools/check_content.py` (or `--staged`) before committing.

---

## 4. Copy-Paste AI Starter Prompt (For Any Future AI Starting on This Repo)

Copy and paste this prompt when starting a new Switch 2 title or debugging F0-F5 in `C:\Games\DKB PC\Universal-NS2-to-PC`:

```text
You are working inside the "Universal NS2 to PC" static recompiler repository at:
C:\Games\DKB PC\Universal-NS2-to-PC

Read AGENTS.md and docs\UNIVERSAL_NS2_TO_PC_PLAYBOOK.md first. Follow these strict rules:

1. WORKFLOW ORDER:
   - Never guess what the game uses. First run:
     python tools\universal_ns2_to_pc.py scan --exefs "<GAME_EXEFS>" --romfs "<GAME_ROMFS>"
   - Review Title ID, extra modules (subsdk*), unhooked nn:: namespaces, NVN2 missing procs,
     ARM64 lifter unhandled count, BNSH shader stages/pairs, SM86 opcodes vs lower_to_maxwell.h,
     huge >5K shaders, and Switch 2 Ounc BNTX textures.
   - Initialize metadata with:
     python tools\universal_ns2_to_pc.py init --ver <ver> --short <short> --name "<Game Name>" --exefs "<GAME_EXEFS>" --romfs "<GAME_ROMFS>"

2. MULTI-GAME ARCHITECTURE RULES:
   - NEVER fork or hardcode a single game name across core runtime files.
   - Register Title ID quirks cleanly in runtime/game_profile.h and runtime/game_profile.c (GAME_QUIRK_*).
   - Use NS2_* primary config keys in runtime/cfg.c + runtime/ui/option_rows.cpp so live HUD controls
     (Console Mode, Output Res, Render Scale, Res Hook, Upscalers, Safe Shader Compile, FPS Limit)
     stay unified across all games.

3. BUILD & LAYERED VERIFICATION (F0 -> F5):
   - Always compile C/C++ with MSYS2 UCRT64 Clang (C:\msys64\ucrt64\bin first on PATH) and Ninja.
   - Verify after EVERY change:
     a) --selftest and --probe-cfg and --probe-gfx-abi
     b) --probe-window (verifies Vulkan swapchain + ImGui HUD overlay)
     c) TOTK_GPU=null <short>.exe --seconds 4 (F0/F1 Horizon OS bring-up & logs/<short>.log)
     d) Full Vulkan <short>.exe --seconds 4 (F2-F4 shaders, pipelines, presents)
   - If you hit SM86 shader miscompiles or NVN2/Horizon issues, consult runtime/third_party/eglantine/,
     runtime/nvn2_lower.cpp, and the cross-emulator fixes documented in docs/UNIVERSAL_NS2_TO_PC_PLAYBOOK.md.

4. REPO HYGIENE:
   - Keep all game dumps, lifted C, and binaries outside git-tracked paths.
   - Run `python tools/check_content.py` before finishing.
```

---

## 5. Crucial Switch 2 Findings & Solutions (Fast Fusion & Beyond)

### 5.1. Massive Vertex Explosions: Speculative SSBO DMA Writeback
- **Symptom:** The 3D scene shows giant skewed polygon sheets, skewed triangles, or exploded vertex geometry covering the screen, while 2D UI/HUD remains intact.
- **Root Cause:** In branching compute/graphics dispatches, `GlobalToStorage.cs` registers every candidate storage buffer expression with `BufferUsageFlags.Write` for SPIR-V validator safety. In `runtime/vk_exec_draw.c`, `ssbo_info` binds these speculative candidates with `guarded=1` (`direct_only=1`). If `vk_mem_gpu_wrote(&sp, n)` and `note_written` are called for candidate buffers, the engine schedules full-extent (`n = 120 KiB+` or pool remainder) `mbuf -> buf` GPU DMA writebacks at `vk_mem_mirror_end`. Because Windows `GetWriteWatch` only tracks host CPU writes and does not track GPU DMA writes, host memory is overwritten with stale mirror buffer bytes. This clobbers guest host RAM where subsequent draws' vertex buffers reside.
- **Solution:** Speculative guarded storage buffer candidates (root constants, `c1`, UBOs, or unbounded `b->size == 0` pointers) must NEVER schedule full-extent writeback or register completion dirty ranges, whereas explicitly bound NVN2 compute `c0` storage-buffer table entries (`guarded_is_declared_ssbo`: `off >= nvn2_c0_part(c0_lay, 2) && off < nvn2_c0_part(c0_lay, 3) && b->size > 0`) write back only their exact declared `b->size`:
  ```c
  // runtime/vk_exec_draw.c: ssbo_info / bind_range
  int writeback = written && (!guarded || guarded_is_declared_ssbo(st, r, b));
  if (writeback) vk_mem_gpu_wrote(&sp, n);
  if (written) vk_usnap_drop(addr, n);
  ```

### 5.2. Missing Volumetric Fog LUT / Black Skybox: Single-Image Fallback
- **Symptom:** Night/space or foggy courses render with a completely pitch-black skybox or missing atmospheric lighting.
- **Root Cause:** Ampere compute shaders writing to 3D image LUTs (`SUST.P` image store instructions) in NVN2 packed `c0` banks may have image handles where the computed handle byte offset does not match `nvn2_c0_part(&s->c0, 4)` partitions, resulting in `r->slot = -1`. When `r->slot` is negative, `vk_exec_draw.c` binds a 1x1 dummy black texture instead of the target 3D LUT (e.g. `lut738` `160x90x64`).
- **Solution:** When a compute shader declares exactly 1 image in its `c0` layout, fall back to slot 0 if slot resolution yielded negative:
  ```c
  // runtime/gfx_shader.c
  if (kind == GFX_RES_IMG && r->slot < 0 && s->c0.images == 1) r->slot = 0;
  ```

### 5.3. Dynamic Window Title Across Titles
- **Solution:** Rather than hardcoding titles in window creation, use `game_profile()->display_name`:
  ```c
  // runtime/gfx_window_win.c & gfx_window_sdl.c
  const char *dn = game_profile()->display_name;
  swprintf(title_w, sizeof title_w / sizeof title_w[0], L"%hs (PC Recomp)", (dn && *dn) ? dn : "Universal NS2 Title");
  ```

### 5.4. Automatic Shader Translator Deployment
- `tools/build_game.py` automatically deploys `build/xlate/totk_xlate.exe` (and `.id`) to `<out>/ns2_xlate.exe` and `ns2_xlate.id` beside the output executable so every new game build has its native shader translator ready out of the box.

### 5.5. Black Skybox in 3D Passes: Unnormalized Fragment Coord Textures & Depth-Stencil Split Copies
- **Symptom:** Skybox, sunset clouds, and atmospheric haze render pitch black or are clipped away, while vehicles and tracks render normally.
- **Root Cause #1 (Texture Coordinates):** Skybox shaders (e.g. Pass 75 `sh_96b7b3b96d984bcf.spv`) sample depth/normal buffers using `gl_FragCoord.xy` as unnormalized coordinates. In `tools/xlate` (specifically patch `0027-unnormalized-fragment-coord-textures.patch`), if a fragment shader uses screen-space coordinates without explicit normalization, the translator ensures texture coordinates are normalized to `[0.0, 1.0]` for Vulkan sampled images.
- **Root Cause #2 (Dual-Aspect Blit in `copy_t2t`):** Fast Fusion performs texture-to-texture depth copies (`copy_t2t` in `runtime/vk_exec_xfer.c`) on format `0x35` (`DEPTH32F_STENCIL8`). In Vulkan, blitting or resolving combined depth/stencil images requires separate aspect masks (`VK_IMAGE_ASPECT_DEPTH_BIT` and `VK_IMAGE_ASPECT_STENCIL_BIT`). If a combined `DEPTH_BIT | STENCIL_BIT` mask is passed to `vkCmdBlitImage` or if `sub_resolve()` doesn't split aspects (`allow_mode = 2`), the blit command fails or produces invalid/stale depth data. Skybox depth tests then discard all sky fragments against 0.0 depth.
- **Solution:** In `runtime/vk_exec_xfer.c` (`copy_t2t`), enable `allow_mode = 2` for format `0x35` (`DEPTH32F_STENCIL8`), splitting dual-aspect blits into separate depth and stencil passes.

### 5.6. High-Resolution & Emulator-Style Internal Resolution Scaling Hooks (1x, 2x, 3x, 4x -> 4K, 6K, 8K)
- **Symptom:** Setting `output_res = 3840x2160` and `render_scale = 100` or `200` in `.ini` displays the window in 4K, but the 3D scene remains locked to native Switch 2 resolution (1080p canvas with 960x540 internal 3D scene), or produces distorted/halved viewport extents.
- **Root Cause & Engine Architecture (Fast Fusion & NS2 Titles):**
  1. The Switch 2 display configuration singleton resides at `*(uint64_t*)0x700071beb8`.
  2. The game separates canvas composition and 3D scene rendering:
     - `f_700011ff04` writes Output Canvas width and height into `disp_cfg + 0x7068` and `disp_cfg + 0x706c` (docked shipped: 3840x2160, handheld: 1920x1080).
     - `f_700011ff1c` writes Internal 3D Scene width and height into `disp_cfg + 0x7070` and `disp_cfg + 0x7074` (docked shipped: 1920x1080, handheld: 1280x720).
     - Non-canvas callers also call `f_700011ff04` for other objects (e.g. `*(uint64_t*)0x70006ab418` passing `x1 = 1, x2 = 0` mode flags). Unconditionally overriding all calls corrupts secondary structs and inflates passes to invalid dimensions (e.g. `8180x1505`).
  3. `f_70001218cc` reads `disp_cfg + 0x7070` to allocate internal 3D render targets via `nvnTextureInitialize`. If `f_700011ff1c` is not scaled, render targets remain 1080p.
  4. In `main_0002.c:33045` (`f_7000075cc0`), the engine applies dynamic resolution downsampling (`*scale_x` and `*scale_y` at `x21 + 0xb0` and `x21 + 0xb4`), dropping the 1080p buffer down to $0.5\times$ (960x540) before upscaling.
- **Solution & Multiplier Scaling:**
  1. In `runtime/resolution.c`:
     - Allow `SCENE_MAX` up to 16384 (PC GPU texture limits).
     - Support emulator-style multiplier scaling (`1x`, `2x`, `3x`, `4x`) and percentage scaling (`50`, `100`, `200`, `300`, `400`):
       - `1x` (100) = 1920x1080 (Native Switch 2 1080p)
       - `2x` (200, native, 4k) = 3840x2160 (**Native 4K Internal 3D Rendering**)
       - `3x` (300) = 5760x3240 (6K Supersampling)
       - `4x` (400, 8k) = 7680x4320 (8K Supersampling)
     - Add guest wrappers:
       - `__wrap_f_700011ff04`: Guards against non-resolution callers (`c->x[0] == disp_cfg` and `c->x[1] >= 640 && c->x[2] >= 360`), setting output canvas to target display resolution (`output_res`, default 3840x2160).
       - `__wrap_f_700011ff1c`: Slices internal 3D scene resolution to target multiplier (`scene_w x scene_h`), directing `f_70001218cc` to allocate 4K/6K/8K 3D render targets.
       - `__wrap_f_7000075cc0`: Locks `*scale_x = 1.0f` and `*scale_y = 1.0f` so the 3D scene renders to 100% of the internal render target extent without downsampling.
  2. In `runtime/nvn_api_obj.c` (`nvnWindowSetCrop`):
     - Unclamp crop `v = (0, 0, width, height)` when the underlying surface was allocated at output resolution (`3840x2160`).
  3. In `runtime/boot.c` (`save_shot`):
     - Remove hardcoded 1706x960 crop override so full-resolution 4K frames are saved.
  4. In `tools/build_game.py`:
     - Pass `-Wl,--wrap,f_700011ff04,-Wl,--wrap,f_700011ff1c,-Wl,--wrap,f_7000075cc0` when linking Fast Fusion builds.

### 5.7. Native RomFS/ExeFS Preshader Warmer & Host GPU Driver Cache Injection
- **Symptom:** Significant compilation stutter when entering new tracks or encountering new effects.
- **Architecture:**
  - Shaders exist as loose files (e.g. `romfs/shaders/*.shdr`), packed in `romfs.bin` / `index.json`, in game archives (`.w3d`, `.sarc`), or as BNSH/BAHS containers.
  - `.shdr` (`SHN!`) container structure:
    - Header (68 bytes): `ctl_off = hdr[1]` (68), `ctl_sz = hdr[2]`, `code_sz = hdr[3]`, `code_off = hdr[9] + 1`, `code_len = hdr[10] - 1`.
    - Validated by checking `b'SHDROUNC'` at `hdr[1]`.
    - SPH v4 header word 0: `(w0 & 31) in (1, 2) && ((w0 >> 5) & 31) == 4`. Graphics stages: `st = (w0 >> 10) & 15` (1/3: ps, 0: vs, 4: gs). Non-graphics: compute (cs).
  - `tools/shader_census.py`:
    - `shdr_shaders(data)`: Parses `SHN!` containers, creates synthetic 0x880 control section (matching `nvn2_lower` layout), and yields `(key, stage, ctl, code)`.
    - `inventory(romfs, exefs)`: Supports both packed RomFS (`index.json` + `romfs.bin`) and loose RomFS directories (`rglob`).
  - `tools/prepare_shaders.py`:
    - Reads inventoried shaders and merges any runtime-recorded shaders (`shader-programs.bin` and `shader-answers.bin`).
    - Writes `seed-programs.bin` and `seed-answers.bin`.
    - Auto-detects the target game executable in build directory (`ff.exe`, `dkb.exe`, `totk.exe`, etc.).
    - Executes `<game>.exe --prepare-shaders`:
      - The runtime (`runtime/gfx_shader.c` and `runtime/vk_pipeline.c`) compiles all seed variants into SPIR-V.
      - Builds stage libraries and compute pipelines with Vulkan GPL (`graphics_pipeline_library`).
      - Injects prebuilt pipelines directly into the host GPU driver's disk cache (NVIDIA NV_Cache/DXCache, AMD, Intel) and `pipeline-cache.bin`.
      - Writes `shader-prepared.bin` for instant prebuild on subsequent game boots (0 fast-link stutters during gameplay).
  - Integrated into `tools/build_game.py` via `--prepare-shaders` flag.

### 5.8. Pristine Native 4K Clarity & Grain Elimination (FSR 1:1 Bypass, DLSS Optimal Settings Sync, & Post-Process Neutralization)
- **Symptom:** The rendered game image appears noticeably grainy, noisy, or pixelated during gameplay, particularly on surfaces, road textures, and vehicle edges ("super grainy / pixelated, might be just the game").
- **Root Causes Discovered:**
  1. **FSR 1 EASU Running at 1:1 Native Resolution:**
     - In `runtime/vk_fsr.c`, if `sharpness > 0` (e.g. `sharpness = 40` or `10`), the recompiler executed the FSR 1 Edge Adaptive Spatial Upscaling (EASU) compute pass even when destination dimensions matched source dimensions ($3840\times 2160 \to 3840\times 2160$).
     - EASU is an edge-reconstruction spatial interpolator designed for upscaling lower-resolution inputs. Running it at 1:1 softens native subpixel details and introduces ringing artifacts, which the subsequent Robust Contrast Adaptive Sharpening (RCAS) pass aggressively sharpens, turning soft edges into stark pixel halos.
     - The intermediate texture was then transferred to the swapchain using `VK_FILTER_NEAREST`, magnifying any subpixel offset into harsh pixelation.
  2. **NVN2 DLSS Optimal Settings Downsampling:**
     - Fast Fusion relies on NVN2 DLSS APIs (`nvnDlssNetworkBuilderSetOutputResolution` and `nvnDlssNetworkBuilderGetOptimalSettings`).
     - In `runtime/nvn_api_nvn2.c`, the DLSS builder mock accepted hardcoded Switch 2 docked sizes (`1920x1080`) from guest game code and returned `optimal = (1920, 1080)`.
     - In response, the engine's dynamic resolution scaling (DRS) system frequently downsampled internal 3D scene rendering mid-game (e.g. to `1266x712` or `2226x1252`), leading to severe resolution drops and noticeable pixel crawl.
  3. **High Frame Generation Multiplier (6x Optical Flow Noise):**
     - When `fg_mult = 6x` is configured, Nodix Super Motion (SMFG 1.3) computes 5 synthetic frames for every 1 physically rendered frame.
     - At high vehicle speeds ($600+\text{ km/h}$), optical flow vector estimation on stochastic dither patterns produces warping grain and crawling noise.
  4. **Post-Processing Color & Contrast Exaggeration:**
     - Fast Fusion utilizes stochastic blue noise / Bayer dithering for alpha testing, soft shadows, and ambient occlusion, designed to be temporally accumulated.
     - Setting `color_preset = custom` with elevated contrast (`110`), saturation (`125`), and low gamma (`0.95`) amplified tiny dither dots into prominent high-contrast grain.
- **Architectural Fixes Implemented:**
  1. **`runtime/nvn_api_nvn2.c`:**
     - Query `ff_get_target_resolutions(&cw, &ch, &sw, &sh)` in `nvnDlssNetworkBuilderSetOutputResolution`, `GetOutputResolution`, and `GetOptimalSettings`.
     - When output resolution is 4K ($3840\times 2160$), override `out_w/out_h` to $3840\times 2160$ and return `(sw, sh, sw, sh, sw, sh)` as optimal/min/max settings. This locks the game's internal render pipeline to full native resolution ($3840\times 2160$) and prevents DRS downsampling drops.
     - Added logging in `nvnCommandBufferEvaluateDlss` to verify blit extents.
  2. **`runtime/vk_fsr.c`:**
     - If `dw == cw && dh == ch`:
       - If `sharpness <= 0`: Bypass FSR completely (`return 0`), letting `gfx_present.c` perform a clean direct linear blit to the swapchain.
       - If `sharpness > 0`: Skip the EASU pass entirely! Dispatch RCAS directly from `src_view` to `view[0]`, providing pure contrast-adaptive sharpening without spatial blurring or ringing.
     - Switched final swapchain blit from `VK_FILTER_NEAREST` to `VK_FILTER_LINEAR` for smooth presentation.
  3. **`ff.ini` Optimal Presentation Configuration:**
     - `upscaler = off` & `sharpness = 0`: Pristine 1:1 presentation with zero artificial sharpening noise.
     - `color_preset = default`: True neutral colors (brightness=0, contrast=100, saturation=100, gamma=1.0) preventing dither amplification.
     - `frame_gen = 0` / `fg_mult = off` (or clean `2x`): Eliminates high-multiplier optical flow noise.
     - `render_scale = 2x` (or `100` / `200`): Delivers razor-sharp Native 4K ($3840\times 2160$) internal 3D rendering.

### 5.9. Cross-Recompiler & Cross-Emulator First-Launch Hardening
- **ARM64 Lifter, Codegen, & Exclusive Monitor (`recomp/lifter.py`, `recomp/gen.py`, `runtime/cpu.h`):**
  1. **Switch 2 `CNTFRQ_EL0` (31.25 MHz vs 19.2 MHz):** `MRS Xd, CNTFRQ_EL0` calls `rt_tick_hz()` dynamically (`31,250,000` Hz on Switch 2, `19,200,000` Hz on Switch 1) instead of hardcoding `19200000ULL`, eliminating $1.6276\times$ timer/audio/physics skew when games read `CNTFRQ_EL0` inline.
  2. **`adrp`+`add` Clobber Stop & Spin-Loop Compiler Barrier (`mkw-recomp` `60961f0`, `ab1ad52`):** `gen.py` stops backward `adrp` scanning when an intermediate instruction overwrites the base register, and emits `__asm__ volatile("" ::: "memory");` on call-free intra-function backward branches so `-O2` Clang never hoists cross-thread memory polls into infinite loops.
  3. **ABA-Safe 256-Slot Exclusive Monitor (`ldxr`/`stxr`, `ldxp`/`stxp`):** Tracks a monotonic generation counter + 256 cacheline-aligned monitor slots (`rt_excl_mon[256]`) so `A -> B -> A` lock-free queue updates cannot falsely succeed.
- **Ampere SM86 -> Maxwell Shader Lowering (`runtime/third_party/eglantine/`, `runtime/nvn2_lower.cpp`):**
  - Upgraded to `Eglantine` `780a1d0` (216 SM86 opcodes vs 197 previously: `IMAD.WIDE`, `F2I.FTZ.U64.TRUNC`, `WARPSYNC`, generalized `TXD` `0xb6c`, cooperative matrix HMMA expansion, `geometry_exit.h` non-passthrough GS check) + `Orchid` `8837379`/`88fdb54` (unsigned constant-buffer offsets `>= 0x8000` on `0x625`/`0xab9`) + `Orchid` `cf66896` (`CALL.REL.NOINC` `0x7944` subroutine capture) + pure-Maxwell `MUFU.TANH` (`EX2` + `RCP` lowering).
- **CMIF IPC Domain Protocol (`runtime/ipc.h`, `runtime/ipc.c`):**
  - Implements CMIF Control Command `0` (`ConvertCurrentObjectToDomain`), `3` (`CopyFromCurrentDomain`), domain sub-object allocation (`ipc_domain_alloc`), and `CMIF` domain input/output headers (`DomainInHeader` `cmd=1` invoke / `cmd=2` `CloseVirtualHandle`, `DomainOutHeader` sub-object ID emission) so Switch 2 SDK `fs` / `vi` / `hid` / `audren` domain clients never abort on boot.
- **Zero-Firmware Shared Fonts & BFTTF Header Fix (`runtime/ov_system.c`, `runtime/cfg.c`):**
  - Fixed `BFTTF` decryption loop to skip the 8-byte `(magic, size)` header and start XORing at byte `8` so `OTTO` / `\x00\x01\x00\x00` magic lands at `out[0..3]`.
  - When no external Switch font dump is configured, automatically loads bundled `Roboto-Medium.ttf` or Windows system fonts (`segoeui.ttf`, `meiryo.ttc`, `YuGothM.ttc`, `malgun.ttf`, `msyh.ttc`) so every game boots with crisp text on first launch.
- **Switch 2 SDK 20/21 HLE Coverage & NVN2 Procs (`runtime/ov_system.c`, `runtime/ov_input.c`, `runtime/ov_codec.c`, `runtime/nvn_api_*.c`):**
  - Added ~170 Switch 2 SDK symbols across `nn::oe` (SDK 20+ `OperationMode`/`PerformanceMode`, `TryPopNotificationMessage`, launch storage, focus), `nn::fs` (`CommitSaveData`, `MountCacheStorage`, `SetSaveDataRootPath`, priority), `nn::settings`/`nn::time`, `nn::account`/`nn::friends`/`nn::nifm`/`nn::ldn`/`nn::ssl`/`nn::bcat`/`nn::irsensor`/`nn::nfc`/`nn::mii`, `nn::hid` (`NpadJoyHoldType`, `GetNpadStates` arrays, `Palma`, keyboard/mouse/gesture/debugpad), and `nn::codec::HardwareOpusMultiStreamDecoder`.
  - Registered 30 missing NVN2 procs (734 resolved total), added `Hookshot` `upload_all_zero` GPU clear optimization in `runtime/vk_texture.c`, and preserved `VK_IMAGE_USAGE_STORAGE_BIT` on format-reinterpreted storage views in `runtime/vk_exec_draw.c`.

### 5.10. rtld Symbol Binding Order: One Copy of a Library's Singletons (Yoshi and the Mysterious Book, 21 Nov 2026)
- **Symptom:** `FMallocBinned2::Malloc` (`main+0xa3434`) reads `0xffffffffffffffff` (or `0xffffffff + 0x28`) right after `nn::os::GetTlsValue`, called from `movie::Extractor::Extractor` (`subsdk2`). The crash site moves between runs.
- **Cause:** UE's TLS manager owns `nn::os` TLS slot 0 (`AllocateTlsSlot` from `main+0x11634`). The movie library in `subsdk2` imports only `Get/SetTlsValue`. It reads its slot from `nn::movie::detail::HeapMemoryManager::GetInstance()::instance`, which the **sdk** sets up. Both `subsdk2` and `sdk` export that instance (and `LegacyMultimediaAllocator::s_Instance`). The console's rtld binds a default-visibility symbol to the first module in load order (main, subsdk0..9, sdk) that defines it, so both use subsdk2's copy. Our loader bound each module to its own copy, so subsdk2's instance kept slot 0 and `SetTlsValue(0, ...)` overwrote UE's per-thread TLS array on the game thread.
- **Fix:** `GAME_QUIRK_RTLD_ORDER` (`runtime/game_profile.h`). `resolve()` in `runtime/loader.c` binds default-visibility symbols in load order; hidden and protected ones stay with their own module. It is on for `yoshi` only. Other titles have the same duplicated movie singleton (DKB, MTF and MKW in main, SM Wonder in subsdk0). Turning the quirk on for them also moves the sdk's `operator new/delete`, typeinfo and libc++ references to main/subsdk0 (DKB 75, MKW 924, TotK 782, FF 19, MTF 3 relocations). So enable it per title only after a boot test.
- **Diagnostic:** `NS2_CRASH_PEEK=where[*count],...` prints guest words with the crash report. `where` is an address, `xN`, or `tlr`, each with an optional `+offset`; `count` is in words, at most 64.
- **H.264 movies (fixed):** `Movies/OpeningDemo/source/Op_1080.mp4` (also `TitleDemo` and `EndingDemo`) is H.264 Main profile, 1920x1080, level 4.1 (the title movie has B frames). The StaffRoll movies are WebM and take the VP9 host path. Yoshi's movie library drives `nn::codec::H264Decoder` directly, and `InitializeH264Decoder*` used to return `0x1c0001`, on which the SDK aborted. `runtime/ov_codec.c` now runs it on the host as it runs VP9 and AV1: the same buffers, fences and submission-ready event, with the pictures from `runtime/h264_win.c` (Media Foundation's built-in software H.264 decoder). That decoder has a reorder delay, so its pictures wait in a per-decoder FIFO (`pics`) until a buffer is reserved, and the end of the stream drains it. Packets arrive as Annex B. An avcC configuration is turned into Annex B SPS/PPS put in front of the first packet, and length-prefixed packets are converted. Off Windows, `h264_sdl.c` has no decoder and init returns `0x1c0001` as before. This SDK also needed the out-parameter `GetH264DecoderSubmissionReadyEvent(SystemEventType **, H264DecoderType *)`, `CalculateH264DecoderWorkBuffer` and the one-size `InitializeH264Decoder` overrides. Measured: a 60 s null-GPU boot plays the opening movie (NV12 reads at 0.5 to 20 s with varying luma). A 40 s Vulkan run presents 2363 frames with no crash.
- **SM86 lowering (fixed, 21 Nov 2026):** all 120 Yoshi stages captured with `DKB_SHADER_DUMP` now lower (`tools/dkb_lower_test.cpp`: 105 before). A 40 s Vulkan run logs no translation failures. Each fix only takes forms that failed before, so other titles' shaders lower as they did.
  - `0x321` ALD is modelled in the `geometry_exit.h` liveness walker: it reads Ra (bits 24) and the vertex register (bits 32), and writes `1 + bits(74,2)` registers.
  - `0x2bf` UPOPC is lowered like UFLO/UBREV: UR to R216+, then Maxwell POPC.
  - `0x361` TEX.B.LZ with no Rd2 (word 1 `0x38......`, LOD bits 87-89 = 1) is a new path: Rd = result, Ra:Ra+1 = (u, v), Rb = handle (from the captures: the next FADD reads Rd after the sample's scoreboard).
  - `0xf63` TLD4 with a uniform-register handle (2D, and ARRAY_2D when bits 61-63 = 5, layer first) is lowered to Maxwell TLD4.B (`0xdef8`, component bits 38-39, handle in Rb).
  - `0x2bf` and `0xf63` are added to `uses_uniform_bank`.
- **Black frames: per-stage program binding (fixed, 21 Nov 2026):** every render pass replayed with 0 draws. The warnings were "a draw without a bound program is skipped" (85% of draws) and "a draw with a program that has no vertex stage is skipped". Unreal binds a vertex program (`BindProgram(p, 0x1)`), a fragment program (`0x2`) of its own, unbinds geometry (`NULL, 0x4`) and the stage at `0x80`, and binds compute programs (`0x20`) between draws. NVN binds a program for the stages in the mask only, but the replay kept one `ex->prog` and the last bind won. `runtime/vk_exec_draw.c` `bind_program()` now keeps a binding per stage (`VkExec.stage_prog[6]`) and the compute binding (`cprog`, swapped into `ex->prog` for a dispatch). If every bound graphics stage comes from one program (how the other titles bind), `ex->prog` is that program, as before. Otherwise it is a combined `prog_t` built from the bound stages, kept per combination of program serials so its serial, the key of the shader and pipeline caches, stays stable. Diagnosed with `TOTK_DUMP=<frame>` (passes.txt: `draws 0` on every pass) and per-return counters in `prepare_draw`. Result: frames render, with a white page and UI. `--probe-vkexec` (needs TotK's `build/v0/shaders/jobs.json`) and `--probe-nvn` ("2 op kinds were not recorded") fail the same way with and without this change.
- **Text as solid boxes: texture handles in uniform blocks (fixed, 21 Nov 2026):** Unreal keeps its texture and sampler handles in its own uniform buffers (c3 and up), not in the driver's slot tables. The translator describes such a texture with Ryujinx's packed `TextureHandle`: `cbuf_slot` = slot0 | (slot1 + 1) << 16, and `handle` = word0 | word1 << 14 | type << 28. For example, `cbuf_slot 0x40003` with `handle 0x100A0008` is type 1: the texture word at c3+0x20 OR the sampler word at c3+0xA0. `add_res` truncated both values into 8 and 16 bits and set slot -1, so every such texture got handle 0 and the placeholder, and glyph quads filled solid. `GfxShaderRes` now keeps `raw_cbuf` and `raw_handle`. `ubo_handle()` in `runtime/vk_exec_draw.c` resolves the handle from the bound uniform block, reading the replay's inline updates first as `ubo_ptr` does. The resolved handle also goes into the descriptor signature (`RsPtr.tex`), so a change in the block's contents rebuilds the descriptors. Types handled: 0 combined, 1 separate sampler handle (`texture | sampler`, matching `nvnDeviceGetSeparateSamplerHandle` = id << 20), 2 sampler id. Type 3 (constant sampler) and array elements past the first are not handled yet. `vk_dump.c` still prints these textures as "slot -1 … no handle (dummy)", because it reads only the slot tables. Result: the title screen renders with its logo, user selector and "Start Game" prompt (`build\yoshi102\title_screen_vk.png`).
- **Title background (fixed, 21 Nov 2026):** after every program bind Unreal also unbinds the stage at mask 0x80, which is outside VS-CS. The first per-stage version took "no VS-CS bit" as "every stage" and cleared all six. Only a mask of 0 means every stage now. Bits past compute leave the six stages alone. The background (`TitleDemo/Title_1080p.mp4`, decoder mode 1, NV12 read back by the game) renders behind the menu.
- **Low-latency H.264 tried and reverted:** with Media Foundation's `CODECAPI_AVLowLatencyMode` a picture comes out per packet. But the title movie has B frames: a packet then gives 0 or 2 pictures, the eight output buffers and the eight queued packets fill up, and the movie stops 0.6 s in (black background). Without it, the decoder holds its reorder delay (38 packets on a level movie) and the title plays.
- **Next Yoshi blocker: black screen entering the first level.** After New Game the level opens a second H.264 decoder in output mode 2 (format 3). `movie::VideoDecoder::AcquireVideoFrame` takes pixel storage type 3 for it: it calls `nn::codec::GetDecoderImagePoolNativeImageHandle(pool, 0)`, passes the 32-bit handle to `VideoFrame::SetNativeImageHandle`, and the movie library (`NvnExternalTextureDictionary`) turns it into an NVN texture through `nvnNativeImageBuilder*` / `nvnNativeImageInitialize` / `nvnTextureInitializeFromNativeImage` (imported from the sdk, none implemented on the host). `ov_codec.c ov_pool_image` returns 0. The player then flushes and loops on acquire/release forever without submitting, and presents stop. To do: hand out a handle per decoder buffer, implement those NVN entry points, and back the texture with a pool the decoded picture is written into (format per `nvnNativeImageBuilderSetFormat`, still to be read; with a handle of 0 the movie library never gets that far).
- **Texture streaming into GPU-owned textures (fixed, 21 Nov 2026):** Unreal GPU-copies the old mips into a new texture, then writes the new large mips with the CPU; those stayed zero (black Yoshis). `merge_cpu_levels()` in `vk_texture.c` uploads each level whose own whole pages were CPU-written since the last GPU write or merge. Sub-page textures never merge, which is a known limit.
- **`GetEntryType` with a trailing slash (fixed, 22 Nov 2026):** `romfs_entry_type()` now trims trailing separators (`rom:/PJ045/` is a directory) and treats `rom:/` as the root.
- **Fixed (22 Nov 2026): dark close-up terrain/foliage surfaces (`spirv_fmz` on all shader stages by default).** Close-up foreground ground, bark, and rock shaders in Stage 1 compute per-instance albedo variation with `fma(0.0, inversesqrt(0.0), base_albedo)` via SM86 `.FTZ`/`.FMZ` `FFMA`/`FMUL` instructions (`b80=1, b76=0`) where `0 * +Inf = 0` on Switch 2. Without fragment-stage FMZ rewriting, `0.0 * +Inf = NaN`, `fma` propagates `NaN`, and final albedo clamps to `0.0` (black). `vk_pipeline.c` (`make_module_linked`, `spirv_fmz`) now defaults `fmz_mode` to `all` (746 rewritten modules vs 345 vertex-only, 0 Vulkan validation errors) and reuses existing `bvec2`/`bvec3`/`bvec4` declarations. Note: `TOTK_SPV_OVERRIDE` matches post-fixup SPIR-V hashes (`spirv_rebind`/`spirv_fixup`/`spirv_layer_from_viewport`/`spirv_fmz`), not pre-fixup dump hashes. Full details: `docs/YOSHI_HANDOVER.md` §6.
- **Fixed (22 Nov 2026): misplaced/occluding scene geometry & Book Hub GPU perf regression via GPU compute diff write-back (`mirror_diff_wb.comp`, `vk_mem_guarded_write`).** Compute shaders writing `GPUScene` buffers (`PrimitiveSceneData`, `InstanceSceneData`, `InstanceIdsBuffer`) through guarded UBO-pointer SSBOs (`cbuf_slot >= 3`) skip `vk_mem_gpu_wrote()` (`writeback == 0`) to avoid §5.1 speculative DMA clobbering. On mirrored pools (`TOTK_MEMORY=mirror`), skipping writeback left host RAM stale (`105,719` mismatched pages in `TOTK_MEMORY=verify`); when the CPU later wrote an adjacent sub-allocation on the same 4 KiB page, `mirror_sync()` uploaded stale host zeros over `r->mbuf`, collapsing meshes' transforms to `(0, 0, 0)`. Demoting guarded pools to PCIe (`vk_mem_no_mirror`) fixed corruption but pushed Book Hub GPU time from `~3.5 ms` to `65 ms` (`15 fps`). Replacing demotion with `vk_mem_guarded_write()` (`vk.h`, `vk_memory.c`) and a Vulkan 1.1 compute shader (`runtime/shaders/mirror_diff_wb.comp` -> `runtime/mirror_diff_wb_spv.h`, dispatched via `rec_push()` in `vk_mem_mirror_end()`) keeps every guarded pool in fast VRAM alongside a device-local snapshot (`r->msnap`) and writes back ONLY the exact 32-bit words the GPU actually changed into `r->buf`. Verified end-to-end across Title -> Book Hub -> Flower Page -> Stage 1 (`0` validation errors over `2948` frames + `1182` title frames; `TOTK_MEMORY=verify` `4` mismatches / `19.9M` pages; `--selftest` `0` failures; Book Hub `40–45 fps` / `9.5 ms` GPU; Stage 1 locked `59.8 fps` / `1.8–2.0 ms` GPU).
- **Fixed (22 Nov 2026): Stage 1 black screen with UI text (SM86 Ampere lowering `0x624` + `0x381`/`0x981`).** Added negated cbuf addend (`bit 63`) in `case 0x424: case 0x624:` (`IMAD`, shader `8ab9b20972a899c5`) and reversed zero-fill predicate (`bits 64..67` `OpLd.pred`) in `case 0x381: case 0x981:` (`LDG.E`, shader `59bba2e4e0ea674c`) in `runtime/third_party/eglantine/shader_recompiler/frontend/ampere/lower_to_maxwell.h`. Stage 1 (`Chapter 1: Wildwoods`) now renders full painted 3D gameplay at `59.8 fps` with `0` lowering/shader failures and `0` skipped draws.
- **Fixed (22 Nov 2026): Stage 1 water flicker, full-screen lighting/bloom blowups, neon particle streaks, compute UAV re-uploads, and VS->GS varying mismatch (`0028-safe-ast-expression-propagation.patch`, `vk_texture.c`, `vk_exec_draw.c`, `vk_pipeline.c`).** Ryujinx `AstOptimizer.Optimize()` propagated single-use local expressions to their use site without alias, barrier, control-flow, or redefinition checks; in Niagara GPU simulation compute shaders (`cs 1b88456e099473cb`, `cs 9f37d16a0986e404`), `LDS` shared-memory reads in the stream-compaction prefix sum were sunk past `STS` writes to the same slot, doubling instance counts and drawing garbage HDR particle quads (`R=757` in `pass_0126_t0`) that blew out bloom, sky, and `PrevSceneColor`/Water SSR. Patch `0028` adds recursive `CanPropagate()` in `AstOptimizer.cs` blocking mutable memory/image loads, warp-collective/derivative/texture ops, `ThreadKill`, and non-SSA locals (`Defs.Count != 1`). Also fixed `vk_texture_storage_bound_locked(img, (r->flags & 4) != 0)` so compute-written storage images (`ImageStore`) become `gpu_owned = 1` (stopping stale host re-uploads over `PrevSceneColor`, TSR History, HZB, Eye Adaptation, and Global Distance Fields), and extended `geometry_validate()`/`create_graphics()` (`vk_pipeline.c`) to synthesize missing non-invariant 32-bit VS outputs for non-passthrough GS via `spirv_add_outputs()`. Verified: `0/62` bad frames across `4150..5675`, `41` stationary bridge frames at `0.25–0.38/255` pure-water diff, `5985` frames under `TOTK_VK_VALIDATION=1` (`0` errors, `0` shader failures, `0` skipped draws, `0` VS->GS warnings), `--selftest` + all 3 `--probe-vkgeometry*` probes passed, `TOTK_MEMORY=verify` (`20` transient mismatches / `63.8M` pages), and Stage 1 locked `59.7–59.9 fps` (Book Hub `43.1–46.8 fps`).
- **Fixed (22 Nov 2026): single-frame flashes/corruption under `TOTK_REPLAY_ASYNC=1` (`vk_backend.c`, `vk_memory.c`, `vk_usnap.c`, `vk_exec_draw.c`, `nvn_api_core.c`).** Reproduced during Yoshi-swap animations with zero-sync `TOTK_FLIGHT=1` (`8/600` bad frames with `replay_async=1`, `0/1200` with `replay_async=0`; `TOTK_SHOTS` hides async races via `vk_finish()`). Five async-replay races fixed: (1) queued `vk_be_texture_register` and `vk_be_sampler_register` onto `rq[]` (`RI_TEX_REG`/`RI_SAMP_REG`, `RQ_CAP` `1024 -> 8192`) so transient descriptor slot reuse cannot overwrite an earlier queued frame's slots; (2) changed `copy_ranges(..., to_mirror=1)` in `vk_memory.c` to copy `r->buf -> r->mbuf`, emit a `COPY -> COPY` barrier, and copy `r->mbuf -> r->msnap` VRAM-to-VRAM so concurrent CPU writes into live host `r->buf` can never leave `mbuf != msnap` and trigger false `mirror_diff_wb` clobbering of the next frame; (3) stored `done_at_take` in `VkUsnap` before copying so `wr_prune()` never drops GPU writes that finished after an async snapshot was taken, and tracked `last_ubo[6][18]` so inherited UBO bindings across split submissions are snapshotted; (4) checked `vk_usnap_find()` for read-only compute UBO-as-SSBO reads (`c0 0x210..0x30f`) in `ssbo_info()`; (5) moved `last_fence` update inside `submit_lock` in `nvnQueueSubmitCommands`. Verified: `0/3,600` bad frames across two 1,800-frame zero-sync flight runs (`max_1frame_spike = 0.09` vs `144.61` baseline, matching `replay_async=0` at `0.08`), clean streamed textures under `TOTK_MEMORY=import` + `TOTK_REPLAY_ASYNC=1`, `0` Vulkan validation errors over `2,769` frames, `0` `--selftest` failures, and locked `59.8 fps` (`3.27 ms` GPU).
- **Fixed (22 Nov 2026): black foliage/flowers from Ryujinx multi-dest `TLD.B` DCE (`0029-keep-live-multidest-sources-when-removing-dead-node.patch`, `tools/build_xlate.py`).** When eliminating a dead destination on a multi-destination texture load (`TLD.B`), `Optimizer.RemoveNode` dropped source operands still consumed by live sibling destinations, zeroing fetched color/mask channels. Patch `0029` retains sources referenced by live sibling destinations so multi-dest texture fetches preserve all live channels.
- **Fixed (22 Nov 2026): 6.1x faster command-buffer replay via cached host-RAM `vk_usnap` shadow (`runtime/vk_usnap.c`).** Because `vk_usnap` arenas live in write-combined ReBAR VRAM (`DEVICE_LOCAL | HOST_VISIBLE`) for fast GPU reads, CPU `ubo_word()`/`ubo_ptr()` reads during replay hit uncached WC PCIe BAR memory (~33 ms/frame). Keeping a cached host-RAM shadow (`Arena.cpu`) beside each BAR arena makes CPU `vk_usnap_bytes()` reads hit L1/L2 cache while the GPU reads the VRAM copy, cutting replay time **6.1x** (`33 ms -> 4.3–5.4 ms`).
- **Fixed (22 Nov 2026): native UE5 resolution (`720p`–`2160p`) & linear UI DPI scaling (`GAME_QUIRK_GRAPHICS_SCALE_ZERO`, `GAME_QUIRK_UE5_CVAR_RES`, `runtime/resolution.c`, `runtime/ov_system.c`, `runtime/nvn_api_nvn2.c`).** Drives `NS2_RESOLUTION` natively through UE5's `IConsoleManager` (`r.SetRes`, `r.DynamicRes.OperationMode=0`, `r.ScreenPercentage`, `r.SecondaryScreenPercentage.GameViewport`), skips internal resolution presets, and linearly scales Slate UI DPI above 1080p (`1.5x` -> `3.0x` at 4K) so HUD elements stay crisp and unclipped. Also fixed `res_display_size()` and gated the Fast Fusion DLSS override in `nvn_api_nvn2.c` to its profile quirk. Added safe stubs for `nn::account::ShowUserCreator` and `nn::account::IsUserRegistrationRequestPermitted`, plus `yatmb` (`v0.1.0`) launch profile (`yatmb.exe`, `yatmb.ini`, `YATMB_` prefix, `logs/yatmb.log`, icon/manifest, `Storybook Meadow` F1 theme).
- **Fixed (23 Nov 2026): locked 60 FPS at native 4K via 128-bit coalesced `mirror_diff_wb.comp`, per-pool `last_fence`, ReBAR `scratch_aligned`, and `LOAD_OP_CLEAR` coalescing (`runtime/shaders/mirror_diff_wb.comp`, `runtime/mirror_diff_wb_spv.h`, `runtime/vk_memory.c`, `runtime/vk_sync.c`, `runtime/vk_exec_draw.c`, `runtime/vk_exec.c`).** Per-pass GPU timestamp profiling at native 4K (`3840x2160`) showed `mirror_diff_wb.comp` consumed **8.516 ms (45.8% of 18.596 ms GPU time)** writing stride-16-byte scalar `uint` stores over PCIe (~730 MB/s vs 41 GB/s `vkCmdCopyBuffer`). Changing `HostBuf` to coalesced 128-bit `uvec4 host[]` cut `DIFF_WB` **41x** (`8.516 ms -> 0.18–0.21 ms`). Combined with per-pool `PoolRec.last_fence` tracking in `vk_pool_fini` (skipping `vk_upload_flush(1)` for `POOL_IMPORT` and waiting only on the newest fence that actually referenced that pool, with `reserved = fence` in `vk_sync_submit_record`: `64+` slow >10 ms pool releases / `552 ms` -> `0`), ReBAR-preferred `scratch_aligned` (`AUTO_PREFER_DEVICE` + `HOST_ACCESS_SEQUENTIAL_WRITE | MAPPED` with `AUTO_PREFER_HOST` fallback and `vk_exec_draw_flush`), and whole-target `clear_color`/`clear_ds` coalescing into `VK_ATTACHMENT_LOAD_OP_CLEAR`, native 4K (`FMZ=all`, full fidelity) jumped from `48.2 fps` (`19.3 ms` GPU, `bound: gpu`) to locked **59.81–59.92 fps** across Book Hub (`9.65–9.98 ms` GPU) and 3D gameplay (`6.93–6.99 ms` GPU, steady exit 1% low `56.3 fps`), while 1440p (`5.98 / 3.59 ms` GPU) and 1080p (`4.74 / 2.46 ms` GPU) also stay locked at `59.85–59.90 fps`.
- **Fixed (23 Nov 2026): Windows WDDM `MEM_WRITE_WATCH` dirty-bit storm on deferred host-memory imports & per-level GPU texture ownership (`runtime/vk.h`, `runtime/vk_exec_xfer.c`, `runtime/vk_texture.c`, `runtime/vk_memory.c`).** Under `TOTK_POOL_LAZY=1`, deferring `import_pool()` (`vkAllocateMemory(VK_EXTERNAL_MEMORY_HANDLE_TYPE_HOST_ALLOCATION_BIT_EXT)`) until first buffer use triggers Windows WDDM `MmProbeAndLockPages(IoWriteAccess)`, setting `MEM_WRITE_WATCH` dirty bits on every 4 KiB page of the entire 16–32 MiB pool. When that pool also holds streamed GPU-owned textures (GPU-copied tail mips + CPU-written top mips) or render targets, `snap_regions()` harvests 4096+ false dirty pages and `merge_cpu_levels()` overwrites valid GPU mip levels with stale host RAM garbage. Two-layer hardware-agnostic fix: (1) track per-level GPU ownership (`gpu_levels` bitmask + `vk_texture_gpu_written_level()` for `copy_t2t`, `copy_decoded_astc`, `copy_b2t`, `clear_tex`), early-out `merge_cpu_levels()` when all levels are GPU-owned, never overwrite `gpu_lv == 1` levels from RAM, check whole pages `[clo, chi)` on `gpu_lv == 0` levels against `max(merge_gen, cpu_gen)`, and compare alias/write-back checks against `max(gpu_gen, merge_gen)`; (2) wrap `import_pool()` in `lazy_import()` with `import_pool_preserve_ww()` (`mem_thaw` before `gen_lock`, fast 4-way `uint64_t` `page_hash64` over committed runs, then under `gen_lock` (`pool_lock -> lazy_lock -> gen_lock`): `query_stamp` -> `import_pool` -> drain driver-induced OS write-watch bits without stamping -> re-hash & stamp only genuinely modified pages). Verified across 4K/1440p/1080p with `0` corrupted mip levels, `0` false re-uploads/merges, `0` Vulkan validation errors (`3,092` frames), and `0` async-flight corrupt frames (`3,247` frames).
- **Release Suite `0.1.0` (`tools/build_yatmb_release.py`, `tools/installer_yatmb/installer.cpp`, `launcher/YATMBLauncher.py`, `launcher/yatmb_dump.py`, `tools/build_game.py`).** Fixed `build_game.py` so Windows `.rc` resources compile directly alongside `INSTALL_SIDE` when linking against `--runtime-lib` (preserving icon, manifest, and `FileVersion 0.1.0` on user-compiled `yatmb.exe` instead of dropping `.rsrc` inside `libyatmbrt.a`). Built the Storybook Meadow static SDL3+ImGui+zstd Setup Wizard (`SteelTemple-YATMB-0.1.0-Full-Setup-Wizard.exe`), `YATMBLauncher.exe` (supporting both `.nup` containers and direct `ExeFS`/`RomFS` dump folders with 7/7 SHA-256 verification and 5-module lifting), and strict allowlist release staging (`7,164` files passing `check_content`, zero personal `.ini`/game files). Verified end-to-end via automated Setup Wizard install, isolated standalone-toolchain compile (`117.5 s`), `--selftest` (`0` failures), zero-config default boot (`1,062` frames, `0` validation/shader errors), and uninstaller cleanup.
