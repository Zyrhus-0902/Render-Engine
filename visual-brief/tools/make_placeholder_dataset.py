"""Generate the starter dataset for a visual-brief project, with placeholder images.

This writes, under visual-brief/datasets/<project>/:

    dataset.json          project, copy, origins, dimensions (with options), chips, brief, tensions
    pairs.json            the A/B pairs, one dimension per pair
    assets/manifest.json  every image: file, dimension, option, origin, materials, palette,
                          climate check, scale, source and credit
    assets/*.svg          labelled placeholder cards (replace with curated photos)

Run it once to scaffold. After that, edit the JSON files directly: the architect
curates by replacing `file`, `source` and `credit` in the manifest and pointing
the file at a real photo in assets/. Re-running this script overwrites the JSON
and the placeholder SVGs (it never deletes other files), so pass --force only
when you really want a fresh start.

    python visual-brief/tools/make_placeholder_dataset.py            # writes erode-hacienda-kerala
    python visual-brief/tools/make_placeholder_dataset.py --force    # overwrite existing JSON
"""
from __future__ import annotations

import argparse
import json
import textwrap
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ID = "erode-hacienda-kerala"

ORIGINS = [
    {"id": "kerala", "label": "Kerala", "description": "Kerala vernacular: steep tiled roofs, timber, nalukettu courtyards."},
    {"id": "hacienda", "label": "Hacienda", "description": "Spanish-colonial / Latin American hacienda: low terracotta roofs, arcades, patios."},
    {"id": "modern", "label": "Modern", "description": "Contemporary abstraction: simplified forms, slab, glass, steel, minimal detail."},
    {"id": "hybrid", "label": "Hybrid / shared", "description": "Shared by both traditions (e.g. lime whitewash) or already a blend."},
]

# ---------------------------------------------------------------------------
# Dimensions. Each option carries its default origin, materials and palette;
# images inherit these unless they override them.
# ---------------------------------------------------------------------------
C = {  # named colours reused across options
    "clay_tile": ("Clay tile red", "#a5482f"),
    "terracotta": ("Terracotta", "#c46a3d"),
    "ochre": ("Ochre", "#c9973a"),
    "whitewash": ("Lime white", "#f1ece1"),
    "teak": ("Dark teak", "#5a3a22"),
    "red_oxide": ("Red oxide", "#8e3b2e"),
    "laterite": ("Laterite", "#9c5a3c"),
    "brick": ("Country brick", "#b0573b"),
    "stucco": ("Warm stucco", "#d9b98f"),
    "sand": ("Sand", "#d8c8a8"),
    "granite": ("Grey granite", "#8b8a86"),
    "concrete": ("Board concrete", "#a9a59c"),
    "steel": ("Dark steel", "#3a3c3f"),
    "iron": ("Wrought iron", "#2b2a29"),
    "glass": ("Glass", "#9fb7bf"),
    "indigo": ("Indigo accent", "#2e4a7a"),
    "talavera": ("Glazed tile blue", "#2f6f9a"),
    "leaf": ("Tropical green", "#3f6b3a"),
    "olive": ("Dry olive", "#7d7a4f"),
    "water": ("Water", "#6f9fb0"),
}


def pal(*keys):
    return [{"name": C[k][0], "hex": C[k][1]} for k in keys]


