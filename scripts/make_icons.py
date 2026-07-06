"""
Generate the home-screen / PWA app icons for the WC2026 Forecast Tracker.

Editorial look matching the site: ink background (#1a1a1f), cream trophy
(#f3f1ea), red accent band (#cf2e2e). Drawn at 4x and downsampled (LANCZOS)
for smooth anti-aliased edges, then exported at the sizes iOS/Android need.

Run once (needs Pillow); the PNGs are committed, so CI/publish.py just copy
them — no image libs required at deploy time.

    python scripts/make_icons.py
"""
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ASSETS = os.path.join(ROOT, "assets", "pwa")

INK = (26, 26, 31)         # #1a1a1f
CREAM = (243, 241, 234)    # #f3f1ea
RED = (207, 46, 46)        # #cf2e2e

S = 4                      # supersample factor (design space is 1024 -> 4096)


def _font(size):
    for p in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def draw_master():
    """Return a 4096px master icon (full-bleed, art within the maskable safe zone)."""
    N = 1024 * S
    img = Image.new("RGB", (N, N), INK)
    d = ImageDraw.Draw(img)

    def sc(*xy):
        return tuple(v * S for v in xy)

    # --- trophy cup -------------------------------------------------------
    # bowl body (tapers to a rounded point)
    bowl = [(352, 322), (672, 322), (636, 486), (566, 566),
            (512, 594), (458, 566), (388, 486)]
    d.polygon([sc(*p) for p in bowl], fill=CREAM)
    # rim (cream ellipse) + inner opening (ink) => open-cup look
    d.ellipse(sc(348, 290, 676, 356), fill=CREAM)
    d.ellipse(sc(374, 300, 650, 348), fill=INK)

    # handles (thick C arcs on each side)
    d.arc(sc(268, 300, 404, 476), start=40, end=300, fill=CREAM, width=30 * S)
    d.arc(sc(620, 300, 756, 476), start=240, end=140, fill=CREAM, width=30 * S)

    # red accent band across the cup
    d.rounded_rectangle(sc(360, 386, 664, 420), radius=8 * S, fill=RED)

    # stem + base
    d.rectangle(sc(486, 590, 538, 656), fill=CREAM)
    d.rounded_rectangle(sc(446, 652, 578, 690), radius=10 * S, fill=CREAM)
    d.rounded_rectangle(sc(388, 690, 636, 746), radius=16 * S, fill=CREAM)

    # --- wordmark ---------------------------------------------------------
    f = _font(150 * S)
    txt = "2026"
    bb = d.textbbox((0, 0), txt, font=f)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    d.text(((N - tw) / 2 - bb[0], 812 * S - bb[1]), txt, font=f, fill=CREAM)
    # small red "WORLD CUP" kicker above the year
    fk = _font(52 * S)
    k = "WORLD CUP"
    bk = d.textbbox((0, 0), k, font=fk)
    kw = bk[2] - bk[0]
    d.text(((N - kw) / 2 - bk[0], 752 * S - bk[1]), k, font=fk, fill=RED)

    return img


def main():
    os.makedirs(ASSETS, exist_ok=True)
    master = draw_master()
    # (filename, size)
    for name, size in [
        ("icon-512.png", 512),
        ("icon-512-maskable.png", 512),
        ("icon-192.png", 192),
        ("apple-touch-icon.png", 180),
    ]:
        master.resize((size, size), Image.LANCZOS).save(os.path.join(ASSETS, name))
        print(f"  wrote {name} ({size}px)")
    # a small favicon too
    master.resize((64, 64), Image.LANCZOS).save(os.path.join(ASSETS, "favicon-64.png"))
    print("  wrote favicon-64.png (64px)")
    print(f"icons -> {os.path.relpath(ASSETS, ROOT)}/")


if __name__ == "__main__":
    main()
