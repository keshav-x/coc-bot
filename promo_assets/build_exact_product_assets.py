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

def create_exact_product_banner(screenshot_path, out_path):
    w, h = 1920, 1080
    bg = Image.new("RGBA", (w, h), (8, 12, 21, 255))
    draw = ImageDraw.Draw(bg)

    # Ambient grid pattern
    for y in range(0, h, 40):
        draw.line([(0, y), (w, y)], fill=(20, 26, 42, 90), width=1)
    for x in range(0, w, 40):
        draw.line([(x, 0), (x, h)], fill=(20, 26, 42, 90), width=1)

    # Deep violet / purple ambient glow matching the app's purple buttons
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse([w//2 - 650, h//2 - 250, w//2 + 650, h//2 + 350], fill=(124, 58, 237, 75))
    glow_draw.ellipse([200, 100, 900, 700], fill=(56, 189, 248, 40))
    glow = glow.filter(ImageFilter.GaussianBlur(130))
    bg = Image.alpha_composite(bg, glow)
    draw = ImageDraw.Draw(bg)

    # Fonts
    f_badge = get_font("arialbd.ttf", 20)
    f_h1 = get_font("impact.ttf", 60)
    f_sub = get_font("segoeuib.ttf", 25)
    f_callout_title = get_font("arialbd.ttf", 22)
    f_callout_desc = get_font("segoeui.ttf", 17)
    f_cta_main = get_font("impact.ttf", 44)
    f_cta_sub = get_font("consola.ttf", 26)

    # Top Header Section
    draw.rounded_rectangle([70, 40, 520, 80], radius=8, fill=(15, 23, 42, 230), outline=(139, 92, 246, 220), width=2)
    draw.text((90, 48), "⚡ APEXCLASH PRO v1.3.2 • OFFICIAL UI DEMO", fill=(192, 132, 252), font=f_badge)

    draw.text((70, 95), "AUTONOMOUS CLASH OF CLANS PC FARMING BOT", fill=(255, 255, 255), font=f_h1)
    draw.text((70, 168), "100% External Vision • Safe Anti-Ban Architecture • Runs on Google Play Games PC & BlueStacks", fill=(148, 163, 184), font=f_sub)

    # Load and process user's exact app screenshot
    app_raw = Image.open(screenshot_path).convert("RGBA")
    
    # Scale screenshot to fit center-left
    target_app_w = 1200
    aspect = app_raw.height / app_raw.width
    target_app_h = int(target_app_w * aspect) # ~748
    
    app_scaled = app_raw.resize((target_app_w, target_app_h), Image.Resampling.LANCZOS)
    
    # Multi-layer drop shadow for realistic 3D elevation
    shadow = Image.new("RGBA", (target_app_w + 80, target_app_h + 80), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow)
    s_draw.rounded_rectangle([40, 40, target_app_w + 40, target_app_h + 40], radius=16, fill=(0, 0, 0, 200))
    shadow = shadow.filter(ImageFilter.GaussianBlur(28))
    
    app_x = 60
    app_y = 230
    bg.paste(shadow, (app_x - 40, app_y - 30), shadow)

    # Sleek border around screenshot
    border_box = Image.new("RGBA", (target_app_w + 6, target_app_h + 6), (124, 58, 237, 200))
    bg.paste(border_box, (app_x - 3, app_y - 3))
    bg.paste(app_scaled, (app_x, app_y))

    # Right side: Feature Callout Cards
    card_x = 1300
    card_w = 550
    card_y = 230

    cards = [
        ("🎯 Autonomous Sneaky Goblin Raids", "Deploys goblins along humanized Bézier paths outside red borders to drain collectors in 30s.", (192, 132, 252)),
        ("🧱 Automated Wall Upgrading", "Detects full gold/elixir storages and dumps overflow into walls automatically between attacks.", (245, 158, 11)),
        ("🛡️ 100% External Vision Anti-Ban", "Zero game client modification. Operates strictly via screen OCR and simulated Windows mouse input.", (56, 189, 248)),
        ("📊 Live Session Yield Telemetry", "Real-time tracking of Gold, Elixir, and Dark Elixir looted with hourly rate calculations.", (16, 185, 129))
    ]

    for title, desc, col in cards:
        draw.rounded_rectangle([card_x, card_y, card_x + card_w, card_y + 115], radius=12, fill=(15, 23, 42, 230), outline=col, width=2)
        draw.text((card_x + 20, card_y + 16), title, fill=col, font=f_callout_title)
        draw.text((card_x + 20, card_y + 54), desc[:54], fill=(226, 232, 240), font=f_callout_desc)
        if len(desc) > 54:
            draw.text((card_x + 20, card_y + 80), desc[54:], fill=(148, 163, 184), font=f_callout_desc)
        card_y += 132

    # Bottom Right: Free Trial CTA Banner
    draw.rounded_rectangle([card_x, card_y + 10, card_x + card_w, card_y + 160], radius=14, fill=(124, 58, 237, 240), outline=(255, 255, 255), width=3)
    draw.text((card_x + 30, card_y + 25), "🎁 2-HOUR FREE TRIAL INCLUDED", fill=(255, 255, 255), font=f_cta_main)
    draw.text((card_x + 30, card_y + 92), "Download: github.com/keshav-x/coc-bot", fill=(255, 235, 150), font=f_cta_sub)

    bg.convert("RGB").save(out_path, quality=95)
    print(f"Exact product banner saved to: {out_path}")

def create_exact_product_shorts(screenshot_path, out_path):
    w, h = 1080, 1920
    bg = Image.new("RGBA", (w, h), (8, 12, 21, 255))
    draw = ImageDraw.Draw(bg)

    # Ambient grid
    for y in range(0, h, 40):
        draw.line([(0, y), (w, y)], fill=(20, 26, 42, 85), width=1)
    for x in range(0, w, 40):
        draw.line([(x, 0), (x, h)], fill=(20, 26, 42, 85), width=1)

    # Violet ambient glow in center
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse([w//2 - 400, 300, w//2 + 400, 1100], fill=(124, 58, 237, 90))
    glow = glow.filter(ImageFilter.GaussianBlur(130))
    bg = Image.alpha_composite(bg, glow)
    draw = ImageDraw.Draw(bg)

    f_tag = get_font("arialbd.ttf", 22)
    f_h1 = get_font("impact.ttf", 62)
    f_sub = get_font("segoeuib.ttf", 27)
    f_card_t = get_font("segoeuib.ttf", 30)
    f_card_d = get_font("segoeui.ttf", 22)
    f_cta = get_font("impact.ttf", 46)

    # Top Header
    draw.rounded_rectangle([60, 60, w - 60, 125], radius=10, fill=(15, 23, 42, 235), outline=(139, 92, 246), width=2)
    draw.text((100, 78), "⚡ APEXCLASH PRO v1.3.2 • PRODUCT DEMO", fill=(192, 132, 252), font=f_tag)

    draw.text((60, 155), "THE ULTIMATE COC BOT FOR PC", fill=(255, 255, 255), font=f_h1)
    draw.text((60, 230), "Zero Modified APK • 100% External Computer Vision", fill=(148, 163, 184), font=f_sub)

    # Place user screenshot in central display frame
    app_raw = Image.open(screenshot_path).convert("RGBA")
    ui_w = 980
    aspect = app_raw.height / app_raw.width
    ui_h = int(ui_w * aspect) # ~611
    app_scaled = app_raw.resize((ui_w, ui_h), Image.Resampling.LANCZOS)

    ui_y = 295
    # Shadow & Frame
    draw.rounded_rectangle([46, ui_y - 4, 46 + ui_w + 8, ui_y + ui_h + 8], radius=14, fill=None, outline=(139, 92, 246), width=3)
    bg.paste(app_scaled, (50, ui_y))

    # Feature Highlight Cards
    card_y = ui_y + ui_h + 35
    features = [
        ("🟣 Autonomous Sneaky Goblin Farm", "Automatic base search, dead-base collector extraction & retreat.", (192, 132, 252)),
        ("🧱 Smart Auto-Wall Upgrader", "Never sit on capped resources; automatically upgrades walls.", (245, 158, 11)),
        ("🛡️ Safe External Anti-Ban Suite", "Runs locally on Windows with natural human mouse curves & pauses.", (56, 189, 248))
    ]

    for title, desc, col in features:
        draw.rounded_rectangle([50, card_y, w - 50, card_y + 130], radius=14, fill=(15, 23, 42, 235), outline=col, width=2)
        draw.text((75, card_y + 18), title, fill=col, font=f_card_t)
        draw.text((75, card_y + 65), desc, fill=(203, 213, 225), font=f_card_d)
        card_y += 155

    # Bottom CTA Box
    draw.rounded_rectangle([50, card_y + 15, w - 50, h - 70], radius=16, fill=(124, 58, 237), outline=(255, 255, 255), width=3)
    draw.text((90, card_y + 45), "🎁 2-HOUR FREE TRIAL INCLUDED!", fill=(255, 255, 255), font=f_cta)
    draw.text((90, card_y + 110), "Download: github.com/keshav-x/coc-bot", fill=(255, 235, 150), font=get_font("consola.ttf", 30))
    draw.text((90, card_y + 155), "Instant Support: Telegram @keshavchaudhary0025", fill=(230, 215, 255), font=get_font("segoeuib.ttf", 22))

    bg.convert("RGB").save(out_path, quality=95)
    print(f"Exact product shorts saved to: {out_path}")

def render_exact_product_video(screenshot_path, out_path):
    w, h = 1920, 1080
    fps = 30
    duration_sec = 16
    total_frames = fps * duration_sec

    app_raw = Image.open(screenshot_path).convert("RGBA")
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(out_path, fourcc, fps, (w, h))

    f_title = get_font("impact.ttf", 52)
    f_badge = get_font("arialbd.ttf", 26)
    f_desc = get_font("segoeuib.ttf", 30)
    f_sub = get_font("segoeui.ttf", 24)
    f_url = get_font("consola.ttf", 28)

    print(f"Rendering exact product video ({total_frames} frames) to {out_path}...")

    # Key timeline phases:
    # 0 - 120 (0-4s): Wide overview of Cockpit & Brand
    # 120 - 240 (4-8s): Zoom into Attack Strategy (Sneaky Goblins) & Modes (Upgrade walls)
    # 240 - 360 (8-12s): Zoom into Start Button & Live Analytics
    # 360 - 480 (12-16s): Pull back with Free Trial CTA Overlay

    for f in range(total_frames):
        canvas = Image.new("RGBA", (w, h), (8, 12, 21, 255))
        draw = ImageDraw.Draw(canvas)

        # Ambient grid
        for gy in range(0, h, 48):
            draw.line([(0, gy), (w, gy)], fill=(20, 26, 42, 90), width=1)
        for gx in range(0, w, 48):
            draw.line([(gx, 0), (gx, h)], fill=(20, 26, 42, 90), width=1)

        # Camera choreography based on frame
        if f < 120: # Phase 1: Wide reveal
            p = f / 120.0
            zoom = 1.0 + 0.05 * p
            center_x, center_y = app_raw.width * 0.5, app_raw.height * 0.5
            phase_tag = "» APEXCLASH PRO v1.3.2 • AUTONOMOUS COMBAT & FARMING SUITE «"
            phase_title = "THE NEXT-GEN CLASH OF CLANS BOT FOR PC"
            phase_desc = "Clean PyQt/PySide dark cockpit with 100% external computer vision"
            accent_col = (139, 92, 246)

        elif f < 240: # Phase 2: Focus on Sneaky Goblins & Wall Upgrade
            p = (f - 120) / 120.0
            zoom = 1.45 + 0.05 * p
            # Target Sneaky Goblins & Modes area
            center_x = app_raw.width * 0.38
            center_y = app_raw.height * 0.48
            phase_tag = "» SNEAKY GOBLIN RAID ENGINE & AUTO-WALL UPGRADE «"
            phase_title = "AUTOMATED RESOURCE EXTRACTION & STORAGE SINK"
            phase_desc = "Deploys along dead-base collectors & auto-dumps overflow into walls"
            accent_col = (245, 158, 11)

        elif f < 360: # Phase 3: Focus on Live Analytics & Start
            p = (f - 240) / 120.0
            zoom = 1.4 + 0.05 * p
            # Target Live Analytics & Start button
            center_x = app_raw.width * 0.55
            center_y = app_raw.height * 0.72
            phase_tag = "» LIVE SESSION TELEMETRY & SAFE EXECUTION «"
            phase_title = "REAL-TIME YIELD TRACKING & BEZIER HUMAN DELAYS"
            phase_desc = "Monitors hourly yield rates and protects accounts with anti-ban kinematics"
            accent_col = (56, 189, 248)

        else: # Phase 4: Pull back to Hero CTA
            p = (f - 360) / 120.0
            zoom = 1.1 - 0.05 * p
            center_x, center_y = app_raw.width * 0.5, app_raw.height * 0.5
            phase_tag = "» 2-HOUR UNRESTRICTED FREE TRIAL ACTIVE «"
            phase_title = "START FARMING TODAY — INSTANT DOWNLOAD"
            phase_desc = "Available now on GitHub for Google Play Games PC & BlueStacks"
            accent_col = (139, 92, 246)

        # Apply crop according to zoom and center
        crop_w = int(app_raw.width / zoom)
        crop_h = int(app_raw.height / zoom)
        crop_x0 = int(np.clip(center_x - crop_w // 2, 0, app_raw.width - crop_w))
        crop_y0 = int(np.clip(center_y - crop_h // 2, 0, app_raw.height - crop_h))

        cropped = app_raw.crop((crop_x0, crop_y0, crop_x0 + crop_w, crop_y0 + crop_h))
        scaled = cropped.resize((1500, 720), Image.Resampling.LANCZOS)

        # Paste window in canvas
        win_x, win_y = 210, 160
        draw.rounded_rectangle([win_x - 3, win_y - 3, win_x + 1503, win_y + 723], radius=12, fill=None, outline=accent_col, width=2)
        canvas.paste(scaled, (win_x, win_y))

        # Top Bar
        draw.rectangle([0, 0, w, 110], fill=(15, 23, 42, 235))
        draw.line([0, 110, w, 110], fill=accent_col, width=2)
        draw.text((60, 22), "APEXCLASH PRO", fill=(255, 255, 255), font=f_title)
        draw.text((450, 36), phase_tag, fill=accent_col, font=f_badge)
        
        # Free trial top pill
        draw.rounded_rectangle([w - 380, 24, w - 60, 86], radius=8, fill=(124, 58, 237), outline=(255, 255, 255), width=2)
        draw.text((w - 355, 38), "2-HOUR FREE TRIAL", fill=(255, 255, 255), font=f_badge)

        # Bottom Information Bar
        draw.rounded_rectangle([180, h - 160, w - 180, h - 30], radius=14, fill=(15, 23, 42, 240), outline=accent_col, width=2)
        draw.text((210, h - 145), phase_title, fill=(255, 255, 255), font=f_desc)
        draw.text((210, h - 90), f"— {phase_desc}", fill=(148, 163, 184), font=f_sub)

        # Pulsing CTA button in final phase
        if f >= 360:
            pulse = int(180 + 75 * np.sin((f - 360) * 0.25))
            draw.rectangle([w - 560, h - 145, w - 210, h - 45], fill=(124, 58, 237), outline=(255, 255, pulse), width=3)
            draw.text((w - 540, h - 130), "DOWNLOAD ON GITHUB", fill=(255, 255, 255), font=f_badge)
            draw.text((w - 540, h - 85), "github.com/keshav-x/coc-bot", fill=(255, 235, 150), font=get_font("consola.ttf", 20))

        frame_rgb = canvas.convert("RGB")
        frame_bgr = cv2.cvtColor(np.array(frame_rgb), cv2.COLOR_RGB2BGR)
        writer.write(frame_bgr)

    writer.release()
    print("Exact product video rendered successfully!")

if __name__ == "__main__":
    screenshot = r"a:\projects\ApexClashBot\promo_assets\user_actual_app_screenshot.png"
    banner_out = r"a:\projects\ApexClashBot\promo_assets\apexclash_exact_poster_16x9.jpg"
    shorts_out = r"a:\projects\ApexClashBot\promo_assets\apexclash_exact_shorts_9x16.jpg"
    video_out = r"a:\projects\ApexClashBot\promo_assets\apexclash_exact_demo_video.mp4"

    create_exact_product_banner(screenshot, banner_out)
    create_exact_product_shorts(screenshot, shorts_out)
    render_exact_product_video(screenshot, video_out)