DIMENSIONS = [
    {
        "id": "roof",
        "name": "Roof form",
        "description": "Pitch, eave depth and roofing material, seen from the same angle on a similar house.",
        "client_prompt": "Look only at the roof. Which one feels more like your home?",
        "isolate_note": "Same mass and wall finish, same sky and camera; only the roof changes.",
        "options": [
            {"id": "kerala_steep_tile", "label": "Steep clay-tile roof", "origin": "kerala",
             "description": "35-45° Mangalore-tile roof, deep eaves, gablet vents (mukhappu).",
             "materials": ["Mangalore clay tile", "Timber rafters"], "palette": pal("clay_tile", "teak"),
             "why_prompt": "What draws you to the steep roof: the silhouette, the deep shade under the eaves, or the tiled texture?"},
            {"id": "hacienda_low_hip", "label": "Low terracotta hip roof", "origin": "hacienda",
             "description": "15-22° hipped roof in barrel (mission) tile, short eaves, heavy walls below.",
             "materials": ["Barrel terracotta tile", "Plastered masonry"], "palette": pal("terracotta", "stucco"),
             "why_prompt": "Is it the lower, calmer roofline you like, or the curved barrel tiles themselves?"},
            {"id": "modern_flat_slab", "label": "Flat slab, thin overhang", "origin": "modern",
             "description": "Flat RCC roof with a thin cantilevered sunshade, usable terrace above.",
             "materials": ["Exposed RCC", "Terrace tiles"], "palette": pal("concrete", "whitewash"),
             "why_prompt": "Do you want a usable roof terrace, or is it the clean flat edge you like?"},
            {"id": "modern_mono_pitch", "label": "Single-pitch deep overhang", "origin": "modern",
             "description": "Abstracted mono-pitch roof, tile or metal, very deep overhang on slim supports.",
             "materials": ["Clay tile on steel", "Steel sections"], "palette": pal("clay_tile", "steel"),
             "why_prompt": "Is the single slope about looking contemporary, or about one big sheltering overhang?"},
        ],
    },
    {
        "id": "courtyard",
        "name": "Courtyard & massing",
        "description": "How rooms gather around (or without) open space.",
        "client_prompt": "Look at how the house wraps around the open space. Which arrangement would you rather live in?",
        "isolate_note": "Aerial or eye-level views at the same scale and plot size.",
        "options": [
            {"id": "nalukettu_enclosed", "label": "Enclosed nalukettu court", "origin": "kerala",
             "description": "Four wings around a small open-to-sky nadumuttam; roofs slope inward; verandah ring.",
             "materials": ["Timber verandah", "Granite courtyard edge"], "palette": pal("teak", "granite"),
             "why_prompt": "What matters most in the enclosed court: privacy, rain falling inside the house, or everyone gathered around one centre?"},
            {"id": "open_patio", "label": "Open central patio", "origin": "hacienda",
             "description": "Larger paved patio, arcaded on two to four sides, more sky and sun.",
             "materials": ["Terracotta paving", "Plastered arcade"], "palette": pal("terracotta", "stucco"),
             "why_prompt": "Do you picture the patio as an outdoor room for gatherings, or mainly as light and air for the house?"},
            {"id": "side_court_linear", "label": "Linear side court", "origin": "modern",
             "description": "Long side garden or slot court along the rooms; rooms open sideways.",
             "materials": ["Glass sliders", "Gravel and stone"], "palette": pal("glass", "granite"),
             "why_prompt": "Is the side court about a garden view from every room, or about keeping the plan compact?"},
            {"id": "compact_no_court", "label": "Compact, no courtyard", "origin": "modern",
             "description": "One compact block, light from skylights and terraces instead of a court.",
             "materials": ["Skylights", "RCC frame"], "palette": pal("concrete", "whitewash"),
             "why_prompt": "You leaned compact: is a courtyard not important to you, or are you worried about cost and upkeep?"},
        ],
    },
    {
        "id": "facade_material",
        "name": "Wall material",
        "description": "The main wall surface, close up and in daylight.",
        "client_prompt": "Look only at the wall surface. Which would you like to touch every day?",
        "isolate_note": "Same window, same light, same crop; only the wall finish changes.",
        "options": [
            {"id": "laterite", "label": "Exposed laterite", "origin": "kerala",
             "description": "Cut laterite blocks left exposed, rough and porous, deep red-brown.",
             "materials": ["Laterite block"], "palette": pal("laterite", "granite"),
             "why_prompt": "Is it the colour of laterite you like, or the rough, handmade texture? (Local brick or stone could give either.)"},
            {"id": "lime_whitewash", "label": "Lime-plastered whitewash", "origin": "hybrid",
             "description": "Smooth-to-soft lime plaster, whitewashed; shared by both traditions.",
             "materials": ["Lime plaster", "Whitewash"], "palette": pal("whitewash", "red_oxide"),
             "why_prompt": "White walls show every stain in Erode's dust. Is the crisp white essential, or would an off-white lime work?"},
            {"id": "exposed_brick", "label": "Exposed brick", "origin": "modern",
             "description": "Wire-cut or country brick, flush or raked joints; contemporary regional.",
             "materials": ["Exposed brick"], "palette": pal("brick", "concrete"),
             "why_prompt": "Do you like brick for its warmth, its pattern, or because it needs no painting?"},
            {"id": "textured_stucco", "label": "Hand-troweled stucco", "origin": "hacienda",
             "description": "Thick, hand-troweled plaster with soft edges, earth-tinted.",
             "materials": ["Textured stucco"], "palette": pal("stucco", "ochre"),
             "why_prompt": "Is it the soft, rounded handmade look, or the warm tint of the plaster?"},
        ],
    },
    {
        "id": "columns",
        "name": "Columns & verandah",
        "description": "The column, bracket and ceiling language of the verandah.",
        "client_prompt": "Look at the columns and the verandah ceiling. Which verandah would you sit in?",
        "isolate_note": "Same verandah depth and floor; columns and ceiling change.",
        "options": [
            {"id": "timber_columns", "label": "Timber columns & brackets", "origin": "kerala",
             "description": "Turned timber posts on stone bases, carved brackets, timber ceiling, built-in seat (charupady).",
             "materials": ["Teak or jackwood posts", "Granite plinth", "Timber ceiling"], "palette": pal("teak", "granite"),
             "why_prompt": "Is it the warmth of the wood, the carved brackets, or the built-in seating along the edge?"},
            {"id": "masonry_arcade", "label": "Masonry arcade", "origin": "hacienda",
             "description": "Round-arched plastered arcade on square piers (portales).",
             "materials": ["Plastered masonry arches"], "palette": pal("stucco", "terracotta"),
             "why_prompt": "Is it the arch shape you like, or the solid, shaded rhythm of a deep arcade?"},
            {"id": "wrought_iron", "label": "Slim iron posts & rails", "origin": "hacienda",
             "description": "Slim wrought-iron posts, corbels and railings, timber beam above.",
             "materials": ["Wrought iron", "Timber beam"], "palette": pal("iron", "teak"),
             "why_prompt": "Do you like the ironwork as ornament, or for how light and open it keeps the verandah?"},
            {"id": "modern_slender", "label": "Slender steel/RCC frame", "origin": "modern",
             "description": "Thin steel or RCC columns, flat soffit, no ornament.",
             "materials": ["Steel columns", "RCC soffit"], "palette": pal("steel", "concrete"),
             "why_prompt": "Is the plain frame about a clean look, or about less maintenance than timber?"},
        ],
    },
    {
        "id": "openings",
        "name": "Windows & openings",
        "description": "Window shape, frame and screening.",
        "client_prompt": "Look at the windows only. Which would you rather look out of?",
        "isolate_note": "Same wall, same room behind; only the opening changes.",
        "options": [
            {"id": "timber_slat_rect", "label": "Rectangular timber slat windows", "origin": "kerala",
             "description": "Rectilinear timber frames, louvred shutters, vertical bars.",
             "materials": ["Timber shutters", "MS bars"], "palette": pal("teak", "whitewash"),
             "why_prompt": "Do you like being able to open everything for breeze, or the filtered light through the slats?"},
            {"id": "arched_openings", "label": "Arched openings, iron grilles", "origin": "hacienda",
             "description": "Arched heads, deep reveals, decorative iron grilles (rejas).",
             "materials": ["Wrought-iron grille", "Plastered reveal"], "palette": pal("iron", "stucco"),
             "why_prompt": "Is it the arch shape, or the deep, thick-walled reveal around the window?"},
            {"id": "modern_full_height", "label": "Full-height shaded glazing", "origin": "modern",
             "description": "Floor-to-ceiling glazing behind deep shade or screens.",
             "materials": ["Glass sliders", "Aluminium or timber frame"], "palette": pal("glass", "steel"),
             "why_prompt": "Big glass in Erode's sun needs deep shade. Which room do you picture this in, and facing which way?"},
            {"id": "jaali_screen", "label": "Brick or terracotta jaali", "origin": "hybrid",
             "description": "Perforated brick or terracotta screen walls filtering light and air.",
             "materials": ["Terracotta jaali", "Brick jaali"], "palette": pal("brick", "terracotta"),
             "why_prompt": "Is the jaali about privacy from the street, or the pattern of light it throws inside?"},
        ],
    },
    {
        "id": "palette",
        "name": "Colour & palette",
        "description": "Overall colour mood of the house, indoors and out.",
        "client_prompt": "Ignore the shapes. Which colours feel more like you?",
        "isolate_note": "Similar rooms or facades; colour is what differs.",
        "options": [
            {"id": "ochre_terracotta", "label": "Ochre & terracotta warmth", "origin": "hacienda",
             "description": "Warm ochre walls, terracotta floors, deep blue or green painted accents.",
             "materials": ["Ochre limewash", "Terracotta floor", "Glazed accent tile"], "palette": pal("ochre", "terracotta", "talavera"),
             "why_prompt": "Is it the warmth you want, or the colourful accents (blue, green, tiles)?"},
            {"id": "wood_whitewash", "label": "Natural wood & whitewash", "origin": "kerala",
             "description": "Dark natural timber, white lime walls, red-oxide floors.",
             "materials": ["Dark teak", "Lime white", "Red-oxide floor"], "palette": pal("teak", "whitewash", "red_oxide"),
             "why_prompt": "Is it the restraint (few colours), or the contrast of dark wood against white?"},
            {"id": "earthy_neutral", "label": "Muted earth & stone", "origin": "modern",
             "description": "Sand, grey granite, concrete, muted greens.",
             "materials": ["Grey granite", "Sand plaster", "Concrete"], "palette": pal("sand", "granite", "olive"),
             "why_prompt": "Do you want calm, low-contrast colour throughout, or a neutral base to add colour to later?"},
        ],
    },
    {
        "id": "landscape",
        "name": "Landscape & threshold",
        "description": "Planting, water and how the verandah meets the garden.",
        "client_prompt": "Look at the garden and how you step into it. Which would you rather walk out to?",
        "isolate_note": "Same verandah edge; the planting and water change.",
        "options": [
            {"id": "courtyard_planting", "label": "Courtyard planting, tulsi thara", "origin": "kerala",
             "description": "Small planted court with a tulsi thara, frangipani, open verandah edges.",
             "materials": ["Granite tulsi thara", "Frangipani", "Lawn"], "palette": pal("leaf", "granite"),
             "why_prompt": "Is the planted court about a ritual centre for the family, or simply greenery you can see from every room?"},
            {"id": "fountain_patio", "label": "Tiled fountain patio", "origin": "hacienda",
             "description": "Central tiled fountain or water channel, paving, potted plants.",
             "materials": ["Glazed tile fountain", "Terracotta paving", "Potted plants"], "palette": pal("talavera", "terracotta", "water"),
             "why_prompt": "Is it the sound of water, the decorative tile, or a paved space for gatherings?"},
            {"id": "lush_verandah_garden", "label": "Lush tropical garden", "origin": "kerala",
             "description": "Verandah opening straight onto a dense green garden (banana, heliconia, palms).",
             "materials": ["Tropical shrubs", "Laterite path"], "palette": pal("leaf", "laterite"),
             "why_prompt": "A lush garden needs a lot of water in Erode. How much maintenance and irrigation are you willing to take on?"},
            {"id": "dry_native", "label": "Dry native garden, shade trees", "origin": "modern",
             "description": "Climate-native planting, gravel, boulders, neem or pongamia shade.",
             "materials": ["Native shrubs", "Gravel", "Boulders"], "palette": pal("olive", "sand", "granite"),
             "why_prompt": "Do you like the dry garden's look, or is it about low water and low upkeep?"},
            {"id": "reflecting_pool", "label": "Minimal reflecting pool", "origin": "modern",
             "description": "Shallow still water edged in stone, sparse planting.",
             "materials": ["Stone-edged pool", "Sparse planting"], "palette": pal("water", "granite"),
             "why_prompt": "Is the still water about calm and reflection, or about cooling the air near the verandah?"},
        ],
    },
    {
        "id": "abstraction",
        "name": "Modern abstraction",
        "description": "How much traditional detail to keep: ornate, restrained, minimal.",
        "client_prompt": "Same kind of space, different amount of detail. Which level feels right?",
        "isolate_note": "Same subject (e.g. a verandah) drawn at different levels of detail.",
        "options": [
            {"id": "ornate", "label": "Ornate, full traditional detail", "origin": "kerala",
             "description": "Carved brackets, mouldings, decorative tile and ironwork kept.",
             "materials": ["Carved timber", "Decorative tile"], "palette": pal("teak", "talavera"),
             "why_prompt": "Which ornaments matter to you, and which are just part of the overall feeling?"},
            {"id": "restrained", "label": "Restrained, simplified traditional", "origin": "hybrid",
             "description": "Traditional forms kept, ornament reduced to a few key pieces.",
             "materials": ["Plain timber", "Lime plaster"], "palette": pal("teak", "whitewash"),
             "why_prompt": "If we keep only two or three traditional pieces, which would they be?"},
            {"id": "minimal", "label": "Minimal, abstracted", "origin": "modern",
             "description": "Only the essence: proportion, shade, material; no ornament.",
             "materials": ["Concrete", "Plain plaster"], "palette": pal("concrete", "sand"),
             "why_prompt": "With no ornament, what should still tell people this house is rooted in tradition?"},
        ],
    },
]

