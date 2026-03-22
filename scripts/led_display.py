#!/usr/bin/env python3
"""
LED Display Driver — Ship Tracker

Drives two 32×64 HUB75 LED panels (32×128 px total) showing approaching ships.
Each row shows direction arrow, ETA, and ship name (scrolls if wider than panel).

Run on the Raspberry Pi:
  python3 led_display.py
  python3 led_display.py --server http://elberta:8080

Test in the terminal (use a wide window — 128 px = 256 terminal chars):
  python3 led_display.py --sim
  python3 led_display.py --sim --server http://elberta:8080
  python3 led_display.py --sim --sample          # use hardcoded prototype data
  python3 led_display.py --sim --color green
  python3 led_display.py --sim --scroll-speed 2 --page-time 4

If the rgbmatrix library is not installed, --sim is enabled automatically.
Live data is fetched from the AIS-catcher web API (/api/ships.json) and ETA/CPA
is computed locally using the same vector math as the C++ ETACalculator.
"""

import argparse
import json
import math
import os
import sys
import threading
import time
import urllib.request

# ---------------------------------------------------------------------------
# Display geometry
# ---------------------------------------------------------------------------
DISPLAY_ROWS   = 32
DISPLAY_COLS   = 128
FONT_H         = 7
FONT_W         = 5
CHAR_GAP       = 1
LINE_GAP       = 2
ROW_H          = FONT_H + LINE_GAP    # 9 px per ship-row slot

ROWS_PER_FRAME = 3   # ship rows visible at once on the 32-px panel

# Vertically centre the 3-row block inside the panel
_BLOCK_H  = ROWS_PER_FRAME * FONT_H + (ROWS_PER_FRAME - 1) * LINE_GAP  # 25 px
Y_START   = (DISPLAY_ROWS - _BLOCK_H) // 2                              # 3 px

# Horizontal split: fixed prefix (text + flag) | scrolling name
# "▶  20m" = 6 chars = 35 px, then 1 px gap, then 14 px flag, then 1 px gap = 51 px total
_PREFIX_TEXT_W = 35
_FLAG_W        = 14
FLAG_X    = _PREFIX_TEXT_W + 1        # 36 — column where the flag bitmap starts
PREFIX_W  = FLAG_X + _FLAG_W + 1      # 51 — first column of the scrolling name zone
NAME_W    = DISPLAY_COLS - PREFIX_W   # 77 px for ship name only
SCROLL_GAP = 16                       # dark px gap before a name repeats

# ---------------------------------------------------------------------------
# Color codes  (same scheme as led_sim.py)
# ---------------------------------------------------------------------------
FC_OFF   = 0
FC_LED   = 1
FC_RED   = 2
FC_WHITE = 3
FC_BLUE  = 4

FLAG_RGB = {
    FC_RED:   (205,  32,  44),
    FC_WHITE: (240, 240, 240),
    FC_BLUE:  (  0,  40, 104),
}

LED_COLORS = {
    "amber":  (255, 140,   0),
    "red":    (220,  30,   0),
    "green":  (  0, 200,   0),
    "blue":   (  0, 120, 255),
    "white":  (220, 220, 220),
    "yellow": (255, 210,   0),
    "cyan":   (  0, 200, 200),
}

# 256-color fallback indices: (lit, dark)
LED_COLORS_256 = {
    "amber":  (214,  94),
    "red":    (196,  88),
    "green":  ( 46,  22),
    "blue":   ( 39,  17),
    "white":  (231, 235),
    "yellow": (226, 100),
    "cyan":   ( 51,  23),
}

FLAG_COLORS_256 = {FC_RED: 160, FC_WHITE: 231, FC_BLUE: 19}

RESET = "\033[0m"

# ---------------------------------------------------------------------------
# 5×7 pixel font  (copied from led_sim.py)
# ---------------------------------------------------------------------------
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
    "→": ["00000","00100","00010","11111","00010","00100","00000"],
    "←": ["00000","00100","01000","11111","01000","00100","00000"],
    "↑": ["00100","01110","10101","00100","00100","00100","00100"],
    "↓": ["00100","00100","00100","00100","10101","01110","00100"],
    "°": ["01100","10010","10010","01100","00000","00000","00000"],
    "★": ["00100","11111","01110","11111","01010","10001","00000"],
    "▶": ["10000","11000","11100","11110","11100","11000","10000"],
    "◀": ["00001","00011","00111","01111","00111","00011","00001"],
}

