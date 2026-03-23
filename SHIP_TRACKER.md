# Ship Tracker Project Notes

## Overview

AIS-catcher is running on a repurposed iMac (x86-64, Debian) with an RTL-SDR Blog V4
dongle, tracking ships on the Detroit River / Lake Erie shipping lane near the observer
station at approximately 42.372498 N, 82.918296 W. A Raspberry Pi 1 Model B drives
HUB75 LED panels as a physical display.

---

## AIS-catcher Modifications

All modifications are committed to a personal fork: `github.com/cobalt917/AIS-catcher`.
The original upstream is `github.com/jvde-github/AIS-catcher`.

### 1. NMEA File Replay (`-R`)

Allows replaying a previously recorded NMEA log file, with optional real-time pacing.

**New files:**
- `Device/FileNMEA.h`
- `Device/FileNMEA.cpp`

**Modified files:**
- `Library/Common.h` — added `NMEAFILE = 15` to `Type` enum
- `Application/Receiver.h` — added `Device::NMEAFile _NMEAFile` member and accessor
- `Application/Receiver.cpp` — added `Type::NMEAFILE` case in `getDeviceByType()`
- `Application/Main.cpp` — added `-R` flag and `-gR` settings parsing
- `Library/Utilities.cpp` — added type string for `NMEAFILE`
- `CMakeLists.txt` — added new files to build

**Usage:**
```bash
AIS-catcher -R recording.nmea
AIS-catcher -R recording.nmea -gR SPEED 2.0 LOOP on
```

**Settings (via `-gR`):**
| Option   | Description                              | Default |
|----------|------------------------------------------|---------|
| FILE     | Path to NMEA file                        | —       |
| SPEED    | Playback speed multiplier                | 1.0     |
| REALTIME | Honour timestamps (on) or play instantly | on      |
| LOOP     | Loop playback                            | off     |

**File format expected:**
```
!AIVDM,1,1,,B,... ( MSG: 1, REPEAT: 0, MMSI: 123456789, signalpower: -32.5, ppm: 0.1, timestamp: 20251225162745)
```
Timestamp format: `YYYYMMDDHHMMSS`

---

### 2. ETA/CPA Screen Mode (`-o 7`)

Displays a live table of ships approaching the observer's location, calculated using
Closest Point of Approach (CPA) vector math rather than simple heading comparison.
Refreshes on a configurable interval, clears the terminal, and sorts by soonest ETA.

**New files:**
- `Tracking/ETA.h` — `ETAInfo` struct and `ETACalculator` class
- `Tracking/ETA.cpp` — CPA/TCPA calculation logic

**Modified files:**
- `Library/Common.h` — added `ETA_SCREEN` to `MessageFormat` enum
- `Tracking/DB.h` — exposed `getFirst()`, `getShips()`, made `getDistanceAndBearing()` public
- `IO/MsgOut.h` — added `ETAScreen` class
- `IO/MsgOut.cpp` — implemented `ETAScreen` display loop and `Set()` options
- `Application/Receiver.h` — added `std::unique_ptr<DB> eta_db`, `IO::ETAScreen eta_screen`
- `Application/Receiver.cpp` — wired up ETA screen to receiver outputs
- `Application/Main.cpp` — added `-o 7` handling and settings parsing
- `CMakeLists.txt` — added new files to build

**Usage:**
```bash
AIS-catcher -R recording.nmea -o 7
AIS-catcher -R recording.nmea -o 7 CPA 2.0 REFRESH 10 LAT 42.37 LON -82.92
```

**Settings (after `-o 7`):**
| Option  | Description                        | Default     |
|---------|------------------------------------|-------------|
| CPA     | CPA threshold in nautical miles    | 2.0         |
| REFRESH | Display refresh interval (seconds) | 10          |
| LAT     | Observer latitude                  | 42.372498   |
| LON     | Observer longitude                 | -82.918296  |

**CPA math summary:**
- Convert lat/lon to local NM coordinates
- Ship velocity vector: `vx = speed*sin(COG)`, `vy = speed*cos(COG)`
- TCPA: `t = -(P·V) / |V|²`
- CPA position: `P + V*t`

---

## LED Matrix Display

### Hardware