# ---------------------------------------------------------------------------
# Images per option (a short subject line each). Overrides: origin, climate, scale.
# ---------------------------------------------------------------------------
IMAGES = {
    "roof": {
        "kerala_steep_tile": ["single-storey house, front elevation", "two-storey house, three-quarter view", "house with gablet, side view"],
        "hacienda_low_hip": ["single-storey house, front elevation", "two-storey house, three-quarter view", "long wing, side view"],
        "modern_flat_slab": [("single-storey house, front elevation", {"climate": ("review", "Flat roof needs insulation and a terrace finish against summer heat gain; drains fine with Erode's low rainfall.")}),
                             "two-storey house, three-quarter view"],
        "modern_mono_pitch": ["single-storey house, front elevation", "two-storey house, three-quarter view"],
    },
    "courtyard": {
        "nalukettu_enclosed": ["eye level from verandah into court", "aerial, four wings", "rain falling into the court"],
        "open_patio": ["eye level from arcade into patio", "aerial, U-shaped plan", "evening gathering in patio"],
        "side_court_linear": ["eye level along side court", "aerial, linear plan"],
        "compact_no_court": ["eye level, skylit double-height hall", "aerial, compact block"],
    },
    "facade_material": {
        "laterite": [("close-up wall with window", {"climate": ("review", "Laterite is quarried in Kerala/coastal Karnataka; transport to Erode adds cost. Consider local brick or stone with a similar look.")}),
                     "corner detail"],
        "lime_whitewash": ["close-up wall with window", "corner detail"],
        "exposed_brick": ["close-up wall with window", "corner detail"],
        "textured_stucco": ["close-up wall with window", "corner detail"],
    },
    "columns": {
        "timber_columns": ["verandah, three columns", "column and bracket close-up"],
        "masonry_arcade": ["verandah, three arches", "arch and pier close-up"],
        "wrought_iron": ["verandah, three posts", "post and corbel close-up"],
        "modern_slender": ["verandah, three columns", "column and soffit close-up"],
    },
    "openings": {
        "timber_slat_rect": ["window from outside", "window from inside, light"],
        "arched_openings": ["window from outside", "window from inside, light"],
        "modern_full_height": [("window from outside", {"climate": ("review", "Only with deep shade or north orientation; unshaded east/west glass overheats in Erode.")}),
                               "window from inside, light"],
        "jaali_screen": ["screen from outside", "screen from inside, light"],
    },
    "palette": {
        "ochre_terracotta": ["living room", "entrance facade"],
        "wood_whitewash": ["living room", "entrance facade"],
        "earthy_neutral": ["living room", "entrance facade"],
    },
    "landscape": {
        "courtyard_planting": ["verandah edge into planted court", "tulsi thara close-up"],
        "fountain_patio": ["verandah edge to fountain patio", "fountain close-up"],
        "lush_verandah_garden": [("verandah edge into dense garden", {"climate": ("review", "High irrigation demand in Erode's dry season; keep only with a water plan (rainwater harvesting, drip).")}),
                                 "garden path"],
        "dry_native": ["verandah edge to dry garden", "gravel path with shade tree"],
        "reflecting_pool": ["verandah edge to reflecting pool", "pool edge close-up"],
    },
    "abstraction": {
        "ornate": [("Kerala-style verandah", {"origin": "kerala"}), ("hacienda-style arcade", {"origin": "hacienda"})],
        "restrained": [("Kerala-style verandah", {"origin": "kerala"}), ("hacienda-style arcade", {"origin": "hacienda"})],
        "minimal": [("Kerala-style verandah", {"origin": "modern"}), ("hacienda-style arcade", {"origin": "modern"})],
    },
}

