# hypr-follow-share (`hfs`)

[![Linux](https://img.shields.io/badge/platform-Linux%20%28Wayland%29-blue.svg)](https://wayland.freedesktop.org/)
[![Hyprland](https://img.shields.io/badge/Hyprland-0.55%2B-00aaee.svg)](https://hyprland.org/)
[![OBS Studio](https://img.shields.io/badge/OBS%20Studio-%E2%89%A5%2030-302e31.svg)](https://obsproject.com/)
[![Python](https://img.shields.io/badge/python-%E2%89%A5%203.11-3776ab.svg)](https://www.python.org/)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)

Share a **dynamic, cursor-following 16:9 crop** of an ultrawide monitor in Discord, Google Meet, Zoom, Slack, or Teams on **Hyprland (Wayland)** via **OBS Studio**.

---

## The Problem

Sharing a full 21:9 or 32:9 ultrawide monitor (e.g., 3440×1440 or 5120×1440) on video calls forces viewers with standard 16:9 screens to endure massive black letterbox bars. Code, terminals, and slides shrink into an unreadable blur:

```
Ultrawide screen on a 16:9 laptop:
┌──────────────────────────────────────────────┐
│                  BLACK BAR                   │
├──────────────────────────────────────────────┤
│ [Tiny unreadable text & shrunk IDE windows]  │
├──────────────────────────────────────────────┤
│                  BLACK BAR                   │
└──────────────────────────────────────────────┘
```

## The Solution

`hfs` dynamically extracts a crisp, full-height 16:9 window (e.g., 2560×1440) that smoothly glides along with your cursor across your ultrawide screen. Viewers see sharp, full-screen 16:9 content with zero letterboxing.

Everything runs through an isolated headless virtual monitor, so your mouse never gets trapped in the shared view, your normal workspace layout remains untouched, and you retain complete control via modal Hyprland keybinds.

---

## Architecture

```
┌────────────────────────────────────────────────────────┐
│ Ultrawide Physical Monitor (e.g. DP-1, 3440×1440)      │
└──────────────────────────┬─────────────────────────────┘
                           │ PipeWire screen capture
                           ▼
┌────────────────────────────────────────────────────────┐
│ OBS Studio (Canvas: 2560×1440 @ 60 FPS)                │
│  └─ Scene "HFS" / Source "HFS Capture"                 │
│     (Sub-pixel transform updated 60×/s)                │
└─────────────┬───────────────────────────▲──────────────┘
              │ Windowed Projector        │ SetSceneItemTransform
              │ (Fullscreen)              │ (obs-websocket v5)
              ▼                           │
┌──────────────────────────┐    ┌─────────┴──────────────┐
│ Headless Monitor "HFS"   │    │ hfs daemon (60 FPS)    │
│ (2560×1440 at -2560x-5000│    │  ├─ Hyprland IPC socket│
│  unreachable by mouse)   │    │  └─ Deadzone/smoothing │
└─────────────┬────────────┘    └────────────────────────┘
              │
              ▼ Screen Share
┌────────────────────────────────────────────────────────┐
│ Discord / Google Meet / Zoom / Slack / Teams           │
└────────────────────────────────────────────────────────┘
```

- **Direct IPC Socket**: Reads cursor coordinates directly from Hyprland's UNIX command socket (`j/cursorpos`, ~0.07 ms per call), completely bypassing `hyprctl` process-spawn overhead.
- **Sub-Pixel Motion**: Pans and zooms via OBS scene item transforms rather than integer crop steps, ensuring fluid 60 FPS panning with exponential smoothing.
- **Isolated Virtual Display**: Spawns a headless Hyprland display positioned far off-grid (`-2560x-5000`). Your physical layout and mouse boundaries are completely unaffected.
- **Dedicated OBS Profile**: Manages its own isolated OBS profile and scene collection (`hfs`). If OBS is started by `hfs`, it shuts down cleanly on exit; if you already had OBS open, `hfs down` safely restores your previous profile and collection.
- **Replacing Notifications**: Action popups automatically coalesce using `notify-send --replace-id` and a dedicated icon, updating cleanly without spamming notification history.

---

## Features

- 🎯 **Smart Follow Modes**:
  - `deadzone`: Screen stays still while your cursor moves inside the central area; only pans when the cursor approaches the margins.
  - `center`: Keeps the cursor centered in the viewport at all times.
- 🔍 **Dynamic Zooming**: Smoothly zoom in up to 360p detail or zoom out back to full height.
- 📐 **Interactive Region Selection**: Drag a box with `slurp` — `hfs` snaps and expands it into an exact 16:9 crop and pauses auto-follow so viewers can focus on one spot.
- ⏸️ **Auto-Pause on Multi-Monitor**: Automatically freezes the shared view whenever your cursor leaves the captured display.
- ⌨️ **Submap Keybinds**: Full modal keybindings (`SUPER+ALT+Y`) supporting held repeatable zoom, centering, follow toggling, and quick exit.

---

## Prerequisites

Ensure the following packages are installed on your system:

| Dependency | Purpose |
|---|---|
| **Hyprland** (≥ 0.55+) | Wayland compositor (Lua config support recommended) |
| **OBS Studio** (≥ 30) | Canvas renderer with native `obs-websocket` v5 |
| **xdg-desktop-portal-hyprland** | PipeWire screen capture portal provider |
| **slurp** | Interactive screen region selection |
| **libnotify** (`notify-send`) | Transient desktop feedback notifications |
| **librsvg** (`rsvg-convert`, optional) | High-DPI icon rendering for notifications |

---

## Installation

### Using `uv` (Recommended)

[`uv`](https://github.com/astral-sh/uv) provides fast, isolated Python tool execution:

```bash
# Clone the repository
git clone https://github.com/humam-hossain/hypr-follow-share.git
cd hypr-follow-share

# Install as a tool in ~/.local/bin
uv tool install --editable .
```

### Using `pipx` or `pip`

```bash
# Via pipx (isolated environment)
pipx install .

# Or directly with pip (into user environment)
pip install --user .
```

Ensure `~/.local/bin` is in your `$PATH`.

---

## Quick Start

### 1. Start the Session

```bash
hfs up
```

> **First Run Note:** A PipeWire screen-share portal dialog will appear. Select your ultrawide monitor (e.g. `DP-1`) and check **"Remember this selection"** or **"Allow restore token"**. Future runs will start automatically without prompting.

### 2. Share the Screen

In your meeting application (Discord, Google Meet, Zoom, Slack):
1. Choose **Share Screen / Entire Screen**.
2. Select the virtual display named **"HFS"** (2560×1440).

### 3. Stop the Session

```bash
hfs down
```

This cleans up the virtual monitor, closes the projector, terminates the follow daemon, and restores your previous OBS profile and scene collection.

> **Tip:** Use `hfs down --keep-profile` if you plan to restart `hfs` soon without reloading your main OBS profile.

---

## Hyprland Keybinds

### Option A: Lua Config (Recommended)

If using Hyprland's Lua configuration, include [`hyprland/hfs-keybinds.lua`](file:///home/pera/github_repo/hypr-follow-share/hyprland/hfs-keybinds.lua) in your configuration:

```lua
pcall(dofile, os.getenv("HOME") .. "/github_repo/hypr-follow-share/hyprland/hfs-keybinds.lua")
```

### Option B: Standard `hyprland.conf`

If using standard `hyprland.conf` syntax:

```ini
# Enter HFS control submap
bind = SUPER ALT, Y, exec, hfs keys on
bind = SUPER ALT, Y, submap, hfs

submap = hfs
# Zoom (repeating while held)
binde = , equal, exec, hfs zoom in
binde = , KP_Add, exec, hfs zoom in
binde = , minus, exec, hfs zoom out
binde = , KP_Subtract, exec, hfs zoom out

# Navigation & Modes
bind = , 0, exec, hfs zoom reset
bind = , C, exec, hfs center
bind = , F, exec, hfs follow toggle
bind = , F, submap, reset
bind = , M, exec, hfs mode toggle
bind = , M, submap, reset
bind = , S, exec, hfs select
bind = , S, submap, reset

# Start / Stop
bind = , U, exec, hfs up --notify
bind = , U, submap, reset
bind = , D, exec, hfs down --notify
bind = , D, submap, reset

# Exit submap
bind = , escape, exec, hfs keys off
bind = , escape, submap, reset
bind = , return, exec, hfs keys off
bind = , return, submap, reset
bind = SUPER ALT, Y, exec, hfs keys off
bind = SUPER ALT, Y, submap, reset

submap = reset
```

### Keybind Reference (`SUPER+ALT+Y`)

| Key | Action | Behavior |
|---|---|---|
| `=` / `-` (or keypad `+` / `-`) | Zoom in / Zoom out | Repeats while held (stays in submap) |
| `0` | Reset zoom (full height, follow ON) | Stays in submap |
| `C` | Re-center crop on cursor | Stays in submap |
| `F` | Toggle cursor follow (freeze / unfreeze) | Exits submap |
| `M` | Toggle mode (`deadzone` ↔ `center`) | Exits submap |
| `S` | Select region with `slurp` (snapped to 16:9) | Exits submap |
| `U` | Start session (`hfs up --notify`) | Exits submap |
| `D` | Stop session (`hfs down --notify`) | Exits submap |
| `Esc` / `Enter` / `SUPER+ALT+Y` | Leave control submap | Exits submap |

---

## CLI Reference

All control commands communicate with the running follow daemon via a local UNIX domain socket.

| Command | Description |
|---|---|
| `hfs up [--notify]` | Initialize OBS scene, virtual monitor, projector, and start follow daemon |
| `hfs down [--keep-profile] [--notify]` | Tear down virtual monitor, projector, daemon, and restore prior OBS profile |
| `hfs follow [on\|off\|toggle]` | Enable, disable, or toggle cursor following |
| `hfs mode [deadzone\|center\|toggle]` | Set or toggle follow style (`deadzone` vs `center`) |
| `hfs zoom in\|out\|reset` | Step zoom level in or out, or reset to full height with follow enabled |
| `hfs select` | Interactively select a screen region using `slurp` (freezes follow) |
| `hfs center` | Instantly jump the shared viewport center to current cursor position |
| `hfs status` | Print current daemon status and crop geometry as JSON |
| `hfs keys on\|off` | Display notification cheat-sheet when entering/leaving submap mode |
| `hfs daemon` | Run the follow daemon loop directly in the foreground (for debugging) |

---

## Configuration

Custom configuration is optional. You can create `~/.config/hypr-follow-share/config.toml` to customize defaults:

```toml
# Monitor to capture
monitor = "DP-1"

# Target aspect ratio (OBS canvas & virtual monitor)
aspect_w = 16
aspect_h = 9

# Follow loop update rate (frames per second)
fps = 60

# Follow mode: "deadzone" (pan near edges) or "center" (lock cursor to center)
mode = "deadzone"

# Fraction of viewport width/height on each side that triggers panning (0.0 to 0.5)
deadzone_margin = 0.22

# Exponential smoothing constant in seconds (higher = floatier/smoother)
smoothing = 0.12

# Zoom scaling factor per step and minimum allowable height in pixels
zoom_step = 1.2
min_height = 360

# OBS naming configuration
profile = "hfs"
collection = "hfs"
scene = "HFS"
source = "HFS Capture"

# Headless virtual monitor configuration
headless_name = "HFS"
headless_position = "-2560x-5000"

# Desktop notifications for changes and toggles
notify = true
```

### Configuration Options

| Option | Type | Default | Description |
|---|---|---|---|
| `monitor` | `string` | `"DP-1"` | Output name of your physical ultrawide monitor. |
| `aspect_w` | `int` | `16` | Aspect ratio width. |
| `aspect_h` | `int` | `9` | Aspect ratio height. |
| `fps` | `int` | `60` | Polling and update frequency in Hz. |
| `mode` | `string` | `"deadzone"` | `"deadzone"` or `"center"`. |
| `deadzone_margin` | `float` | `0.22` | Boundary margin fraction where the cursor pushes the view. |
| `smoothing` | `float` | `0.12` | Exponential smoothing tau in seconds (`0` for instant jump). |
| `zoom_step` | `float` | `1.2` | Multiplier for each zoom step. |
| `min_height` | `int` | `360` | Minimum crop height in source pixels (maximum zoom level). |
| `headless_name` | `string` | `"HFS"` | Name of the virtual headless output. |
| `headless_position`| `string` | `"-2560x-5000"` | Coordinate offset keeping the monitor away from your physical displays. |
| `notify` | `bool` | `true` | Send transient notifications on state changes. |

---

## Troubleshooting

### OBS WebSocket Connection Refused
If OBS is already open but its websocket is disabled:
- Go to **OBS Studio** > **Tools** > **WebSocket Server Settings**.
- Check **Enable WebSocket server** (default port `4455`).
- *Alternatively*: Close OBS completely. Running `hfs up` will automatically enable the WebSocket in OBS's configuration file and launch OBS for you.

### Portal Prompt Does Not Open or Frames Don't Produce
- Ensure `xdg-desktop-portal-hyprland` is running.
- In the portal dialog, select your physical monitor (`DP-1`) and check **"Remember"** / **"Allow restore token"**.
- If a source fails, open OBS, open the **HFS Capture** properties, and click **Reload**.

### Cursor Missing on Screen Share
- `hfs` automatically sets `ShowCursor: true` on the PipeWire capture source.
- If your hardware cursor is invisible on the stream, add this to your `hyprland.conf`:
  ```ini
  cursor {
      no_hardware_cursors = true
  }
  ```

### Multi-Monitor Cursor Behavior
- When moving your mouse away from the captured monitor onto another physical display, `hfs` automatically **pauses** panning and retains the last known position until the cursor returns.

### Testing Keybinds from Scripts
- If sending synthetic keypresses, use [`ydotool`](https://github.com/ReimuNotMoe/ydotool) (kernel uinput). Synthetic Wayland tools like `wtype` do not trigger Hyprland submap binds and may break out of the submap.

### Diagnostic Logs
View real-time daemon activity:
```bash
tail -f ~/.local/state/hypr-follow-share/daemon.log
```

---

## Development

Run the test suite using `pytest`:

```bash
uv run pytest
```

---

## License

This project is licensed under the [MIT License](LICENSE).
