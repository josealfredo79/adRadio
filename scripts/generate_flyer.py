#!/usr/bin/env python3
"""Generate promotional flyer for IaRadio (1080x1080px for social media)."""
from PIL import Image, ImageDraw, ImageFont
import os

W, H = 1080, 1080
BG = (6, 6, 15)  # #06060f
ACCENT = (103, 76, 196)  # #674CC4
WHITE = (255, 255, 255)
GRAY = (160, 160, 170)
GREEN = (34, 197, 94)

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
FONT_BOLD = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")
FONT_REG = os.path.join(FONT_DIR, "DejaVuSans.ttf")

img = Image.new("RGB", (W, H), BG)
draw = ImageDraw.Draw(img)

# Gradient accent bar top
draw.rectangle([0, 0, W, 8], fill=ACCENT)

# Accent circle decoration (top right)
for r in range(200, 0, -1):
    alpha = int(30 * (r / 200))
    draw.ellipse([W - 100 - r, -50 - r, W - 100 + r, -50 + r], fill=ACCENT)

# Radio icon
cx, cy = 180, 200
for r in [60, 45, 30]:
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=ACCENT, width=2)
for r in [75, 90]:
    draw.arc([cx - r, cy - r, cx + r, cy + r], -40, 40, fill=ACCENT, width=2)
draw.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=ACCENT)

# Load fonts
try:
    font_big = ImageFont.truetype(FONT_BOLD, 72)
    font_med = ImageFont.truetype(FONT_BOLD, 36)
    font_body = ImageFont.truetype(FONT_REG, 28)
    font_small = ImageFont.truetype(FONT_REG, 22)
    font_tag = ImageFont.truetype(FONT_BOLD, 24)
except OSError:
    font_big = font_med = font_body = font_small = font_tag = ImageFont.load_default()

# Title
draw.text((100, 300), "IaRadio", fill=WHITE, font=font_big)
draw.text((100, 390), "Tu negocio en WhatsApp", fill=ACCENT, font=font_med)
draw.text((100, 440), "con Inteligencia Artificial", fill=GRAY, font=font_med)

# Features
y = 530
features = [
    "Bot IA que responde 24/7",
    "Campanas masivas por WhatsApp",
    "Cunas de radio con IA",
    "Cupones automaticos con QR",
    "Panel de control en tiempo real",
]
for feat in features:
    draw.ellipse([100, y + 8, 112, y + 20], fill=GREEN)
    draw.text((130, y), feat, fill=WHITE, font=font_body)
    y += 45

# Price tag
draw.rounded_rectangle([80, 750, 500, 830], radius=12, fill=ACCENT)
draw.text((100, 765), "Desde $499/mes", fill=WHITE, font=font_med)

# CTA
draw.text((100, 870), "15 dias gratis sin tarjeta", fill=GREEN, font=font_tag)
draw.text((100, 920), "www.iaradio.online", fill=GRAY, font=font_small)

# Bottom bar
draw.rectangle([0, H - 8, W, H], fill=ACCENT)

out = os.path.join(os.path.dirname(__file__), "..", "flyer_iaradio.png")
img.save(out, "PNG")
print(f"Saved {out} ({W}x{H})")
