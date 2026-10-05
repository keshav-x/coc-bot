import os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

def get_font(name, size):
    fonts_dir = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts')
    path = os.path.join(fonts_dir, name)
    if os.path.exists(path):
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()

def render_vertical_short(screenshot_path, out_path):
    w, h = 1080, 1920
    fps = 30
    duration_sec = 18
    total_frames = fps * duration_sec

    app_raw = Image.open(screenshot_path).convert("RGBA")
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(out_path, fourcc, fps, (w, h))

    f_top_tag = get_font("arialbd.ttf", 24)
    f_hook = get_font("impact.ttf", 58)
    f_sub = get_font("segoeuib.ttf", 30)
    f_card_t = get_font("arialbd.ttf", 32)
    f_card_d = get_font("segoeui.ttf", 26)
    f_cta_big = get_font("impact.ttf", 52)
    f_url = get_font("consola.ttf", 32)

    print(f"Rendering 9:16 Vertical Short Video ({total_frames} frames) to {out_path}...")

    # Timeline Phases (18 seconds total):
    # 0 - 135 (0-4.5s): Hook - Overview & Problem "Tired of Grinding Walls?"
    # 135 - 270 (4.5-9s): Feature 1 - Sneaky Goblins & Auto-Wall Dump
    # 270 - 405 (9-13.5s): Feature 2 - Live Telemetry & Safe Anti-Ban Vision
    # 405 - 540 (13.5-18s): Call To Action - 2-Hour Free Trial

    for f in range(total_frames):
        canvas = Image.new("RGBA", (w, h), (8, 12, 21, 255))
        draw = ImageDraw.Draw(canvas)

        # Ambient tech grid background
        for gy in range(0, h, 48):
            draw.line([(0, gy), (w, gy)], fill=(18, 24, 38, 90), width=1)
        for gx in range(0, w, 48):
            draw.line([(gx, 0), (gx, h)], fill=(18, 24, 38, 90), width=1)

        # Violet ambient glow in center
        glow_alpha = int(75 + 20 * np.sin(f * 0.1))
        glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        glow_draw.ellipse([w//2 - 450, 400, w//2 + 450, 1200], fill=(124, 58, 237, glow_alpha))
        glow = glow.filter(ImageFilter.GaussianBlur(140))
        canvas = Image.alpha_composite(canvas, glow)
        draw = ImageDraw.Draw(canvas)

        # Dynamic Top Story Progress Bar (Instagram / Shorts style)
        progress_w = int((f / float(total_frames)) * (w - 80))
        draw.rounded_rectangle([40, 25, w - 40, 31], radius=3, fill=(35, 45, 65, 180))
        draw.rounded_rectangle([40, 25, 40 + progress_w, 31], radius=3, fill=(139, 92, 246, 255))

        # Top Product Pill
        draw.rounded_rectangle([50, 50, w - 50, 115], radius=10, fill=(15, 23, 42, 235), outline=(139, 92, 246), width=2)
        draw.text((80, 68), "⚡ APEXCLASH PRO v1.3.2 • NEXT-GEN COC BOT", fill=(192, 132, 252), font=f_top_tag)
        draw.text((w - 290, 68), "2-HR FREE TRIAL", fill=(245, 158, 11), font=f_top_tag)

        # Phase logic & camera coordinates
        if f < 135: # Phase 1: Hook & Wide View
            p = f / 135.0
            zoom = 1.05 + 0.04 * p
            center_x = app_raw.width * 0.5
            center_y = app_raw.height * 0.5
            accent_col = (139, 92, 246)
            
            hero_title = "TIRED OF GRINDING WALLS?"
            hero_sub = "Automate Clash of Clans on PC with 100% External Vision"
            card_title = "⚡ Autonomous PC Companion"
            card_desc = "Runs locally on Google Play Games PC & BlueStacks.\nZero root • Zero modified APK • Zero ban risk."

        elif f < 270: # Phase 2: Zoom on Sneaky Goblins & Wall Dump
            p = (f - 135) / 135.0
            zoom = 1.6 + 0.05 * p
            center_x = app_raw.width * 0.38
            center_y = app_raw.height * 0.44
            accent_col = (245, 158, 11)

            hero_title = "AUTONOMOUS SNEAKY GOBLINS"
            hero_sub = "Dead-Base Raids + Auto-Wall Overflow Dump"
            card_title = "🧱 Smart Wall Upgrades"
            card_desc = "Bot loots 1M+ per raid and sinks excess Gold into walls,\nso your storages are never full and zero loot is lost!"

        elif f < 405: # Phase 3: Zoom on Live Telemetry & Anti-Ban
            p = (f - 270) / 135.0
            zoom = 1.55 + 0.04 * p
            center_x = app_raw.width * 0.55
            center_y = app_raw.height * 0.73
            accent_col = (56, 189, 248)

            hero_title = "REAL-TIME TELEMETRY & ANTI-BAN"
            hero_sub = "Track Looted Gold/Elixir with Human Bézier Kinematics"
            card_title = "🛡️ 100% External Vision"
            card_desc = "Analyzes your screen with OCR & simulates human clicks\nwith natural pauses, micro-jitter, and fatigue breaks."

        else: # Phase 4: Big CTA & Free Trial
            p = (f - 405) / 135.0
            zoom = 1.12 - 0.04 * p
            center_x = app_raw.width * 0.5
            center_y = app_raw.height * 0.5
            accent_col = (139, 92, 246)

            hero_title = "START FARMING TODAY!"
            hero_sub = "2 Hours Free Trial Included With Every Download"
            card_title = "🎁 Instant Setup in 60 Seconds"
            card_desc = "Download release from GitHub & start botting right away.\nAffordable full licenses from $1.99 on our store."

        # Header titles
        draw.text((50, 140), hero_title, fill=(255, 255, 255), font=f_hook)
        draw.text((50, 215), hero_sub, fill=(148, 163, 184), font=f_sub)

        # Crop and display app window
        crop_w = int(app_raw.width / zoom)
        crop_h = int(app_raw.height / zoom)
        crop_x0 = int(np.clip(center_x - crop_w // 2, 0, app_raw.width - crop_w))
        crop_y0 = int(np.clip(center_y - crop_h // 2, 0, app_raw.height - crop_h))

        cropped = app_raw.crop((crop_x0, crop_y0, crop_x0 + crop_w, crop_y0 + crop_h))
        display_w, display_h = 980, 720
        scaled = cropped.resize((display_w, display_h), Image.Resampling.LANCZOS)

        ui_x, ui_y = 50, 280
        # Multi-layer border
        draw.rounded_rectangle([ui_x - 3, ui_y - 3, ui_x + display_w + 3, ui_y + display_h + 3], radius=14, fill=None, outline=accent_col, width=3)
        canvas.paste(scaled, (ui_x, ui_y))

        # Bottom Feature Information Card
        card_box_y = 1040
        draw.rounded_rectangle([50, card_box_y, w - 50, card_box_y + 280], radius=16, fill=(15, 23, 42, 240), outline=accent_col, width=2)
        
        # Tag pill
        draw.rounded_rectangle([75, card_box_y + 20, 520, card_box_y + 65], radius=8, fill=accent_col)
        tag_text_color = (15, 23, 42) if accent_col == (245, 158, 11) else (255, 255, 255)
        draw.text((95, card_box_y + 25), card_title, fill=tag_text_color, font=f_card_t)

        # Body desc lines
        lines = card_desc.split('\n')
        line_y = card_box_y + 85
        for l in lines:
            draw.text((75, line_y), l, fill=(226, 232, 240), font=f_card_d)
            line_y += 42

        # Bottom Big Call To Action Banner
        cta_y = 1360
        pulse = int(180 + 75 * np.sin(f * 0.2))
        draw.rounded_rectangle([50, cta_y, w - 50, h - 80], radius=18, fill=(124, 58, 237), outline=(255, 255, pulse), width=3)
        
        draw.text((85, cta_y + 40), "🎁 GET 2 HOURS FREE TRIAL NOW!", fill=(255, 255, 255), font=f_cta_big)
        draw.text((85, cta_y + 115), "DOWNLOAD: github.com/keshav-x/coc-bot", fill=(255, 235, 150), font=f_url)
        draw.text((85, cta_y + 175), "Telegram: @keshavchaudhary0025", fill=(220, 210, 255), font=f_sub)
        draw.text((85, cta_y + 225), "👉 Check the description & pinned comment!", fill=(255, 255, 255), font=f_sub)

        # Convert to BGR for OpenCV
        frame_rgb = canvas.convert("RGB")
        frame_bgr = cv2.cvtColor(np.array(frame_rgb), cv2.COLOR_RGB2BGR)
        writer.write(frame_bgr)

    writer.release()
    print("Vertical Short Video rendered successfully!")

if __name__ == "__main__":
    screenshot = r"a:\projects\ApexClashBot\promo_assets\user_actual_app_screenshot.png"
    out_video = r"a:\projects\ApexClashBot\promo_assets\apexclash_vertical_short.mp4"
    render_vertical_short(screenshot, out_video)
