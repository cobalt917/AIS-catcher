#!/usr/bin/env python3
"""
LED Matrix Display Simulator

Simulates an HUB75-style LED panel in the terminal using ANSI color output.
Useful for planning panel layout and count before ordering hardware.

Usage:
  python3 led_sim.py "NORTHBOUND  8min"
  python3 led_sim.py "LAKE FREIGHTER" --size 32x128 --color green
  python3 led_sim.py "→ SOUTHBOUND  23min" --size 32x128 --panel 32x64
  python3 led_sim.py "8min" --size 16x48 --color amber --align center
"""

import argparse
import sys

# ---------------------------------------------------------------------------
# Colors — two palettes for the two rendering modes.
#
# 24-bit (truecolor): (on_rgb, off_rgb) tuples
# 256-color:          (on_index, off_index, seam_index) from the xterm palette
#   Colors 16-231 are the 6×6×6 RGB cube: index = 16 + 36r + 6g + b (r,g,b ∈ 0-5)
#   Colors 232-255 are a grayscale ramp from #080808 to #eeeeee
# ---------------------------------------------------------------------------
COLORS_24BIT = {
    "amber":  ((255, 155,   0), ( 45,  25,   0)),
    "red":    ((255,  40,   0), ( 50,   5,   0)),
    "green":  ((  0, 220,   0), (  0,  40,   0)),
    "blue":   ((  0, 130, 255), (  0,  20,  50)),
    "white":  ((220, 220, 220), ( 30,  30,  30)),
    "yellow": ((255, 215,   0), ( 40,  35,   0)),
    "cyan":   ((  0, 210, 210), (  0,  35,  35)),
}

# 256-color palette entries:  (lit_fg, panel_bg, seam_bg)
#   214 = #ffaf00 (amber),  94 = #875f00 (dark amber),  136 = #af8700 (mid amber)
#    46 = #00ff00 (green),  22 = #005f00 (dark green),   28 = #008700 (mid green)
#   196 = #ff0000 (red),    88 = #870000 (dark red),     124 = #af0000 (mid red)
#    39 = #00afff (blue),   17 = #00005f (dark blue),     26 = #005fd7 (mid blue)
#   231 = #ffffff (white), 235 = #262626 (dark grey),    239 = #4e4e4e (mid grey)
#   226 = #ffff00 (yellow),100 = #878700 (dark yellow), 142 = #afaf00 (mid yellow)
#    51 = #00ffff (cyan),   23 = #005f5f (dark cyan),    30 = #008787 (mid cyan)
COLORS_256 = {
    "amber":  (214,  94, 136),
    "red":    (196,  88, 124),
    "green":  ( 46,  22,  28),
    "blue":   ( 39,  17,  26),
    "white":  (231, 235, 239),
    "yellow": (226, 100, 142),
    "cyan":   ( 51,  23,  30),
}

import os

def _truecolor_supported():
    """Return True if the terminal advertises 24-bit color support."""
    ct = os.environ.get("COLORTERM", "").lower()
    return ct in ("truecolor", "24bit")

# ---------------------------------------------------------------------------
# Flag color codes (stored in the pixel grid alongside the normal 0/1 values)
#   0  = off  (panel background)
#   1  = lit  (user-selected LED color, e.g. amber)
#   2+ = flag colors
# ---------------------------------------------------------------------------
FC_OFF   = 0
FC_LED   = 1
FC_RED   = 2
FC_WHITE = 3
FC_BLUE  = 4

# 24-bit (R,G,B) for each flag color code
FLAG_COLORS_24BIT = {
    FC_RED:   (205,  32,  44),
    FC_WHITE: (240, 240, 240),
    FC_BLUE:  (  0,  40, 104),
}

# 256-color terminal index for each flag color code
# 160 ≈ #d70000 (red), 231 = #ffffff (white), 19 = #0000af (blue)
FLAG_COLORS_256 = {
    FC_RED:   160,
    FC_WHITE: 231,
    FC_BLUE:   19,
}

# Short aliases used in the bitmap definitions below
_R = FC_RED
_W = FC_WHITE
_B = FC_BLUE

