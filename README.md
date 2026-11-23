# hypr-follow-share

Share a **cursor-following 16:9 crop** of an ultrawide monitor in Discord, Google Meet or Zoom, on **Hyprland (Wayland)**, via **OBS**.

Sharing a whole 3440x1440 screen leaves viewers on 16:9 laptops with letterbox bars and tiny text. `hfs` shares a 2560x1440 (full-height, 16:9) window onto your screen that glides along with your cursor. You can zoom in/out, select a region with the mouse, and turn following on or off, all from Hyprland keybinds.

## How it works

```
DP-1 (3440x1440) --PipeWire--> OBS scene "HFS" (canvas 2560x1440)
                                   ^ capture item panned/zoomed 60x/s
hfs daemon --cursor via Hyprland IPC socket--> obs-websocket SetSceneItemTransform
OBS windowed projector --fullscreen--> headless monitor "HFS" (2560x1440, unreachable by the mouse)
Discord / Meet / Zoom --share screen--> "HFS"
```

- The cursor position comes from Hyprland's command socket (`j/cursorpos`, ~0.07 ms per call), not from `hyprctl` processes.
- Panning uses sub-pixel scene item position/scale, not integer crop values, so motion is smooth.
- The **deadzone** mode keeps the view still while the cursor stays in the middle. The view moves only when the cursor nears an edge. The **center** mode keeps the cursor centered.
- OBS global hotkeys don't work on Wayland, so all controls go through `hfs` CLI commands bound in Hyprland.
- `hfs up` switches OBS to its own `hfs` profile and scene collection (2560x1440 @ 60 canvas). `hfs down` switches back to the ones you had before.
- The headless monitor sits at `-2560x-5000`, away from every real monitor, so the mouse can never wander onto it and your real monitor layout stays the same.

## Install

```sh
uv tool install --editable .     # puts `hfs` in ~/.local/bin
```

Requirements: Hyprland with the Lua config (0.55+), OBS ≥ 30 (obs-websocket built in), `xdg-desktop-portal-hyprland`, `slurp`, `notify-send`.

## Use

```sh
hfs up        # first run: pick DP-1 in the portal dialog and tick "allow restore token"
# share screen "HFS" in your meeting app
hfs down      # --keep-profile leaves OBS on the hfs profile/collection
```

| Command | Effect |
|---|---|
| `hfs follow [on\|off\|toggle]` | cursor follow |
| `hfs mode [deadzone\|center\|toggle]` | follow style |
| `hfs zoom in\|out\|reset` | shrink / grow region (reset = full height + follow on) |
| `hfs select` | drag a region (snapped to 16:9, follow turns off) |
| `hfs center` | jump region to the cursor |
| `hfs status` | JSON state |

### Keybinds

Include `hyprland/hfs-keybinds.lua` from your Hyprland Lua config:

```lua
pcall(dofile, os.getenv("HOME") .. "/github_repo/hypr-follow-share/hyprland/hfs-keybinds.lua")
```

`SUPER+ALT+Y` enters the `hfs` submap and shows a cheat-sheet notification. Then:

| Key | Action | Submap after |
|---|---|---|
| `=` / `-` (also keypad `+` / `-`) | zoom in / out, repeats while held | stays |
| `0` | zoom reset (full height, follow on) | stays |
| `C` | center on cursor | stays |
| `F` | follow toggle | exits |
| `M` | mode toggle (deadzone / center) | exits |
| `S` | select region (slurp) | exits |
| `U` / `D` | `hfs up --notify` / `hfs down --notify` | exits |
| `Esc`, `Return`, `SUPER+ALT+Y` | leave | exits |

`--notify` reports the result of `up` / `down` as a desktop notification, since a keybind has no terminal.

Testing binds from a script: use `ydotool` (kernel uinput). `wtype` key presses do not trigger Hyprland binds here, and they drop you out of the submap.

## Config

Optional `~/.config/hypr-follow-share/config.toml`. Keys and defaults are in `src/hfs/config.py`. Example:

```toml
monitor = "DP-1"
aspect_w = 16
aspect_h = 9
deadzone_margin = 0.22   # fraction of the region per side where the cursor pushes
smoothing = 0.12         # seconds; higher = floatier
zoom_step = 1.2
```

## Troubleshooting

- **"OBS is running but its websocket is off"**: enable it in OBS > Tools > WebSocket Server Settings. Or quit OBS and `hfs up` enables it and starts OBS.
- **Daemon log**: `~/.local/state/hypr-follow-share/daemon.log`.
- **Cursor missing in the share**: OBS capture has `ShowCursor` on. If you still see no cursor, set `cursor { no_hardware_cursors = true }`.
