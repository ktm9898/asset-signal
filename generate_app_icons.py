import os
import math
from PIL import Image, ImageDraw, ImageFilter

asset_dir = r"c:\Users\김태명\.gemini\antigravity\scratch\asset-signal"

def create_asset_signal_icon(size=1024):
    canvas_size = size * 2
    img = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Background Rounded Rect with Gradient
    r = canvas_size * 0.22
    bg = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(bg)
    
    margin = canvas_size * 0.04
    rect_box = [margin, margin, canvas_size - margin, canvas_size - margin]
    
    for y in range(int(margin), int(canvas_size - margin)):
        prog = (y - margin) / (canvas_size - 2 * margin)
        r_col = int(11 * (1 - prog) + 26 * prog)
        g_col = int(18 * (1 - prog) + 46 * prog)
        b_col = int(32 * (1 - prog) + 95 * prog)
        bg_draw.line([(margin, y), (canvas_size - margin, y)], fill=(r_col, g_col, b_col, 255))
    
    mask = Image.new("L", (canvas_size, canvas_size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle(rect_box, radius=r, fill=255)
    
    border_mask = Image.new("L", (canvas_size, canvas_size), 0)
    b_draw = ImageDraw.Draw(border_mask)
    b_draw.rounded_rectangle(rect_box, radius=r, outline=255, width=int(canvas_size * 0.012))
    
    glow = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    center_x, center_y = canvas_size // 2, canvas_size // 2
    
    for rad in range(int(canvas_size * 0.42), 0, -8):
        alpha = int(45 * (1 - rad / (canvas_size * 0.42)))
        glow_draw.ellipse(
            [center_x - rad, center_y - rad, center_x + rad, center_y + rad],
            fill=(37, 99, 235, alpha)
        )
    
    final_bg = Image.composite(bg, Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0)), mask)
    final_bg = Image.alpha_composite(final_bg, glow)
    
    border_layer = Image.new("RGBA", (canvas_size, canvas_size), (255, 255, 255, 30))
    final_bg = Image.composite(border_layer, final_bg, border_mask)

    # 2. Draw Donut Segments
    outer_r = canvas_size * 0.33
    inner_r = canvas_size * 0.20
    cx, cy = center_x, center_y
    
    arcs = [
        (-40, 95, (56, 189, 248), (37, 99, 235)),    # Sky to Royal Blue
        (108, 215, (52, 211, 153), (5, 150, 105)),   # Emerald Green
        (228, 305, (167, 139, 250), (99, 102, 241))  # Purple to Indigo
    ]
    
    donut_layer = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    d_draw = ImageDraw.Draw(donut_layer)
    
    for start_a, end_a, col1, col2 in arcs:
        pts_outer = []
        pts_inner = []
        steps = 40
        for i in range(steps + 1):
            ang = math.radians(start_a + (end_a - start_a) * (i / steps))
            x_out = cx + outer_r * math.cos(ang)
            y_out = cy + outer_r * math.sin(ang)
            x_in = cx + inner_r * math.cos(ang)
            y_in = cy + inner_r * math.sin(ang)
            pts_outer.append((x_out, y_out))
            pts_inner.append((x_in, y_in))
            
        poly_pts = pts_outer + list(reversed(pts_inner))
        mid_col = (
            (col1[0] + col2[0]) // 2,
            (col1[1] + col2[1]) // 2,
            (col1[2] + col2[2]) // 2,
            255
        )
        d_draw.polygon(poly_pts, fill=mid_col)

    # 3. Dynamic Center Icon: Surging Signal Pulse Bars (No Arrow)
    center_icon = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    c_draw = ImageDraw.Draw(center_icon)
    
    bar_width = int(canvas_size * 0.046)
    bar_gap = int(canvas_size * 0.024)
    total_w = 3 * bar_width + 2 * bar_gap
    start_x = cx - total_w // 2
    bar_base_y = cy + int(canvas_size * 0.088)
    
    # 3 Ascending Signal bars
    bar_heights = [int(canvas_size * 0.08), int(canvas_size * 0.13), int(canvas_size * 0.18)]
    colors = [
        (147, 197, 253, 240), # Light blue
        (56, 189, 248, 255),  # Sky cyan
        (52, 211, 153, 255)   # Emerald green
    ]
    
    for i in range(3):
        bx = start_x + i * (bar_width + bar_gap)
        by = bar_base_y - bar_heights[i]
        c_draw.rounded_rectangle(
            [bx, by, bx + bar_width, bar_base_y],
            radius=int(bar_width * 0.4),
            fill=colors[i]
        )
    
    combined = Image.alpha_composite(final_bg, donut_layer)
    combined = Image.alpha_composite(combined, center_icon)
    
    final_img = combined.resize((size, size), Image.Resampling.LANCZOS)
    return final_img

