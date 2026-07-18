--[[
  resolve_cut.lua  —  paste into DaVinci Resolve's Console (Lua)

  Workflow (free version, no manual cutting):
    1. Import the VOD and drop it on a timeline (any timeline is fine).
    2. Workspace > Console, switch the dropdown from Py3 to Lua.
    3. Paste this whole file, press Enter.

  It reads the cuts.csv of the last `cutter run` (via last_job.txt), or the
  newest job under Documents\CutterJobs; timeline is named `<job> Recap`.
  It then creates a NEW timeline containing only the matched recap segments,
  in recap-script (CSV row) order, padded ~1s on each side. Your original
  timeline/VOD is untouched.

  Edit the CONFIG block below if your paths/preferences differ.
]]

-- ===================== CONFIG =====================
local PAD          = 1.0            -- seconds of padding added before start / after end
local MIN_CONF     = 0.15           -- skip matches below this confidence
-- =================================================

-- ---- locate the cuts.csv written by `cutter run` ----
local function readLastJob()
  local appdata = os.getenv("APPDATA")
  if not appdata then return nil end
  local f = io.open(appdata .. "\\Blackmagic Design\\DaVinci Resolve\\Support\\Fusion\\Scripts\\Utility\\last_job.txt", "r")
  if not f then return nil end
  local p = f:read("*l")
  f:close()
  if p and #p > 0 then return p end
  return nil
end

local function newestCutsInJobsRoot()
  -- fallback: newest cuts.csv anywhere under Documents\CutterJobs
  local cmd = [[powershell -NoProfile -Command "Get-ChildItem (Join-Path $env:USERPROFILE 'Documents\CutterJobs') -Recurse -Filter cuts.csv -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName"]]
  local h = io.popen(cmd)
  if not h then return nil end
  local out = h:read("*l")
  h:close()
  if out and #out > 0 then return out end
  return nil
end

local CSV = readLastJob() or newestCutsInJobsRoot()
if not CSV then
  print("ERROR: no cuts.csv found. Run 'cutter run <job>' first.")
  return
end
local probe = io.open(CSV, "r")
if not probe then
  print("ERROR: cuts file listed in last_job.txt is missing: " .. CSV)
  return
end
probe:close()

-- timeline named after the job folder: ...\myjob\out\cuts.csv -> "myjob Recap"
local jobName = CSV:match("([^\\]+)\\out\\cuts%.csv$") or "Cutter"
local TIMELINE_NAME = jobName .. " Recap"
print("Cutting from: " .. CSV .. "  ->  timeline '" .. TIMELINE_NAME .. "'")

-- ---- get the Resolve app object (console usually predefines `resolve`) ----
local app = resolve
if not app and Resolve then app = Resolve() end
if not app and bmd then app = bmd.scriptapp("Resolve") end
if not app then print("ERROR: could not get the Resolve object."); return end

local project = app:GetProjectManager():GetCurrentProject()
if not project then print("ERROR: no project open."); return end
local mediaPool = project:GetMediaPool()

-- ---- find the VOD's media pool item ----
-- Preferred: read it off the clip you put on the current timeline.
local function findFromTimeline()
  local tl = project:GetCurrentTimeline()
  if not tl then return nil end
  local items = tl:GetItemListInTrack("video", 1)
  if not items then return nil end
  for _, it in ipairs(items) do
    local m = it:GetMediaPoolItem()
    if m then return m end
  end
  return nil
end

-- Fallback: search the media pool for an .mp4 / Zenless clip.
local function findInFolder(folder)
  local clips = folder:GetClipList()
  if clips then
    for _, c in ipairs(clips) do
      local nm = (c:GetName() or ""):lower()
      if nm:match("%.mp4$") or nm:find("zenless") then return c end
    end
  end
  local subs = folder:GetSubFolderList()
  if subs then
    for _, sf in ipairs(subs) do
      local r = findInFolder(sf)
      if r then return r end
    end
  end
  return nil
end

local mpi = findFromTimeline() or findInFolder(mediaPool:GetRootFolder())
if not mpi then
  print("ERROR: couldn't find the VOD. Put it on a timeline or in the media pool.")
  return
end

-- ---- source frame rate + length ----
local fps = tonumber(mpi:GetClipProperty("FPS"))
if not fps then
  local tl = project:GetCurrentTimeline()
  if tl then fps = tonumber(tl:GetSetting("timelineFrameRate")) end
end
fps = fps or 30
local totalFrames = tonumber(mpi:GetClipProperty("Frames"))  -- may be nil
print(string.format("VOD: %s  |  fps=%s  |  frames=%s", mpi:GetName(), tostring(fps), tostring(totalFrames)))

-- ---- minimal quote-aware CSV line parser ----
local function parseLine(line)
  local fields, i, n = {}, 1, #line
  while true do
    local buf = {}
    if line:sub(i, i) == '"' then          -- quoted field
      i = i + 1
      while i <= n do
        local ch = line:sub(i, i)
        if ch == '"' then
          if line:sub(i + 1, i + 1) == '"' then buf[#buf + 1] = '"'; i = i + 2
          else i = i + 1; break end
        else buf[#buf + 1] = ch; i = i + 1 end
      end
      fields[#fields + 1] = table.concat(buf)
    else                                    -- unquoted field
      local s = i
      while i <= n and line:sub(i, i) ~= ',' do i = i + 1 end
      fields[#fields + 1] = line:sub(s, i - 1)
    end
    if i <= n and line:sub(i, i) == ',' then i = i + 1 else break end
  end
  return fields
end

-- ---- read matches.csv: columns are recap_line, start, end, confidence, matched_transcript ----
local fh = io.open(CSV, "r")
if not fh then print("ERROR: cannot open " .. CSV); return end

local clipInfos, kept, skipped, header = {}, 0, 0, true
for line in fh:lines() do
  if header then header = false                 -- skip header row
  elseif line:match("%S") then
    local f = parseLine(line)
    local startSec = tonumber(f[2])
    local endSec   = tonumber(f[3])
    local conf     = tonumber(f[4])
    if startSec and endSec and conf then
      if conf < MIN_CONF then
        skipped = skipped + 1
      else
        local sf = math.floor((startSec - PAD) * fps + 0.5)
        local ef = math.floor((endSec + PAD) * fps + 0.5)
        if sf < 0 then sf = 0 end
        if totalFrames and ef > totalFrames - 1 then ef = totalFrames - 1 end
        if ef > sf then
          clipInfos[#clipInfos + 1] = { mediaPoolItem = mpi, startFrame = sf, endFrame = ef }
          kept = kept + 1
        end
      end
    end
  end
end
fh:close()

if kept == 0 then print("Nothing to cut (0 segments after filtering)."); return end

-- ---- create a fresh timeline and append the segments ----
local name, tl, k = TIMELINE_NAME, nil, 2
tl = mediaPool:CreateEmptyTimeline(name)
while not tl and k < 50 do
  name = TIMELINE_NAME .. " " .. k
  tl = mediaPool:CreateEmptyTimeline(name)
  k = k + 1
end
if not tl then print("ERROR: could not create a new timeline."); return end

local ok = mediaPool:AppendToTimeline(clipInfos)
if not ok then print("ERROR: AppendToTimeline failed."); return end

local totalSec = 0
for _, ci in ipairs(clipInfos) do totalSec = totalSec + (ci.endFrame - ci.startFrame) / fps end
print(string.format("Done. Timeline '%s': %d segments, ~%.1f min. (%d skipped below conf %.2f)",
      name, kept, totalSec / 60, skipped, MIN_CONF))
