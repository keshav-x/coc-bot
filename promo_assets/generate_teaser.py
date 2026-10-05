import os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

def create_teaser_video(output_path, bg_image_path):
    print(f"Loading background image from {bg_image_path}...")
    bg_raw = Image.open(bg_image_path).convert("RGBA")
    
    width, height = 1920, 1080
    fps = 30
    duration_sec = 12
    total_frames = fps * duration_sec
    
    fonts_dir = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts')
    title_font = ImageFont.truetype(os.path.join(fonts_dir, 'impact.ttf'), 76)
    badge_font = ImageFont.truetype(os.path.join(fonts_dir, 'arialbd.ttf'), 32)
    body_font = ImageFont.truetype(os.path.join(fonts_dir, 'segoeuib.ttf'), 38)
    sub_font = ImageFont.truetype(os.path.join(fonts_dir, 'consola.ttf'), 30)
    cta_font = ImageFont.truetype(os.path.join(fonts_dir, 'impact.ttf'), 60)
    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    
    print(f"Rendering {total_frames} frames to {output_path}...")
    
    for f in range(total_frames):
        t = f / fps # time in seconds
        
        # Ken Burns zoom (1.00 to 1.12 scale)
        zoom = 1.0 + (f / total_frames) * 0.12
        crop_w = int(bg_raw.width / zoom)
        crop_h = int(bg_raw.height / zoom)
        crop_x = int((bg_raw.width - crop_w) * 0.5)
        crop_y = int((bg_raw.height - crop_h) * (0.3 + 0.2 * (f / total_frames)))
        
        cropped = bg_raw.crop((crop_x, crop_y, crop_x + crop_w, crop_y + crop_h))
        frame_img = cropped.resize((width, height), Image.Resampling.LANCZOS)
        
        # Overlay for readable text and cyber effects
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        # Top banner glassmorphic bar
        draw.rectangle([0, 0, width, 90], fill=(10, 15, 25, 210))
        draw.line([0, 90, width, 90], fill=(0, 240, 255, 180), width=3)
        
        # Top Header Tag
        draw.text((60, 25), "» APEXCLASH PRO v1.3.2 • NEXT-GEN COC AUTOMATION «", fill=(0, 240, 255, 255), font=badge_font)
        draw.text((width - 430, 25), "2-HOUR FREE TRIAL ACTIVE", fill=(255, 215, 0, 255), font=badge_font)
        
        # Bottom HUD Panel
        draw.rectangle([0, height - 240, width, height], fill=(7, 10, 20, 225))
        draw.line([0, height - 240, width, height - 240], fill=(255, 170, 0, 200), width=3)
        
        # Dynamic phase transitions
        if f < 90: # Phase 1: Intro (0-3s)
            alpha_fade = min(1.0, f / 20.0)
            c_val = int(255 * alpha_fade)
            
            # Title
            draw.text((70, height - 210), "AUTOMATE YOUR CLASH OF CLANS", fill=(255, 255, 255, c_val), font=title_font)
            draw.text((70, height - 120), "Sneaky Goblin Smart Raids • Auto Wall Upgrader • 100% External Vision", fill=(0, 230, 255, c_val), font=body_font)
            draw.text((70, height - 65), "Runs locally on Google Play Games PC / BlueStacks • Zero memory hooks", fill=(180, 200, 220, c_val), font=sub_font)
            
        elif f < 180: # Phase 2: Live Stats & Loot (3-6s)
            p = (f - 90) / 90.0
            cur_gold = int(1850000 * min(1.0, p * 1.2))
            cur_elixir = int(1620000 * min(1.0, p * 1.2))
            
            draw.text((70, height - 215), "AUTONOMOUS TARGETING ENGINE", fill=(255, 215, 0, 255), font=title_font)
            draw.text((70, height - 125), f"LOOT LOCATED:  GOLD: {cur_gold:,}  |  ELIXIR: {cur_elixir:,}  |  DE: 14,200", fill=(50, 255, 150, 255), font=body_font)
            draw.text((70, height - 65), "Bézier Humanized Trajectory • Dynamic Deadzone Deployment • Safe Anti-Ban", fill=(200, 225, 255, 255), font=sub_font)
            
        elif f < 270: # Phase 3: Anti-Ban & Features (6-9s)
            draw.text((70, height - 215), "100% EXTERNAL COMPUTER VISION", fill=(0, 240, 255, 255), font=title_font)
            draw.text((70, height - 125), "NO MODIFIED APK  •  NO ROOT  •  NO CLIENT INJECTION", fill=(255, 100, 100, 255), font=body_font)
            draw.text((70, height - 65), "Open-source Python inspection • Local Windows Execution • Direct Mouse Synthesis", fill=(220, 235, 255, 255), font=sub_font)
            
        else: # Phase 4: Call To Action (9-12s)
            pulse = int(128 + 127 * np.sin((f - 270) * 0.25))
            draw.text((70, height - 220), "GET 2 HOURS FREE TRIAL RIGHT NOW!", fill=(255, 215, 0, 255), font=cta_font)
            draw.text((70, height - 130), "DOWNLOAD: github.com/keshav-x/coc-bot", fill=(255, 255, 255, 255), font=body_font)
            draw.text((70, height - 65), "Fast Setup in 60 Seconds  •  Instant Key via Telegram @keshavchaudhary0025", fill=(0, 240, 255, 255), font=sub_font)
            
            # Pulsing Download Badge Box
            draw.rectangle([width - 450, height - 190, width - 70, height - 80], outline=(255, 215, 0, 255), width=4, fill=(30, 40, 60, 220))
            draw.text((width - 410, height - 160), "DOWNLOAD NOW", fill=(255, 220, pulse, 255), font=badge_font)
            
        # Compose overlay
        combined = Image.alpha_composite(frame_img, overlay).convert("RGB")
        frame_arr = cv2.cvtColor(np.array(combined), cv2.COLOR_RGB2BGR)
        writer.write(frame_arr)
        
    writer.release()
    print("Video rendered successfully!")

if __name__ == "__main__":
    out_video = r"a:\projects\ApexClashBot\promo_assets\apexclash_teaser_trailer.mp4"
    bg_img = r"a:\projects\ApexClashBot\promo_assets\apexclash_youtube_thumbnail_16x9.jpg"
    create_teaser_video(out_video, bg_img)