def generate_svg_favicon(output_path):
    svg_content = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0f172a"/>
      <stop offset="50%" stop-color="#172554"/>
      <stop offset="100%" stop-color="#1e3a8a"/>
    </linearGradient>
    <linearGradient id="blueArc" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#38bdf8"/>
      <stop offset="100%" stop-color="#2563eb"/>
    </linearGradient>
    <linearGradient id="greenArc" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#34d399"/>
      <stop offset="100%" stop-color="#059669"/>
    </linearGradient>
    <linearGradient id="purpleArc" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#c084fc"/>
      <stop offset="100%" stop-color="#6366f1"/>
    </linearGradient>
    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="8" result="blur"/>
      <feComposite in="SourceGraphic" in2="blur" operator="over"/>
    </filter>
  </defs>
  
  <!-- Rounded Base -->
  <rect x="24" y="24" width="464" height="464" rx="112" fill="url(#bgGrad)" stroke="rgba(255,255,255,0.15)" stroke-width="6"/>
  
  <!-- Donut Ring Background Glow -->
  <circle cx="256" cy="256" r="130" fill="rgba(37,99,235,0.2)" filter="url(#glow)"/>
  
  <!-- Segmented Donut Slices -->
  <!-- Arc 1: Blue (QQQ/Equity) -->
  <path d="M 256 106 A 150 150 0 0 1 403 282 L 354 273 A 100 100 0 0 0 256 156 Z" fill="url(#blueArc)"/>
  
  <!-- Arc 2: Green (SCHD/Dividend) -->
  <path d="M 388 335 A 150 150 0 0 1 123 335 L 167 309 A 100 100 0 0 0 344 309 Z" fill="url(#greenArc)"/>
  
  <!-- Arc 3: Purple (Leverage/Cash) -->
  <path d="M 109 282 A 150 150 0 0 1 220 110 L 232 159 A 100 100 0 0 0 158 273 Z" fill="url(#purpleArc)"/>
  
  <!-- Center Balanced Signal Bars (No Arrow) -->
  <rect x="206" y="260" width="22" height="40" rx="8" fill="#93c5fd"/>
  <rect x="245" y="234" width="22" height="66" rx="8" fill="#38bdf8"/>
  <rect x="284" y="206" width="22" height="94" rx="8" fill="#34d399"/>
</svg>'''
    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(svg_content)

if __name__ == "__main__":
    print("Generating Asset Signal App Icons without white arrow...")
    
    icon_512 = create_asset_signal_icon(512)
    icon_512.save(os.path.join(asset_dir, "icon-512.png"), "PNG", optimize=True)
    
    icon_192 = create_asset_signal_icon(192)
    icon_192.save(os.path.join(asset_dir, "icon-192.png"), "PNG", optimize=True)
    
    icon_180 = create_asset_signal_icon(180)
    icon_180.save(os.path.join(asset_dir, "apple-touch-icon.png"), "PNG", optimize=True)
    
    icon_64 = create_asset_signal_icon(64)
    icon_64.save(os.path.join(asset_dir, "favicon-64.png"), "PNG", optimize=True)
    
    icon_32 = create_asset_signal_icon(32)
    icon_32.save(os.path.join(asset_dir, "favicon-32.png"), "PNG", optimize=True)
    icon_32.save(os.path.join(asset_dir, "favicon.ico"), "ICO")
    
    generate_svg_favicon(os.path.join(asset_dir, "favicon.svg"))
    
    # Overwrite generate_app_icons.py in asset-signal
    with open(os.path.join(asset_dir, "generate_app_icons.py"), "w", encoding="utf-8", newline="\n") as f:
        f.write(open(__file__, "r", encoding="utf-8").read())
        
    # Bump SW version
    sw_path = os.path.join(asset_dir, "sw.js")
    with open(sw_path, "r", encoding="utf-8") as f:
        sw_c = f.read()
    if "asset-signal-v16" in sw_c:
        sw_c = sw_c.replace("asset-signal-v16", "asset-signal-v17")
        with open(sw_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(sw_c)
        print("sw.js bumped to v17")

    print("All icons successfully regenerated and saved without white arrow!")