| Component         | Details                                              |
|-------------------|------------------------------------------------------|
| Controller        | Raspberry Pi 1 Model B (pre-2014, 26-pin GPIO header)|
| Panels            | HUB75 32×64 px, ×2 daisy-chained                    |
| Power supply      | Meanwell LRS-50-5 (5V 10A)                          |
| RTL-SDR           | RTL-SDR Blog V4 (on Debian server, not the Pi)       |

**Power wiring:** Panels powered directly from Meanwell. Pi powered via the Adafruit
RGB Matrix Bonnet's 5V passthrough (not USB).

**Important:** The Pi 1 Model B has only 26 GPIO pins. The default rpi-rgb-led-matrix
GPIO mapping uses GPIO 27 (pin 13 on a 40-pin header, absent here) for G1, which caused
the green channel to not display. Fix: use `--led-gpio-mapping=regular-pi1`.

### Software

Library: [rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix) by Henner Zeller.

**Installed on the Raspberry Pi** (not the Debian server).

**Installing the Python bindings** (needed for `led_display.py`):
```bash
sudo apt install python3-pip python3-dev cython3
cd ~/rpi-rgb-led-matrix
sudo pip3 install . --break-system-packages
```
Note: compiling Cython on Pi 1 takes 5–10 minutes. The `--break-system-packages` flag
is required on newer Raspberry Pi OS (Bookworm) due to PEP 668.

**Key flags for this hardware:**
```bash
--led-gpio-mapping=regular-pi1   # required — default mapping missing on 26-pin Pi
--led-rows=32
--led-cols=64
--led-chain=2                    # two panels daisy-chained
--led-slowdown-gpio=2            # may be needed on slow Pi 1 hardware
```

**Blacklisted modules** (add to `/etc/modprobe.d/raspi-blacklist.conf`):
```
blacklist snd_bcm2835    # shares PWM hardware with the matrix library — causes flicker
```

**Working smoke-test command:**
```bash
sudo ./text-scroller -f ../fonts/helvR12.bdf \
  --led-gpio-mapping=regular-pi1 \
  --led-rows=32 --led-cols=64 --led-chain=2 \
  "Hello World" -C 255,255,255
```

---

## LED Panel Simulator (`scripts/led_sim.py`)

Terminal-based simulator for planning panel layout before ordering hardware.
Uses ANSI color codes; auto-detects 24-bit vs 256-color terminal support.

**Usage:**
```bash
python3 scripts/led_sim.py "NORTHBOUND  8min" --size 32x128 --panel 32x64
python3 scripts/led_sim.py "NORTHBOUND\n8 min" --size 32x128 --panel 32x64
python3 scripts/led_sim.py "[US] ALGOMA SPIRIT" --size 32x128 --panel 32x64 --color amber
python3 scripts/led_sim.py "[CA] WHITEFISH BAY\n12min" --size 32x128 --panel 32x64
```

**Flags:**
| Flag          | Description                                      | Default   |
|---------------|--------------------------------------------------|-----------|
| `--size HxW`  | Total display size in pixels                     | 32x128    |
| `--color`     | LED color: amber/red/green/blue/white/yellow/cyan| amber     |
| `--align`     | left / center / right                            | left      |
| `--margin`    | Left/right margin in pixels                      | 1         |
| `--panel HxW` | Individual panel size — draws seam lines         | (none)    |
| `--truecolor` | Force 24-bit ANSI color output                   | auto      |

**Multi-line:** separate lines with `\n` in the text argument.

**Flag tokens:** `[US]` and `[CA]` render 7×14 pixel flag bitmaps inline with text.
New flags can be added to the `FLAGS` dict in the script.

**Special characters** (paste directly into text):
`→ ← ↑ ↓ ▶ ◀ ° ★`

---

## LED Display Driver (`scripts/led_display.py`)

Animates the two 32×64 panels with approaching ship data fetched live from AIS-catcher.
Falls back to `--sample` (hardcoded `SAMPLE_SHIPS`) for offline testing.

**Live data source:** `/api/ships.json` on the AIS-catcher web server (elberta:8080).
ETA/CPA math runs in Python using the same vector math as `ETACalculator.cpp`.
Direction: `cos(COG) >= 0` → UP (northerly), else DOWN (southerly).

**Display states:**
- Wave image — server reachable but no ships pass the CPA filter; navy-blue water body + white foam caps (uses flag colour pipeline, not the LED colour)
- `"Server error"` (centred text) — most recent fetch failed (network down, server not running, etc.)
- Blank screen — Pi itself has crashed or the script is not running

