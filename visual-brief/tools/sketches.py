"""Text-free sketch placeholders, one simple scene per option.

They stand in for the curated reference photos so the client flow can be
reviewed as it will be used: pictures only, no labels. Each scene keeps
everything constant except the tested variable, like a well-matched pair.
"""
from __future__ import annotations

import math
import random

W, H = 800, 600
SKY, GROUND = "#dfe6ea", "#cbbb9b"


def _poly(points, fill, extra=""):
    return f'<polygon points="{" ".join(f"{x:.0f},{y:.0f}" for x, y in points)}" fill="{fill}" {extra}/>'


def _rect(x, y, w, h, fill, extra=""):
    return f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" fill="{fill}" {extra}/>'


def _circle(x, y, r, fill, extra=""):
    return f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r:.0f}" fill="{fill}" {extra}/>'


def _sky_ground(horizon=470, sky=SKY, ground=GROUND):
    return _rect(0, 0, W, horizon, sky) + _rect(0, horizon, W, H - horizon, ground)


def _shrub(x, y, s, rnd, colour="#557a45"):
    return "".join(_circle(x + rnd.uniform(-s, s), y + rnd.uniform(-s / 2, 0), s * rnd.uniform(.5, .9), colour) for _ in range(4))


# ---------------------------------------------------------------- roof
def roof(opt, n, rnd):
    two = n % 2 == 0
    top = 210 if two else 300
    wall = "#efe9dd"
    body = _rect(170, top, 460, 470 - top, wall)
    wins = "".join(_rect(220 + i * 120, top + 40 + r * 120, 50, 70, "#4a3a2c") for i in range(4) for r in range(2 if two else 1) if not (i == 1 and r == (1 if two else 0)))
    door = _rect(330, 390, 50, 80, "#5a3a22")
    o = opt
    if o == "kerala_steep_tile":
        rf = _poly([(120, top), (400, top - 200), (680, top)], "#a5482f") + _poly([(370, top - 178), (400, top - 200), (430, top - 178), (400, top - 120)], "#5a3a22")
        rf += "".join(f'<line x1="{400 - k * 28}" y1="{top - 200 + k * 20}" x2="{400 + k * 28}" y2="{top - 200 + k * 20}" stroke="#8a3a25" stroke-width="2"/>' for k in range(2, 10))
        shade = _rect(170, top, 460, 26, "#00000022")
    elif o == "hacienda_low_hip":
        rf = _poly([(150, top), (260, top - 70), (540, top - 70), (650, top)], "#c46a3d")
        rf += "".join(f'<line x1="{x}" y1="{top - 68}" x2="{x - 30 + (x - 400) * .25:.0f}" y2="{top}" stroke="#a5552e" stroke-width="5"/>' for x in range(270, 540, 22))
        shade = _rect(170, top, 460, 8, "#00000018")
        wall = "#d9b98f"; body = _rect(170, top, 460, 470 - top, wall)
    elif o == "modern_flat_slab":
        rf = _rect(140, top - 18, 520, 18, "#a9a59c") + _rect(170, top - 40, 460, 22, "#efe9dd")
        shade = _rect(170, top, 460, 6, "#00000018")
    else:  # mono pitch
        rf = _poly([(90, top + 10), (710, top - 90), (710, top - 72), (90, top + 28)], "#a5482f")
        rf += "".join(_rect(x, top - 80 + (710 - x) * 0, 6, 470 - top + 80, "#3a3c3f") for x in (110,))
        rf += _rect(100, top + 20, 6, 450 - top, "#3a3c3f") + _rect(690, top - 72, 6, 542 - top, "#3a3c3f")
        shade = _rect(170, top, 460, 40, "#00000022")
    trees = _shrub(90, 450, 40, rnd) + _shrub(720, 455, 34, rnd)
    return _sky_ground() + body + wins + door + shade + rf + trees


