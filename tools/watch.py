#!/usr/bin/env python3
"""AirDrop watcher: edits split-screen (clone) videos with nobody asking.

Runs from launchd (~/Library/LaunchAgents/com.izaiahwest.clonewatch.plist) whenever
~/Downloads changes, and every 3 minutes.
  1. Looks at new videos in ~/Downloads (not screen recordings, portrait, 5 s - 10 min).
  2. Waits until AirDrop is done (no new or growing file for 2 minutes).
  3. Pairs takes: filmed within 20 min of each other + same shot (ceiling/headrest lines
     match) + him on opposite sides. A random video never pairs, so it's never touched.
  4. Moves each pair into raw/, edits it (clone.py; hook said together when both takes open
     with the same line), puts the video in final/ AND iCloud Drive/TikTok Edits/, and pops a
     Mac notification. Unpaired clips stay in Downloads; they're retried for 6 hours in case
     the partner shows up, then ignored.
Log: edits/watch.log. State: edits/watch_state.json.
"""
import datetime, fcntl, json, shutil, subprocess, sys, time, traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import edit as E  # noqa: E402
sys.modules["edit"] = E
import clone as C  # noqa: E402

DL = Path.home() / "Downloads"
ICLOUD = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/TikTok Edits"
SCRIPTS = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/TikTok Scripts"
CONFIG = Path.home() / ".clonewatch.json"   # {"imessage_to": "+1..."}; kept out of the repo
PICS = Path.home() / "Pictures" / "TikTok Edits"   # Messages can attach files from here
STATE = E.ROOT / "edits" / "watch_state.json"
LOCK = E.ROOT / "edits" / ".watch.lock"
SETTLE = 120          # s with no new / growing file before starting
GIVE_UP = 6 * 3600    # stop retrying an unpaired clip after this long


