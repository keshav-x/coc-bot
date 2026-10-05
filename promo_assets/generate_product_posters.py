import os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

def get_font(name, size):
    fonts_dir = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts')
    path = os.path.join(fonts_dir, name)
    if os.path.exists(path):
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()

def draw_rounded_rect(draw, bbox, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(bbox, radius=radius, fill=fill, outline=outline, width=width)

def create_product_banner_16x9(out_path):
    w, h = 1920, 1080
    img = Image.new("RGBA", (w, h), (10, 14, 23, 255))
    draw = ImageDraw.Draw(img)

    # Subtle background radial gradient & grid lines
    for y in range(0, h, 40):
        draw.line([(0, y), (w, y)], fill=(20, 28, 45, 120), width=1)
    for x in range(0, w, 40):
        draw.line([(x, 0), (x, h)], fill=(20, 28, 45, 120), width=1)

    # Radial ambient glow in center
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse([w//2 - 600, h//2 - 350, w//2 + 600, h//2 + 350], fill=(20, 75, 140, 80))
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    img = Image.alpha_composite(img, glow)
    draw = ImageDraw.Draw(img)

    # Top Navigation / Product Badge Header
    f_title = get_font("impact.ttf", 64)
    f_h2 = get_font("segoeuib.ttf", 26)
    f_badge = get_font("arialbd.ttf", 20)
    f_feature = get_font("segoeuib.ttf", 22)
    f_cta = get_font("impact.ttf", 42)
    f_url = get_font("consola.ttf", 26)

    # Header bar
    draw.rounded_rectangle([70, 45, 520, 85], radius=8, fill=(15, 23, 42, 230), outline=(56, 189, 248, 200), width=2)
    draw.text((85, 52), "⚡ APEXCLASH PRO v1.3.2 • PRODUCT SHOWCASE", fill=(56, 189, 248), font=f_badge)

    draw.text((70, 105), "THE NEXT-GEN AUTONOMOUS COC BOT", fill=(255, 255, 255), font=f_title)
    draw.text((70, 180), "100% External Vision Architecture • Runs locally on Google Play Games PC & BlueStacks", fill=(148, 163, 184), font=f_h2)

    # Load UI captures
    cockpit_path = r"promo_assets/ui_screens/cockpit_active_demo.png"
    antiban_path = r"promo_assets/ui_screens/antiban_page.png"
    loot_path = r"promo_assets/ui_screens/loot_filter_page.png"

    if os.path.exists(cockpit_path):
        cockpit_img = Image.open(cockpit_path).convert("RGBA")
        
        # Resize to fit main showcase area
        target_w, target_h = 1140, 720
        cockpit_resized = cockpit_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        
        # Drop shadow for main window
        shadow = Image.new("RGBA", (target_w + 60, target_h + 60), (0, 0, 0, 0))
        s_draw = ImageDraw.Draw(shadow)
        s_draw.rounded_rectangle([30, 30, target_w + 30, target_h + 30], radius=16, fill=(0, 0, 0, 180))
        shadow = shadow.filter(ImageFilter.GaussianBlur(25))
        img.paste(shadow, (50, 240), shadow)

        # Border frame for realistic app window
        frame = Image.new("RGBA", (target_w + 8, target_h + 8), (30, 41, 59, 255))
        img.paste(frame, (76, 266))
        img.paste(cockpit_resized, (80, 270))

    # Right side: Feature Cards & Secondary Window
    right_x = 1270
    card_w = 580

    features = [
        ("🎯 Autonomous Smart Raids", "Computer vision scans dead bases & deploys Sneaky Goblins with randomized human taps.", (16, 185, 129)),
        ("🧱 Auto-Wall Upgrade Dump", "Instantly sinks overflowing Gold/Elixir into walls between raids. Zero loot wasted.", (245, 158, 11)),
        ("🛡️ Intelligent Anti-Ban Suite", "Bézier mouse trajectories, micro-jitter, and physiological fatigue breaks.", (56, 189, 248)),
        ("💻 Zero Memory Hooks", "Zero modified APK, zero root. Operates entirely as an external Windows companion.", (236, 72, 153))
    ]

    card_y = 265
    for title, desc, col in features:
        # Card background
        draw.rounded_rectangle([right_x, card_y, right_x + card_w, card_y + 115], radius=12, fill=(15, 23, 42, 220), outline=col, width=2)
        draw.text((right_x + 20, card_y + 16), title, fill=col, font=f_feature)
        
        # Word wrap desc
        draw.text((right_x + 20, card_y + 54), desc[:58], fill=(226, 232, 240), font=get_font("segoeui.ttf", 18))
        if len(desc) > 58:
            draw.text((right_x + 20, card_y + 80), desc[58:], fill=(148, 163, 184), font=get_font("segoeui.ttf", 17))
        card_y += 135

    # Bottom Right: 2-Hour Free Trial CTA Badge
    draw.rounded_rectangle([right_x, card_y + 5, right_x + card_w, card_y + 145], radius=14, fill=(245, 158, 11, 240), outline=(255, 255, 255), width=3)
    draw.text((right_x + 35, card_y + 20), "🎁 2-HOUR FREE TRIAL INCLUDED", fill=(15, 23, 42), font=f_cta)
    draw.text((right_x + 35, card_y + 85), "Instant Download: github.com/keshav-x/coc-bot", fill=(15, 23, 42), font=f_url)

    # Save
    img.convert("RGB").save(out_path, quality=95)
    print(f"Product banner saved to {out_path}")

def create_product_shorts_9x16(out_path):
    w, h = 1080, 1920
    img = Image.new("RGBA", (w, h), (10, 14, 23, 255))
    draw = ImageDraw.Draw(img)

    # Background grid
    for y in range(0, h, 40):
        draw.line([(0, y), (w, y)], fill=(22, 30, 48, 110), width=1)
    for x in range(0, w, 40):
        draw.line([(x, 0), (x, h)], fill=(22, 30, 48, 110), width=1)

    f_hero = get_font("impact.ttf", 60)
    f_sub = get_font("segoeuib.ttf", 26)
    f_tag = get_font("arialbd.ttf", 22)
    f_card_title = get_font("segoeuib.ttf", 30)
    f_cta = get_font("impact.ttf", 46)

    # Header
    draw.rounded_rectangle([60, 60, w - 60, 130], radius=10, fill=(15, 23, 42, 230), outline=(56, 189, 248), width=2)
    draw.text((100, 78), "⚡ APEXCLASH PRO • PRODUCT DEMO", fill=(56, 189, 248), font=f_tag)

    draw.text((60, 160), "REAL PRODUCT. REAL RESULTS.", fill=(255, 255, 255), font=f_hero)
    draw.text((60, 235), "100% External Vision Farming Engine for PC", fill=(148, 163, 184), font=f_sub)

    # Load UI screenshots
    screens = [
        (r"promo_assets/ui_screens/cockpit_active_demo.png", "1. LIVE COCKPIT & RAID TELEMETRY", "+42.2M Farmed • Auto Wall Upgrader Active", (16, 185, 129)),
        (r"promo_assets/ui_screens/loot_filter_page.png", "2. SMART OCR LOOT FILTER", "Filter bases by Gold, Elixir & Dead-Base status", (245, 158, 11)),
        (r"promo_assets/ui_screens/antiban_page.png", "3. INTELLIGENT ANTI-BAN SUITE", "Bézier kinematic curves & physiological jitter", (56, 189, 248))
    ]

    curr_y = 295
    for path, title, desc, col in screens:
        if os.path.exists(path):
            ui = Image.open(path).convert("RGBA")
            ui_scaled = ui.resize((960, 360), Image.Resampling.LANCZOS)
            
            # Card frame
            draw.rounded_rectangle([56, curr_y, w - 56, curr_y + 440], radius=14, fill=(15, 23, 42, 230), outline=col, width=2)
            draw.text((75, curr_y + 16), title, fill=col, font=f_card_title)
            draw.text((75, curr_y + 54), desc, fill=(148, 163, 184), font=f_sub)
            
            img.paste(ui_scaled, (60, curr_y + 90))
            curr_y += 465

    # Bottom CTA Box
    draw.rounded_rectangle([60, curr_y + 20, w - 60, h - 80], radius=16, fill=(245, 158, 11), outline=(255, 255, 255), width=3)
    draw.text((100, curr_y + 45), "🎁 GET 2 HOURS FREE TRIAL RIGHT NOW!", fill=(15, 23, 42), font=f_cta)
    draw.text((100, curr_y + 105), "Download: github.com/keshav-x/coc-bot", fill=(15, 23, 42), font=get_font("consola.ttf", 30))
    draw.text((100, curr_y + 145), "Instant Support: Telegram @keshavchaudhary0025", fill=(30, 41, 59), font=get_font("segoeuib.ttf", 22))

    img.convert("RGB").save(out_path, quality=95)
    print(f"Product shorts saved to {out_path}")

if __name__ == "__main__":
    banner_out = r"a:\projects\ApexClashBot\promo_assets\apexclash_product_banner_16x9.jpg"
    shorts_out = r"a:\projects\ApexClashBot\promo_assets\apexclash_product_shorts_9x16.jpg"
    create_product_banner_16x9(banner_out)
    create_product_shorts_9x16(shorts_out)