# ---------------------------------------------------------------- courtyard (aerial)
def courtyard(opt, n, rnd):
    g = _rect(0, 0, W, H, "#b9b28e")
    tile, plaster = "#a5482f", "#c46a3d"
    s = ""
    if opt == "nalukettu_enclosed":
        s += _rect(200, 110, 400, 380, tile)
        s += "".join(f'<line x1="{a}" y1="{b}" x2="{c}" y2="{d}" stroke="#7d3322" stroke-width="3"/>' for a, b, c, d in [(200, 110, 340, 250), (600, 110, 460, 250), (200, 490, 340, 350), (600, 490, 460, 350)])
        s += _rect(340, 250, 120, 100, "#8b8a86") + _rect(360, 270, 80, 60, "#6b8f55") + _rect(392, 292, 16, 16, "#d8c8a8")
    elif opt == "open_patio":
        s += _rect(170, 100, 460, 110, plaster) + _rect(170, 210, 110, 290, plaster) + _rect(520, 210, 110, 290, plaster)
        s += _rect(280, 210, 240, 290, "#d4a27c") + _circle(400, 350, 38, "#2f6f9a") + _circle(400, 350, 22, "#6f9fb0")
        s += "".join(_circle(x, y, 14, "#557a45") for x, y in [(300, 230), (500, 230), (300, 480), (500, 480)])
    elif opt == "side_court_linear":
        s += _rect(160, 110, 300, 390, "#a9a59c") + _rect(460, 110, 140, 390, "#d8c8a8")
        s += "".join(_shrub(530, y, 22, rnd) for y in range(150, 480, 70)) + _rect(462, 110, 4, 390, "#9fb7bf")
    else:
        s += _rect(220, 140, 360, 320, "#a9a59c") + "".join(_rect(270 + i * 110, 200 + j * 120, 50, 50, "#9fb7bf") for i in range(3) for j in range(2))
    s += _shrub(90, 90, 40, rnd) + _shrub(700, 520, 40, rnd)
    return g + s