def log(msg):
    print(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def notify(title, text):
    subprocess.run(["osascript", "-e", f'display notification "{text}" with title "{title}"'],
                   capture_output=True)


SEND = """
on run argv
  tell application "Messages"
    set acc to missing value
    repeat with a in every account
      try
        if (service type of a as string) is "iMessage" and enabled of a then set acc to a
      end try
    end repeat
    set p to participant (item 1 of argv) of acc
    send (item 2 of argv) to p
    if (count of argv) > 2 then send (POSIX file (item 3 of argv)) to p
  end tell
end run
"""


REMIND = """
on run argv
  tell application "Reminders"
    if not (exists list "TikTok Editor") then make new list with properties {name:"TikTok Editor"}
    tell list "TikTok Editor"
      repeat with r in (every reminder whose completed is false)
        set completed of r to true
      end repeat
      make new reminder with properties {name:(item 1 of argv), body:(item 2 of argv), remind me date:((current date) + 20)}
    end tell
  end tell
end run
"""


def alert_me(title, body=""):
    """Phone alert with sound: a Reminder in his "TikTok Editor" list, due in 20 s, synced by
    iCloud. (Texts to himself never alert on his iPhone.) Older ones are ticked off so the list
    stays clean. His pick, 2026-11-18."""
    r = subprocess.run(["osascript", "-e", REMIND, title, body], capture_output=True, text=True, timeout=120)
    if r.returncode:
        log(f"alert failed: {r.stderr.strip()[:200]}")


def tell(title, body="", video=None):
    """Mac pop-up + phone alert (Reminders) + text with the video (to watch in Messages)."""
    notify(title, body)
    alert_me(title, body)
    text_me(f"{title}. {body}".strip(" ."), video)


def text_me(msg, video=None):
    """iMessage him (to himself) so his phone buzzes, with the video attached to preview."""
    try:
        to = json.loads(CONFIG.read_text()).get("imessage_to")
    except Exception:
        return
    if not to:
        return
    args = ["osascript", "-e", SEND, to, f"TikTok Editor: {msg}"]
    if video:
        PICS.mkdir(parents=True, exist_ok=True)
        dst = PICS / Path(video).name
        shutil.copy2(video, dst)
        args.append(str(dst))
    r = subprocess.run(args, capture_output=True, text=True, timeout=120)
    if r.returncode:
        log(f"text failed: {r.stderr.strip()[:200]}")


def candidates(state):
    out = []
    for f in sorted(DL.iterdir()):
        if f.suffix.lower() not in E.VIDEO_EXT or f.name.lower().startswith("screenrecording"):
            continue
        key = f"{f.name}:{f.stat().st_size}"
        if key in state["ignored"] or key in state["used"]:
            continue
        out.append(f)
    return out


def looks_like_take(f):
    """Portrait phone video, 5 s - 10 min."""
    try:
        info = json.loads(E.sh([E.FP, "-v", "error", "-select_streams", "v:0", "-show_entries",
                                "stream=width,height:stream_side_data=rotation:format=duration",
                                "-of", "json", str(f)]).stdout)
        st = info["streams"][0]
        w, h = st["width"], st["height"]
        rot = abs(int(next((d.get("rotation", 0) for d in st.get("side_data_list", [])), 0)))
        if rot in (90, 270):
            w, h = h, w
        return h > w and 5 <= float(info["format"]["duration"]) <= 600
    except Exception:
        return False


def settled(files):
    if not files:
        return False
    if time.time() - max(f.stat().st_mtime for f in files) < SETTLE:
        return False
    sizes = {f: f.stat().st_size for f in files}
    time.sleep(5)
    return all(f.exists() and f.stat().st_size == s for f, s in sizes.items())


def into_raw(f):
    dest = E.ROOT / "raw" / f.name
    if dest.exists():
        if dest.stat().st_size == f.stat().st_size:
            f.unlink()          # same file AirDropped twice: use the copy we have
            return dest
        dest = dest.with_name(f"{f.stem}_{int(time.time())}{f.suffix}")
    shutil.move(str(f), dest)
    return dest


_last = None


def one_pass(state):
    """Edit every pair that's ready. Returns how many videos were made (0 = nothing to do)."""
    global _last
    files = [f for f in candidates(state) if looks_like_take(f)]
    keys = sorted(f"{f.name}:{f.stat().st_size}" for f in files)
    if keys == _last:   # nothing new since the last look (just leftovers waiting for a partner)
        return 0
    if not settled(files):
        return 0
    _last = keys
    now = time.time()
    for f in files:
        state["seen"].setdefault(f"{f.name}:{f.stat().st_size}", now)
    pairs, left = C.pair_takes(files)
    log(f"{len(files)} new clip(s): {len(pairs)} pair(s), {len(left)} unpaired")
    if pairs:
        msg = f"Got {len(files)} clip(s) → {len(pairs)} video(s). Editing now, about 3–5 min each."
        tell("🎬 Editing", msg)
    scripts = sorted(p for p in SCRIPTS.glob("*") if p.suffix.lower() in (".txt", ".md")) if SCRIPTS.exists() else []
    summary, made = [], 0
    for n, (a, b, why) in enumerate(pairs, 1):
        keys = [f"{x.name}:{x.stat().st_size}" for x in (a, b)]
        ra, rb = into_raw(a), into_raw(b)
        state["used"] += keys
        STATE.write_text(json.dumps(state, indent=1))
        log(f"editing {ra.name} + {rb.name} {why}")
        try:
            n0 = len(summary)
            status = C.process_clone([ra, rb], summary, None, "auto", scripts)
            out = E.ROOT / "final" / f"{ra.stem}_clone.mp4"
            if status == "needs_order":
                tell(f"⚠️ Video {n} of {len(pairs)} needs the script",
                     f"{ra.name} + {rb.name}: couldn't tell the order of the lines (you paused mid-turn). "
                     "Save the script in iCloud Drive › TikTok Scripts, or message Claude.")
            elif status == "ok" and out.exists():
                made += 1
                ICLOUD.mkdir(parents=True, exist_ok=True)
                shutil.copy2(out, ICLOUD / out.name)
                flag = " ⚠️ check this one" if any("⚠️" in x for x in summary[n0:]) else ""
                tell(f"✅ Video {n} of {len(pairs)} ready{flag}", "Watch it in Messages or Files › iCloud Drive › TikTok Edits.", out)
            log("\n".join(summary[n0:]))
        except Exception as e:
            summary.append(f"- **clone {ra.name} + {rb.name}**: FAILED: {e}")
            log(traceback.format_exc())
            tell(f"❌ Video {n} of {len(pairs)} failed", f"{ra.name} + {rb.name}. Message Claude.")
    stuck = []
    for f, why in left:
        key = f"{f.name}:{f.stat().st_size}"
        # filmed in the last day = probably a take we failed to pair (new location, phone bumped):
        # tell him instead of failing silently
        if now - C.shot_time(f) < 24 * 3600 and key not in state["notified"]:
            stuck.append(f.name)
            state["notified"].append(key)
        if now - state["seen"].get(key, now) > GIVE_UP:
            state["ignored"].append(key)
            log(f"ignoring {f.name} ({why}) after 6 h")
        else:
            log(f"left alone for now: {f.name} ({why})")
    STATE.write_text(json.dumps(state, indent=1))
    if summary:
        day = datetime.date.today().isoformat()
        sp = E.ROOT / "final" / f"SUMMARY-{day}.md"
        head = "" if sp.exists() else f"# Edits {day}\n\n"
        with sp.open("a") as fh:
            fh.write(head + "\n".join(summary) + "\n")
    if stuck:
        tell("⚠️ Clips not edited", f"Couldn't pair {len(stuck)} new clip(s): {', '.join(stuck[:3])}. Message Claude.")
    return made


def main():
    (E.ROOT / "edits").mkdir(exist_ok=True)
    lock = open(LOCK, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return  # another run is already editing; it keeps checking for new AirDrops itself
    state = json.loads(STATE.read_text()) if STATE.exists() else {"used": [], "ignored": [], "seen": {}}
    state.setdefault("notified", [])
    if not one_pass(state):
        return
    # He AirDrops a batch, goes back to filming, AirDrops more. Keep going: after each batch,
    # watch Downloads for up to 15 more minutes and edit whatever arrives, without waiting for launchd.
    quiet_since = time.time()
    while time.time() - quiet_since < 15 * 60:
        time.sleep(20)
        if one_pass(state):
            quiet_since = time.time()


if __name__ == "__main__":
    main()
