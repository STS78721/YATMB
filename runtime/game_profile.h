// Universal NS2 to PC: central game identity & per-title runtime quirks registry.
// Looks up rt_application_id at startup so game-specific fixes live in one table
// instead of scattered magic constants across kernel/system/graphics files.
#pragma once
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum {
    GAME_QUIRK_NONE             = 0,
    GAME_QUIRK_PT_BR            = 1u << 0, // Ship PT-BR when locale is "pt" (DKB)
    GAME_QUIRK_MTF_WORKER_ARGS  = 1u << 1, // ThreadType doubly-indirect worker arg fix (MTF)
    GAME_QUIRK_MKW_HEAP_FALLBACK= 1u << 2, // Wrap sead::ExpHeap::alloc / camera / delegate checks (MKW)
    GAME_QUIRK_MKW_VTABLES      = 1u << 3, // Patch ExpHeap / dispose guest vtables after init_array (MKW)
    GAME_QUIRK_TOTK_PATCH_RES   = 1u << 4, // Game uses TotK-style output/scene/aspect assembly patches
    GAME_QUIRK_NO_RU            = 1u << 5, // Title disables "ru" in language table; fall back to en-US (MTF)
    GAME_QUIRK_RTLD_ORDER       = 1u << 6, // Bind default-visibility symbols in load order, as rtld does (loader.c)
    GAME_QUIRK_GRAPHICS_SCALE_ZERO = 1u << 7, // nn::oe::GetCurrentGraphicsScale: 0 is full quality (1.0x), 2 is throttled
    GAME_QUIRK_UE5_CVAR_RES     = 1u << 8, // Drive NS2_RESOLUTION via UE5 console variables (r.SetRes, DynamicRes, ScreenPercentage)
};

typedef struct {
    uint64_t title_id;
    const char *short_name;     // e.g. "dkb", "mkw", "mtf", "yatmb", "totk", "ns2"
    const char *display_name;   // Human-readable title
    const char *ini_name;       // Preferred config filename, e.g. "yatmb.ini"
    const char *default_menu_theme; // Default F1 menu theme: "storybook", "tennis", "dark", "light"
    uint32_t docked_w, docked_h;
    uint32_t handheld_w, handheld_h;
    uint32_t quirks;
} RtGameProfile;

const RtGameProfile *game_profile(void);
int game_profile_has(uint32_t quirk);
void game_profile_log(void);

#ifdef __cplusplus
}
#endif