# ---------------------------------------------------------------------------
# Flag bitmaps — 7 rows (same height as FONT_H) × N cols
# Each cell is a flag color code; FC_OFF means show panel background.
# Add new flags here; they are referenced in text as [XX] tokens.
# ---------------------------------------------------------------------------
FLAGS = {
    # United States — 7 × 14
    # 4-col blue canton (top half) + red/white stripes across full width
    "US": [
        [_B,_B,_B,_B,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R],
        [_B,_B,_B,_B,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W],
        [_B,_B,_B,_B,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R],
        [_B,_B,_B,_B,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W],
        [_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R],
        [_W,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W],
        [_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R],
    ],
    # Canada — 7 × 14
    # 3-col red bands; centre 8 cols white with a simplified maple-leaf silhouette
    #   row 0 / row 6 : narrow tip / stem (2 red px in centre)
    #   row 1         : single-pixel upper lobes
    #   row 2 / row 4 : wider body (6 red px)
    #   row 3         : widest row — leaf blends across full width
    "CA": [
        [_R,_R,_R,_W,_W,_W,_R,_R,_W,_W,_W,_R,_R,_R],
        [_R,_R,_R,_W,_R,_W,_R,_R,_W,_R,_W,_R,_R,_R],
        [_R,_R,_R,_W,_R,_R,_R,_R,_R,_R,_W,_R,_R,_R],
        [_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R],
        [_R,_R,_R,_W,_R,_R,_R,_R,_R,_R,_W,_R,_R,_R],
        [_R,_R,_R,_W,_W,_W,_R,_R,_W,_W,_W,_R,_R,_R],
        [_R,_R,_R,_W,_W,_W,_R,_R,_W,_W,_W,_R,_R,_R],
    ],
}

# ---------------------------------------------------------------------------
# 5×7 pixel bitmap font
# Each entry: list of 7 binary strings, each 5 chars wide ('1'=lit, '0'=off)
# ---------------------------------------------------------------------------
FONT_W = 5
FONT_H = 7
CHAR_GAP = 1  # dark pixels between characters
LINE_GAP = 2  # dark pixel rows between text lines

