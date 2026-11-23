# Yoshi and the Mysterious Book: full hand-over (23 Nov 2026)

For whoever takes over (Gemini Neon or another session). This file is complete on its own: what the game is, how to
build and run it, everything fixed so far, everything measured, what I was in the middle of, and what the game still
needs.

- Title `0x0400245021D2C000`, Switch 2, Unreal Engine 5 "Sage" (`PJ045`), version 1.0.2 (`yoshi102`).
- Repo: `C:\Games\DKB PC\Universal-NS2-to-PC`, branch `main` on `ca7b691`. **Everything below is uncommitted.**
  Don't touch the sibling repo `Universal-NS2-to-PC-ff`.
- Game data: `C:\Games\Yoshi and the Mysterious Book PC` (`exefs\`, `romfs\`, `romfs_packed\`, `generated\yoshi102\`,
  `build\yoshi102\yatmb.exe`, `yatmb.ini`, `logs\yatmb.log`).
- **Hand-over pack (screenshots, shader files, logs, scripts, a backup of the uncommitted work):**
  `C:\Games\Yoshi and the Mysterious Book PC\handover\`. See "The hand-over pack" below.

## 1. User's standing rules (keep these)

- No game files or derived data leave the PC (dumps, screenshots and shaders stay local; never upload them).
- No game names in engine code: per-title behaviour goes in `runtime/game_profile.c` as data or quirks.
- Fidelity first: match what the console does, no cosmetic hacks.
- Never force-push `main`. Commit locally only when asked; ask before pushing or releasing.
- Config keys use `YATMB_` / `NS2_` prefixes (`TOTK_` is still accepted; most debug keys below also accept `TOTK_`).
- Keep the handbook docs current as work lands: this file and `docs/UNIVERSAL_NS2_TO_PC_PLAYBOOK.md` §5.10.
- Keep the user's e-mail private.

## 2. Where it stands

| Area | State |
|---|---|
| Boot, audio, HID, saves, account stubs | Work (`nn::account::ShowUserCreator` / `IsUserRegistrationRequestPermitted` safe stubs; live `Slot00` untouched) |
| Launch branding & F1 menu | `yatmb.exe` v`0.1.0` (`update 1.0.2`), `yatmb.ini`, `YATMB_` env prefix, `logs\yatmb.log`, spotted-egg `yatmb.ico`/`yatmb.rc`/`yatmb.manifest`, clean window title, `Storybook Meadow` F1 menu theme |
| Title movie, opening movie, level intro movie (H.264 via Media Foundation) | Work, including the decode-to-texture path |
| Title screen and menus | Render correctly (`handover\screens\02_title_screen.png`) |
| Shader lowering (SM86 → Maxwell) & Ryujinx translator | 120/120 then 378/378 captured stages + Stage 1 shaders (`0x624`, `0x381`/`0x981`) lower with 0 failures; 455/455 cached SPIR-V pass `spirv-val`; patches `0028` & `0029` active |
| Native Resolution & UI DPI Scaling | Native `720p`/`900p`/`1080p`/`1440p`/`2160p` (4K) via UE5 CVar hooks (`GAME_QUIRK_UE5_CVAR_RES`, `GAME_QUIRK_GRAPHICS_SCALE_ZERO`) with linear UI DPI scaling above 1080p (3.0x at 4K, 0 HUD overlap) |
| Book Hub, Book Hub Fruit Icons, Stage 1 & Wiggling Fruit 3D Gameplay | All render pixel-perfectly at 1080p, 1440p, and native 4K: clean Book Hub with magnifying glass & crisp Wiggling Fruit cluster matching console reference, Stage 1 painted 3D gameplay, and Wiggling Fruit 3D stage with vibrant pink/purple flowers & teal grass |
| Vulkan validation & Async Flight Check | **0 validation errors, 0 shader failures, 0 draws skipped, 0 unimplemented calls** end-to-end at 4K across Title -> Book Hub -> Wiggling Fruit 3D (`3,092` frames under `YATMB_VK_VALIDATION=1 YATMB_GPL=0`); `YATMB_FLIGHT=1 YATMB_REPLAY_ASYNC=1` (`3,247` frames, 1,800 load-transition thumbnails scanned): **0 flicker/corrupt frames** |
| Selftest & shader checks | `tools/build_shaders.py --check`: exit 0; `--selftest`: `passed (0 failures)`; `--probe-vkgeometry*`: passed (`0` failures) |
| Frame rate (1080p / 1440p / **native 4K**) | **LOCKED 60 FPS across 1080p, 1440p, and native 4K** (`REPLAY_ASYNC=0` and `1`): 4K Book Hub **59.92 fps** (`9.65 ms` GPU, replay `4.62 ms`, `0` slow pool releases) & 4K Wiggling Fruit 3D **59.86 fps** (`6.93 ms` GPU, replay `1.85 ms`, steady 1% low `56.3 fps`); 1440p **59.90 / 59.85 fps** (`5.98 / 3.59 ms` GPU); 1080p **59.90 / 59.85 fps** (`4.74 / 2.46 ms` GPU) |
| Release Suite (`0.1.0` Setup Wizard + Launcher + Packager) | Built & E2E-verified (`build/release-yatmb/`): `SteelTemple-YATMB-0.1.0-Full-Setup-Wizard.exe` (`133.8 MiB`), `Portable-StandAlone.zip` (`155.9 MiB`), `Update.zip` (`155.9 MiB`). Storybook Meadow Setup Wizard + `YATMBLauncher` (supports `.nup` containers and direct `ExeFS`/`RomFS` folders, 7/7 SHA-256 verification, 5-module lifting, standalone LLVM/Ninja compile with PE `0.1.0` icon/version info, shader warm, zero-config default profile). |

## 3. Build and run

```powershell
Set-Location 'C:\Games\DKB PC\Universal-NS2-to-PC'
.venv\Scripts\python.exe tools\build_game.py --version yoshi102 --gen "C:\Games\Yoshi and the Mysterious Book PC\generated\yoshi102" --out "C:\Games\Yoshi and the Mysterious Book PC\build\yoshi102" --exefs "C:\Games\Yoshi and the Mysterious Book PC\exefs" --romfs "C:\Games\Yoshi and the Mysterious Book PC\romfs_packed" --profile "C:\Games\Yoshi and the Mysterious Book PC\profile" --expected "C:\Games\DKB PC\Universal-NS2-to-PC\tools\data\expected-yoshi102.json"
```

A runtime-only rebuild takes about 2 s (ninja). Run from `build\yoshi102`:

- **Selftest** (must stay at 0 failures): `$env:YATMB_GPU='null'; .\yatmb.exe --selftest`
- **Screenshot:** `.\yatmb.exe --seconds 25 --shot title_now.png`. `--seconds` counts game-world seconds.
- **Reach Stage 1 without a controller:** `TOTK_INPUT_SCRIPT=scripts\yoshi_level1_long.txt` (a copy is in
  `build\yoshi102\scripts\` and in the hand-over pack; the temp scratchpad copy was wiped once, so don't rely on
  `%TEMP%`). One line `<frame> A 6` every 120 frames from 1500 to 15000. The third press (frame 1740) starts the game;
  Mr. E's dialog runs, and around frame 12000 the camera is on the close-up. Use `--seconds 330`: Stage 1 runs at
  ~40 fps, so 230 s only reaches frame ~10,000 and the dump at 12000 never happens.
- **Frame dump:** `TOTK_DUMP=12000 TOTK_DUMP_DIR=dump_x`. `passes.txt` lists every pass, pipeline, binding, and PNGs of
  the targets. `TOTK_DUMP_TEX=<id>|<w>x<h>` dumps sampled textures (compressed ones as `_blocks.png` block maps).
- **Uniform blocks in the dump:** `TOTK_DUMP_UBO=1` prints the first 16 vec4 of c3 and up. **New:**
  `TOTK_DUMP_UBO_VEC=4:151,4:204,5:9` prints any vec4 by index and turns `TOTK_DUMP_UBO` on (`vk_dump.c`).
- **Traces:** `TOTK_TRACE=codec|fs|perf|gfx`. **New in `fs`:** failed opens, `GetEntryType` and `OpenDirectory`, each
  with its result (`fs_host.c`, `traced()`).
- **Shader replacement (debug):** `TOTK_SPV_OVERRIDE=<16-hex FNV-1a of the post-fixup SPIR-V>:<file.spv>` (`vk_pipeline.c`
  `spv_override()`). Runs after `spirv_rebind`, `spirv_fixup`, `spirv_layer_from_viewport`, and `spirv_fmz`, so match
  against the post-fixup hash rather than pre-fixup dumps.
- **Fused-multiply-zero rule:** `TOTK_FMZ=all` (default) | `vertex` | `0`. Rewrites 32-bit float `OpFMul`/`Fma` across all
  shader stages so `0 * x = 0` (even for Inf/NaN), matching Switch 2 SM86 `.FTZ`/`.FMZ`.
- **Skip fragment stages:** `TOTK_SKIP_FS=<nvn2 hash>,…`
- **Crash memory peek:** `NS2_CRASH_PEEK=addr[*n],xN+off,tlr+off`
- **Offline lowering check:** capture with `DKB_SHADER_DUMP=<dir>`, build
  `clang++ -std=c++20 -O1 -I runtime/third_party/eglantine tools/dkb_lower_test.cpp -o build/dkb_lower_test.exe`.
- **SPIR-V tools:** `C:\VulkanSDK\1.4.363.0\Bin\` (`spirv-cross --version 450 x.spv` gives readable GLSL,
  `spirv-dis`, `spirv-as --target-env vulkan1.1`; vulkan1.3 rejects the `BufferBlock` decoration).

Gotchas:
- Runs aren't deterministic. The same script reaches different states at the same frame. Always take texture ids and
  addresses from that run's own `passes.txt`.
- `Copy-Item` keeps the timestamp, so ninja won't rebuild a restored file. Touch it first.
- Bash heredocs mangle `\n` in Python patch scripts. Write the script to a file and run it.
- Several runtime files are committed with CRLF line endings. That is how they are in `HEAD`; leave them.
- A DualSense controller is now plugged in (`input: gamepad "DualSense Wireless Controller"` in the log), so the user can
  play-test by hand.

## 4. Everything fixed so far (cause → fix)

1. **Crash in `FMallocBinned2::Malloc` under `movie::Extractor` (wrong symbol binding).** The sdk and subsdk2 both
   export `nn::movie::detail::HeapMemoryManager::GetInstance()::instance`. The console's rtld binds default-visibility
   symbols to the first module in load order (main, subsdk0..9, sdk); our loader preferred each module's own copy, so
   subsdk2's copy took TLS slot 0 and overwrote Unreal's TLS array.
   - Fix: `GAME_QUIRK_RTLD_ORDER` (`game_profile.h/.c`, set for this title only) and `resolve()` in `loader.c`.
   - Other titles keep own-first binding. Turning the quirk on elsewhere also rebinds the sdk's `new`/`delete` and
     typeinfo (DKB 75 relocations, MKW 924, TotK 782), so each title needs its own boot test.
2. **H.264 movies.** `nn::codec` H.264 runs on the host via the new `runtime/h264_win.c` (Media Foundation's software
   decoder) and `h264.h`; `h264_sdl.c` is a stub off Windows. In `ov_codec.c`: init overrides, a picture FIFO (`pics[]`,
   `pics_out()`, `decode_h264()`), flush handling, and overrides for this SDK's `GetH264DecoderSubmissionReadyEvent`,
   `CalculateH264DecoderWorkBuffer` and the single-size `InitializeH264Decoder`. `build_game.py` links
   `-lmfplat -lmfuuid -lole32`. **Don't enable `CODECAPI_AVLowLatencyMode`:** it stalls the B-frame title movie.
3. **SM86 lowering** (`runtime/third_party/eglantine/shader_recompiler/frontend/ampere/`): `geometry_exit.h` models ALD
   `0x321`; `lower_to_maxwell.h` adds UPOPC `0x2bf`, TEX.B zero-LOD `0x361`, TLD4 with a uniform handle `0xf63`
   (2D / 2D array → Maxwell TLD4.B `0xdef8`), and bindless `TXQ.B` (`0xdf50`). `0x2bf`/`0xf63` are in
   `uses_uniform_bank`.
4. **Black frames (nothing drawn).** Unreal binds one program per stage (VS mask `0x1`, FS `0x2`, `NULL` for `0x4`/`0x80`,
   compute `0x20`). The replay kept one program. `bind_program()` (`vk_exec_draw.c`) now keeps per-stage bindings
   (`stage_prog[6]`, `stage_mask[6]`, `cprog`), and `resolve_program()` builds and caches a combined `prog_t` lazily at
   the next draw (`combo_tab`, `combined_program()`). Only mask 0 means "every stage"; bits past compute are ignored.
   (Treating `0x80` as "all" broke the menu background.)
5. **Text drawn as solid boxes.** Unreal keeps texture/sampler handles in its own uniform blocks.
   `GfxShaderRes.raw_cbuf`/`raw_handle` (`gfx.h`, `gfx_shader.c`) keep the untruncated Ryujinx `TextureHandle`
   packing (`cbuf_slot = slot0 | (slot1+1) << 16`; `handle = word0 | word1 << 14 | type << 28`). `ubo_handle()` reads
   the handle from the bound block, and the handle is part of the descriptor signature (`RsPtr.tex`).
6. **Decode-to-texture and texel buffers** (Gemini): native images for the in-level H.264 decoder
   (`ov_codec.c` `ni_tab`, `nvn_api_obj.c` `ov_ni_init`/`ov_tex_from_ni`), `NVN_TEXTURE_TARGET_BUFFER`, and 32-bit
   storage texel-buffer view formats matched to the shader's declared format.
7. **Translator draw parameters** (`tools/xlate/Program.cs`, `tools/build_xlate.py`), **bindless TXQ / 3D dims**
   (`BindlessElimination.cs`), **non-passthrough lowered GS and interface validation**, **256-bit integer image masks
   and storage view keys** (Gemini; see the playbook). These took Vulkan validation errors from 33 to 0.
8. **Black characters and close-up surfaces (texture streaming).** `vk_texture.c` treated a texture as GPU-owned for
   good after any GPU write. Unreal's streaming GPU-copies the old mips into a new texture (making it GPU-owned), then
   writes the new large mips into its storage with the CPU, and those mips stayed zero.
   - Fix: `merge_cpu_levels()` (called from `make_fresh`/`make_fresh_snap`) uploads each level/layer whose own whole
     pages were written since `max(gpu_gen, merge_gen)`. `write_back()` advances `merge_gen`. A perf line counts the
     merged levels.
   - Limit: pages a level shares with a neighbour are excluded, so a texture smaller than a page never merges. That's
     fine for streaming, but keep it in mind for tiny textures.
9. **`GetEntryType("rom:/Dir/")` with a trailing slash returned not-found** (22 Nov, `romfs.c`
   `romfs_entry_type`). `romfs_path_norm` rejects a trailing slash, so `rom:/PJ045/` (the project directory, which
   exists) failed. Trailing separators are now trimmed first and `rom:/` is the root directory, as `nn::fs` accepts.
   Verified: `fs type rom:/PJ045/ -> 0`. It didn't change the dark page.
10. **Dark close-up terrain/bark/rock surfaces in Stage 1 (fragment FMZ semantics)** (22 Nov, `vk_pipeline.c`).
    Close-up foreground terrain shaders (`efcffdf58785378d` et al.) compute per-instance albedo variation with
    `normalize(frac(ObjectPosition / 100 + PerInstanceRandom)) * strength + base_albedo`. When the vector is `(0, 0, 0)`,
    `inversesqrt(0.0) = +Inf`; on Switch 2 SM86 `.FTZ`/`.FMZ` (`FFMA`/`FMUL` `b80=1, b76=0`), `0 * +Inf = 0` so `fma`
    preserves `base_albedo`. Vertex-only `spirv_fmz` left fragment shaders using IEEE semantics (`0 * +Inf = NaN`, then
    clamped to `0.0` black).
    - Fix: `make_module_linked()` (`vk_pipeline.c`) now defaults `fmz_mode` to `all` (every shader stage) and
      `spirv_fmz()` reuses existing `bvec2`/`bvec3`/`bvec4` declarations. Verified with `--selftest`, Stage 1 (`9705`
      frames, `746` FMZ rewrites, `0` validation errors), and title regression (`1482` frames, `0` validation errors).
    - Cleanup: removed the stray game-name comment in `vk_texture.c`.
11. **Floating grass/hills/rock/trunk occluding the open Book Hub + Book Hub GPU perf regression (VRAM mirror coherence via GPU compute diff write-back)** (22 Nov, `runtime/shaders/mirror_diff_wb.comp`, `runtime/mirror_diff_wb_spv.h`, `vk.h`, `vk_memory.c`, `vk_exec_draw.c`).
    UE5's `GPUScene` compute shaders (`FScatterUploadCS` `2b3cd7d63c03334f`, `FInstanceCullingCS` `eb0a9252c1b56ce7`) write
    `PrimitiveSceneData`, `InstanceSceneData`, and `InstanceIdsBuffer` through guarded UBO-pointer SSBOs (`cbuf_slot >= 3`).
    Because speculative guarded candidates carry no exact write extent, `vk_exec_draw.c` skips `vk_mem_gpu_wrote()`
    (`writeback == 0`) to prevent full-extent DMA writeback from clobbering adjacent CPU buffers. However, on mirrored
    pools (`TOTK_MEMORY=mirror`, default on discrete GPUs), skipping writeback left host RAM at `0` while GPU writes
    lived only in `r->mbuf` (`105,719` mismatched pages in `TOTK_MEMORY=verify`, starting at `InstanceSceneData`
    `+0x110e00`). Whenever the CPU touched an adjacent sub-allocation on the same 4 KiB page, `mirror_sync()` uploaded
    stale host zeros over `r->mbuf`, collapsing affected meshes' `TilePosition` / world transforms to `(0, 0, 0)` right
    in front of Mr. E's open book. Demoting guarded pools to PCIe host memory (`vk_mem_no_mirror`) fixed the corruption
    but exploded Book Hub GPU time from `~3.5 ms` (`40 fps`) to `65 ms` (`15 fps`, with `175 ms` spikes) because every
    VS/FS/CS read `GPUScene`/`LightGrid` over PCIe.
    - Fix: replaced pool demotion with `vk_mem_guarded_write()` (`vk.h`, `vk_memory.c`) and a 24-line Vulkan 1.1
      compute shader (`runtime/shaders/mirror_diff_wb.comp` -> `runtime/mirror_diff_wb_spv.h`). Every guarded pool stays
      in fast device-local VRAM (`r->mbuf`) alongside a device-local snapshot (`r->msnap`) updated by prologue CPU
      uploads and bounded `wbl` copies. At `vk_mem_mirror_end()`, `mirror_diff_wb.comp` compares `r->mbuf` against
      `r->msnap` in 128-bit coalesced VRAM reads and writes back ONLY the exact 32-bit words the GPU actually changed
      into `r->buf` (using `rec_push()` through the async command recorder), leaving adjacent CPU-written buffers
      untouched while preserving full 4 KiB page syncs and CPU `memset(0)` zero-fills.
    - Verified: `--selftest` (`0` failures), end-to-end Title -> Book Hub -> Flower Page -> Stage 1 with
      `TOTK_VK_VALIDATION=1` (`2948` frames, `0` validation errors, `0` shader failures, `0` skipped draws),
      `TOTK_MEMORY=verify` (`4` mismatches out of `19.9M` pages compared across all 93–131 pools, down from `105,719`),
      title regression (`1182` frames, `0` validation errors), Book Hub recovered to `40–45 fps` (`9.5 ms` GPU), and
      Stage 1 gameplay runs at locked `59.8 fps` (`1% low 58.0 fps`, `1.8–2.0 ms` GPU, `0` frames > 25 ms).
12. **Stage 1 (`Chapter 1: Wildwoods`) black screen with UI text after selecting the flower (SM86 Ampere lowering)** (22 Nov, `runtime/third_party/eglantine/shader_recompiler/frontend/ampere/lower_to_maxwell.h`).
    Loading into Stage 1 failed to lower two SM86 instructions (`shader 8ab9b20972a899c5` and `shader 59bba2e4e0ea674c`),
    causing Stage 1 world rendering draws to be skipped while HUD/dialogue still drew:
    - `op=0x624` (`IMAD` with cbuf addend, `[ff0e7624 81002800 078e02ff 000fe400]`): `bit 63` negates the cbuf addend
      (matching `0xe24`). Added `negate_c` handling in `case 0x424: case 0x624:`, negating into `R252` before
      `multiply_low(a, b, c, false)`.
    - `op=0x381`/`0x981` (`LDG.E`, `[2e1c7381 00000800 001e890e 000ea200]`): `bits 64..67` encode a reversed
      zero-fill predicate (`load_pred = (7 - insn.Bits(64, 3)) | (insn.Bits(67, 1) << 3)`, verified against Mesa NAK
      `sm70_encode.rs` / `ir.rs` `OpLd.pred`: returns `0` when false). Added predicated `LDG` + `!load_pred` zero-fill
      emission (combining with `outer_pred` via `P6` when needed).
    - Verified: Stage 1 enters full painted 3D gameplay with Blue Yoshi (`handover\screens\16_stage1_wildwoods_FIXED.png`)
      at `59.8 fps` (`0` lowering failures, `0` shader failures, `0` draws skipped, `0` validation errors).
13. **Stage 1 water flicker, full-screen lighting/bloom color blowups, neon particle streaks, compute UAV re-uploads, and skipped VS+GS shadow pipeline** (22 Nov, `tools/xlate/patches/0028-safe-ast-expression-propagation.patch`, `tools/build_xlate.py`, `runtime/vk.h`, `runtime/vk_texture.c`, `runtime/vk_exec_draw.c`, `runtime/vk_pipeline.c`).
    Reproduced deterministically in Stage 1 from the flower-bloom VFX (`f04375`) across the orange-leaf water bridge into
    the cave (`f05675`): frames blew up into flickering solid grey/blue/mint/lavender/magenta/red/yellow/white washes
    (`pass_0126_t0` Separate Translucency `rgba16f` hit `R=757`, which propagated into TSR `PrevSceneColor` -> Water SSR
    and Bloom) and logged `vk_pipeline: graphics pipeline not built: vertex-to-geometry varying mismatch`.
    - **Root cause 1 (primary — Niagara GPU particle corruption):** Ryujinx's `AstOptimizer.Optimize()` propagated any
      single-use local expression from its definition to its use site without alias, barrier, control-flow, or
      redefinition analysis. In Niagara GPU simulation compute shaders (`cs 1b88456e099473cb` / `nvn2 693d0e26c6474d78`,
      `cs 9f37d16a0986e404` / `nvn2 897f863d369c3e9c`), `LDS` shared-memory reads in the stream-compaction exclusive
      prefix sum were sunk past `STS` writes to the exact same slot (`_24[i+1] = a0; sum = a0 + _24[i+1]`, doubling
      counts), corrupting `RWInstanceCounts` and compacted particle indices so `pass 0126` drew uninitialized/garbage
      HDR particle quads (`R=757`) and neon streaks across the screen and into `PrevSceneColor` / Water SSR.
      - Fix: added `tools/xlate/patches/0028-safe-ast-expression-propagation.patch` (`CanPropagate()` in `AstOptimizer.cs`,
        bumping `tools/build_xlate.py` to 28 patches, `ns2_xlate.id` `33ef028ef40825a2`): only pure, time-invariant
        expressions may be propagated (blocks mutable `Load` from shared/local/storage/global/output memory, `ImageLoad`,
        warp-collective `Ballot`/`Shuffle*`/`Vote*`/`SwizzleAdd`, quad-derivative/texture ops `Ddx`/`Ddy`/`Lod`/`TextureSample`,
        `ThreadKill`, and non-SSA locals with `Defs.Count != 1`).
    - **Root cause 2 (compute UAV re-uploads):** `vk_texture_storage_bound_locked()` (`vk_texture.c`) only updated
      `wr_fence` and left compute-written storage images (`r->flags & 4`, `TextureUsageFlags.ImageStore`) with
      `gpu_owned = 0`, causing page checks to re-upload stale host bytes over live compute outputs (`PrevSceneColor`
      `uploads 3`, TSR History `59 MiB` / Global Distance Field `16 MiB` / 1x1 Eye Adaptation `uploads 2`) and
      preventing `alias_has_gpu_content()` / `ReadTexels` from seeing GPU content.
      - Fix: `vk_texture_storage_bound_locked(img, (r->flags & 4) != 0)` (`vk.h`, `vk_texture.c`, `vk_exec_draw.c`)
        marks written storage images `gpu_owned = 1` + `gpu_dirty = 1` + `own_add(e)` using zero-syscall
        `vk_mem_changed_snap(..., submit_epoch, &e->gpu_gen)`.
    - **Root cause 3 (VS->GS varying mismatch):** depth-only cubemap shadow casters omit unused UV `location 0` that
      the shared shadow GS (`478e546…` / `c3fce9d…`) declares alongside `location 1` (`gl_Layer`). `geometry_validate()`
      rejected `gi.mask & ~vo.mask` and `create_graphics()` did not synthesize missing VS outputs for non-passthrough GS.
      - Fix: `geometry_validate()` and `create_graphics()` (`vk_pipeline.c`) synthesize missing non-invariant 32-bit VS
        outputs needed by GS via `spirv_add_outputs()` (matching the existing VS->FS path, including depth-only draws
        with `s->fs == NULL`).
    - Verified: 62/62 frames across `f04150..f05675` clean (`0` bad frames, `handover\screens\17_stage1_water_bridge_FIXED.png`,
      `18_stage1_cave_FIXED.png`); 41 consecutive stationary bridge frames (`f04440..f04480`) show pure-water frame-to-frame
      mean diff `0.25–0.38 / 255` (zero flicker); `TOTK_VK_VALIDATION=1` across `5985` frames (`0` validation errors, `0`
      shader failures, `0` skipped draws, `0` VS->GS warnings); `--selftest` and all 3 `--probe-vkgeometry*` probes pass
      (`0` failures); `TOTK_MEMORY=verify` (`20` transient mismatches / `63.8M` pages); default-mode `TOTK_TRACE=perf`
      Book Hub `43.1–46.8 fps`, Stage 1 gameplay locked `59.7–59.9 fps` (`0.4–0.9 MiB` texture re-uploads / 60 frames).
14. **Single-frame red/black/displaced flashes during `Select Yoshi` and Yoshi-swap animations under `replay_async = 1`** (22 Nov, `runtime/vk_backend.c`, `runtime/vk_memory.c`, `runtime/vk_usnap.c`, `runtime/vk_exec_draw.c`, `runtime/nvn_api_core.c`).
    Reproduced with the zero-sync GPU flight recorder (`TOTK_FLIGHT=1`, since `TOTK_SHOTS` calls `vk_finish()` on captured
    frames and masks async-replay races): `8 / 600` corrupt single frames with `TOTK_REPLAY_ASYNC=1` (`max_1frame_spike = 144.61` —
    blurred red/orange silhouette flash during Red Yoshi's walk-to-book animation, pitch-black 3D scene frames under intact UI,
    and wrong-camera/displaced geometry frames), versus `0 / 1,200` with `TOTK_REPLAY_ASYNC=0` (`max_1frame_spike = 0.08`).
    - **Root cause 1 (async descriptor-slot overwrite):** `vk_be_texture_register` and `vk_be_sampler_register` (`vk_backend.c`)
      mutated live descriptor slots immediately on the game thread instead of queueing onto `rq[]` behind earlier `RI_SUBMIT`
      items (unlike `vk_be_texture_release`). Under transient RDG slot reuse (~175K texture registrations in 3,500 frames),
      frame `N+1` overwrote frame `N`'s texture/sampler slots mid-replay.
      - Fix: queue `RI_TEX_REG` / `RI_SAMP_REG` copies onto `rq[]` (bumping `RQ_CAP` `1024 -> 8192` and reserving timeline
        values only for `RI_SUBMIT`/`RI_PRESENT`), cutting bad frames from `8 / 600` to `3 / 1,800`.
    - **Root cause 2 (guarded-diff mirror double-read race):** `copy_ranges(..., to_mirror=1)` (`vk_memory.c`) copied live
      host-visible `r->buf` twice (`r->buf -> r->mbuf`, then `r->buf -> r->msnap`). When a game thread wrote frame `N+1`
      into `r->buf` between those two DMA copies, `mbuf != msnap` caused `mirror_diff_wb.comp` at `vk_mem_mirror_end` to
      falsely detect a GPU write and overwrite the fresh guest bytes in `r->buf` with stale `mbuf` bytes.
      - Fix: copy `r->buf -> r->mbuf` once, emit a `COPY -> COPY` barrier, and copy `r->mbuf -> r->msnap` VRAM-to-VRAM.
    - **Root cause 3 (`vk_usnap` async tracking gaps & fence-publish ordering):** (a) `wr_prune()` in `vk_usnap.c` pruned GPU
      writes against current `vk_sync_fence_done()` instead of the fence completed when `vk_usnap_take()` copied guest memory,
      allowing a snapshot taken before an earlier GPU write finished to survive and serve stale pre-write bytes; (b)
      `vk_usnap_take()` did not snapshot UBO bindings inherited across split submissions (`ex->ubo` persists across
      `nvnQueueSubmitCommands`); (c) `ssbo_info()` (`vk_exec_draw.c`) skipped `vk_usnap_find()` for read-only compute
      UBO-as-SSBO bindings (`c0 0x210..0x30f`); (d) `nvnQueueSubmitCommands` (`nvn_api_core.c`) published `last_fence`
      outside `submit_lock`, allowing a concurrent `nvnQueueFenceSync` to capture an older fence (which also caused streamed
      character texture corruption under slow `TOTK_MEMORY=import` + `TOTK_REPLAY_ASYNC=1`).
      - Fix: record `done_at_take` in `VkUsnap` before copying and prune `U.wr[]` against it; track `last_ubo[6][18]` in
        `vk_usnap.c` so inherited UBOs are snapshotted; check `vk_usnap_find()` for read-only compute `ubo == 1` SSBOs;
        publish `last_fence` inside `submit_lock`.
    - Verified: **0 / 3,600** bad frames across two independent 1,800-frame zero-sync flight runs covering 6 full Yoshi swaps
      with `TOTK_REPLAY_ASYNC=1` (`max_1frame_spike = 0.09`, matching `TOTK_REPLAY_ASYNC=0` at `0.08`); `TOTK_MEMORY=import`
      + `TOTK_REPLAY_ASYNC=1` (`0 / 600` corrupt frames, Red Yoshi streamed texture clean); `TOTK_REPLAY_ASYNC=0` (`0 / 600`,
      `max_1frame_spike = 0.08`); `TOTK_VK_VALIDATION=1` + `TOTK_REPLAY_ASYNC=1` (`2,769` frames, `0` validation errors, `0`
      shader failures, `0` skipped draws); `--selftest` (`0` failures); `TOTK_TRACE=perf` + `TOTK_REPLAY_ASYNC=1` locked
      **59.8 fps** (`interval avg 16.71 ms`, `3.27 ms` GPU).
15. **Black flowers, sprouts, and foliage in Wiggling Fruit 3D gameplay (Ryujinx `Optimizer.RemoveNode` multi-dest `TLD.B` DCE)** (22 Nov, `tools/xlate/patches/0029-keep-live-multidest-sources-when-removing-dead-node.patch`, `tools/build_xlate.py`).
    When removing a dead instruction node from a multi-destination texture load (`TLD.B`), Ryujinx's `Optimizer.RemoveNode`
    dropped source operands still needed by live sibling destinations, leaving vertex/fragment shader texture fetch outputs
    zeroed and turning flowers, sprouts, and grass accents black.
    - Fix: patch `0029` preserves live sources when removing a dead multi-dest node (29 patches total). Verified: Wiggling
      Fruit 3D flowers render vibrant pink/purple against bright teal grass (`0` regressions at 1080p/1440p/4K).
16. **6.1x faster command-buffer replay (`vk_usnap.c` cached host-RAM shadow `Arena.cpu`)** (22 Nov, `runtime/vk_usnap.c`).
    `vk_usnap` arenas are allocated in write-combined ReBAR VRAM (`DEVICE_LOCAL | HOST_VISIBLE`) for fast GPU reads, so
    `ubo_word()`/`ubo_ptr()` CPU reads during replay were performing uncached WC PCIe BAR reads (~33 ms replay time,
    dragging Book Hub to ~28 fps).
    - Fix: keep a cached host-RAM shadow (`Arena.cpu`) beside each mapped BAR arena so CPU `vk_usnap_bytes()` reads hit L1/L2
      cache while the GPU reads the VRAM BAR copy. Replay time dropped **6.1x** (`33 ms -> 4.3–5.4 ms`), bringing Book Hub
      from `28 fps` to locked `60 fps` at 1080p and 1440p.
17. **Native UE5 resolution (`720p`/`900p`/`1080p`/`1440p`/`2160p`) & linear UI DPI scaling** (22 Nov, `runtime/resolution.c`, `runtime/ov_system.c`, `runtime/nvn_api_nvn2.c`, `runtime/game_profile.h/.c`).
    - Added `GAME_QUIRK_GRAPHICS_SCALE_ZERO` (`ov_system.c`) and `GAME_QUIRK_UE5_CVAR_RES` (`resolution.c`) wrapping
      `f_700049829c` (sets `r.SetRes`, `r.DynamicRes.OperationMode=0`, `r.ScreenPercentage`, `r.SecondaryScreenPercentage.GameViewport`
      via `IConsoleManager`), `f_700582d83c` (skips internal resolution preset resets), and `f_7002d7a41c` (scales UI DPI
      linearly above 1080p — e.g. `3.000` at 4K from the `1.500` 1080p baseline — preventing HUD/title overlap).
    - Fixed `res_display_size()` and gated the Fast Fusion DLSS resolution override in `nvn_api_nvn2.c` so non-FF titles are
      unaffected. Verified cleanly at `720p`, `900p`, `1080p`, `1440p`, and `2160p` (4K).
18. **`yatmb` launch rebrand, `Storybook Meadow` F1 menu theme, & `nn::account` safe stubs** (22 Nov, `runtime/game_profile.c`, `runtime/cfg.c`, `runtime/ui/menu.cpp`, `runtime/ui/theme.h`, `runtime/ov_system.c`, `runtime/yatmb.ico/.rc/.manifest`, `tools/build_game.py`).
    - Branded binary as `yatmb.exe` (`PC 0.1.0 · update 1.0.2`), `yatmb.ini`, `YATMB_` env prefix, `logs/yatmb.log`,
      spotted-egg icon/manifest, clean window title, and `Storybook Meadow` F1 settings menu (`Yoshi and the Mysterious Book Settings`).
    - Added safe stubs for `nn::account::ShowUserCreator` and `nn::account::IsUserRegistrationRequestPermitted`.
19. **Locked 60 FPS at native 4K (`YATMB_RESOLUTION=2160`, full fidelity, `FMZ=all`)** (23 Nov, `runtime/shaders/mirror_diff_wb.comp`, `runtime/mirror_diff_wb_spv.h`, `runtime/vk_memory.c`, `runtime/vk_sync.c`, `runtime/vk_exec_draw.c`, `runtime/vk_exec.c`).
    Per-pass Vulkan GPU timestamp profiling at 4K proved `DIFF_WB` (`mirror_diff_wb.comp`) took **8.516 ms (45.8% of 18.596 ms
    total GPU time)** because changed words were written to PCIe system RAM (`HostBuf`) as stride-16-byte scalar `uint` stores
    (~730 MB/s vs 41 GB/s `vkCmdCopyBuffer`), and `vk_pool_fini` stalled on unrelated newer timeline submissions + upload flushes
    (`64+` slow >10 ms releases / `552 ms` per run).
    - Fixes (all hardware-agnostic, zero fidelity loss):
      1. `mirror_diff_wb.comp` (+ regenerated `mirror_diff_wb_spv.h`): changed `HostBuf` to coalesced 128-bit `uvec4 host[]`,
         cutting `DIFF_WB` **41x** (`8.516 ms -> 0.18–0.21 ms`) and cutting 4K Book Hub GPU time nearly in half (`19.3 ms -> 9.65 ms`).
      2. `vk_memory.c` + `vk_sync.c`: tracked per-pool `volatile uint64_t last_fence` on `PoolRec` (stamped on GPU resolve,
         write-back, guarded diff, and `verify_record`, with `reserved = fence` in `vk_sync_submit_record`). In `vk_pool_fini`,
         `POOL_IMPORT` skips `vk_upload_flush(1)` (upload batches never bind `POOL_IMPORT` buffers) and waits only on `r->last_fence`,
         cutting slow >10 ms pool releases from `64` (`552 ms`) to **`0`**.
      3. `vk_exec_draw.c` + `vk_exec.c`: allocated transient `scratch_aligned` chunks (`c0`, `support`, UBO/IB copies) with
         `VMA_MEMORY_USAGE_AUTO_PREFER_DEVICE` + `HOST_ACCESS_SEQUENTIAL_WRITE | MAPPED` (clean `AUTO_PREFER_HOST` fallback for
         non-ReBAR GPUs) and added `vk_exec_draw_flush(fence, done)` before splits and submission end.
      4. `vk_exec.c`: coalesced whole-target `clear_color`/`clear_ds` outside a pass into `VK_ATTACHMENT_LOAD_OP_CLEAR` on
         `vk_exec_pass_begin` (with `flush_pending_clears` on RT change, barrier, or submit end, and `fb_dirty` updated for
         feedback-loop targets).
    - Verified (independent verifier, `YATMB_TRACE=perf`, NO `TOTK_SHOTS`, both `REPLAY_ASYNC=0` and `1`):
      - **4K Book Hub**: `48.21 -> 59.92 fps` (async0, GPU `19.29 -> 9.65 ms`, replay `15.17 -> 4.62 ms`, `bound: cpu`, `0` slow rel);
        async1: `48.69 -> 59.82 fps` (GPU `19.37 -> 9.98 ms`, max `70.12 -> 17.86 ms`).
      - **4K Wiggling Fruit 3D**: **59.86 fps** (async0, GPU `6.93 ms`, replay `1.85 ms`); async1 **59.81 fps** (GPU `6.99 ms`,
        replay `1.82 ms`); steady exit 1% low **56.3 fps** (`0` frames > 25 ms).
      - **1440p**: Book Hub **59.90 fps** (`5.98 ms` GPU), Wiggling Fruit 3D **59.85 fps** (`3.59 ms` GPU).
      - **1080p**: Book Hub **59.90 fps** (`4.74 ms` GPU), Wiggling Fruit 3D **59.85 fps** (`2.46 ms` GPU).
20. **Book Hub Wiggling Fruit icon corruption & Windows WDDM write-watch hazard on deferred pool imports** (23 Nov, `runtime/vk.h`, `runtime/vk_exec_xfer.c`, `runtime/vk_texture.c`, `runtime/vk_memory.c`).
    On Windows, deferred host-memory imports (`TOTK_POOL_LAZY` -> `lazy_import()` -> `vkAllocateMemory(HOST_ALLOCATION)`)
    cause the WDDM driver (`MmProbeAndLockPages(IoWriteAccess)`) to set `MEM_WRITE_WATCH` dirty bits on every 4 KiB page of
    the entire 16–32 MiB pool. When a buffer later triggered `lazy_import()` on a shared pool containing GPU-owned streamed
    textures (`1024x1024` BC1 Book Hub fruit textures with GPU-copied tail mips `L1..L10`) or render targets, `snap_regions()`
    harvested 4096+ false dirty pages and `merge_cpu_levels()` overwrote live GPU `L1..L3` with stale RAM garbage (rainbow/black
    spots on the Book Hub Wiggling Fruit cluster) while also triggering false re-uploads of static textures.
    - Two-layer fix (stock `TOTK_POOL_LAZY=1` default preserved):
      1. `vk.h`, `vk_exec_xfer.c`, `vk_texture.c`: added per-level GPU ownership tracking (`gpu_levels` bitmask +
         `vk_texture_gpu_written_level()` on `copy_t2t`, `copy_decoded_astc`, `copy_b2t`, `clear_tex`); `merge_cpu_levels()`
         early-outs when all levels are GPU-owned, skips `gpu_lv == 1` levels (never overwrites GPU mips from stale host RAM),
         and checks whole pages `[clo, chi)` on `gpu_lv == 0` levels against `max(merge_gen, cpu_gen)`. Updated
         `alias_has_gpu_content`, `revive_reset`, and `vk_texture_write_back*` to compare against `max(gpu_gen, merge_gen)`.
      2. `vk_memory.c` (`import_pool_preserve_ww()` in `lazy_import()`): `mem_thaw` before `gen_lock`, fast 4-way `uint64_t`
         `page_hash64` over committed runs (`plat_mem_state`), then under `gen_lock` (`pool_lock -> lazy_lock -> gen_lock`):
         `query_stamp` (capture real prior writes) -> `import_pool` -> drain driver-induced OS write-watch bits without
         stamping -> re-hash and stamp only pages whose bytes actually changed during import.
    - Verified: 1:1 native crops at 4K, 1440p, and 1080p (including magnifying glass zoom) match console reference cleanly with
      `0` black/rainbow spots; Book Hub re-uploads and false merged levels dropped to `0`; `YATMB_VK_VALIDATION=1 YATMB_GPL=0`
      at 4K (`3,092` frames): `0` validation errors, `0` shader failures, `0` skipped draws; `YATMB_FLIGHT=1 YATMB_REPLAY_ASYNC=1`
      (`3,247` frames): `0` flicker/corrupt frames.

Smaller changes: `combined_program()` hash table; a 4 KiB-page bit set in the UPD filter (`upd_note`/`upd_read`); the
unknown device-property log now shows the caller; `vk_dump` prints SSBOs read through uniform blocks; and
`TOTK_DUMP_BUF=ubo:<slot>:<off>:<size>`.

## 5. Stage 1 view structure (established, correct)

Each frame renders the level as a deferred 1280x720 view. That view becomes the illustrated "Chapter 1: Wildwoods" book
page: pass 0000 draws the paper (`03_…png`), and pass 0001 composites the 1920x1080 page illustration
(`04_…png`, correct). A deferred 1284x724 gameplay camera then looks at Mr. E (a talking book) and the Yoshis. A
336x336 scene capture also renders the page every frame. The G-buffer is t0 scene colour (r11g11b10f), t1 normal
(rgb10a2), t2 material (bgra8), t3 albedo (bgra8srgb), t4 (bgra8), d24s8 depth. Lighting is pass ~181–190.

## 6. Fixed: the dark close-up terrain surfaces in Stage 1 (resolved 22 Nov 2026)

**Symptom** (`12_final_frame_12000_dark_closeup.png`): in dialog close-ups the foreground filling the lower half of the
screen rendered near-black, initially mistaken for Mr. E's open book page, while the "Chapter 1: Wildwoods" header,
plants, and Yoshis above it rendered normally.

### 6.1 What actually caused it (and why the earlier DBuffer hypothesis was ruled out)
- **The book page shader was already working.** In `dump_l8`, `pass 0171` (vs `16187ccc324adfe0`, fs
  `85540f828fcbccb4`) writes full-colour page albedo into `t3` (`[151, 130, 99]` at `(250, 120)`), and dummy DBuffer
  textures `tex 356` (`0,0,0,1`) and `tex 358` (`0.502,0.502,0.502,1`) have alpha `1.0` (an identity blend, not
  black-multiply).
- **The dark region was foreground terrain, bark, and rock**, drawn over the lower half of the frame by `pass 0175`
  (`723,798` black pixels; valid `t1` normals and `t2 = [0, 127, 255]`, `t3 = [0, 0, 0]`) and `pass 0173` (`44,536`
  black pixels on trunk/rock), using fragment shaders `efcffdf58785378d`, `4a30845f50e08874`, `fa0247dd936882c5`,
  `b8f406e3a89dda45`, and `fd6bd432e1b68c7b`. Sampled BC1/BC5 textures (`tex 2898` 2048x2048 ground, `tex 2083`
  1024x1024 bark, `tex 4773` 1024x1024) already contained valid non-zero blocks on the GPU.
- **Root cause (`0 * +Inf = NaN` without fragment FMZ):** those shaders compute per-instance colour variation with
  `normalize(frac(ObjectPosition / 100.0 + PerInstanceRandom)) * strength + base_albedo`. For meshes placed on `0` or
  1 m grid multiples with `PerInstanceRandom = 0`, the vector is `(0, 0, 0)`, so `inversesqrt(0.0) = +Inf` and
  `normalize(0)` multiplies `0.0 * (+Inf)`. On Switch 2 (SM86 census across captured `shaders_lvl1`: 19,138 `FFMA`
  and 21,621 `FMUL` instructions have `.FTZ`/`.FMZ` `b80=1, b76=0`), `0 * +Inf = 0`, so `fma` preserves `base_albedo`.
  With `vk_pipeline.c` defaulting `fmz_mode` to `vertex` only, fragment shaders used standard IEEE arithmetic
  (`0 * +Inf = NaN`, propagated through `fma`, then clamped to `0.0` black).
- **Why the earlier `TOTK_SPV_OVERRIDE` test didn't apply:** `make_module_linked()` runs `spirv_rebind()`,
  `spirv_fixup()`, `spirv_layer_from_viewport()`, and `spirv_fmz()` *before* `spv_override()`, so `spv_override()`
  hashes the post-fixup SPIR-V bytes rather than the pre-fixup dump hash `85540f828fcbccb4`.

### 6.2 Fix & verification
- **`runtime/vk_pipeline.c`:** changed default `fmz_mode` in `make_module_linked()` from `1` (`vertex`) to `2` (`all`),
  and updated `spirv_fmz()` to reuse existing `bvec2`/`bvec3`/`bvec4` type IDs when already declared in fragment/compute
  shaders.
- **Verification (default settings, no `TOTK_FMZ` override):**
  - `TOTK_GPU=null .\yoshi.exe --selftest`: `passed (0 failures)`.
  - Stage 1 close-up (`--seconds 330`, `TOTK_INPUT_SCRIPT=scripts\yoshi_level1_long.txt`, `TOTK_VK_VALIDATION=1`):
    `9705` frames presented, `0` validation errors, `0` shader failures, `746` FMZ module rewrites; full-colour grass
    foreground, bark, rock, hills, and book (`handover\screens\14_stage1_closeup_FIXED_fmz_all.png`).
  - Title screen regression (`--seconds 25`, `TOTK_VK_VALIDATION=1`): `1482` frames presented, `0` validation errors,
    `124` FMZ rewrites, renders cleanly.

### 6.3 Ruled out during investigation (preserved for reference)
- Movie / native-image textures feeding the page: in-level H.264 decoder does not feed frame 12000 terrain/book passes.
- Missing loose files or failed resource/pool creation: ruled out via `TOTK_TRACE=fs` and allocation logs.
- Depth `EQUAL` vs prepass PDO or stale streamed sub-page dummy textures (`tex 256`/`356`/`358`): ruled out via `dump_l8`
  and `dump_diag` inspection.

## 7. Frame rate (resolved 22–23 Nov 2026 — locked 60 FPS up to native 4K)
- Earlier Stage 1 / Book Hub bottlenecks (`~28–42 fps` from WC BAR reads in `vk_usnap` and `~48 fps` at 4K from uncoalesced
  scalar PCIe stores in `mirror_diff_wb.comp` + `vk_pool_fini` timeline stalls) are now completely resolved (§4 items 16 & 19).
- Verified clean performance (`YATMB_TRACE=perf`, NO `TOTK_SHOTS`, `FMZ=all`):
  - **4K (`2160p`)**: Book Hub **59.92 fps** (`9.65 ms` GPU, replay `4.62 ms`), Wiggling Fruit 3D **59.86 fps** (`6.93 ms` GPU,
    replay `1.85 ms`), steady exit 1% low **56.3 fps** (`0` frames > 25 ms, `0` slow pool releases). Identical lock under `REPLAY_ASYNC=1`.
  - **1440p**: Book Hub **59.90 fps** (`5.98 ms` GPU), Wiggling Fruit 3D **59.85 fps** (`3.59 ms` GPU).
  - **1080p**: Book Hub **59.90 fps** (`4.74 ms` GPU), Wiggling Fruit 3D **59.85 fps** (`2.46 ms` GPU).

## 8. What the game still needs (priority order)
1. **A longer play-test** across later chapters/stages, the staff roll (VP9 `.webm`), and the ending movie
   (`ED_W10_1080p.mp4`, H.264), with `YATMB_VK_VALIDATION=1`. The user has a DualSense connected.
2. **Review and commit** the uncommitted work when the user asks (commit locally only; ask before pushing).
3. Lower priority:
   - `--probe-vkexec` fails (needs TotK's `jobs.json`), and `--probe-nvn` reports "2 op kinds were not recorded". Both
     predate this work.
   - No H.264 decoder off Windows (`h264_sdl.c` is a stub).
   - Other titles have the same duplicated movie singleton (DKB, MTF, MKW, SM Wonder). Consider
     `GAME_QUIRK_RTLD_ORDER` for each, after a boot test.
   - `vk_dump.c` still prints uniform-block texture handles as "slot -1".
   - Texture handle type 3 and array elements past the first aren't resolved by `ubo_handle()`.

## 9. The hand-over pack: `C:\Games\Yoshi and the Mysterious Book PC\handover\`
Local only (derived game data; it must not leave the PC).
- `screens\`
  - `01` Stage 1 Yoshis coloured (after the streaming fix)
  - `02` title screen
  - `03` page paper (pass 0000)
  - `04` page illustration render target (correct)
  - `05` capture view, page albedo correct
  - `06` main view, page albedo black
  - `07` main-view depth (the prepass covers the page)
  - `08` main view after lighting
  - `11` the override test (still black; override not applied)
  - `12` final frame 12000, the dark close-up
  - `13` an end-of-level-1 shot
  - `14` Stage 1 close-up after fragment FMZ fix (grass/bark/rock coloured instead of black, revealing the misplaced foreground geometry)
  - `15` Book Hub FIXED (clean open "Chapter 1: Wildwoods" book, live magnifying glass, Blue Yoshi, zero occluding geometry, default mirror mode + `TOTK_VK_VALIDATION=1`)
  - `16` Stage 1 (`Chapter 1: Wildwoods`) FIXED (full painted 3D gameplay with Blue Yoshi, sketch-to-paint edge, Mr. E dialogue, locked 59.8 fps, `0` validation errors, `0` shader failures)
  - `17` Stage 1 orange-leaf water bridge FIXED (clean water surface & reflection after `AstOptimizer` patch `0028` + storage-image `gpu_owned` fix; 41 consecutive stationary frames `0.25–0.38/255` mean diff)
  - `18` Stage 1 cave FIXED (previously solid red/magenta/white `R=757` Niagara translucency blowup; now clean across all frames `4800–5675`)
- `shader\`: the page fragment shader as `.spv`, `.spvasm` and `.glsl`, plus the NOMASK experiment `.spv`/`.spvasm`.
- `logs\`
  - `dump_l8_passes_with_ubo_vectors.txt` (has the `c4[204]` evidence)
  - `dump_l7_passes_with_ubo.txt`
  - the run logs with fs and codec traces
- `scripts\`: `yoshi_level1_long.txt` (Book Hub input script), `stage1_flower.txt` (automated Title -> Book Hub -> Flower Page -> Stage 1 gameplay script), `trace_spv.py` (SPIR-V backtracer:
  `python trace_spv.py <x.spvasm> %id depth`), and `patch_ubo_vec.py` (how the `TOTK_DUMP_UBO_VEC` patch was applied).
- `uncommitted_tracked_changes.patch` (`git diff` of all 45 tracked files), `untracked_files\` (the 7 new files),
  `git_status.txt`. To restore on a clean `ca7b691`: `git apply uncommitted_tracked_changes.patch`, then copy
  `untracked_files\*` back.
- Full frame dumps still in `build\yoshi102\`: `dump_l7` (UBO, frame 12000), `dump_l8` (UBO vectors), `dump_l9`
  (override test). Older `dump_l1`–`dump_l6` are gone (deleted outside this session).

## 10. Session history (what happened, in order)
1. Boot crash in `FMallocBinned2` → rtld load-order binding (§4 item 1). First Vulkan screenshot.
2. "Add H.264 host decoder" → Media Foundation backend (item 2).
3. "Fix SM86 ops" → 120/120 stages lower (item 3).
4. "Chase black screen" → per-stage program binding (item 4).
5. "Text glyph boxes" → texture handles in uniform blocks (item 5).
6. "Chase background" → the menu background (only mask 0 means all stages). The user then reported a black screen
   booting the first level (fixed), "Menu seems fine now", then "Start Menu background broken again" (caused by
   H.264 low-latency mode, reverted).
7. A hand-over for Gemini. Gemini then added items 6 and 7 (native images, texel buffers, translator and validation
   fixes; validation errors from 33 to 0).
8. The user asked for the SM Wonder crash fix to be pushed to GitHub. That was forwarded to the Wonder session
   (`local_2c35cd93…`), which **failed**; the user was told. It is still not done.
9. The hub session asked for the Stage 1 glitches and low fps. "Fix the glitches" → the texture streaming fix (item 8).
   Frame rate measured (§7).
10. "Play-test first", "Chase the dark close up", "Keep digging" → §6, plus the `romfs` trailing-slash fix (item 9),
    fs/UBO debug tooling, and the override experiment (stopped while it was running).
11. Proved dark close-up terrain (`efcffdf58785378d` et al., not page shader `85540f828fcbccb4`) came from missing
    fragment FMZ semantics (`0 * inversesqrt(0) = NaN`), enabled `spirv_fmz` for all stages by default and hardened
    `bvec` lookup (`vk_pipeline.c`), cleaned game name from `vk_texture.c`, and verified (`--selftest`, Stage 1 + title
    under `TOTK_VK_VALIDATION=1`) → §4 item 10, §6.
12. User identified that the now-coloured grass/hills/rock/trunk in `14` was misplaced geometry occluding Mr. E's book.
    Diffed clean `dump_1900` vs occluded `dump_1920`, proved `TOTK_MEMORY=import` rendered the open book cleanly,
    confirmed `105,719` mirror mismatches on `InstanceSceneData`/`PrimitiveSceneData` via `TOTK_MEMORY=verify`, and
    fixed VRAM mirror coherence initially via `vk_mem_no_mirror()` (`15_book_hub_FIXED_mirror_demote.png`).
13. User reported Stage 1 black screen with UI text after selecting the flower and iffy performance. Fixed the two
    missing SM86 Ampere lowering paths (`0x624` negated cbuf addend and `0x381`/`0x981` reversed zero-fill predicate in
    `lower_to_maxwell.h`), bringing Stage 1 (`Chapter 1: Wildwoods`) to full painted 3D gameplay (`16_stage1_wildwoods_FIXED.png`).
    Profiled the Book Hub performance regression (`65 ms` GPU / `15.3 fps` from demoting guarded pools to PCIe) and
    replaced pool demotion with a GPU compute diff write-back pass (`runtime/shaders/mirror_diff_wb.comp` +
    `vk_mem_guarded_write()` in `vk_memory.c`, routed via `rec_push()`). Re-verified `--selftest` (`0` failures),
    end-to-end Title -> Book Hub -> Flower Page -> Stage 1 under `TOTK_VK_VALIDATION=1` (`2948` frames, `0` errors),
    `TOTK_MEMORY=verify` (`4` mismatches / `19.9M` pages), title regression (`1182` frames, `0` errors), Book Hub
    `40–45 fps` (`9.5 ms` GPU), and Stage 1 locked `59.8 fps` (`1% low 58.0 fps`, `1.8–2.0 ms` GPU).
14. User reported water flicker, lighting-effect screen flicker, and neon purple streaks in Stage 1. Reproduced
    deterministically from flower-bloom VFX (`f04375`) across the water bridge into the cave (`f05675`) and captured
    blown-up `dump_f5200` (`pass_0126_t0` `R=757` Separate Translucency from Niagara GPU particles). Traced root cause
    to Ryujinx `AstOptimizer.cs` sinking `LDS` shared-memory loads past `STS` stores in Niagara's exclusive prefix sum
    (`cs 1b88456e099473cb` / `cs 9f37d16a0986e404`), plus compute storage images staying `gpu_owned=0` (`vk_texture.c`)
    and unpatched missing VS outputs on depth-only VS+GS shadow pipelines (`vk_pipeline.c`). Landed patch
    `0028-safe-ast-expression-propagation.patch`, `vk_texture_storage_bound_locked(img, written)`, and VS->GS
    `spirv_add_outputs` synthesis; verified across `5985` frames under `TOTK_VK_VALIDATION=1` (`0` errors, `0` skipped
    draws, `0` VS->GS warnings), `41` stationary bridge frames (`0.25–0.38/255` pure-water diff), `--selftest`, all 3
    `--probe-vkgeometry*` probes, `TOTK_MEMORY=verify`, and `TOTK_TRACE=perf` (`59.7–59.9 fps` in Stage 1).
15. Fixed black flowers/sprouts/foliage in Wiggling Fruit 3D via Ryujinx `Optimizer.RemoveNode` multi-dest `TLD.B` DCE
    patch `0029`; added cached host-RAM shadow `Arena.cpu` in `vk_usnap.c` (6.1x faster replay `33 ms -> 4.3–5.4 ms`,
    Book Hub locked 60 fps at 1080p/1440p); wired native UE5 resolution (`720p`–`2160p`) & linear UI DPI scaling hooks
    (`GAME_QUIRK_GRAPHICS_SCALE_ZERO`, `GAME_QUIRK_UE5_CVAR_RES`, `res_display_size`, gated FF DLSS override); completed
    `yatmb.exe` v`0.1.0` launch rebrand (`yatmb.ini`, `YATMB_` prefix, spotted-egg icon, `Storybook Meadow` F1 theme,
    `nn::account` safe stubs).
16. Achieved locked 60 FPS at native 4K (`YATMB_RESOLUTION=2160`, full fidelity, `FMZ=all`) and fixed Book Hub Wiggling
    Fruit icon corruption (23 Nov): coalesced `mirror_diff_wb.comp` to 128-bit `uvec4` (41x faster `DIFF_WB`: `8.516 ms ->
    0.18 ms`, 4K Book Hub GPU `19.3 ms -> 9.65 ms`), added per-pool `PoolRec.last_fence` (`64 -> 0` slow pool releases),
    ReBAR-preferred `scratch_aligned`, whole-target `LOAD_OP_CLEAR` coalescing, per-level `gpu_levels` ownership in
    `vk_texture.c`/`vk_exec_xfer.c`/`vk.h`, and `import_pool_preserve_ww()` in `vk_memory.c` neutralizing Windows WDDM
    `MmProbeAndLockPages` false `MEM_WRITE_WATCH` dirty bits on `lazy_import()`. Independently verified across all 7 checks
    (build + `--check`, `--selftest`, 4K `YATMB_VK_VALIDATION=1 YATMB_GPL=0` `3,092` frames `0` errors, 4K/1440p/1080p
    locked `59.81–59.92 fps` on `REPLAY_ASYNC=0` and `1`, 4K `YATMB_FLIGHT=1` `3,247` frames `0` corrupt frames, 1:1 visual
    crops matching console reference, live `Slot00` untouched).
17. Built and end-to-end verified the complete **SteelTemple YATMB `0.1.0` Release Suite** (23 Nov):
    - Confirmed steady 60 fps Book Hub matrix (`1080p`: `59.83 fps / 4.77 ms GPU`, `1440p`: `59.81 fps / 6.01 ms GPU`,
      `4K`: `59.82 fps / 9.66 ms GPU`; `ver_2160p_val`: `2,011` frames, `0` validation errors, `0` shader failures, `0`
      skipped draws, `0` unimplemented calls).
    - Fixed `tools/build_game.py` so `.rc` compiles directly into `yatmb.exe` under `--runtime-lib` (instead of being
      dropped inside `libyatmbrt.a`), added `'yoshi102': '1.0.2'` to `DISPLAY_VERSIONS`, cleaned duplicate key in
      `tools/data/expected-yoshi102.json`, prioritized `yatmb.exe` in `tools/prepare_shaders.py`, added `tools/pack_romfs.py`,
      `yatmb.ini.example` (clean hardware-agnostic defaults), and `launcher/yatmb_version.txt` (`0.1.0`).
    - Generated original Storybook Meadow art assets (`tools/make_yatmb_icons.py` -> `runtime/yatmb.png`,
      `runtime/yatmb_book.png`, `launcher/assets/yatmb.ico`), built the static SDL3 + Dear ImGui + zstd Setup Wizard &
      uninstaller (`tools/installer_yatmb/installer.cpp`, `YATMBV01` magic), the Storybook Meadow GUI launcher
      (`launcher/YATMBLauncher.py`, `launcher/yatmb_dump.py`, `YATMBLauncher.spec`, supporting `.nup` containers & direct
      `ExeFS`/`RomFS` dumps and targeting `https://github.com/STS78721/YATMB`), and the clean allowlist packager
      (`tools/build_yatmb_release.py`, `verify_clean_stage` passing on all `7,164` staged files).
    - End-to-end verified on final artifacts: visually inspected all Setup Wizard + `YATMBLauncher` UI screenshots (after
      fixing footer pinning, path truncation, GPU label timing, and disabled Play contrast), ran automated Setup Wizard
      install (`7,166` files, zero `yatmb.ini`, `HKCU\...\Uninstall\YATMB-test`), compiled & linked `yatmb.exe` using ONLY
      the installed standalone toolchain (`117.5 s`, `795` verified objects, PE `FileVersion=0.1.0.0` /
      `ProductVersion=0.1.0`), passed `YATMB_GPU=null yatmb.exe --selftest` (`0` failures), booted cleanly with zero-config
      defaults (`1,062` frames, `0` validation errors, `0` shader failures, `0` skipped draws, crisp 1080p title frame),
      and verified `uninstall.exe` cleanly removes program files & registry entry while preserving `yatmb.exe` & saves.

## 11. Related notes
- `docs/UNIVERSAL_NS2_TO_PC_PLAYBOOK.md` §5.10: the rtld binding-order write-up and the detailed history.