# Pairs per dimension as (option_a, option_b). The main Kerala-vs-hacienda contrast
# appears more than once (with different images, sides swapped) so the profile
# can check consistency. For abstraction, a third item picks the image subject
# index so both sides show the same subject.
PAIRS = {
    "roof": [("kerala_steep_tile", "hacienda_low_hip"), ("hacienda_low_hip", "kerala_steep_tile"),
             ("kerala_steep_tile", "hacienda_low_hip"), ("kerala_steep_tile", "modern_flat_slab"),
             ("hacienda_low_hip", "modern_flat_slab"), ("modern_mono_pitch", "kerala_steep_tile"),
             ("hacienda_low_hip", "modern_mono_pitch")],
    "courtyard": [("nalukettu_enclosed", "open_patio"), ("open_patio", "nalukettu_enclosed"),
                  ("nalukettu_enclosed", "open_patio"), ("nalukettu_enclosed", "side_court_linear"),
                  ("open_patio", "compact_no_court"), ("side_court_linear", "open_patio"),
                  ("compact_no_court", "nalukettu_enclosed")],
    "facade_material": [("laterite", "textured_stucco"), ("lime_whitewash", "exposed_brick"),
                        ("textured_stucco", "lime_whitewash"), ("exposed_brick", "laterite"),
                        ("laterite", "lime_whitewash"), ("textured_stucco", "exposed_brick"),
                        ("textured_stucco", "laterite")],
    "columns": [("timber_columns", "masonry_arcade"), ("wrought_iron", "timber_columns"),
                ("masonry_arcade", "modern_slender"), ("masonry_arcade", "timber_columns"),
                ("modern_slender", "timber_columns"), ("wrought_iron", "masonry_arcade"),
                ("modern_slender", "wrought_iron")],
    "openings": [("timber_slat_rect", "arched_openings"), ("modern_full_height", "timber_slat_rect"),
                 ("arched_openings", "jaali_screen"), ("arched_openings", "timber_slat_rect"),
                 ("jaali_screen", "timber_slat_rect"), ("modern_full_height", "arched_openings"),
                 ("jaali_screen", "modern_full_height")],
    "palette": [("ochre_terracotta", "wood_whitewash"), ("earthy_neutral", "ochre_terracotta"),
                ("wood_whitewash", "earthy_neutral"), ("wood_whitewash", "ochre_terracotta"),
                ("ochre_terracotta", "earthy_neutral"), ("earthy_neutral", "wood_whitewash")],
    "landscape": [("courtyard_planting", "fountain_patio"), ("lush_verandah_garden", "dry_native"),
                  ("fountain_patio", "reflecting_pool"), ("dry_native", "courtyard_planting"),
                  ("fountain_patio", "courtyard_planting"), ("reflecting_pool", "lush_verandah_garden"),
                  ("courtyard_planting", "reflecting_pool"), ("dry_native", "fountain_patio")],
    "abstraction": [("ornate", "restrained", 0), ("restrained", "ornate", 1), ("restrained", "minimal", 0),
                    ("minimal", "restrained", 1), ("ornate", "minimal", 0), ("minimal", "ornate", 1)],
}