FONT = {
    " ": ["00000","00000","00000","00000","00000","00000","00000"],
    "!": ["00100","00100","00100","00100","00100","00000","00100"],
    '"': ["01010","01010","00000","00000","00000","00000","00000"],
    "#": ["01010","01010","11111","01010","11111","01010","01010"],
    "$": ["00100","01111","10100","01110","00101","11110","00100"],
    "%": ["11000","11001","00010","00100","01000","10011","00011"],
    "&": ["01100","10010","10100","01000","10101","10010","01101"],
    "'": ["01100","00100","01000","00000","00000","00000","00000"],
    "(": ["00010","00100","01000","01000","01000","00100","00010"],
    ")": ["01000","00100","00010","00010","00010","00100","01000"],
    "*": ["00000","10101","01110","11111","01110","10101","00000"],
    "+": ["00000","00100","00100","11111","00100","00100","00000"],
    ",": ["00000","00000","00000","00000","01100","00100","01000"],
    "-": ["00000","00000","00000","11111","00000","00000","00000"],
    ".": ["00000","00000","00000","00000","00000","01100","01100"],
    "/": ["00001","00010","00010","00100","01000","01000","10000"],
    "0": ["01110","10001","10001","10001","10001","10001","01110"],
    "1": ["00100","01100","00100","00100","00100","00100","01110"],
    "2": ["01110","10001","00001","00110","01000","10000","11111"],
    "3": ["11110","00001","00001","01110","00001","00001","11110"],
    "4": ["00110","01010","10010","10010","11111","00010","00010"],
    "5": ["11111","10000","11110","00001","00001","10001","01110"],
    "6": ["01110","10000","10000","11110","10001","10001","01110"],
    "7": ["11111","00001","00010","00100","01000","01000","01000"],
    "8": ["01110","10001","10001","01110","10001","10001","01110"],
    "9": ["01110","10001","10001","01111","00001","00001","01110"],
    ":": ["00000","01100","01100","00000","01100","01100","00000"],
    ";": ["00000","01100","01100","00000","01100","00100","01000"],
    "<": ["00011","00110","01100","11000","01100","00110","00011"],
    "=": ["00000","00000","11111","00000","11111","00000","00000"],
    ">": ["11000","01100","00110","00011","00110","01100","11000"],
    "?": ["01110","10001","00001","00110","00100","00000","00100"],
    "@": ["01110","10001","00001","01101","10101","10101","01110"],
    "A": ["01110","10001","10001","11111","10001","10001","10001"],
    "B": ["11110","10001","10001","11110","10001","10001","11110"],
    "C": ["01110","10001","10000","10000","10000","10001","01110"],
    "D": ["11100","10010","10001","10001","10001","10010","11100"],
    "E": ["11111","10000","10000","11110","10000","10000","11111"],
    "F": ["11111","10000","10000","11110","10000","10000","10000"],
    "G": ["01110","10001","10000","10111","10001","10001","01111"],
    "H": ["10001","10001","10001","11111","10001","10001","10001"],
    "I": ["01110","00100","00100","00100","00100","00100","01110"],
    "J": ["00111","00010","00010","00010","00010","10010","01100"],
    "K": ["10001","10010","10100","11000","10100","10010","10001"],
    "L": ["10000","10000","10000","10000","10000","10000","11111"],
    "M": ["10001","11011","10101","10001","10001","10001","10001"],
    "N": ["10001","11001","10101","10011","10001","10001","10001"],
    "O": ["01110","10001","10001","10001","10001","10001","01110"],
    "P": ["11110","10001","10001","11110","10000","10000","10000"],
    "Q": ["01110","10001","10001","10001","10101","10010","01101"],
    "R": ["11110","10001","10001","11110","10100","10010","10001"],
    "S": ["01111","10000","10000","01110","00001","00001","11110"],
    "T": ["11111","00100","00100","00100","00100","00100","00100"],
    "U": ["10001","10001","10001","10001","10001","10001","01110"],
    "V": ["10001","10001","10001","10001","10001","01010","00100"],
    "W": ["10001","10001","10001","10101","10101","11011","10001"],
    "X": ["10001","10001","01010","00100","01010","10001","10001"],
    "Y": ["10001","10001","01010","00100","00100","00100","00100"],
    "Z": ["11111","00001","00010","00100","01000","10000","11111"],
    "[": ["01110","01000","01000","01000","01000","01000","01110"],
    "\\":["10000","01000","01000","00100","00010","00010","00001"],
    "]": ["01110","00010","00010","00010","00010","00010","01110"],
    "^": ["00100","01010","10001","00000","00000","00000","00000"],
    "_": ["00000","00000","00000","00000","00000","00000","11111"],
    "a": ["00000","00000","01110","00001","01111","10001","01111"],
    "b": ["10000","10000","11110","10001","10001","10001","11110"],
    "c": ["00000","00000","01110","10000","10000","10001","01110"],
    "d": ["00001","00001","01111","10001","10001","10001","01111"],
    "e": ["00000","00000","01110","10001","11111","10000","01110"],
    "f": ["00110","01001","01000","11100","01000","01000","01000"],
    "g": ["00000","01111","10001","10001","01111","00001","01110"],
    "h": ["10000","10000","11110","10001","10001","10001","10001"],
    "i": ["00100","00000","01100","00100","00100","00100","01110"],
    "j": ["00010","00000","00110","00010","00010","10010","01100"],
    "k": ["10000","10010","10100","11000","10100","10010","10001"],
    "l": ["01100","00100","00100","00100","00100","00100","01110"],
    "m": ["00000","00000","11010","10101","10101","10001","10001"],
    "n": ["00000","00000","11110","10001","10001","10001","10001"],
    "o": ["00000","00000","01110","10001","10001","10001","01110"],
    "p": ["00000","00000","11110","10001","10001","11110","10000"],
    "q": ["00000","00000","01111","10001","10001","01111","00001"],
    "r": ["00000","00000","10110","11001","10000","10000","10000"],
    "s": ["00000","00000","01111","10000","01110","00001","11110"],
    "t": ["01000","01000","11110","01000","01000","01001","00110"],
    "u": ["00000","00000","10001","10001","10001","10011","01101"],
    "v": ["00000","00000","10001","10001","10001","01010","00100"],
    "w": ["00000","00000","10001","10001","10101","10101","01010"],
    "x": ["00000","00000","10001","01010","00100","01010","10001"],
    "y": ["00000","00000","10001","10001","01111","00001","01110"],
    "z": ["00000","00000","11111","00010","00100","01000","11111"],
    # Arrows and special symbols
    "→": ["00000","00100","00010","11111","00010","00100","00000"],
    "←": ["00000","00100","01000","11111","01000","00100","00000"],
    "↑": ["00100","01110","10101","00100","00100","00100","00100"],
    "↓": ["00100","00100","00100","00100","10101","01110","00100"],
    "°": ["01100","10010","10010","01100","00000","00000","00000"],
    "★": ["00100","11111","01110","11111","01010","10001","00000"],
    "▶": ["10000","11000","11100","11110","11100","11000","10000"],
    "◀": ["00001","00011","00111","01111","00111","00011","00001"],
}

