import os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

def get_font(name, size):
    fonts_dir = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts')
    path = os.path.join(fonts_dir, name)
    if os.path.exists(path):
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()

def render_product_demo_video(out_path):
    w, h = 1920, 1080
    fps = 30
    duration_sec = 20
    total_frames = fps * duration_sec

    # Load UI screenshots
    ui_cockpit = Image.open(r"promo_assets/ui_screens/cockpit_active_demo.png").convert("RGBA")
    ui_loot = Image.open(r"promo_assets/ui_screens/loot_filter_page.png").convert("RGBA")
    ui_antiban = Image.open(r"promo_assets/ui_screens/antiban_page.png").convert("RGBA")
    ui_license = Image.open(r"promo_assets/ui_screens/license_page.png").convert("RGBA")

    # Font instances
    f_header = get_font("impact.ttf", 46)
    f_step = get_font("arialbd.ttf", 26)
    f_title = get_font("segoeuib.ttf", 36)
    f_desc = get_font("segoeui.ttf", 24)
    f_badge = get_font("arialbd.ttf", 22)
    f_cta = get_font("impact.ttf", 52)
    f_url = get_font("consola.ttf", 28)

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(out_path, fourcc, fps, (w, h))

    print(f"Rendering product demo video ({total_frames} frames) to {out_path}...")

    # Scenes: (StartFrame, EndFrame, Image, StepName, Title, Desc, AccentColor)
    scenes = [
        (0, 120, ui_cockpit, "FEATURE 1: COCKPIT & STRATEGY", "One-Click Automated Raid Setup", "Choose Sneaky Goblins, set auto-wall dump, and hit Start.", (16, 185, 129)),
        (120, 240, ui_loot, "FEATURE 2: SMART OCR LOOT FILTER", "Computer Vision Target Detection", "Autonomous OCR inspects enemy collectors and skips poor bases.", (245, 158, 11)),
        (240, 360, ui_antiban, "FEATURE 3: INTELLIGENT ANTI-BAN", "Multi-Layered Behavioral Humanization", "Bézier curves, micro-jitter, and physiological fatigue breaks.", (56, 189, 248)),
        (360, 480, ui_cockpit, "FEATURE 4: LIVE RAID TELEMETRY", "Real-Time Yield Tracking & Wall Dump", "+42.2M Farmed at 12.6M/hr • Zero overflow waste.", (236, 72, 153)),
        (480, 600, ui_license, "GET STARTED: 2-HOUR FREE TRIAL", "Instant Download • Windows x64", "Fully automated companion for Google Play Games PC.", (245, 158, 11))
    ]

    for f in range(total_frames):
        # Determine active scene
        for start_f, end_f, ui_img, step_name, title, desc, accent_col in scenes:
            if start_f <= f < end_f:
                break

        scene_progress = (f - start_f) / float(end_f - start_f)

        # Base canvas
        canvas = Image.new("RGBA", (w, h), (11, 15, 25, 255))
        draw = ImageDraw.Draw(canvas)

        # Ambient background grid
        for gy in range(0, h, 48):
            draw.line([(0, gy), (w, gy)], fill=(22, 30, 48, 100), width=1)
        for gx in range(0, w, 48):
            draw.line([(gx, 0), (gx, h)], fill=(22, 30, 48, 100), width=1)

        # Slow smooth zoom on the UI screenshot
        zoom = 1.0 + 0.04 * scene_progress
        target_ui_w = int(1440 * zoom)
        target_ui_h = int(900 * zoom)
        
        ui_scaled = ui_img.resize((target_ui_w, target_ui_h), Image.Resampling.LANCZOS)
        
        # Center crop to 1440x800
        crop_x = (target_ui_w - 1440) // 2
        crop_y = (target_ui_h - 800) // 2
        ui_cropped = ui_scaled.crop((crop_x, crop_y, crop_x + 1440, crop_y + 800))

        # Paste UI window with border and shadow
        win_x, win_y = 240, 160
        draw.rounded_rectangle([win_x - 4, win_y - 4, win_x + 1444, win_y + 804], radius=14, fill=None, outline=accent_col, width=3)
        canvas.paste(ui_cropped, (win_x, win_y))

        # Top Bar: Product Branding
        draw.rectangle([0, 0, w, 110], fill=(15, 23, 42, 235))
        draw.line([0, 110, w, 110], fill=accent_col, width=2)
        draw.text((60, 25), "APEXCLASH PRO v1.3.2", fill=(255, 255, 255), font=f_header)
        draw.text((580, 38), "•  OFFICIAL PRODUCT DEMO & UI WALKTHROUGH", fill=(148, 163, 184), font=f_title)
        
        # Free trial top badge
        draw.rounded_rectangle([w - 410, 24, w - 60, 86], radius=8, fill=(245, 158, 11, 230), outline=(255, 255, 255), width=2)
        draw.text((w - 385, 38), "2-HOUR FREE TRIAL", fill=(15, 23, 42), font=f_step)

        # Bottom Feature Information Card
        draw.rounded_rectangle([200, h - 165, w - 200, h - 25], radius=16, fill=(15, 23, 42, 245), outline=accent_col, width=2)
        
        # Step Tag
        draw.rounded_rectangle([220, h - 150, 680, h - 112], radius=6, fill=accent_col)
        draw.text((235, h - 145), step_name, fill=(15, 23, 42) if accent_col == (245, 158, 11) else (255, 255, 255), font=f_step)

        # Title & Description
        draw.text((220, h - 98), title, fill=(255, 255, 255), font=f_title)
        draw.text((700, h - 94), f"— {desc}", fill=(203, 213, 225), font=f_desc)

        # Final Scene CTA Overlay
        if f >= 480:
            pulse = int(180 + 75 * np.sin((f - 480) * 0.2))
            draw.rectangle([w - 620, h - 150, w - 220, h - 45], fill=(30, 41, 59, 230), outline=(245, pulse, 11), width=3)
            draw.text((w - 595, h - 135), "DOWNLOAD ON GITHUB", fill=(245, pulse, 11), font=f_step)
            draw.text((w - 595, h - 85), "github.com/keshav-x/coc-bot", fill=(255, 255, 255), font=get_font("consola.ttf", 20))

        # Convert to BGR for OpenCV
        frame_rgb = canvas.convert("RGB")
        frame_bgr = cv2.cvtColor(np.array(frame_rgb), cv2.COLOR_RGB2BGR)
        writer.write(frame_bgr)

    writer.release()
    print("Product demo video rendered successfully!")

if __name__ == "__main__":
    out_demo = r"a:\projects\ApexClashBot\promo_assets\apexclash_product_demo.mp4"
    render_product_demo_video(out_demo)