CHIPS = [
    {"id": "shape", "label": "Shape"},
    {"id": "colour", "label": "Colour"},
    {"id": "material", "label": "Material"},
    {"id": "light", "label": "Light & shade"},
    {"id": "mood", "label": "Mood"},
    {"id": "detail", "label": "Detail"},
]

BRIEF = {
    "title": "A few practical questions",
    "intro": "Optional, but it helps us connect what you liked to how you live.",
    "fields": [
        {"id": "household", "type": "textarea", "label": "Who will live in the house?", "placeholder": "e.g. the two of us, two children, my parents on weekends"},
        {"id": "spaces", "type": "multi", "label": "Which spaces must the house have?", "options": [
            "Pooja room", "Ground-floor bedroom for elders", "Guest room with own entrance", "Home office",
            "Large dining for gatherings", "Second (dirty) kitchen", "Outdoor kitchen / barbecue",
            "Car porch", "Store room", "Terrace for drying / sit-out", "Swing (oonjal) space"]},
        {"id": "cars", "type": "number", "label": "How many cars should be parked under cover?", "min": 0, "max": 6},
        {"id": "must_haves", "type": "textarea", "label": "Anything you definitely want?", "placeholder": "e.g. a courtyard with rain falling in, a big verandah swing"},
        {"id": "never", "type": "textarea", "label": "Anything you definitely don't want?", "placeholder": "e.g. no dark rooms, no high maintenance garden"},
        {"id": "plot", "type": "single", "label": "Do you know the plot yet?", "options": ["Yes, it's bought", "Shortlisted", "Not yet"]},
    ],
}