# Fallback for unknown characters: small rectangle
UNKNOWN_CHAR = ["11111","10001","10001","10001","10001","10001","11111"]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def char_pixels(ch):
    """Return 7×5 pixel rows for a character, falling back to a box glyph."""
    return FONT.get(ch, UNKNOWN_CHAR)


def tokenize(text):
    """Split text into a list of tokens — single characters or '[XX]' flag codes."""
    tokens = []
    i = 0
    while i < len(text):
        if text[i] == '[':
            j = text.find(']', i + 1)
            if j != -1:
                key = text[i+1:j].upper()
                if key in FLAGS:
                    tokens.append('[' + key + ']')
                    i = j + 1
                    continue
        tokens.append(text[i])
        i += 1
    return tokens


def token_width(tok):
    """Pixel width of a single token (not including the trailing inter-token gap)."""
    if tok.startswith('[') and tok.endswith(']'):
        key = tok[1:-1]
        if key in FLAGS:
            return len(FLAGS[key][0])
    return FONT_W


def render_text(text, width, height, align="left", margin=1):
    """
    Render text into a (height × width) pixel grid.
    Returns a 2D list: grid[row][col] holds a color code:
      FC_OFF (0) = panel background
      FC_LED (1) = user-selected LED color (amber / red / green …)
      FC_RED/WHITE/BLUE (2-4) = flag pixel colors

    Supports multiple lines separated by real newlines or the literal sequence \\n.
    Flag tokens like [US] and [CA] are expanded to tiny flag bitmaps inline.
    """
    text = text.replace("\\n", "\n")
    lines = text.split("\n")

    grid = [[FC_OFF] * width for _ in range(height)]

    n = len(lines)
    block_h = n * FONT_H + (n - 1) * LINE_GAP
    y_start = max(0, (height - block_h) // 2)

    for li, line in enumerate(lines):
        tokens = tokenize(line)
        if not tokens:
            continue

        line_px = sum(token_width(t) for t in tokens) + CHAR_GAP * (len(tokens) - 1)

        if align == "center":
            x0 = (width - line_px) // 2
        elif align == "right":
            x0 = width - line_px - margin
        else:
            x0 = margin

        y0 = y_start + li * (FONT_H + LINE_GAP)
        x = x0

        for tok in tokens:
            if tok.startswith('[') and tok.endswith(']'):
                # Flag token — blit the color bitmap into the grid
                bitmap = FLAGS[tok[1:-1]]
                for ri, row in enumerate(bitmap):
                    y = y0 + ri
                    if y >= height:
                        break
                    for ci, code in enumerate(row):
                        px = x + ci
                        if 0 <= px < width and code != FC_OFF:
                            grid[y][px] = code
                x += len(bitmap[0]) + CHAR_GAP
            else:
                # Regular character
                for ri, row in enumerate(char_pixels(tok)):
                    y = y0 + ri
                    if y >= height:
                        break
                    for ci, bit in enumerate(row):
                        px = x + ci
                        if 0 <= px < width and bit == "1":
                            grid[y][px] = FC_LED
                x += FONT_W + CHAR_GAP

    return grid


RESET = "\033[0m"


def grid_to_terminal(grid, color_name, panel_w=None, force_truecolor=False):
    """
    Render the pixel grid as colored terminal output.

    Unlit pixels (FC_OFF) show a dark panel surface; LED pixels (FC_LED) use
    the user-selected color; flag pixels (FC_RED/WHITE/BLUE) use their real
    colors as solid ██ blocks.  Seam lines are drawn at panel boundaries.
    Automatically selects 24-bit or 256-color codes based on terminal capability.
    """
    use_24bit = force_truecolor or _truecolor_supported()

    if use_24bit:
        on_rgb, off_rgb = COLORS_24BIT.get(color_name, COLORS_24BIT["amber"])
        or_, og, ob = on_rgb
        dr, dg, db = off_rgb
        sr = min(255, dr * 5)
        sg = min(255, dg * 5)
        sb = min(255, db * 5)

        # Build a lookup: color_code -> ANSI escape string
        color_str = {
            FC_OFF: f"\033[48;2;{dr};{dg};{db}m  ",
            FC_LED: f"\033[38;2;{or_};{og};{ob}m\033[48;2;{dr};{dg};{db}m██",
        }
        for code, (fr, fg, fb) in FLAG_COLORS_24BIT.items():
            color_str[code] = f"\033[38;2;{fr};{fg};{fb}m\033[48;2;{fr};{fg};{fb}m██"
        seam_str = f"\033[48;2;{sr};{sg};{sb}m  "
    else:
        lit_i, dark_i, seam_i = COLORS_256.get(color_name, COLORS_256["amber"])

        color_str = {
            FC_OFF: f"\033[48;5;{dark_i}m  ",
            FC_LED: f"\033[38;5;{lit_i}m\033[48;5;{dark_i}m██",
        }
        for code, idx in FLAG_COLORS_256.items():
            color_str[code] = f"\033[38;5;{idx}m\033[48;5;{idx}m██"
        seam_str = f"\033[48;5;{seam_i}m  "

    lines = []
    for row in grid:
        line = ""
        for ci, px in enumerate(row):
            if panel_w and ci > 0 and ci % panel_w == 0:
                line += RESET + seam_str
                continue                          # don't also draw the pixel here
            line += color_str.get(px, color_str[FC_LED])
        line += RESET
        lines.append(line)

    return "\n".join(lines)


def panel_summary(height, width, panel_h, panel_w):
    """Return a human-readable panel count description."""
    cols = (width  + panel_w - 1) // panel_w
    rows = (height + panel_h - 1) // panel_h
    total = cols * rows
    return f"{rows}×{cols} panels ({total} total, each {panel_h}×{panel_w}px)"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_size(s, name="size"):
    try:
        h, w = s.lower().split("x")
        return int(h), int(w)
    except (ValueError, AttributeError):
        print(f"Error: invalid {name} '{s}' — use HxW format, e.g. 32x128", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Simulate an HUB75 LED matrix panel in the terminal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  %(prog)s "NORTHBOUND  8min"
  %(prog)s "LAKE FREIGHTER" --size 32x128 --color green
  %(prog)s "→ SOUTHBOUND  23min" --size 32x128 --panel 32x64
  %(prog)s "8min" --size 16x48 --align center
  %(prog)s "MV ONTARIO" --size 32x192 --panel 32x64 --color amber
  %(prog)s "8min" --size 32x48 --align center --color red
  %(prog)s "[US] NORTHBOUND 8min" --size 32x192 --panel 32x64
  %(prog)s "[CA] ALGOMA SPIRIT\n12min" --size 32x128 --panel 32x64

special characters you can paste into text:
  arrows  → ← ↑ ↓   triangles ▶ ◀   degree °   star ★
  flags   [US]  [CA]  (use brackets around the two-letter country code)
""",
    )
    parser.add_argument("text", help="text to display on the panel")
    parser.add_argument(
        "--size", default="32x128",
        help="total display size as HxW pixels (default: 32x128)",
    )
    parser.add_argument(
        "--color", default="amber", choices=sorted(COLORS_256),
        help="LED color (default: amber)",
    )
    parser.add_argument(
        "--align", default="left", choices=["left", "center", "right"],
        help="text alignment (default: left)",
    )
    parser.add_argument(
        "--margin", type=int, default=1,
        help="left/right margin in pixels (default: 1)",
    )
    parser.add_argument(
        "--panel", default=None, metavar="HxW",
        help="individual panel size, e.g. 32x64 — draws seam lines and reports panel count",
    )
    parser.add_argument(
        "--truecolor", action="store_true",
        help="force 24-bit color output (use if COLORTERM=truecolor is set in your terminal)",
    )
    args = parser.parse_args()

    height, width = parse_size(args.size)
    panel_h, panel_w = parse_size(args.panel) if args.panel else (height, width)

    grid = render_text(args.text, width, height, align=args.align, margin=args.margin)
    output = grid_to_terminal(
        grid, args.color,
        panel_w=(panel_w if args.panel else None),
        force_truecolor=args.truecolor,
    )

    # Header
    clipped = ""
    norm_text = args.text.replace("\\n", "\n")
    max_line_px = 0
    for line in norm_text.split("\n"):
        toks = tokenize(line)
        if toks:
            lw = sum(token_width(t) for t in toks) + CHAR_GAP * (len(toks) - 1)
            max_line_px = max(max_line_px, lw)
    if max_line_px > width - args.margin * 2:
        clipped = f"  ⚠ widest line ({max_line_px}px) wider than display ({width - args.margin*2}px usable) — clipped"

    print()
    print(f"  Display: {height}×{width}px  |  Color: {args.color}  |  Align: {args.align}")
    if args.panel:
        print(f"  Panels:  {panel_summary(height, width, panel_h, panel_w)}")
    if clipped:
        print(f" {clipped}")
    print()
    print(output)
    print()


if __name__ == "__main__":
    main()
