#!/usr/bin/env python3
"""Generate og-image.png for IaRadio (1200x630px)."""
from PIL import Image, ImageDraw, ImageFont
import os

W, H = 1200, 630
BG = (6, 6, 15)  # #06060f
ACCENT = (103, 76, 196)  # #674CC4
WHITE = (255, 255, 255)
GRAY = (160, 160, 170)

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
FONT_BOLD = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")
FONT_REG = os.path.join(FONT_DIR, "DejaVuSans.ttf")

img = Image.new("RGB", (W, H), BG)
draw = ImageDraw.Draw(img)

# Decorative gradient circle (top-right)
for r in range(300, 0, -1):
    alpha = int(40 * (r / 300))
    color = (103, 76, 196, alpha)
    draw.ellipse([W - 200 - r, -100 - r, W - 200 + r, -100 + r], fill=ACCENT)

# Left accent bar
draw.rectangle([0, 0, 8, H], fill=ACCENT)

# Radio icon (simple circle + lines)
cx, cy = 160, 280
for r in [80, 60, 40]:
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=ACCENT, width=2)
# Signal waves
for r in [100, 120]:
    draw.arc([cx - r, cy - r, cx + r, cy + r], -40, 40, fill=ACCENT, width=2)
# Dot
draw.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=ACCENT)

# Title
try:
    font_title = ImageFont.truetype(FONT_BOLD, 64)
    font_sub = ImageFont.truetype(FONT_BOLD, 28)
    font_tag = ImageFont.truetype(FONT_REG, 20)
except OSError:
    font_title = ImageFont.load_default()
    font_sub = font_title
    font_tag = font_title

draw.text((280, 200), "IaRadio", fill=WHITE, font=font_title)
draw.text((280, 290), "Spots de radio con IA", fill=GRAY, font=font_sub)
draw.text((280, 335), "para tu negocio en WhatsApp", fill=ACCENT, font=font_sub)

# Tagline
draw.text((280, 410), "Campanas masivas · Bot IA · Cuñas de radio · Cupones", fill=GRAY, font=font_tag)

# Bottom bar
draw.rectangle([0, H - 6, W, H], fill=ACCENT)

# URL
draw.text((280, 480), "www.iaradio.online", fill=(100, 100, 120), font=font_tag)

out = os.path.join(os.path.dirname(__file__), "..", "frontend", "public", "og-image.png")
img.save(out, "PNG")
print(f"Saved {out} ({W}x{H})")