# Cross-dimension combinations worth a conversation. All `when` conditions must hold.
TENSIONS = [
    {"id": "nalukettu_low_roof", "when": [{"dimension": "courtyard", "option": "nalukettu_enclosed"}, {"dimension": "roof", "option": "hacienda_low_hip"}],
     "prompt": "You liked the enclosed nalukettu court and the low hacienda roof. A nalukettu traditionally depends on steep roofs draining into the court. Was it the enclosure you liked, or the rain falling inside?"},
    {"id": "flat_roof_timber", "when": [{"dimension": "roof", "option": "modern_flat_slab"}, {"dimension": "columns", "option": "timber_columns"}],
     "prompt": "You chose a flat roof but timber verandah columns. Should the timber carry the tradition while the roof stays modern, or does the roof feel unfinished without tiles?"},
    {"id": "glazing_heat", "when": [{"dimension": "openings", "option": "modern_full_height"}],
     "prompt": "You liked full-height glass. In Erode's heat it needs deep shade: which rooms do you picture opening up fully, and which way would they face?"},
    {"id": "lush_water", "when": [{"dimension": "landscape", "option": "lush_verandah_garden"}],
     "prompt": "You chose the lush garden. It needs a lot of irrigation through Erode's dry months. Would a dense planted courtyard with a smaller dry garden outside give you the same feeling?"},
    {"id": "minimal_ornament", "when": [{"dimension": "abstraction", "option": "minimal"}, {"dimension": "columns", "option": "timber_columns"}],
     "prompt": "You chose minimal detail overall but liked the carved timber verandah. Which one or two traditional pieces are worth keeping in a minimal house?"},
    {"id": "white_ochre", "when": [{"dimension": "facade_material", "option": "lime_whitewash"}, {"dimension": "palette", "option": "ochre_terracotta"}],
     "prompt": "You liked white lime walls but an ochre-terracotta palette. Should the walls stay white with the warmth in floors and roofs, or should the walls themselves be tinted?"},
    {"id": "compact_court_landscape", "when": [{"dimension": "courtyard", "option": "compact_no_court"}, {"dimension": "landscape", "option": "courtyard_planting"}],
     "prompt": "You leaned towards a compact house without a courtyard, but liked the planted courtyard garden. Is a small court worth the extra footprint?"},
]

