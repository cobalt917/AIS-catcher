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

**Power wiring:** Panels powered directly from Meanwell. Pi powered either via a
sacrificed Micro USB cable wired to the Meanwell (+5V/GND), or by injecting 5V directly
into GPIO pins 2/4 (+5V) and pin 6 (GND). The USB route goes through the onboard
polyfuse; the GPIO route bypasses it.

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

## Raspberry Pi WiFi Setup

The Pi uses a small USB WiFi adapter (plug-and-play, no driver install needed).

**Interface:** `wlan0`
**MAC address:** `10:5a:95:99:87:48` — added to MAC filter on router (UDM SE)
**Network:** `hillcountry` (WPA2/WPA3 mixed mode on UDM SE)

**wpa_supplicant config** — `/etc/wpa_supplicant/wpa_supplicant-wlan0.conf` (owned `root:root`, mode `600`):
```
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=US

network={
    ssid="hillcountry"
    psk="..."
    key_mgmt=WPA-PSK
    mac_addr=0
}
```

Note: `key_mgmt=WPA-PSK` is required even though the network is WPA2/WPA3 mixed — the older
wpa_supplicant on Pi 1 does not successfully negotiate SAE. The router accepts WPA2 from it fine.

**Services** (both enabled and persistent across reboots):
- `wpa_supplicant@wlan0` — authenticates using the `-wlan0` config file
- `dhcpcd` — requests DHCP lease; installed via `sudo apt install dhcpcd5`

---

## LED Display Autostart

The display script runs as a systemd service on boot.

