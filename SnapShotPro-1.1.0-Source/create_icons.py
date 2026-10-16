#!/usr/bin/env python3
"""
SnapShot Pro — Icon Generator Script
Generates high-resolution application icon assets:
- assets/icon.png (512x512 Master)
- assets/icon.ico (Windows multi-resolution: 256, 128, 64, 48, 32, 16)
- assets/icon.icns (macOS bundle icon)
"""

import os
import pathlib
from PIL import Image, ImageDraw


def generate_icons() -> None:
    base_dir = pathlib.Path(__file__).resolve().parent
    assets_dir = base_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    w, h = 512, 512
    # 1. Background Mask (Rounded Rectangle / Squircle)
    mask = Image.new("L", (w, h), 0)
    d_mask = ImageDraw.Draw(mask)
    d_mask.rounded_rectangle([24, 24, 488, 488], radius=115, fill=255)

    # 2. Rich Vibrant Gradient (Indigo -> Violet -> Cyan)
    grad = Image.new("RGBA", (w, h))
    for y in range(h):
        t = y / float(h)
        # Linear blend from #4F46E5 (79, 70, 229) to #0EA5E9 (14, 165, 233)
        r = int(79 * (1.0 - t) + 14 * t)
        g = int(70 * (1.0 - t) + 165 * t)
        b = int(229 * (1.0 - t) + 233 * t)
        for x in range(w):
            grad.putpixel((x, y), (r, g, b, 255))

    icon_img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    icon_img.paste(grad, (0, 0), mask)

    draw = ImageDraw.Draw(icon_img)

    # 3. Viewfinder / Screenshot crop frame
    # Outer white viewfinder boundary
    draw.rounded_rectangle([126, 126, 386, 386], radius=44, outline=(255, 255, 255, 245), width=16)

    # Corner highlight brackets
    bracket_len = 36
    b_thick = 6
    # Top-Left bracket accent
    draw.line([(106, 150), (106, 106), (150, 106)], fill=(56, 189, 248, 255), width=b_thick)
    # Top-Right bracket accent
    draw.line([(406, 150), (406, 106), (362, 106)], fill=(56, 189, 248, 255), width=b_thick)
    # Bottom-Left bracket accent
    draw.line([(106, 362), (106, 406), (150, 406)], fill=(56, 189, 248, 255), width=b_thick)
    # Bottom-Right bracket accent
    draw.line([(406, 362), (406, 406), (362, 406)], fill=(56, 189, 248, 255), width=b_thick)

    # 4. Glowing Aperture / Camera Lens
    draw.ellipse([192, 192, 320, 320], fill=(56, 189, 248, 255), outline=(255, 255, 255, 230), width=8)
    draw.ellipse([228, 228, 284, 284], fill=(15, 23, 42, 255))
    draw.ellipse([216, 212, 244, 240], fill=(255, 255, 255, 225))

    # 5. Pro Feature Flash Indicator
    draw.ellipse([338, 158, 362, 182], fill=(245, 158, 11, 255), outline=(255, 255, 255, 200), width=3)

    # Save PNG Master
    png_path = assets_dir / "icon.png"
    icon_img.save(png_path, "PNG")
    print(f"✔ Generated: {png_path}")

    # Save Multi-Resolution Windows ICO
    ico_path = assets_dir / "icon.ico"
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    icon_img.save(ico_path, format="ICO", sizes=sizes)
    print(f"✔ Generated: {ico_path}")

    # Save macOS ICNS
    icns_path = assets_dir / "icon.icns"
    try:
        icon_img.save(icns_path, format="ICNS")
        print(f"✔ Generated: {icns_path}")
    except Exception as exc:
        print(f"Note: ICNS generation skipped: {exc}")


if __name__ == "__main__":
    generate_icons()