COPY = {
    "en": {
        "intro_title": "Help us see your home",
        "intro_body": "You'll see pairs of pictures, a few rounds of 6-8 each. Each pair changes one thing only: the roof, the walls, the garden. Tap the one you prefer. There are no right answers and no need to explain; go with your first feeling.",
        "intro_time": "About 10-15 minutes.",
        "name_label": "Your name",
        "name_placeholder": "e.g. Priya",
        "start": "Start",
        "resume": "Continue where you left off",
        "start_over": "Start over",
        "round": "Round",
        "of": "of",
        "begin_round": "Begin",
        "both": "Both equally",
        "neither": "Neither",
        "never": "Never this",
        "next": "Next",
        "back": "Back",
        "skip": "Skip",
        "chips_prompt": "What caught your eye? (optional)",
        "brief_continue": "Finish",
        "brief_skip": "Skip these",
        "done_title": "Thank you",
        "done_body": "That's everything. We'll go through your choices before our next meeting.",
        "download": "Download my answers",
        "another": "Another person's turn",
        "remote_hint": "If you did this remotely, please download your answers and send the file to us.",
    }
}


def svg_card(img: dict, dim: dict, opt: dict, origin_label: str) -> str:
    """A labelled placeholder: origin band, dimension, option, subject, swatches."""
    w, h = 800, 600
    band = {"kerala": "#2a78d6", "hacienda": "#eb6834", "modern": "#1baf7a", "hybrid": "#eda100"}[img["origin"]]
    lines = textwrap.wrap(opt["description"], 52)
    desc = "".join(f'<tspan x="48" dy="{0 if i == 0 else 30}">{escape(l)}</tspan>' for i, l in enumerate(lines))
    sw = "".join(
        f'<rect x="{48 + i * 132}" y="440" width="116" height="72" rx="6" fill="{c["hex"]}" stroke="#0002"/>'
        f'<text x="{48 + i * 132}" y="534" font-size="15" fill="#52514e">{escape(c["name"])}</text>'
        for i, c in enumerate(img["palette"][:5]))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" font-family="system-ui, sans-serif">