UNKNOWN_CHAR = ["11111","10001","10001","10001","10001","10001","11111"]

# ---------------------------------------------------------------------------
# Flag bitmaps  (copied from led_sim.py)
# ---------------------------------------------------------------------------
_R = FC_RED
_W = FC_WHITE
_B = FC_BLUE

FLAGS = {
    "US": [
        [_B,_B,_B,_B,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R],
        [_B,_B,_B,_B,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W],
        [_B,_B,_B,_B,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R],
        [_B,_B,_B,_B,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W],
        [_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R],
        [_W,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W],
        [_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R],
    ],
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
# Prototype / sample ship data
# ---------------------------------------------------------------------------
SAMPLE_SHIPS = [
    {"direction": "UP",   "eta_min":  4, "flag": "CA", "name": "ALGONOVA"},
    {"direction": "UP",   "eta_min": 11, "flag": "US", "name": "WHITEFISH BAY"},
    {"direction": "DOWN", "eta_min": 22, "flag": "CA", "name": "ALGOMA MARINER"},
    {"direction": "UP",   "eta_min": 38, "flag": "CA", "name": "EDWIN H TUTTLE"},
    {"direction": "DOWN", "eta_min": 45, "flag": "US", "name": "AMERICAN SPIRIT"},
    {"direction": "UP",   "eta_min": 67, "flag": "CA", "name": "ALGOMA TRANSPORT"},
]

# ---------------------------------------------------------------------------
# Live data — ETA/CPA computation and background fetch
# ---------------------------------------------------------------------------

# Observer defaults (Detroit River, ~42.37 N / -82.92 W)
DEFAULT_SERVER        = "http://elberta:8080"
DEFAULT_STATION_LAT   = 42.372498
DEFAULT_STATION_LON   = -82.918296
DEFAULT_CPA_NM        = 2.0    # nautical mile threshold
DEFAULT_FETCH_INTERVAL = 30    # seconds between server polls
DEFAULT_MAX_AGE_SEC   = 300    # exclude ships last seen more than this many seconds ago


def _cpa_direction(cog_deg):
    """UP (northerly COG) or DOWN (southerly COG). cos(COG)>=0 → north."""
    return "UP" if math.cos(math.radians(cog_deg)) >= 0 else "DOWN"


def _compute_eta(ship_json, station_lat, station_lon, cpa_threshold_nm):
    """
    Compute ETA dict for one ship, or None if it should be excluded.
    Uses the same CPA vector math as ETACalculator.cpp.
    """
    try:
        lat   = ship_json.get("lat")
        lon   = ship_json.get("lon")
        speed = ship_json.get("speed")
        cog   = ship_json.get("cog")

        if lat is None or lon is None:
            return None

        # Local NM offsets (ship relative to station)
        dlat = (lat - station_lat) * 60.0
        dlon = (lon - station_lon) * 60.0 * math.cos(math.radians(station_lat))

        if speed is None or speed <= 0 or cog is None or cog >= 360:
            return None  # stationary / no course data

        # Velocity vector (knots = NM/hour)
        vx = speed * math.sin(math.radians(cog))   # east component
        vy = speed * math.cos(math.radians(cog))   # north component

        v_sq = vx * vx + vy * vy
        if v_sq < 1e-4:
            return None

        # Time to CPA (hours): t = -(P·V) / |V|²
        tcpa_h = -(dlon * vx + dlat * vy) / v_sq
        if tcpa_h <= 0:
            return None  # moving away

        # CPA distance
        cpa_x = dlon + vx * tcpa_h
        cpa_y = dlat + vy * tcpa_h
        cpa_nm = math.sqrt(cpa_x * cpa_x + cpa_y * cpa_y)

        if cpa_nm > cpa_threshold_nm:
            return None  # won't come close enough

        eta_min   = tcpa_h * 60.0
        direction = _cpa_direction(cog)
        raw_name  = (ship_json.get("shipname") or "").strip()
        name      = raw_name if raw_name else f"MMSI {ship_json.get('mmsi', '?')}"
        country   = (ship_json.get("country") or "").strip().upper()
        flag      = country if country in FLAGS else ""

        return {
            "direction": direction,
            "eta_min":   round(eta_min),
            "flag":      flag,
            "name":      name,
            "_eta_f":    eta_min,   # float for sorting
        }
    except Exception:
        return None


def fetch_ships(server_url, station_lat, station_lon, cpa_nm, max_age_sec):
    """
    Fetch /api/ships.json from the AIS-catcher server, compute CPA/ETA for each
    ship, filter to approaching ships within cpa_nm, sort by ETA ascending.
    Returns a list of ship dicts, or None on network/parse error.
    """
    try:
        url = server_url.rstrip("/") + "/api/ships.json"
        req = urllib.request.urlopen(url, timeout=10)
        data = json.loads(req.read().decode())
    except Exception:
        return None

    results = []
    for ship in data.get("ships", []):
        if (ship.get("last_signal") or 9999) > max_age_sec:
            continue
        entry = _compute_eta(ship, station_lat, station_lon, cpa_nm)
        if entry is not None:
            results.append(entry)

    results.sort(key=lambda s: s["_eta_f"])
    return results


class ShipFetcher:
    """Background thread that polls the AIS-catcher server periodically."""

    def __init__(self, server_url, station_lat, station_lon, cpa_nm,
                 fetch_interval, max_age_sec):
        self._url          = server_url
        self._lat          = station_lat
        self._lon          = station_lon
        self._cpa          = cpa_nm
        self._interval     = fetch_interval
        self._max_age      = max_age_sec
        self._ships        = []
        self._fetch_failed = False   # True if the most recent fetch failed
        self._lock         = threading.Lock()
        self._stop         = threading.Event()
        self._ok           = False   # True after at least one successful fetch

    def start(self):
        """Initial blocking fetch, then kick off background thread."""
        self._do_fetch()
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def _do_fetch(self):
        result = fetch_ships(self._url, self._lat, self._lon, self._cpa, self._max_age)
        with self._lock:
            if result is not None:
                self._ships        = result
                self._fetch_failed = False
                self._ok           = True
            else:
                self._fetch_failed = True

    def _run(self):
        while not self._stop.wait(self._interval):
            self._do_fetch()

    def get_status(self):
        """Return (ships, fetch_failed) atomically."""
        with self._lock:
            return list(self._ships), self._fetch_failed

    def stop(self):
        self._stop.set()

# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def tokenize(text):
    """Split text into single characters and [FLAG] tokens."""
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


def _token_width(tok):
    if tok.startswith('[') and tok.endswith(']'):
        return len(FLAGS[tok[1:-1]][0])
    return FONT_W


def render_strip(text):
    """
    Render text into a pixel strip.
    Returns a 2D list: strip[row][col] = FC_* color code.
    Height is always FONT_H; width depends on content.
    """
    tokens = tokenize(text)
    if not tokens:
        return [[FC_OFF]]

    widths = [_token_width(t) for t in tokens]
    total_w = sum(widths) + CHAR_GAP * (len(tokens) - 1)
    grid = [[FC_OFF] * total_w for _ in range(FONT_H)]

    x = 0
    for tok, w in zip(tokens, widths):
        if tok.startswith('[') and tok.endswith(']'):
            bitmap = FLAGS[tok[1:-1]]
            for ri, row in enumerate(bitmap):
                for ci, code in enumerate(row):
                    if code != FC_OFF:
                        grid[ri][x + ci] = code
        else:
            rows = FONT.get(tok, UNKNOWN_CHAR)
            for ri, row_str in enumerate(rows):
                for ci, bit in enumerate(row_str):
                    if bit == '1':
                        grid[ri][x + ci] = FC_LED
        x += w + CHAR_GAP

    return grid


# Cache rendered name strips — they don't change during a session
_strip_cache = {}

def get_name_strip(name):
    if name not in _strip_cache:
        _strip_cache[name] = render_strip(name)
    return _strip_cache[name]


def render_frame(ships, v_offset, h_offsets):
    """
    Build a complete display frame as FC_* color codes.
    Returns frame[y][x] — size DISPLAY_ROWS × DISPLAY_COLS.

    ships     — list of ship dicts
    v_offset  — index of first visible ship (vertical cycling)
    h_offsets — dict of ship_idx → horizontal scroll offset in pixels
    """
    frame = [[FC_OFF] * DISPLAY_COLS for _ in range(DISPLAY_ROWS)]
    n = len(ships)
    if not n:
        return frame

    for dr in range(ROWS_PER_FRAME):
        ship_idx = (v_offset + dr) % n
        ship = ships[ship_idx]
        y_top = Y_START + dr * ROW_H

        if y_top + FONT_H > DISPLAY_ROWS:
            break

        # -- Fixed prefix: direction arrow + right-justified ETA --
        dir_char = "◀" if ship["direction"] == "UP" else "▶"
        prefix_strip = render_strip(f"{dir_char} {ship['eta_min']:3d}m")
        for ri in range(FONT_H):
            for ci, code in enumerate(prefix_strip[ri]):
                if ci < FLAG_X:
                    frame[y_top + ri][ci] = code

        # -- Fixed flag bitmap --
        flag_key = ship.get("flag")
        if flag_key and flag_key in FLAGS:
            for ri, row in enumerate(FLAGS[flag_key]):
                for ci, code in enumerate(row):
                    if code != FC_OFF:
                        frame[y_top + ri][FLAG_X + ci] = code

        # -- Scrolling name only --
        name_strip = get_name_strip(ship["name"])
        strip_w = len(name_strip[0])

        if strip_w <= NAME_W:
            # Name fits — blit once, rest stays FC_OFF
            for ri in range(FONT_H):
                for ci in range(strip_w):
                    frame[y_top + ri][PREFIX_W + ci] = name_strip[ri][ci]
        else:
            # Name is wider than the zone — scroll with wrap
            h_off = h_offsets.get(ship_idx, 0)
            cycle = strip_w + SCROLL_GAP
            for px in range(NAME_W):
                src_x = (h_off + px) % cycle
                for ri in range(FONT_H):
                    code = name_strip[ri][src_x] if src_x < strip_w else FC_OFF
                    frame[y_top + ri][PREFIX_W + px] = code

    return frame


def advance_scrolls(ships, h_offsets, scroll_speed):
    """Advance horizontal scroll offsets for ships whose names are wider than NAME_W."""
    for i, ship in enumerate(ships):
        strip_w = len(get_name_strip(ship["name"])[0])
        if strip_w > NAME_W:
            h_offsets[i] = (h_offsets[i] + scroll_speed) % (strip_w + SCROLL_GAP)


def render_status_frame(text):
    """
    Render a single line of text centered on the display.
    Used for 'No incoming ships' and server error states.
    """
    frame = [[FC_OFF] * DISPLAY_COLS for _ in range(DISPLAY_ROWS)]
    strip = render_strip(text)
    strip_w = len(strip[0])
    x0 = max(0, (DISPLAY_COLS - strip_w) // 2)
    y0 = (DISPLAY_ROWS - FONT_H) // 2
    for ri in range(FONT_H):
        for ci in range(min(strip_w, DISPLAY_COLS - x0)):
            frame[y0 + ri][x0 + ci] = strip[ri][ci]
    return frame


# ---------------------------------------------------------------------------
# LED matrix output
# ---------------------------------------------------------------------------

def create_matrix():
    from rgbmatrix import RGBMatrix, RGBMatrixOptions  # type: ignore
    opts = RGBMatrixOptions()
    opts.rows = DISPLAY_ROWS
    opts.cols = 64
    opts.chain_length = 2
    opts.parallel = 1
    opts.hardware_mapping = "regular-pi1"
#    opts.slowdown_gpio = 2
    opts.brightness = 80
    return RGBMatrix(options=opts)


def write_frame_to_canvas(canvas, frame, led_rgb):
    lr, lg, lb = led_rgb
    for y, row in enumerate(frame):
        for x, code in enumerate(row):
            if code == FC_OFF:
                canvas.SetPixel(x, y, 0, 0, 0)
            elif code == FC_LED:
                canvas.SetPixel(x, y, lr, lg, lb)
            else:
                r, g, b = FLAG_RGB.get(code, led_rgb)
                canvas.SetPixel(x, y, r, g, b)


# ---------------------------------------------------------------------------
# Terminal simulation
# ---------------------------------------------------------------------------

def _truecolor_supported():
    ct = os.environ.get("COLORTERM", "").lower()
    return ct in ("truecolor", "24bit")


def frame_to_terminal(frame, color_name, force_truecolor=False):
    """Render a FC_* frame as an ANSI terminal string (DISPLAY_ROWS lines)."""
    use_24bit = force_truecolor or _truecolor_supported()

    if use_24bit:
        lr, lg, lb = LED_COLORS.get(color_name, LED_COLORS["amber"])
        cell = {
            FC_OFF: "\033[48;2;8;8;8m  ",
            FC_LED: f"\033[38;2;{lr};{lg};{lb}m\033[48;2;8;8;8m\u2588\u2588",
        }
        for code, (fr, fg, fb) in FLAG_RGB.items():
            cell[code] = f"\033[38;2;{fr};{fg};{fb}m\033[48;2;{fr};{fg};{fb}m\u2588\u2588"
    else:
        lit_i, dark_i = LED_COLORS_256.get(color_name, LED_COLORS_256["amber"])
        cell = {
            FC_OFF: f"\033[48;5;{dark_i}m  ",
            FC_LED: f"\033[38;5;{lit_i}m\033[48;5;{dark_i}m\u2588\u2588",
        }
        for code, idx in FLAG_COLORS_256.items():
            cell[code] = f"\033[38;5;{idx}m\033[48;5;{idx}m\u2588\u2588"

    lines = []
    for row in frame:
        line = "".join(cell.get(code, cell[FC_LED]) for code in row) + RESET
        lines.append(line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Animation loop
# ---------------------------------------------------------------------------

def run(ships, color, scroll_speed, page_time, tick_ms, use_sim, truecolor,
        fetcher=None):
    """
    Animation loop.

    ships   — initial ship list (used as-is when fetcher is None / --sample)
    fetcher — ShipFetcher instance; if set, ships are refreshed at each page turn
    """
    led_rgb   = LED_COLORS.get(color, LED_COLORS["amber"])
    h_offsets = {i: 0 for i in range(len(ships))}
    v_offset  = 0
    last_page = time.time()
    data_src  = "sample" if fetcher is None else "live"

    # fetch_failed is always False in --sample mode
    fetch_failed = False

    def _refresh(current_ships, current_failed):
        """Pull fresh state from fetcher; reset scroll state when ship list changes."""
        nonlocal h_offsets, v_offset
        if fetcher is None:
            return current_ships, False
        new_ships, new_failed = fetcher.get_status()
        if [s["name"] for s in new_ships] != [s["name"] for s in current_ships]:
            h_offsets = {i: 0 for i in range(len(new_ships))}
            v_offset  = 0
        return new_ships, new_failed

    def _build_frame(current_ships, current_failed):
        """Return the appropriate frame for the current display state."""
        if current_failed:
            return render_status_frame("Server error")
        if not current_ships:
            return render_status_frame("No incoming ships")
        return render_frame(current_ships, v_offset, h_offsets)

    if use_sim:
        for s in ships:
            get_name_strip(s["name"])

        print("\033[?25l", end="", flush=True)  # hide cursor
        n = len(ships)
        print(f"  {n} ships [{data_src}] | ◀=UP  ▶=DOWN | "
              f"display: {DISPLAY_ROWS}×{DISPLAY_COLS}px "
              f"(terminal width needed: {DISPLAY_COLS * 2} chars) | Ctrl+C to exit")
        first = True
        try:
            while True:
                frame  = _build_frame(ships, fetch_failed)
                output = frame_to_terminal(frame, color, force_truecolor=truecolor)

                if first:
                    print(output, flush=True)
                    first = False
                else:
                    print(f"\033[{DISPLAY_ROWS}A" + output, flush=True)

                advance_scrolls(ships, h_offsets, scroll_speed)

                now = time.time()
                if now - last_page >= page_time:
                    ships, fetch_failed = _refresh(ships, fetch_failed)
                    n = len(ships)
                    v_offset = (v_offset + 1) % max(1, n)
                    last_page = now

                time.sleep(tick_ms / 1000)

        except KeyboardInterrupt:
            pass
        finally:
            print(f"\033[?25h{RESET}")  # restore cursor

    else:
        matrix = create_matrix()
        canvas = matrix.CreateFrameCanvas()
        try:
            while True:
                frame = _build_frame(ships, fetch_failed)
                canvas.Clear()
                write_frame_to_canvas(canvas, frame, led_rgb)
                canvas = matrix.SwapOnVSync(canvas)

                advance_scrolls(ships, h_offsets, scroll_speed)

                now = time.time()
                if now - last_page >= page_time:
                    ships, fetch_failed = _refresh(ships, fetch_failed)
                    v_offset = (v_offset + 1) % max(1, len(ships))
                    last_page = now

                time.sleep(tick_ms / 1000)

        except KeyboardInterrupt:
            pass


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="LED display driver for ship tracker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  %(prog)s --sim                                  terminal preview, live data from default server
  %(prog)s --sim --server http://elberta:8080     explicit server URL
  %(prog)s --sim --sample                         use hardcoded prototype data
  %(prog)s --sim --color green                    different LED color
  %(prog)s --sim --cpa 5.0                        wider CPA filter (5 NM)
  %(prog)s                                        real LED matrix (Pi only)
""",
    )
    parser.add_argument(
        "--sim", action="store_true",
        help="render to terminal instead of real LED matrix",
    )
    parser.add_argument(
        "--sample", action="store_true",
        help="use hardcoded SAMPLE_SHIPS instead of fetching live data",
    )
    parser.add_argument(
        "--server", default=DEFAULT_SERVER, metavar="URL",
        help=f"AIS-catcher server URL (default: {DEFAULT_SERVER})",
    )
    parser.add_argument(
        "--lat", type=float, default=DEFAULT_STATION_LAT, metavar="DEG",
        help=f"observer latitude in decimal degrees (default: {DEFAULT_STATION_LAT})",
    )
    parser.add_argument(
        "--lon", type=float, default=DEFAULT_STATION_LON, metavar="DEG",
        help=f"observer longitude in decimal degrees (default: {DEFAULT_STATION_LON})",
    )
    parser.add_argument(
        "--cpa", type=float, default=DEFAULT_CPA_NM, metavar="NM",
        help=f"CPA threshold in nautical miles (default: {DEFAULT_CPA_NM})",
    )
    parser.add_argument(
        "--fetch-interval", type=int, default=DEFAULT_FETCH_INTERVAL, metavar="SEC",
        help=f"seconds between server polls (default: {DEFAULT_FETCH_INTERVAL})",
    )
    parser.add_argument(
        "--max-age", type=int, default=DEFAULT_MAX_AGE_SEC, metavar="SEC",
        help=f"exclude ships last heard more than this many seconds ago (default: {DEFAULT_MAX_AGE_SEC})",
    )
    parser.add_argument(
        "--color", default="amber", choices=sorted(LED_COLORS),
        help="LED color (default: amber)",
    )
    parser.add_argument(
        "--scroll-speed", type=int, default=1, metavar="PX",
        help="pixels to advance per tick for scrolling names (default: 1)",
    )
    parser.add_argument(
        "--page-time", type=float, default=5.0, metavar="SEC",
        help="seconds between vertical ship rotation (default: 5.0)",
    )
    parser.add_argument(
        "--tick-ms", type=int, default=50, metavar="MS",
        help="milliseconds per animation tick, ~= 1000/fps (default: 50)",
    )
    parser.add_argument(
        "--truecolor", action="store_true",
        help="force 24-bit ANSI color in --sim mode",
    )
    args = parser.parse_args()

    use_sim = args.sim
    if not use_sim:
        try:
            import rgbmatrix  # noqa: F401
        except ImportError:
            print("rgbmatrix not available — switching to --sim mode", file=sys.stderr)
            use_sim = True

    if args.sample:
        fetcher       = None
        initial_ships = SAMPLE_SHIPS
    else:
        print(f"Connecting to {args.server} …", file=sys.stderr)
        fetcher = ShipFetcher(
            server_url     = args.server,
            station_lat    = args.lat,
            station_lon    = args.lon,
            cpa_nm         = args.cpa,
            fetch_interval = args.fetch_interval,
            max_age_sec    = args.max_age,
        )
        fetcher.start()
        initial_ships, _ = fetcher.get_status()
        if not fetcher._ok:
            print(f"Warning: could not reach {args.server} — display will be blank until data arrives",
                  file=sys.stderr)

    run(
        initial_ships,
        args.color,
        args.scroll_speed,
        args.page_time,
        args.tick_ms,
        use_sim,
        args.truecolor,
        fetcher=fetcher,
    )


if __name__ == "__main__":
    main()
