# Changelog

## SteelTemple YATMB 0.1.2 — Language & Locale Hotfix

Hotfix preventing unexpected Japanese fallback on Russian and Portuguese Windows locales, and adding a Game Language selector to **YATMBLauncher** and the in-game `F1` menu.

■ Fixes & Improvements

- **Fixed Unexpected Japanese Fallback on Russian & Portuguese Windows Systems:** *Yoshi and the Mysterious Book* (`1.0.2`) ships 14 locales (excluding Russian `ru` and plain European Portuguese `pt`) and defaults to Japanese (`ja`) whenever the OS returns an unsupported language code. The `yatmb` profile now automatically maps Russian locales to English (`en-US`) and maps all Portuguese locales (`pt-BR`, `pt-PT`, and explicit `lang = pt`) to Brazilian Portuguese (`pt-BR`).
- **Game Language Selector in YATMBLauncher & F1 Menu:** Added a **Game Language** dropdown (`auto` + all 14 supported game languages) to **YATMBLauncher** → **Graphics & Input**, added **Português (Brasil)** (`pt-BR`) to the in-game `F1` → **System** → **Game language** list, and hid unsupported `Русский` from the in-game selector.
- **Startup Language Diagnostics:** Logs the resolved game language and detected system locale once on startup (`oe: desired language ...`) for easier troubleshooting, and treats explicit `lang = auto` in `yatmb.ini` cleanly as automatic detection.

---

## SteelTemple YATMB 0.1.1 — Stability & AMD Hotfix

Hotfix resolving reproducible first-boot crashes (`access violation writing address 0x3`) on AMD integrated/discrete GPUs and slower systems during initial shader compilation.

■ Fixes & Improvements

- **Fixed First-Boot Hang Detector Crash (`0xc0000005` writing `0x3`):** Disabled Unreal Engine 5's console thread hang watchdog (`FThreadHeartBeat`) on PC builds so cold shader translation and pipeline compilation on AMD GPUs, integrated graphics (e.g. Radeon 890M), and handhelds never trigger false 25-second crash kills during startup or shader pre-warming.
- **Faster Compute Shader Compilation on AMD (Graphics-Only `.FMZ` Default):** Scoped fused-multiply-zero (`FMZ`) SPIR-V rewriting to graphics stages (vertex, tessellation, geometry, and fragment) by default instead of inflating large UE5 compute shaders for AMD's LLPC compiler, preserving all Stage 1 terrain visual fixes while cutting first-run compute pipeline build times.
- **Removed Pipeline Lock Stalls During Compute Compiles:** Released the global pipeline table mutex while `vkCreateComputePipelines` runs on the driver so background pipeline cache autosaves and worker threads never stall during heavy compute shader builds.
- **Dynamic Setup Wizard Versioning:** Setup Wizard PE version metadata now tracks the release version (`0.1.1`) automatically.

---

## SteelTemple YATMB 0.1.0 — Early Release

Initial early public release of **SteelTemple YATMB**, bringing *Yoshi and the Mysterious Book* (`1.0.2`) natively to Windows PC with a dedicated Setup Wizard, **YATMBLauncher**, Vulkan 1.3 renderer, and clean hardware-agnostic default settings.

> **Early Release Notice:** The game is working and playable today, but as an early `0.1.0` release there may still be rendering glitches, shader compilation stutters, or performance issues in later chapters and across different GPU/CPU setups.

■ Highlights

- **Native Windows PC Recompilation (`yatmb.exe`):** Ahead-of-time ARM64-to-C lifting and local LLVM/Ninja compilation across all 5 modules (`main`, `subsdk0`, `subsdk1`, `subsdk2`, `sdk`) with Switch 2 rtld load-order symbol resolution and safe account stubs.
- **Storybook Meadow Setup Wizard & YATMBLauncher:** Self-contained Windows installer (`SteelTemple-YATMB-0.1.0-Full-Setup-Wizard.exe`) and portable archive with bundled Python, LLVM-MinGW, Ninja, and `ns2_xlate`. Supports both `.nup` containers (combined or split base + update) and direct `ExeFS`/`RomFS` dump folders, with `7/7` SHA-256 verification, automatic shader pre-warming, save backup vault, and built-in GitHub release auto-updates.
- **Vulkan 1.3 Renderer & SM86 Shader Lowering:** Full Ampere (`SM86`) shader lowering, fragment/all-stage `.FMZ` (`0 * x = 0`) semantics, per-stage program binding, uniform-block texture/sampler handle resolution, safe AST shared-memory ordering & multi-dest texture load fixes, 128-bit coalesced GPU compute diff write-back, and per-level GPU texture ownership for streamed mips.
- **Native 720p–4K Resolution & UI Scaling:** Drive UE5 natively at `Original`, `720p`, `900p`, `1080p`, `1440p`, or `2160p (4K)` with linear UI DPI scaling, AMD FSR 1.0, `16x` anisotropic filtering, and the **Storybook Meadow** in-game `F1` menu.
- **Host H.264 Movie Playback:** Native Windows Media Foundation H.264 decoding for title, opening, and in-level movies (including decode-to-texture playback).
- **Clean Zero-Config Default Profile:** Starts cleanly at `1920x1080` Windowed, Original internal resolution, AMD FSR, `16x` Aniso, Frame Generation Off, and `60 FPS` limit with no personal `.ini` settings bundled.

■ Known Issues (Early Release)

- As an early `0.1.0` release, rendering bugs, visual artifacts, and performance dips may still occur in untested stages, later chapters, or certain GPU/driver configurations.
- First-time traversal into new scenes can cause brief shader translation stutters before the local shader cache warms up.
- Online features are not supported.

■ Install & Update

- **New install:** Run `SteelTemple-YATMB-0.1.0-Full-Setup-Wizard.exe`, open **YATMBLauncher** → **SETUP FROM DUMP**, select your *Yoshi and the Mysterious Book* `1.0.2` `.nup` container or `ExeFS`/`RomFS` folders, click **VERIFY & BUILD YATMB.EXE**, and press **PLAY YOSHI PC**.
- **Portable:** Extract `SteelTemple-YATMB-0.1.0-Portable-StandAlone.zip` anywhere and launch `YATMBLauncher.exe`.
- **Update:** Future updates apply cleanly via **YATMBLauncher**'s built-in updater or `Update.zip` without touching your dump, saves, or `yatmb.ini`.