**Usage:**
```bash
# Terminal preview — live data (any machine)
python3 scripts/led_display.py --sim
python3 scripts/led_display.py --sim --server http://elberta:8080

# Terminal preview — prototype data
python3 scripts/led_display.py --sim --sample

# Real LED matrix (Pi only)
python3 scripts/led_display.py
python3 scripts/led_display.py --server http://elberta:8080
```

> Terminal is 256 chars wide for a 128 px panel — use a wide window or small font.

**All options:**
| Option | Description | Default |
|---|---|---|
| `--sim` | Render to terminal instead of real matrix | off |
| `--sample` | Use hardcoded SAMPLE_SHIPS instead of live data | off |
| `--server URL` | AIS-catcher base URL | `http://elberta:8080` |
| `--lat DEG` | Observer latitude | 42.372498 |
| `--lon DEG` | Observer longitude | -82.918296 |
| `--cpa NM` | CPA threshold in nautical miles | 2.0 |
| `--fetch-interval SEC` | Seconds between server polls | 30 |
| `--max-age SEC` | Exclude ships last heard > N sec ago | 300 |
| `--color` | LED color: amber/red/green/blue/white/yellow/cyan | amber |
| `--scroll-speed PX` | Pixels to advance per tick for scrolling names | 1 |
| `--page-time SEC` | Seconds between vertical ship rotation | 5.0 |
| `--tick-ms MS` | Milliseconds per animation tick (~1000/fps) | 50 |
| `--truecolor` | Force 24-bit ANSI color in sim mode | auto |

**Display layout (per row, 32×128 px total):**
```
[◀ 4m][CA flag] ALGONOVA
[▶22m][CA flag] ALGOMA MARINER scrolls...
```
- **Fixed zone (45 px):** arrow + ETA (23 px) · flag (14 px) · status icon (5 px) · each separated by 1 px gap
- **Scrolling zone (83 px):** ship name only — scrolls if wider than 83 px, static otherwise
- **Direction:** `◀` = upstream (UP), `▶` = downstream (DOWN)
- **Vertical cycling:** 3 ships visible at once; rotates by 1 every `--page-time` seconds

**Matrix options** (baked into `create_matrix()`):
- `hardware_mapping = "regular-pi1"` — required for 26-pin Pi 1 Model B
- `slowdown_gpio = 2`, `brightness = 80`, chain of two 32×64 panels

**Prototype sample ships** (edit `SAMPLE_SHIPS` at top of file):
```python
{"direction": "UP",   "eta_min":  4, "flag": "CA", "name": "ALGONOVA"},
{"direction": "UP",   "eta_min": 11, "flag": "US", "name": "WHITEFISH BAY"},
{"direction": "DOWN", "eta_min": 22, "flag": "CA", "name": "ALGOMA MARINER"},
...
```

**Still to do:**
- Font size options for fitting more ships on screen simultaneously
- Direction tolerance tuning (currently pure north/south hemisphere split on COG)
- Time-of-day brightness dimming: reduce LED brightness at night/early morning for kitchen installation
- ~~Flag coverage~~ **Done** — curated Great Lakes / St Lawrence Seaway subset: US CA NL FR DE MT LR PA BS NO DK SE FI GB BE IT (16 countries). Unknown MMSI country codes show a `?` icon; ships with no country field show a blank. New FC_ colour constants added: FC_YELLOW, FC_BLACK, FC_GREEN. Both `led_display.py` and `led_sim.py` updated identically. Preview any flag: `python3 scripts/led_sim.py "[NL] TEST" --size 32x128 --panel 32x64`
- ~~Compress fixed zone layout~~ **Done** — fixed zone reduced from 51 px to 39 px; name zone expanded from 77 px to 89 px; ETA now 2-digit right-justified (`▶ 4m` / `▶22m`)
- ~~AIS status icons~~ **Done** — 5×7 px static icons between flag and name: anchor glyph (FC_LED colour) for nav_status 1 (at anchor), red X (FC_RED) for nav_status 6 (aground); blank for all other states. API field: `status`. Two SAMPLE_SHIPS entries carry test values (ALGOMA MARINER=1, AMERICAN SPIRIT=6)