# ---------------------------------------------------------------- wall material (close-up)
def facade_material(opt, n, rnd):
    s = ""
    if opt == "laterite":
        s += _rect(0, 0, W, H, "#8a4d33")
        for y in range(0, H, 60):
            off = 0 if (y // 60) % 2 else 60
            for x in range(-off, W, 120):
                c = rnd.choice(["#9c5a3c", "#a5623f", "#93533a", "#a8694a"])
                s += _rect(x + 2, y + 2, 116, 56, c)
                s += "".join(_circle(x + rnd.uniform(8, 110), y + rnd.uniform(8, 52), rnd.uniform(1.5, 3.5), "#6e3a26") for _ in range(6))
    elif opt == "lime_whitewash":
        s += _rect(0, 0, W, H, "#f1ece1") + "".join(_circle(rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(40, 120), "#e7e0d2", 'opacity=".35"') for _ in range(12))
        s += _rect(0, H - 60, W, 60, "#8e3b2e")
    elif opt == "exposed_brick":
        s += _rect(0, 0, W, H, "#d9cfc2")
        for y in range(0, H, 30):
            off = 0 if (y // 30) % 2 else 45
            for x in range(-off, W, 90):
                s += _rect(x + 2, y + 2, 86, 26, rnd.choice(["#b0573b", "#a84f35", "#b9624a", "#9f4a32"]))
    else:
        s += _rect(0, 0, W, H, "#d9b98f")
        for _ in range(60):
            x, y = rnd.uniform(-50, W), rnd.uniform(0, H)
            s += f'<path d="M{x:.0f},{y:.0f} q40,-14 80,0 t80,0" stroke="#c9a676" stroke-width="{rnd.uniform(3, 8):.0f}" fill="none" opacity=".6" stroke-linecap="round"/>'
    # same window in every variant
    s += _rect(300, 150, 200, 260, "#5a3a22") + _rect(316, 166, 168, 228, "#2d2620") + _rect(398, 166, 4, 228, "#5a3a22")
    s += _rect(290, 410, 220, 16, "#8b8a86")
    s += f'<polygon points="0,0 {W},0 {W},{H} 0,{H}" fill="url(#light)"/>'
    return s


# ---------------------------------------------------------------- columns / verandah
def columns(opt, n, rnd):
    close = n == 2
    s = _rect(0, 0, W, H, "#e6dccb") + _rect(0, 0, W, 330, "#cfdcc4")  # garden beyond
    s += _shrub(150, 300, 50, rnd) + _shrub(420, 310, 60, rnd) + _shrub(690, 300, 50, rnd)
    floor = _rect(0, 470, W, 130, "#8e3b2e") + _rect(0, 460, W, 14, "#8b8a86")
    xs = [140, 400, 660] if not close else [260, 540]
    if opt == "timber_columns":
        s += _rect(0, 0, W, 90, "#5a3a22") + "".join(f'<line x1="0" y1="{y}" x2="{W}" y2="{y}" stroke="#4a2f1b" stroke-width="2"/>' for y in range(10, 90, 14))
        for x in xs:
            s += _rect(x - 14, 90, 28, 370, "#6b4426") + _rect(x - 26, 430, 52, 30, "#8b8a86")
            s += _poly([(x - 14, 120), (x - 60, 92), (x - 14, 92)], "#5a3a22") + _poly([(x + 14, 120), (x + 60, 92), (x + 14, 92)], "#5a3a22")
        s += _rect(0, 420, W, 40, "#6b4426", 'opacity=".9"')  # charupady seat
    elif opt == "masonry_arcade":
        s += _rect(0, 0, W, 90, "#d9b98f")
        path = f"M0,90 H{W} V460 H0 Z"
        holes = ""
        span = (W - 60) / (len(xs) + 1) if not close else 300
        for i in range(len(xs) + 1 if not close else 2):
            x0 = 30 + i * span + 25 if not close else 100 + i * 330
            w = span - 50 if not close else 270
            holes += f" M{x0:.0f},460 V{200:.0f} A{w / 2:.0f},{w / 2:.0f} 0 0 1 {x0 + w:.0f},200 V460 Z"
        s += f'<path d="{path}{holes}" fill="#d9b98f" fill-rule="evenodd"/>'
    elif opt == "wrought_iron":
        s += _rect(0, 0, W, 70, "#5a3a22") + _rect(0, 70, W, 14, "#2b2a29")
        for x in xs:
            s += _rect(x - 4, 84, 8, 376, "#2b2a29")
            s += f'<path d="M{x},150 q-50,0 -50,-60 M{x},150 q50,0 50,-60" stroke="#2b2a29" stroke-width="4" fill="none"/>'
        s += "".join(_rect(x, 400, 3, 60, "#2b2a29") for x in range(0, W, 24)) + _rect(0, 398, W, 5, "#2b2a29")
    else:
        s += _rect(0, 0, W, 80, "#a9a59c")
        s += "".join(_rect(x - 5, 80, 10, 380, "#3a3c3f") for x in xs)
    return s + floor


# ---------------------------------------------------------------- openings
def openings(opt, n, rnd):
    inside = n == 2
    wall = "#efe9dd" if not inside else "#e2d8c6"
    s = _rect(0, 0, W, H, wall)
    view = "#cfdcc4"
    if opt == "timber_slat_rect":
        s += _rect(250, 110, 300, 340, "#5a3a22") + _rect(266, 126, 268, 308, view)
        s += "".join(_rect(266, y, 268, 9, "#6b4426") for y in range(130, 430, 20))
    elif opt == "arched_openings":
        s += f'<path d="M260,460 V240 A140,140 0 0 1 540,240 V460 Z" fill="#c9b79c"/><path d="M285,460 V250 A115,115 0 0 1 515,250 V460 Z" fill="{view}"/>'
        s += "".join(f'<line x1="{x}" y1="140" x2="{x}" y2="460" stroke="#2b2a29" stroke-width="4"/>' for x in range(310, 500, 38))
        s += "".join(f'<line x1="285" y1="{y}" x2="515" y2="{y}" stroke="#2b2a29" stroke-width="3"/>' for y in (300, 380))
    elif opt == "modern_full_height":
        s += _rect(80, 60, 640, 470, "#3a3c3f") + _rect(92, 72, 616, 446, "#9fb7bf") + _rect(398, 72, 6, 446, "#3a3c3f")
        s += _shrub(250, 420, 60, rnd) + _shrub(560, 430, 70, rnd)
        s += _rect(40, 30, 720, 30, "#a9a59c") if not inside else ""
    else:
        s += _rect(200, 80, 400, 420, "#b0573b")
        s += "".join(_rect(x, y, 22, 22, view if not inside else "#f6e7c4") for x in range(214, 586, 36) for y in range(94, 486, 36))
    s += _rect(0, H - 70, W, 70, "#8e3b2e" if inside else GROUND)
    return s


# ---------------------------------------------------------------- palette (room or facade)
def palette(opt, n, rnd):
    c = {"ochre_terracotta": ("#c9973a", "#c46a3d", "#2f6f9a"), "wood_whitewash": ("#f1ece1", "#8e3b2e", "#5a3a22"),
         "earthy_neutral": ("#d8c8a8", "#8b8a86", "#7d7a4f")}[opt]
    if n == 1:  # living room
        s = _rect(0, 0, W, 420, c[0]) + _poly([(0, 420), (W, 420), (W, H), (0, H)], c[1])
        s += _rect(300, 120, 200, 300, c[2]) + _rect(318, 138, 164, 282, "#00000025")
        s += _rect(80, 330, 160, 70, c[2]) + _rect(560, 300, 140, 120, "#00000018") + _rect(100, 280, 120, 50, c[2], 'opacity=".8"')
    else:  # entrance facade
        s = _sky_ground(ground=c[1]) + _rect(160, 230, 480, 240, c[0]) + _poly([(130, 230), (400, 140), (670, 230)], c[1])
        s += _rect(360, 330, 80, 140, c[2]) + _rect(220, 300, 60, 80, c[2]) + _rect(520, 300, 60, 80, c[2])
    return s


# ---------------------------------------------------------------- landscape (from the verandah)
def landscape(opt, n, rnd):
    s = ""
    if opt == "courtyard_planting":
        s += _rect(0, 0, W, 300, "#efe9dd") + _rect(0, 300, W, 300, "#7fa063")
        s += _rect(360, 330, 80, 40, "#8b8a86") + _rect(370, 300, 60, 30, "#8b8a86") + _shrub(400, 290, 18, rnd, "#3f6b3a")
        s += _rect(150, 180, 10, 140, "#5a3a22") + _shrub(155, 170, 50, rnd, "#6b8f55") + "".join(_circle(155 + rnd.uniform(-40, 40), 160 + rnd.uniform(-30, 20), 5, "#f6efe0") for _ in range(10))
    elif opt == "fountain_patio":
        s += _rect(0, 0, W, 300, "#d9b98f") + _rect(0, 300, W, 300, "#c46a3d")
        s += "".join(f'<line x1="0" y1="{y}" x2="{W}" y2="{y}" stroke="#a5552e" stroke-width="2"/>' for y in range(330, 600, 40))
        s += '<ellipse cx="400" cy="420" rx="150" ry="50" fill="#2f6f9a"/><ellipse cx="400" cy="414" rx="125" ry="38" fill="#6f9fb0"/>' + _rect(390, 330, 20, 80, "#2f6f9a")
        s += "".join(_rect(x, 330, 40, 50, "#a5482f") + _shrub(x + 20, 320, 22, rnd) for x in (120, 640))
    elif opt == "lush_verandah_garden":
        s += _rect(0, 0, W, H, "#cfdcc4") + "".join(_shrub(rnd.uniform(0, W), rnd.uniform(150, 560), rnd.uniform(40, 90), rnd, rnd.choice(["#3f6b3a", "#557a45", "#2f5530"])) for _ in range(22))
    elif opt == "dry_native":
        s += _rect(0, 0, W, 300, SKY) + _rect(0, 300, W, 300, "#d8c8a8")
        s += "".join(f'<ellipse cx="{rnd.uniform(60, 740):.0f}" cy="{rnd.uniform(380, 560):.0f}" rx="{rnd.uniform(25, 60):.0f}" ry="{rnd.uniform(15, 30):.0f}" fill="#8b8a86"/>' for _ in range(5))
        s += _rect(560, 160, 14, 160, "#5a4a3a") + _shrub(567, 150, 80, rnd, "#7d7a4f") + "".join(_shrub(rnd.uniform(80, 500), rnd.uniform(330, 400), 20, rnd, "#9a9563") for _ in range(5))
    else:
        s += _rect(0, 0, W, 300, SKY) + _rect(0, 300, W, 300, "#8b8a86") + _rect(120, 360, 560, 150, "#6f9fb0") + _rect(120, 360, 560, 30, "#9fc3cf")
        s += _shrub(700, 320, 30, rnd)
    # verandah frame: same in every variant
    s += _rect(0, 520, W, 80, "#8e3b2e") + _rect(0, 0, W, 50, "#5a3a22") + _rect(60, 50, 20, 470, "#6b4426") + _rect(720, 50, 20, 470, "#6b4426")
    return s


# ---------------------------------------------------------------- abstraction
def abstraction(opt, n, rnd):
    arches = n == 2
    s = _rect(0, 0, W, H, "#cfdcc4") + _shrub(400, 330, 70, rnd)
    wall = "#efe9dd" if not arches else "#d9b98f"
    level = {"ornate": 2, "restrained": 1, "minimal": 0}[opt]
    s += _rect(0, 0, W, 110, wall if level < 2 or arches else "#5a3a22")
    if level >= 1:
        s += _rect(0, 96, W, 14, "#8e3b2e" if not arches else "#c46a3d")
    if level == 2:
        s += "".join(_poly([(x, 20), (x + 20, 50), (x, 80), (x - 20, 50)], "#2f6f9a" if arches else "#c9973a") for x in range(30, W, 60))
    xs = [130, 400, 670]
    for x in xs:
        if arches:
            pass
        else:
            w = 30 if level else 12
            s += _rect(x - w / 2, 110, w, 360, "#6b4426" if level else "#3a3c3f")
            if level == 2:
                s += _poly([(x - 15, 150), (x - 70, 112), (x - 15, 112)], "#5a3a22") + _poly([(x + 15, 150), (x + 70, 112), (x + 15, 112)], "#5a3a22")
                s += _rect(x - 28, 430, 56, 40, "#8b8a86") + "".join(_rect(x - 15, y, 30, 4, "#4a2f1b") for y in (200, 260, 320))
    if arches:
        holes = "".join(f" M{x0},470 V{250 if level else 470} " + (f"A120,120 0 0 1 {x0 + 240},250 V470 Z" if level else f"V140 H{x0 + 240} V470 Z") for x0 in (25, 280, 535))
        s += f'<path d="M0,110 H{W} V470 H0 Z{holes}" fill="{wall}" fill-rule="evenodd"/>'
        if level == 2:
            s += "".join(f'<path d="M{x0},250 A120,120 0 0 1 {x0 + 240},250" stroke="#c46a3d" stroke-width="10" fill="none"/>' for x0 in (25, 280, 535))
            s += "".join(_rect(x, 380, 20, 20, "#2f6f9a") for x in range(20, W, 40))
    s += _rect(0, 470, W, 130, "#8e3b2e" if level else "#a9a59c")
    return s


SCENES = {"roof": roof, "courtyard": courtyard, "facade_material": facade_material, "columns": columns,
          "openings": openings, "palette": palette, "landscape": landscape, "abstraction": abstraction}


def sketch_svg(dim_id: str, opt_id: str, n: int, code: str) -> str:
    rnd = random.Random(f"{dim_id}/{opt_id}/{n}")
    body = SCENES[dim_id](opt_id, n, rnd)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
<defs><linearGradient id="light" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".18"/><stop offset="1" stop-color="#000" stop-opacity=".18"/></linearGradient></defs>
{body}
<rect width="{W}" height="{H}" fill="url(#light)"/>
<text x="{W - 14}" y="{H - 12}" font-family="system-ui, sans-serif" font-size="13" fill="#ffffff" fill-opacity=".75" text-anchor="end" stroke="#000" stroke-opacity=".25" stroke-width=".5">{code}</text>
</svg>'''
