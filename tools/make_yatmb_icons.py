"""Generate original Storybook Meadow icon & storybook emblem artwork for SteelTemple YATMB.

Zero copyrighted game assets: uses the procedural spotted-egg icon (`runtime/yatmb.ico`) and Pillow
vector drawing at 4x supersampling to emit:

  runtime/yatmb.png          512 px rounded emerald storybook tile (Setup header & Launcher icon)
  runtime/yatmb_book.png     512 px open storybook + hovering spotted egg + golden stars on alpha
  launcher/assets/yatmb.ico  Launcher executable icon (synced from runtime/yatmb.ico)

Usage: python tools/make_yatmb_icons.py
"""

from __future__ import annotations

import math
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SS = 4

FOREST_TOP = (24, 58, 34)
FOREST_BOT = (9, 24, 15)
MEADOW_GLOW = (96, 226, 68)
GOLD = (255, 224, 96)
GOLD_DEEP = (212, 162, 54)
LEATHER_OUT = (86, 48, 24)
LEATHER_IN = (128, 72, 36)
PARCHMENT = (252, 246, 228)
PARCHMENT_SHADE = (228, 214, 184)
INK_LINE = (176, 154, 118)
RIBBON = (214, 52, 62)


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(len(a)))


def vertical_gradient(size: int, top, bot) -> Image.Image:
    g = Image.new("RGB", (1, size))
    for y in range(size):
        g.putpixel((0, y), lerp(top, bot, y / max(1, size - 1)))
    return g.resize((size, size))


def draw_four_star(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float, fill) -> None:
    pts = []
    for i in range(8):
        ang = i * math.pi / 4.0
        rad = r if i % 2 == 0 else r * 0.28
        pts.append((cx + math.cos(ang) * rad, cy + math.sin(ang) * rad))
    d.polygon(pts, fill=fill)


def load_egg_rgba(size: int) -> Image.Image:
    ico = ROOT / "runtime" / "yatmb.ico"
    im = Image.open(ico).convert("RGBA")
    return im.resize((size, size), Image.LANCZOS)


def make_tile(px: int = 512) -> Image.Image:
    size = px * SS
    rad = int(size * 0.22)
    bg = vertical_gradient(size, FOREST_TOP, FOREST_BOT).convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), rad, fill=255)

    # Soft sunlit leaf-green + warm golden aura behind the egg
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((size * 0.16, size * 0.14, size * 0.84, size * 0.84), fill=MEADOW_GLOW + (72,))
    gd.ellipse((size * 0.28, size * 0.24, size * 0.72, size * 0.72), fill=GOLD + (44,))
    glow = glow.filter(ImageFilter.GaussianBlur(size * 0.08))
    bg.alpha_composite(glow)

    # Subtle storybook corner stars
    stars = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    sd = ImageDraw.Draw(stars)
    for sx, sy, sr, al in [
        (0.18, 0.20, 0.048, 225),
        (0.82, 0.22, 0.040, 210),
        (0.80, 0.78, 0.044, 195),
        (0.20, 0.78, 0.032, 175),
    ]:
        draw_four_star(sd, size * sx, size * sy, size * sr, GOLD + (al,))
    bg.alpha_composite(stars)

    # Spotted Yoshi egg centered with gentle drop shadow
    egg_sz = int(size * 0.72)
    egg = load_egg_rgba(egg_sz)
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    s_mask = egg.getchannel("A")
    s_fill = Image.new("RGBA", (egg_sz, egg_sz), (4, 14, 8, 120))
    s_fill.putalpha(s_mask)
    off = (size - egg_sz) // 2
    shadow.paste(s_fill, (off, off + int(size * 0.025)), s_fill)
    shadow = shadow.filter(ImageFilter.GaussianBlur(size * 0.02))
    bg.alpha_composite(shadow)
    bg.alpha_composite(egg, (off, off - int(size * 0.008)))

    # Double golden storybook border
    rim = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    rd = ImageDraw.Draw(rim)
    rd.rounded_rectangle(
        (int(size * 0.012), int(size * 0.012), int(size * 0.988), int(size * 0.988)),
        rad,
        outline=GOLD + (205,),
        width=max(2, int(size * 0.018)),
    )
    rd.rounded_rectangle(
        (int(size * 0.042), int(size * 0.042), int(size * 0.958), int(size * 0.958)),
        int(rad * 0.88),
        outline=MEADOW_GLOW + (120,),
        width=max(2, int(size * 0.008)),
    )
    bg.alpha_composite(rim)
    bg.putalpha(Image.composite(bg.getchannel("A"), Image.new("L", (size, size), 0), mask))
    return bg.resize((px, px), Image.LANCZOS)


