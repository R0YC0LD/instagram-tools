"""
make_icon.py  -  draws the application icon: Pacman eating an Instagram-style camera glyph.

Outputs (next to the project):
  assets/app.ico          multi-size Windows icon (used for the .exe)
  assets/app_preview.png  1024 px preview
  src/igdm_assets.py      the same icon embedded as base64 (so the exe needs no data files)

Everything is drawn from scratch with Pillow (supersampled for smooth edges).
"""

import base64
import io
import math
import os

from PIL import Image, ImageDraw, ImageChops

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
S = 1024            # master canvas
SS = 2              # supersampling factor for anti-aliasing


def gradient_square(size, stops):
    """Diagonal gradient (bottom-left -> top-right), stops = [(t, (r, g, b)), ...]."""
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = ((x / (size - 1)) + (1 - y / (size - 1))) / 2
            for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
                if t0 <= t <= t1:
                    k = (t - t0) / (t1 - t0) if t1 > t0 else 0
                    px[x, y] = tuple(int(c0[i] + (c1[i] - c0[i]) * k) for i in range(3))
                    break
    return img


def rounded_mask(size, box, radius):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle(box, radius=radius, fill=255)
    return m


def draw_master():
    n = S * SS
    k = SS
    canvas = Image.new("RGBA", (n, n), (0, 0, 0, 0))

    # --- Instagram-style glyph (rounded square, gradient, ring + dot) --------------------------
    gx0, gy0, gx1, gy1 = 372 * k, 190 * k, 972 * k, 790 * k
    side = gx1 - gx0
    grad = gradient_square(side, [(0.0, (254, 213, 89)), (0.25, (247, 119, 55)), (0.5, (221, 42, 123)),
                                  (0.78, (129, 52, 175)), (1.0, (81, 91, 212))]).convert("RGBA")
    glyph = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    glyph.paste(grad, (gx0, gy0))
    mask = rounded_mask(n, (gx0, gy0, gx1, gy1), 165 * k)
    glyph.putalpha(mask)
    d = ImageDraw.Draw(glyph)
    cx, cy = (gx0 + gx1) // 2, (gy0 + gy1) // 2
    r_out, r_in = 150 * k, 108 * k
    d.ellipse((cx - r_out, cy - r_out, cx + r_out, cy + r_out), outline=(255, 255, 255, 255), width=r_out - r_in)
    dot_r = 24 * k
    dx, dy = gx1 - 118 * k, gy0 + 118 * k
    d.ellipse((dx - dot_r, dy - dot_r, dx + dot_r, dy + dot_r), fill=(255, 255, 255, 255))
    # outer square outline (the "frame" of the camera glyph) stays part of the gradient, so just keep it solid.

    # --- bite: Pacman's body removes a disc from the glyph (plus a small gap) --------------------
    pc_x, pc_y, pr = 300 * k, 512 * k, 292 * k
    bite = Image.new("L", (n, n), 255)
    ImageDraw.Draw(bite).ellipse((pc_x - pr - 26 * k, pc_y - pr - 26 * k, pc_x + pr + 26 * k, pc_y + pr + 26 * k), fill=0)
    glyph.putalpha(ImageChops.multiply(glyph.getchannel("A"), bite))
    canvas.alpha_composite(glyph)

    # --- Pacman ------------------------------------------------------------------------------
    pac = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    pd = ImageDraw.Draw(pac)
    yellow = (255, 204, 0, 255)
    pd.ellipse((pc_x - pr, pc_y - pr, pc_x + pr, pc_y + pr), fill=yellow)
    # mouth wedge opening to the right (chomping the glyph)
    half = math.radians(36)
    far = pr * 2
    pts = [(pc_x, pc_y),
           (pc_x + far * math.cos(-half), pc_y + far * math.sin(-half)),
           (pc_x + far * math.cos(half), pc_y + far * math.sin(half))]
    wedge = Image.new("L", (n, n), 255)
    ImageDraw.Draw(wedge).polygon(pts, fill=0)
    pac.putalpha(ImageChops.multiply(pac.getchannel("A"), wedge))
    ed = ImageDraw.Draw(pac)
    ex, ey, er = pc_x + 20 * k, pc_y - 160 * k, 34 * k
    ed.ellipse((ex - er, ey - er, ex + er, ey + er), fill=(30, 30, 40, 255))
    ed.ellipse((ex - er // 3 + 6 * k, ey - er // 2, ex + er // 3 + 6 * k, ey - er // 6), fill=(255, 255, 255, 230))
    canvas.alpha_composite(pac)

    # --- pellets on the way (little dots between Pacman's mouth and the glyph) ------------------
    dd = ImageDraw.Draw(canvas)
    for i, px in enumerate((650, 730)):
        pass  # (kept minimal: the glyph is already right next to the mouth)

    # breathing room: shrink to 88% and centre (bounding box of the artwork, not the canvas)
    art = canvas.resize((S, S), Image.LANCZOS)
    box = art.getbbox()
    art = art.crop(box)
    scale = (S * 0.86) / max(art.size)
    art = art.resize((int(art.width * scale), int(art.height * scale)), Image.LANCZOS)
    out = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    out.alpha_composite(art, ((S - art.width) // 2, (S - art.height) // 2))
    return out


def main():
    master = draw_master()
    assets = os.path.join(ROOT, "assets")
    os.makedirs(assets, exist_ok=True)
    master.save(os.path.join(assets, "app_preview.png"))
    sizes = [16, 24, 32, 48, 64, 128, 256]
    master.save(os.path.join(assets, "app.ico"), format="ICO", sizes=[(s, s) for s in sizes])

    small = master.resize((44, 44), Image.LANCZOS)   # sidebar logo
    buf = io.BytesIO()
    small.save(buf, format="PNG", optimize=True)
    png_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    big = master.resize((150, 150), Image.LANCZOS)      # intro screen logo
    buf2 = io.BytesIO()
    big.save(buf2, format="PNG", optimize=True)
    png_large_b64 = base64.b64encode(buf2.getvalue()).decode("ascii")
    with open(os.path.join(assets, "app.ico"), "rb") as fp:
        ico_b64 = base64.b64encode(fp.read()).decode("ascii")

    def wrap(s, w=100):
        return "\n".join(f'    "{s[i:i + w]}"' for i in range(0, len(s), w))

    with open(os.path.join(ROOT, "src", "igdm_assets.py"), "w", encoding="utf-8") as fp:
        fp.write('"""Generated by tools/make_icon.py - the app icon embedded as base64."""\n\n')
        fp.write(f"ICON_PNG_B64 = (\n{wrap(png_b64)}\n)\n\n")
        fp.write(f"ICON_PNG_LARGE_B64 = (\n{wrap(png_large_b64)}\n)\n\n")
        fp.write(f"ICON_ICO_B64 = (\n{wrap(ico_b64)}\n)\n")
    print("icon written:", os.path.join(assets, "app.ico"))


if __name__ == "__main__":
    main()
