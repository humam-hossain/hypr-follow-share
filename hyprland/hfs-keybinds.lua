-- hypr-follow-share keybinds (Hyprland Lua config).
--
-- SUPER+ALT+Y enters the "hfs" submap. Inside it:
--   =  / -     zoom in / out      (stays in the submap, so you can tap repeatedly)
--   0          zoom reset         (full height, follow on; stays)
--   C          center on cursor   (stays)
--   F          follow toggle      (exits)
--   M          mode toggle        (deadzone <-> center; exits)
--   S          select region      (slurp; exits)
--   U / D      hfs up / hfs down  (exits)
--   Esc, Return, SUPER+ALT+Y      exit
--
-- Include from your Hyprland config:
--   pcall(dofile, os.getenv("HOME") .. "/github_repo/hypr-follow-share/hyprland/hfs-keybinds.lua")

local HOME = os.getenv("HOME")
local HFS = HOME .. "/.local/bin/hfs"
local SUBMAP = "hfs"

-- Every action shows a "Screen share" notification with the hfs icon; they replace
-- each other instead of stacking. `hfs keys on|off` covers entering/leaving the mode.
local function run(args)
    return hl.dsp.exec_cmd(HFS .. " " .. args)
end

-- Run a command, then leave the submap.
local function run_and_exit(cmd)
    return function()
        hl.dispatch(hl.dsp.exec_cmd(cmd))
        hl.dispatch(hl.dsp.submap("reset"))
    end
end

hl.bind("SUPER + ALT + Y", function()
    hl.dispatch(hl.dsp.exec_cmd(HFS .. " keys on"))
    hl.dispatch(hl.dsp.submap(SUBMAP))
end, { description = "Screen share (hfs): enter control mode" })

-- Submap keys ignore modifiers, so they work whether or not SUPER+ALT is still held.
local function key(k, action, opts)
    opts = opts or {}
    opts.ignore_mods = true
    hl.bind(k, action, opts)
end

hl.define_submap(SUBMAP, function()
    -- Repeatable: stay in the submap.
    key("equal", run("zoom in"), { repeating = true, description = "hfs: zoom in" })
    key("KP_Add", run("zoom in"), { repeating = true })
    key("minus", run("zoom out"), { repeating = true, description = "hfs: zoom out" })
    key("KP_Subtract", run("zoom out"), { repeating = true })
    key("0", run("zoom reset"), { description = "hfs: zoom reset (full height, follow on)" })
    key("C", run("center"), { description = "hfs: center on cursor" })

    -- One-shot: act, then exit.
    key("F", run_and_exit(HFS .. " follow toggle"), { description = "hfs: follow toggle" })
    key("M", run_and_exit(HFS .. " mode toggle"), { description = "hfs: mode toggle" })
    key("S", run_and_exit(HFS .. " select"), { description = "hfs: select region" })
    key("U", run_and_exit(HFS .. " up --notify"), { description = "hfs: up" })
    key("D", run_and_exit(HFS .. " down --notify"), { description = "hfs: down" })

    -- Exit.
    key("Escape", run_and_exit(HFS .. " keys off"))
    key("Return", run_and_exit(HFS .. " keys off"))
    -- Exact match, not ignore_mods: a mod-less "Y" would also catch the very
    -- SUPER+ALT+Y press that entered the submap and exit immediately.
    hl.bind("SUPER + ALT + Y", run_and_exit(HFS .. " keys off"))
end)