def make_storybook_emblem(px: int = 512) -> Image.Image:
    """Open storybook + glowing magic pages + hovering spotted egg + golden stars on alpha."""
    size = px * SS
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    # Radiant magical meadow glow rising from the open book
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((size * 0.14, size * 0.12, size * 0.86, size * 0.78), fill=MEADOW_GLOW + (72,))
    gd.ellipse((size * 0.24, size * 0.22, size * 0.76, size * 0.70), fill=GOLD + (88,))
    glow = glow.filter(ImageFilter.GaussianBlur(size * 0.075))
    layer.alpha_composite(glow)

    d = ImageDraw.Draw(layer)
    cx = size * 0.50
    by = size * 0.72
    bw = size * 0.42
    bh = size * 0.16

    # Soft ground shadow under the storybook
    sh = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse(
        (cx - bw * 1.04, by + bh * 0.55, cx + bw * 1.04, by + bh * 1.25),
        fill=(4, 14, 8, 125),
    )
    sh = sh.filter(ImageFilter.GaussianBlur(size * 0.025))
    layer.alpha_composite(sh)

    # Leather storybook cover (left & right wings + spine)
    left_cover = [
        (cx - bw * 1.02, by - bh * 0.18),
        (cx - bw * 0.04, by + bh * 0.22),
        (cx - bw * 0.04, by + bh * 0.94),
        (cx - bw * 0.94, by + bh * 0.52),
    ]
    right_cover = [
        (cx + bw * 1.02, by - bh * 0.18),
        (cx + bw * 0.04, by + bh * 0.22),
        (cx + bw * 0.04, by + bh * 0.94),
        (cx + bw * 0.94, by + bh * 0.52),
    ]
    d.polygon(left_cover, fill=LEATHER_OUT + (255,), outline=GOLD_DEEP + (235,))
    d.polygon(right_cover, fill=LEATHER_OUT + (255,), outline=GOLD_DEEP + (235,))
    d.rounded_rectangle(
        (cx - bw * 0.07, by + bh * 0.18, cx + bw * 0.07, by + bh * 1.00),
        int(size * 0.012),
        fill=LEATHER_IN + (255,),
        outline=GOLD + (220,),
        width=max(2, int(size * 0.006)),
    )

    # Layered page edge thickness (warm shaded parchment)
    for side in (-1, 1):
        edge_pts = [
            (cx + side * bw * 0.04, by + bh * 0.18),
            (cx + side * bw * 0.94, by - bh * 0.24),
            (cx + side * bw * 0.90, by + bh * 0.40),
            (cx + side * bw * 0.04, by + bh * 0.80),
        ]
        d.polygon(edge_pts, fill=PARCHMENT_SHADE + (255,))

    # Curved open top pages (left & right)
    def page_poly(side: int) -> list[tuple[float, float]]:
        pts = [(cx + side * bw * 0.03, by + bh * 0.14)]
        steps = 16
        for k in range(1, steps + 1):
            t = k / steps
            x = cx + side * bw * (0.03 + 0.89 * t)
            arch = math.sin(t * math.pi) * bh * 0.42
            y = by + bh * (0.14 - 0.52 * t) - arch
            pts.append((x, y))
        for k in range(steps, -1, -1):
            t = k / steps
            x = cx + side * bw * (0.03 + 0.85 * t)
            arch = math.sin(t * math.pi) * bh * 0.25
            y = by + bh * (0.64 - 0.36 * t) - arch
            pts.append((x, y))
        return pts

    d.polygon(page_poly(-1), fill=PARCHMENT + (255,), outline=GOLD_DEEP + (180,))
    d.polygon(page_poly(1), fill=PARCHMENT + (255,), outline=GOLD_DEEP + (180,))

    # Subtle storybook text lines on both pages
    lw = max(2, int(size * 0.005))
    for side in (-1, 1):
        for row in range(3):
            frac_y = 0.24 + row * 0.15
            x1 = cx + side * bw * 0.18
            x2 = cx + side * bw * 0.72
            y1 = by + bh * (frac_y - 0.08)
            y2 = by + bh * (frac_y - 0.28)
            d.line([(x1, y1), (x2, y2)], fill=INK_LINE + (155,), width=lw)

    # Center gutter crease + crimson ribbon bookmark with V-notch
    d.line([(cx, by + bh * 0.10), (cx, by + bh * 0.68)], fill=INK_LINE + (210,), width=max(2, int(size * 0.007)))
    rib = [
        (cx - size * 0.015, by + bh * 0.56),
        (cx + size * 0.015, by + bh * 0.56),
        (cx + size * 0.019, by + bh * 1.28),
        (cx, by + bh * 1.12),
        (cx - size * 0.019, by + bh * 1.28),
    ]
    d.polygon(rib, fill=RIBBON + (255,), outline=(140, 22, 30, 220))

    # Hovering spotted Yoshi egg above the open storybook
    egg_sz = int(size * 0.48)
    egg = load_egg_rgba(egg_sz)
    ex = int(cx - egg_sz * 0.50)
    ey = int(size * 0.12)
    layer.alpha_composite(egg, (ex, ey))

    # Floating golden storybook stars around the hovering egg
    for sx, sy, sr, al in [
        (0.20, 0.28, 0.044, 245),
        (0.81, 0.24, 0.048, 245),
        (0.16, 0.48, 0.028, 200),
        (0.85, 0.44, 0.032, 215),
        (0.32, 0.12, 0.026, 210),
        (0.70, 0.11, 0.024, 195),
    ]:
        draw_four_star(d, size * sx, size * sy, size * sr, GOLD + (al,))

    return layer.resize((px, px), Image.LANCZOS)


def main() -> None:
    ico_src = ROOT / "runtime" / "yatmb.ico"
    ico_dst = ROOT / "launcher" / "assets" / "yatmb.ico"
    ico_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ico_src, ico_dst)
    print(f"Synced {ico_dst}")

    tile_out = ROOT / "runtime" / "yatmb.png"
    make_tile(512).save(tile_out, format="PNG", optimize=True)
    print(f"Generated {tile_out} ({tile_out.stat().st_size} B)")

    book_out = ROOT / "runtime" / "yatmb_book.png"
    make_storybook_emblem(512).save(book_out, format="PNG", optimize=True)
    print(f"Generated {book_out} ({book_out.stat().st_size} B)")


if __name__ == "__main__":
    main()