<rect width="{w}" height="{h}" fill="#f3f1ec"/>
<rect width="{w}" height="10" fill="{band}"/>
<text x="48" y="64" font-size="18" fill="#52514e" letter-spacing="2">{escape(dim["name"].upper())} · {escape(origin_label.upper())}</text>
<text x="48" y="124" font-size="40" font-weight="600" fill="#1d1c1a">{escape(opt["label"])}</text>
<text x="48" y="172" font-size="22" fill="#1d1c1a">Shows: {escape(img["subject"])}</text>
<text x="48" y="226" font-size="21" fill="#3b3a37">{desc}</text>
{sw}
<text x="48" y="580" font-size="14" fill="#8a8984">PLACEHOLDER · {escape(img["id"])} · replace with a curated photo</text>
</svg>'''


def build(force: bool) -> Path:
    out = ROOT / "datasets" / PROJECT_ID
    assets = out / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    if (out / "dataset.json").exists() and not force:
        raise SystemExit(f"{out}/dataset.json exists; pass --force to overwrite (curated edits will be lost)")

    origin_labels = {o["id"]: o["label"] for o in ORIGINS}
    images, by_option = [], {}
    for dim in DIMENSIONS:
        for opt in dim["options"]:
            for n, entry in enumerate(IMAGES[dim["id"]][opt["id"]], start=1):
                subject, over = (entry if isinstance(entry, tuple) else (entry, {}))
                status, note = over.get("climate", ("ok", ""))
                img = {
                    "id": f"{dim['id']}--{opt['id']}--{n}",
                    "file": f"{dim['id']}--{opt['id']}--{n}.svg",
                    "dimension_id": dim["id"],
                    "option_id": opt["id"],
                    "origin": over.get("origin", opt["origin"]),
                    "subject": subject,
                    "materials": opt["materials"],
                    "palette": opt["palette"],
                    "scale": "single-family, 2400-4000 sq ft",
                    "climate": {"status": status, "note": note},
                    "source": "placeholder",
                    "credit": "",
                    "placeholder": True,
                }
                images.append(img)
                by_option.setdefault((dim["id"], opt["id"]), []).append(img)
                (assets / img["file"]).write_text(svg_card(img, dim, opt, origin_labels[img["origin"]]), encoding="utf-8")

    pairs = []
    for dim in DIMENSIONS:
        used: dict[str, int] = {}
        for n, spec in enumerate(PAIRS[dim["id"]], start=1):
            oa, ob = spec[0], spec[1]

            def pick(opt_id):
                pool = by_option[(dim["id"], opt_id)]
                if len(spec) == 3:
                    return pool[spec[2]]
                i = used.get(opt_id, 0)
                used[opt_id] = i + 1
                return pool[i % len(pool)]

            a, b = pick(oa), pick(ob)
            pairs.append({
                "id": f"{dim['id']}-{n:02d}",
                "dimension_id": dim["id"],
                "image_a": a["id"],
                "image_b": b["id"],
                "origin_a": a["origin"],
                "origin_b": b["origin"],
                "tags": [oa, ob],
                "note": dim["isolate_note"],
            })

    dataset = {
        "schema_version": 1,
        "project": {
            "id": PROJECT_ID,
            "name": "House in Erode",
            "subtitle": "Hacienda + Kerala, abstracted with modern influence",
            "location": "Erode, Tamil Nadu",
            "climate_note": "Inland Tamil Nadu: hot, semi-arid; long dry season, rain mostly from the northeast monsoon (Oct-Dec). Verify against IMD normals before locking the image filter.",
        },
        "branding": {"studio_name": "", "accent": "#8e3b2e"},
        "languages": ["en"],
        "copy": COPY,
        "origins": ORIGINS,
        "chips": CHIPS,
        "dimensions": DIMENSIONS,
        "brief": BRIEF,
        "tensions": TENSIONS,
        "settings": {"shuffle_pairs": True, "randomise_sides": True, "show_chips": True},
    }
    (out / "dataset.json").write_text(json.dumps(dataset, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "pairs.json").write_text(json.dumps({"pairs": pairs}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (assets / "manifest.json").write_text(json.dumps({"images": images}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out}: {len(DIMENSIONS)} dimensions, {len(pairs)} pairs, {len(images)} images")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="overwrite existing dataset JSON")
    build(ap.parse_args().force)