**`/etc/systemd/system/led-display.service`:**
```ini
[Unit]
Description=LED Ship Display
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/python3 /home/daniel/AIS-catcher/scripts/led_display.py --server http://elberta:8080
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enabled with `sudo systemctl enable --now led-display`. Runs as root (required for GPIO access).

---

## LED Display Driver (`scripts/led_display.py`)

Animates the two 32×64 panels with approaching ship data fetched live from AIS-catcher.
Falls back to `--sample` (hardcoded `SAMPLE_SHIPS`) for offline testing.

**Live data source:** `/api/ships.json` on the AIS-catcher web server (elberta:8080).
ETA/CPA math runs in Python using the same vector math as `ETACalculator.cpp`.
Direction: MMSI latitude trend (primary) — increasing lat = UP (toward Lake Huron).
Fallback for first-seen ships: COG projected onto 340° waterway axis (`_direction_cog_axis()`).

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
- **Fixed zone (39 px):** arrow + ETA (23 px) · flag (14 px) · status icon (5 px) · each separated by 1 px gap
- **Scrolling zone (89 px):** ship name only — scrolls if wider than 89 px, static otherwise
- **Direction:** `◀` = upstream (UP), `▶` = downstream (DOWN)
- **Vertical cycling:** 3 ships visible at once; rotates by 1 every `--page-time` seconds

**Matrix options** (baked into `create_matrix()`):
- `hardware_mapping = "regular-pi1"` — required for 26-pin Pi 1 Model B
- `slowdown_gpio = 2` (commented out), `brightness = 80`, chain of two 32×64 panels
- `pwm_bits = 4` — 16 brightness levels; reduces driver thread CPU ~8× and eliminates flicker caused by scan-cycle preemption on the overloaded Pi 1
- `pwm_lsb_nanoseconds = 500` — widens the LSB pulse, forcing the driver to sleep more between GPIO ops; reduces driver CPU ~4× further
- `limit_refresh_rate_hz = 50` — caps internal scan rate at 50 Hz; imperceptible for ship data, halves driver loop rate

**Frame rendering:**
`write_frame_to_canvas()` builds a flat RGB `bytearray` using a list-indexed LUT (FC codes 0–8) then calls `canvas.SetImage()` once (PIL Image), replacing 4096 individual `SetPixel()` Python→C calls per frame. Requires `python3-pil` (`sudo apt install python3-pil`).

The matrix run loop only calls render+blit+`SwapOnVSync` when something actually changed: a name scroll advanced, a page turn fired, or ship data was refreshed. When the display is static this reduces Python rendering work to nearly zero. `advance_scrolls()` returns `True` when any offset moved to signal this.

`main()` calls `os.nice(10)` at startup so SSH and systemd can preempt the Python process readily (the RT-priority driver thread is unaffected).

**Prototype sample ships** (edit `SAMPLE_SHIPS` at top of file):
```python
{"direction": "UP",   "eta_min":  4, "flag": "CA", "name": "ALGONOVA"},
{"direction": "UP",   "eta_min": 11, "flag": "US", "name": "WHITEFISH BAY"},
{"direction": "DOWN", "eta_min": 22, "flag": "CA", "name": "ALGOMA MARINER"},
...
```

**Still to do:**
- ~~Display `...` instead of `MMSI XXXXXXXXX` when no ship name is received~~ **Done** — `led_display.py` fallback name is now `"..."` when `shipname` is absent
- ~~Single ship displayed on all 3 rows~~ **Fixed** — `render_frame` now iterates `min(ROWS_PER_FRAME, n)` rows so fewer ships than slots don't wrap back to row 0
- ~~Display rotates when all ships fit on screen~~ **Fixed** — `v_offset` only advances when ship count exceeds the number of visible rows (3 in normal mode, 2 in stacked mode)
- ~~Font size options~~ **Done** — `--zoom` flag activates stacked layout when 1–2 ships visible: arrow stretched to full row height (5px wide × 16 or 32px tall), ETA and flag stacked vertically (both small font) in a 17px column, name scrolls in the remaining 104px zone (vs 83px normal). Try: `python3 scripts/led_display.py --sim --sample --zoom` (trim SAMPLE_SHIPS to 1–2 entries to test stacked mode)
- ~~Direction tolerance tuning~~ **Done** — MMSI latitude history (primary) + COG projected onto 340° waterway axis (fallback). History requires ≥ 2 observations, ≥ 60 s spread, ≥ 0.002° lat delta; falls back to axis projection for first-seen ships. `import collections` added; `_lat_history` dict, `_record_lat()`, `_direction_from_lat_history()`, `_direction_cog_axis()` added to `led_display.py`.
- Time-of-day brightness dimming: reduce LED brightness at night/early morning for kitchen installation
- ~~Pi 1 CPU overload / LED flicker~~ **Fixed** — `pwm_bits=4` + `pwm_lsb_nanoseconds=500` + `limit_refresh_rate_hz=50` in `create_matrix()` reduces driver thread CPU substantially; `write_frame_to_canvas()` replaced with PIL `SetImage()` bulk blit (1 C call vs 4096 `SetPixel()` calls); render loop skips rebuild when display is static; `os.nice(10)` improves SSH responsiveness. Systemd unit runs with `--tick-ms 150`. If load remains high, lower `pwm_bits` to 3.
- ~~Negative ETA / recent passage~~ **Done** — ships within 10 min past CPA are kept and shown with negative countdown (`◀-3m`). `_compute_eta` changed to allow `tcpa_h >= -10/60`; ETA format is `-{N}m` (1 digit, capped at 9) for negative, ` Nm` (2 digit right-justified) for positive. Past ships sort after approaching ships, most recently passed first. SAMPLE_SHIPS has a -3m test entry.
- ~~Flag coverage~~ **Done** — curated Great Lakes / St Lawrence Seaway subset: US CA NL FR DE MT LR PA BS NO DK SE FI GB BE IT (16 countries). Unknown MMSI country codes show a `?` icon; ships with no country field show a blank. New FC_ colour constants added: FC_YELLOW, FC_BLACK, FC_GREEN. Both `led_display.py` and `led_sim.py` updated identically. Preview any flag: `python3 scripts/led_sim.py "[NL] TEST" --size 32x128 --panel 32x64`
- ~~Compress fixed zone layout~~ **Done** — fixed zone reduced from 51 px to 39 px; name zone expanded from 77 px to 89 px; ETA now 2-digit right-justified (`▶ 4m` / `▶22m`)
- ~~AIS status icons~~ **Done** — 5×7 px static icons between flag and name: ⚓-shaped glyph (FC_GREY, rgb 130,130,130) for nav_status 1 (at anchor); red X (FC_RED) for nav_status 6 (aground); blank for all other states. Anchor design: shaft pierces ring centre (`10101` row) matching ⚓ emoji. API field: `status`. FC_GREY = 8 added to both scripts. Two SAMPLE_SHIPS entries carry test values (ALGOMA MARINER=1, AMERICAN SPIRIT=6)
