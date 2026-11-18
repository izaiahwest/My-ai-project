"""Clone videos: two of him on screen talking to each other (@dealswithkeelz style).

How he films it: phone on a stand, NOT touched between takes.
  Take 1: he stands on one side and says character A's lines, leaving a beat after each
          one (that's where B talks) and reacting like he's listening.
  Take 2: same spot for the phone, he stands on the other side and says B's lines.
Run:  python tools/edit.py --clone raw/A.MOV raw/B.MOV [--script script.txt]

What happens:
  1. Each take gets the normal edit: Whisper, drop ums/retakes, audio-level cuts.
  2. Each take's words are split into lines (on his pauses, or by matching a script).
  3. Lines are put in order: A, B, A, B... (or the script's order).
  4. Which side each take is on is detected from where he moves in the frame, so the
     order of the files doesn't matter for left/right.
  5. A seam is found through the background between him and him (where the two takes look
     the same and nothing moves). It can bend around an arm near the middle.
  6. For every stretch where one character talks, the talker comes from their take (jump
     cuts and all) and the other side shows the other take's quiet moments (listening /
     reacting). If there isn't enough quiet footage, it plays back and forth.
  7. Blend along the seam (80 px soft edge), join, loudness, export, QC as usual.
No masking/cut-out of his body: if he crosses the middle, the crossing arm gets cut off.
"""
import difflib, json, math, re, subprocess
from pathlib import Path

import numpy as np

import edit as E

LINE_GAP = 0.8      # a pause this long in a take ends a line (he leaves a beat for the other character)

# ---- Adjustable settings. Override any of them in clone_settings.json at the project root. ----
SETTINGS = dict(
    split_default=0.50,    # straight vertical split, CapCut style; 0.5 = center
    split_min=0.35,        # how far it may move to show a product (0.40 = a 40/60 split)
    split_max=0.65,
    feather_px=10,         # soft edge at 1080 wide
    split_keep=0.15,       # only move the split if the new spot is >15% better (no needless jumps)
    center_pull=0.25,      # how strongly it prefers the center
    turn_gap_ms=0,         # silence added between speakers (0 = his approved back-to-back pace)
    declick_ms=2,          # 2 ms ramp at each cut: stops clicks, not an audible fade (0 = off)
    crf=14,                # final H.264 quality (lower = better)
    audio_bitrate="320k",
)
_sf = Path(__file__).resolve().parent.parent / "clone_settings.json"
if _sf.exists():
    SETTINGS.update(json.loads(_sf.read_text()))
FEATHER = SETTINGS["feather_px"]
TW, TH = 270, 480   # thumbnail size for seam / side detection


# ---------- seam + sides ----------
def gray_frames(src, n=24):
    dur = E.probe(src)
    out = subprocess.run([E.FF, "-v", "error", "-i", str(src), "-vf",
                          f"fps={n / dur:.5f},scale={TW}:{TH},format=gray", "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    k = len(out) // (TW * TH)
    return np.frombuffer(out[: k * TW * TH], np.uint8).reshape(k, TH, TW).astype(np.float32)


def blur(a, r):
    k = np.ones(2 * r + 1) / (2 * r + 1)
    a = np.apply_along_axis(lambda v: np.convolve(v, k, "same"), 0, a)
    return np.apply_along_axis(lambda v: np.convolve(v, k, "same"), 1, a)


def person_side(fa, fb):
    """> 0: take a is on the LEFT. Uses where things move (him) in each take."""
    sa, sb = fa.std(0).mean(0), fb.std(0).mean(0)
    h = len(sa) // 2
    return float((sa[:h].mean() - sa[h:].mean()) - (sb[:h].mean() - sb[h:].mean()))


def find_seam(fl, fr):
    """Seam (x per thumbnail row) through background that looks the same in both takes and
    where nothing moves. Dynamic programming, like seam carving, kept to the middle 60%."""
    ml, mr = np.median(fl, 0), np.median(fr, 0)
    cost = blur(np.abs(ml - mr) + 2 * (fl.std(0) + fr.std(0)), 3)
    h, w = cost.shape
    lo, hi = int(w * 0.2), int(w * 0.8)
    big = 1e12
    C = np.full((h, w), big)
    C[0, lo:hi] = cost[0, lo:hi]
    back = np.zeros((h, w), int)
    xs = np.arange(w)
    pen = 0.5  # small cost for bending: straight unless there's a reason
    for y in range(1, h):
        p = C[y - 1]
        cand = np.stack([np.r_[big, p[:-1]] + pen, p, np.r_[p[1:], big] + pen])
        j = cand.argmin(0)
        C[y] = cand[j, xs] + cost[y]
        C[y, :lo] = big
        C[y, hi:] = big
        back[y] = xs + j - 1
    seam = np.zeros(h, int)
    seam[-1] = int(C[-1].argmin())
    for y in range(h - 1, 0, -1):
        seam[y - 1] = back[y, seam[y]]
    seam = np.convolve(np.pad(seam.astype(float), 7, mode="edge"), np.ones(15) / 15, "valid")
    rows = np.arange(h)
    ix = np.clip(seam.round().astype(int), 0, w - 1)
    stats = dict(
        seam_x=[int(seam.min() * 1080 / TW), int(seam.max() * 1080 / TW)],
        background_diff=round(float(np.abs(ml - mr)[rows, ix].mean()), 1),   # phone moved / light changed
        motion_on_seam=round(float((fl.std(0) + fr.std(0))[rows, ix].mean()), 1))  # he crossed the middle
    return seam, stats


def span_frames(src, start, dur, n=16):
    out = subprocess.run([E.FF, "-v", "error", "-ss", f"{start:.3f}", "-t", f"{max(dur, 0.1):.3f}", "-i", str(src),
                          "-vf", f"fps={n / max(dur, 0.1):.4f},scale={TW}:{TH},format=gray", "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    k = len(out) // (TW * TH)
    return np.frombuffer(out[: k * TW * TH], np.uint8).reshape(k, TH, TW).astype(np.float32)


def choose_split(fl, fr, prev_x=None):
    """Straight vertical split (CapCut style) for ONE turn, as a fraction of the width.
    Cost of each column = how different the two clips look there + how much moves there.
    Prefers the center; moves (within split_min..split_max) only when that clearly shows more,
    e.g. a product held toward the middle. Returns (x, stats)."""
    S = SETTINGS
    if len(fl) < 2 or len(fr) < 2:
        return (prev_x or S["split_default"]), None
    diff = np.abs(np.median(fl, 0) - np.median(fr, 0)).mean(0)
    motion = (fl.std(0) + fr.std(0)).mean(0)
    cost = np.convolve(diff + 2 * motion, np.ones(9) / 9, "same")
    xs = np.arange(int(S["split_min"] * TW), int(S["split_max"] * TW) + 1)
    c0 = float(np.median(cost[xs])) + 1e-6
    score = cost[xs] / c0 + S["center_pull"] * np.abs(xs / TW - S["split_default"]) / 0.15
    best = int(xs[np.argmin(score)])
    x = best / TW
    if prev_x is not None:  # keep the previous spot unless the new one is clearly better
        ip = int(round(prev_x * TW))
        if xs[0] <= ip <= xs[-1] and score[ip - xs[0]] <= score.min() * (1 + S["split_keep"]):
            x = prev_x
    ic = int(round(S["split_default"] * TW))
    if score[ic - xs[0]] <= score.min() * (1 + S["split_keep"]):
        x = S["split_default"]          # back to the center when the center is fine
    ix = int(round(x * TW))
    band = slice(max(0, ix - 3), ix + 4)
    st = dict(split=round(x, 3), background_diff=round(float(diff[band].mean()), 1),
              motion_on_seam=round(float(motion[band].mean()), 1))
    return x, st


def straight_mask(x, path, W=1080, H=1920):
    """0 = left take, 255 = right take; straight line at x (fraction), FEATHER px soft edge."""
    col = np.clip((np.arange(W) - x * W) / max(FEATHER, 1) + 0.5, 0, 1)
    img = np.tile((col * 255).round().astype(np.uint8), (H, 1))
    path.write_bytes(f"P5\n{W} {H}\n255\n".encode() + img.tobytes())


def read_script(path):
    """Lines like 'A: ...' / 'B: ...' (also L/R, left/right, or two names: first name = take 1).
    Returns [(take_index, text)]."""
    out, names = [], {}
    for raw in Path(path).read_text().splitlines():
        m = re.match(r"\s*([^:]{1,20}):\s*(.*\S)", raw)
        if not m:
            if out and raw.strip():
                out[-1] = (out[-1][0], out[-1][1] + " " + raw.strip())
            continue
        who = m.group(1).strip().lower()
        k = {"a": 0, "l": 0, "left": 0, "b": 1, "r": 1, "right": 1}.get(who)
        if k is None:
            k = min(1, names.setdefault(who, len(names)))
        out.append((k, m.group(2)))
    return out


def label_by_script(kept, script, take):
    """Which script line each kept word belongs to (by matching words)."""
    sw, owner = [], []
    for gi, (k, text) in enumerate(script):
        if k == take:
            for t in text.split():
                if E.norm(t):
                    sw.append(E.norm(t))
                    owner.append(gi)
    if not sw or not kept:
        return None, 0.0
    kw = [E.norm(w["w"]) for w in kept]
    lab = [None] * len(kw)
    blocks = difflib.SequenceMatcher(None, kw, sw, autojunk=False).get_matching_blocks()
    for a, b, n in blocks:
        for i in range(n):
            lab[a + i] = owner[b + i]
    # words that didn't match ("40" vs "forty", ad-libs) join the nearer line in time
    known = [i for i, x in enumerate(lab) if x is not None]
    if not known:
        return None, 0.0
    out = list(lab)
    for i, x in enumerate(lab):
        if x is None:
            p = max((j for j in known if j < i), default=None)
            n = min((j for j in known if j > i), default=None)
            if p is None or (n is not None and lab[p] != lab[n]
                             and kept[n]["s"] - kept[i]["e"] < kept[i]["s"] - kept[p]["e"]):
                out[i] = lab[n]
            else:
                out[i] = lab[p]
    return out, sum(n for *_, n in blocks) / len(sw)


def expect(w):
    return 0.15 + 0.085 * len(E.norm(w["w"]))


def eff_s(w, t=None):
    """Whisper sometimes stretches a word over a long pause. Stretched BACKWARD ("no" lasting 8 s
    before a line): use a believable start. Stretched FORWARD ("all." running 2 s past the end of
    a sentence): the start is real. With the take's audio we can tell which: is he talking right
    at Whisper's start time?"""
    if w["e"] - w["s"] <= 1.6 * expect(w):
        return w["s"]
    if t is not None:
        sm = t.setdefault("_sm", 20 * np.log10(np.convolve(t["env"], np.ones(20) / 20, "same") + 1e-9))
        lvl = t.setdefault("_lvl", float(np.percentile(sm, 95)))
        a = sm[int(w["s"] * 1000):int(w["s"] * 1000) + 300]
        b = sm[max(0, int(w["e"] * 1000) - 300):int(w["e"] * 1000)]
        # talking at Whisper's start and not at its end -> stretched forward ("all." 1.0 vs 0.0);
        # otherwise stretched backward ("no" 0.77 vs 0.91, "I'm" 0.12 vs 0.93) - measured on his takes
        if len(a) and len(b) and (a > lvl - 15).mean() > (b > lvl - 15).mean():
            return w["s"]
    return max(w["s"], w["e"] - 1.3 * expect(w))


def raw_groups(t, n=3):
    """First n stretches of talk in the take, split on pauses (index ranges into t["words"])."""
    ws, out, a = t["words"], [], 0
    for i in range(1, len(ws) + 1):
        if i == len(ws) or eff_s(ws[i], t) - ws[i - 1]["e"] >= LINE_GAP:
            out.append((a, i))
            a = i
            if len(out) == n:
                break
    return out


def analyze_take(raw, k, together=False):
    src = E.make_proxy(Path(raw))
    t = dict(raw=Path(raw), src=src, k=k, dur=E.probe(src))
    t["audio"] = E.load_audio(src)
    t["words"] = E.transcribe(t["audio"])
    t["env"] = E.env_ms(t["audio"])
    set_kept(t, together)
    return t


def set_kept(t, together, hook=None):
    """hook = (start, end) word range of the hook said together. Words before it are a false
    start ("I'm definitely the boy-"), dropped."""
    if together:
        # the hook is said by both at once: it's its own line, never a "retake" of a later line
        lo, hi = hook or raw_groups(t, 1)[0]
        k1, _, r1 = E.choose_words(t["words"][lo:hi])
        k2, _, r2 = E.choose_words(t["words"][hi:])
        if lo:
            r1 = [" ".join(w["w"] for w in t["words"][:lo])] + r1
        t["kept"], t["retakes"], t["hook_n"] = k1 + k2, r1 + r2, len(k1)
    else:
        t["kept"], _, t["retakes"] = E.choose_words(t["words"])
        t["hook_n"] = 0


def same_hook(takes):
    """Both takes open with the same line -> say it together (his call 2026-11-18: together
    when the lines match, normal back-and-forth when they don't). Compares each take's first
    3 stretches of talk and picks the best-matching pair, so a false start before the hook
    ("I'm definitely the boy-" then "I'm definitely the better boyfriend.") is skipped."""
    ga, gb = raw_groups(takes[0]), raw_groups(takes[1])
    txt = lambda t, g: letters(w["w"] for w in t["words"][g[0]:g[1]])
    best = max(((difflib.SequenceMatcher(None, txt(takes[0], a), txt(takes[1], b), autojunk=False).ratio(), a, b)
                for a in ga for b in gb if b[1] - b[0] >= 2 and a[1] - a[0] >= 2), default=(0, None, None))
    if best[0] >= 0.75:
        set_kept(takes[0], True, best[1])
        set_kept(takes[1], True, best[2])
        return True
    for t in takes:
        set_kept(t, False)
    return False


def trim_edges(pcs, t, words, drop_db):
    """Cut a line right where its loud waveform starts / ends, judged against THIS line's own
    voice level (drop_db under it). Clone takes are mostly silence, so the whole-take threshold
    kept breaths / car noise at line edges. His feedback 2026-11-18: 'back to back to back',
    'right after the louder waveform, boom, cut'. Never more than 0.12 s into Whisper's
    first/last word; Whisper re-checks the result (see tight_line)."""
    if not pcs or not words:
        return pcs
    sm = 20 * np.log10(np.convolve(t["env"], np.ones(20) / 20, "same") + 1e-9)
    a, b = int(eff_s(words[0]) * 1000), int(words[-1]["e"] * 1000)
    if b - a < 80:
        return pcs
    thr = np.percentile(sm[a:b], 85) - drop_db
    pcs = [list(p) for p in pcs]
    i, stop = int(pcs[0][0] * 1000), min(int((eff_s(words[0]) + 0.12) * 1000), int(pcs[0][1] * 1000) - 40)
    while i < stop and sm[i] <= thr:
        i += 1
    pcs[0][0] = max(pcs[0][0], np.floor((i / 1000 - 0.005) * E.FPS) / E.FPS)
    j, stop = int(pcs[-1][1] * 1000) - 1, max(int((words[-1]["e"] - 0.12) * 1000), int(pcs[-1][0] * 1000) + 40)
    while j > stop and sm[j] <= thr:
        j -= 1
    pcs[-1][1] = min(pcs[-1][1], np.ceil((j / 1000 + 0.010) * E.FPS) / E.FPS)
    return [(float(x), float(y)) for x, y in pcs if y - x >= 1 / E.FPS]


def letters(ws):
    return "".join(E.norm(w) for w in ws)


def tight_line(pcs, t, words):
    """Tightest edge trim that still keeps every word: try cutting 7 dB under his voice, check
    with Whisper that the first and last words are still heard; back off to 10, then 13 dB."""
    want = letters(w["w"] for w in words)
    for drop in (7, 10, 13):
        cand = trim_edges(pcs, t, words, drop)
        clip = np.concatenate([t["audio"][int(a * E.SR):int(b * E.SR)] for a, b in cand] or [np.zeros(1, np.float32)])
        clip = np.concatenate([np.zeros(int(0.3 * E.SR), np.float32), clip, np.zeros(int(0.3 * E.SR), np.float32)])
        segs, _ = E.model().transcribe(clip, word_timestamps=False, vad_filter=False, condition_on_previous_text=False)
        got = letters(" ".join(sg.text for sg in segs).split())
        sim = lambda x, y: difflib.SequenceMatcher(None, x, y, autojunk=False).ratio()
        if (sim(want, got) >= 0.9 and sim(want[:6], got[:6]) >= 0.65 and sim(want[-6:], got[-6:]) >= 0.65):
            return cand, drop
    return pcs, None


def make_lines(t, script):
    kept = t["kept"]
    labels, cover = label_by_script(kept, script, t["k"]) if script else (None, None)
    t["script_match"] = cover
    groups = []
    for i, w in enumerate(kept):
        new = (not groups or (t["hook_n"] and i == t["hook_n"])
               or (labels is not None and labels[i] != groups[-1]["key"])
               or (labels is None and eff_s(w, t) - groups[-1]["words"][-1]["e"] >= LINE_GAP))
        if new:
            groups.append(dict(key=labels[i] if labels else len(groups), words=[], hook=bool(t["hook_n"]) and i == 0))
        groups[-1]["words"].append(w)
    t["lines"] = []
    for g in groups:
        pcs = E.build_pieces(t["words"], g["words"], t["env"], 0.0, t["dur"])
        pcs, _ = E.clean_pieces(pcs, t["audio"])
        pcs, drop = tight_line(pcs, t, g["words"])
        if pcs:
            t["lines"].append(dict(take=t["k"], key=g["key"], pieces=pcs, hook=g["hook"], trim_db=drop,
                                   text=" ".join(w["w"] for w in g["words"])))
    t["quiet"] = quiet_spans(t)


def quiet_spans(t):
    """Stretches (s) where he isn't talking and isn't walking around: listening footage."""
    n = int(t["dur"] * 100)
    talk = np.zeros(n + 1, bool)
    for w in t["words"]:
        talk[max(0, int((w["s"] - 0.25) * 100)):int((w["e"] + 0.25) * 100)] = True
    for ln in t["lines"]:
        for s, e in ln["pieces"]:
            talk[max(0, int((s - 0.15) * 100)):int((e + 0.15) * 100)] = True
    # (no audio-level check: car/road noise is loud enough to look like talking all the time)
    m = E.motion_series(t["src"], 0, t["dur"])  # 10 fps
    busy = m > max(3 * float(np.median(m)), 1.5)  # walking in/out, reaching for the phone
    busy = np.convolve(busy, np.ones(7), "same") > 0  # +-0.3 s
    busy100 = np.repeat(busy, 10)[:n]
    talk[: len(busy100)] |= busy100
    # only footage of him in place: after he's settled (walked in) and before he walks off
    first = min((ln["pieces"][0][0] for ln in t["lines"]), default=0.0)
    last = max((ln["pieces"][-1][1] for ln in t["lines"]), default=t["dur"])
    b_idx = np.flatnonzero(busy)
    before, after = b_idx[b_idx / 10 < first], b_idx[b_idx / 10 > last]
    settle = (before.max() + 1) / 10 + 0.1 if len(before) else 0.0
    leave = after.min() / 10 - 0.1 if len(after) else t["dur"]
    talk[: int(settle * 100)] = True
    talk[int(leave * 100):] = True
    spans, i = [], 0
    while i < n:
        if not talk[i]:
            j = i
            while j < n and not talk[j]:
                j += 1
            if j - i >= 20:
                spans.append((i / 100, j / 100))
            i = j
        else:
            i += 1
    return spans


def order_lines(takes, script):
    """List of runs: (take, [lines]) or ("both", [hookA, hookB]) for a hook said together."""
    a, b = takes[0]["lines"], takes[1]["lines"]
    head = []
    if a and b and a[0]["hook"] and b[0]["hook"]:
        head = [("both", [a[0], b[0]])]
        a, b = a[1:], b[1:]
    if script:
        seq = sorted(a + b, key=lambda ln: (ln["key"], ln["take"]))
    else:
        seq = []
        first, second = (b, a) if head and len(b) > len(a) else (a, b)  # after a joint hook, whoever has more lines answers
        for i in range(max(len(a), len(b))):  # A, B, A, B... (take 1 talks first)
            seq += first[i:i + 1] + second[i:i + 1]
    runs = list(head)
    for ln in seq:
        if runs and runs[-1][0] == ln["take"]:
            runs[-1][1].append(ln)
        else:
            runs.append((ln["take"], [ln]))
    return runs


def pick_listening(t, region, need):
    """(start, length) of quiet footage from take t inside region (s). Prefer right after his
    last line (a reaction), or right before his first line."""
    r0, r1 = region
    cands = [(max(s, r0), min(e, r1)) for s, e in t["quiet"] if min(e, r1) - max(s, r0) >= 0.2]
    if not cands:  # nothing quiet in that window: the nearest quiet moment anywhere in the take
        mid = (r0 + r1) / 2
        ok = [q for q in t["quiet"] if q[1] - q[0] >= 0.2]
        cands = [min(ok, key=lambda q: abs((q[0] + q[1]) / 2 - mid))] if ok else [(r0, r0 + 1 / E.FPS)]
    fits = [c for c in cands if c[1] - c[0] >= need]
    if fits:
        if r0 <= 0.0:   # before his first line: the moment just before he speaks
            s, e = fits[-1]
            return e - need, need
        return fits[0][0], need
    s, e = max(cands, key=lambda c: c[1] - c[0])
    return s, max(e - s, 1 / E.FPS)


# ---------- render (frame-exact: every clip is N frames with exactly N x 1600 audio samples) ----------
def blend(left, right, mask, n, out, audio_file):
    """Left/right clips (N frames each) through the straight mask; audio copied untouched."""
    fc = (f"[0:v]setpts=PTS-STARTPTS[l];[1:v]setpts=PTS-STARTPTS[r];"
          f"[2:v]fps={E.FPS},setpts=PTS-STARTPTS,format=gray[m];"
          f"[r][m]alphamerge[ra];[l][ra]overlay=0:0:eof_action=repeat:format=auto,format=yuv420p[v]")
    E.sh([E.FF, "-y", "-v", "error", "-i", str(left), "-i", str(right),
          "-loop", "1", "-framerate", str(E.FPS), "-i", str(mask), "-i", str(audio_file),
          "-filter_complex", fc, "-map", "[v]", "-map", "3:a:0", "-frames:v", str(n),
          "-c:v", "libx264", "-qp", "0", "-preset", "ultrafast", "-bf", "0", "-pix_fmt", "yuv420p",
          "-c:a", "copy", str(out)])


def listener_clip(src, k0, n, avail, out):
    """N frames of the listener's real footage from frame k0. If the quiet stretch is shorter
    than N (avail frames), it plays forward then backward - flagged in QC, never hidden."""
    if avail >= n:
        E.cut_frames(src, k0, n, out, audio=False)
        return False
    m = max(1, avail)
    loops = math.ceil(n / (2 * m)) + 1
    E.cut_frames(src, k0, m, out.with_suffix(".seg.mov"), audio=False)
    E.sh([E.FF, "-y", "-v", "error", "-i", str(out.with_suffix(".seg.mov")), "-filter_complex",
          f"[0:v]split[f][r];[r]reverse[rv];[f][rv]concat=n=2:v=1:a=0,loop=loop={loops}:size={2 * m}:start=0,"
          f"setpts=N/{E.FPS}/TB[v]", "-map", "[v]", "-frames:v", str(n),
          "-c:v", "libx264", "-qp", "0", "-preset", "ultrafast", "-bf", "0", "-pix_fmt", "yuv420p", str(out)])
    out.with_suffix(".seg.mov").unlink()
    return True


def listener_plan(t, region, n, cuts, min_chunk=30):
    """Real footage of the listener for n frames. First choice: one unbroken quiet stretch from
    between his own lines (a real reaction). If none is long enough: several real quiet stretches
    in a row, each switch placed on one of the talker's own cuts (cuts = frame offsets) so it
    reads as a normal jump cut. Returns [(source_frame, count)], or None if the take doesn't have
    enough quiet footage at all."""
    fr_ = lambda x: int(round(x * E.FPS))
    g0, glen = pick_listening(t, region, n / E.FPS)
    if fr_(glen) >= n:
        return [(fr_(g0), n)]
    r0, r1 = region
    mid = (r0 + r1) / 2
    spans = sorted(((fr_(a), fr_(b) - fr_(a)) for a, b in t["quiet"] if fr_(b) - fr_(a) >= min_chunk),
                   key=lambda sp: (not (r0 - 0.5 <= sp[0] / E.FPS <= r1 + 0.5), abs(sp[0] / E.FPS - mid)))
    plan, done = [], 0
    for k0, avail in spans:
        left = n - done
        if avail >= left:
            plan.append((k0, left))
            return plan
        # end this stretch on a talker cut if one falls inside it (and leaves >= 1 s)
        ok = [c - done for c in cuts if min_chunk <= c - done <= avail]
        take = max(ok) if ok else avail
        plan.append((k0, take))
        done += take
    return None


def mix_together(lf, rf, n, out):
    """Hook said together: both voices as recorded, added (no level changes)."""
    E.sh([E.FF, "-y", "-v", "error", "-i", str(lf), "-i", str(rf), "-filter_complex",
          f"[0:a][1:a]amix=inputs=2:normalize=0:duration=first,atrim=end_sample={n * E.SPF}[a]",
          "-map", "[a]", "-c:a", "pcm_s16le", "-ar", "48000", str(out)])


def pick_script(takes, paths):
    """Of his saved scripts, the one both takes match best (>= 60% of each side's words)."""
    best = (0.6, None)
    for pth in paths:
        try:
            sc = read_script(pth)
        except Exception:
            continue
        for order in ((0, 1), (1, 0)):
            cov = min(label_by_script(takes[i]["kept"], sc, k)[1] for i, k in zip((0, 1), order))
            if cov > best[0]:
                best = (cov, pth)
    return best[1]


def process_clone(raws, summary, script_path=None, together="auto", scripts=()):
    """together: True / False, or "auto" = together when both takes open with the same line.
    scripts: his saved scripts (iCloud Drive › TikTok Scripts); the best match is used for
    the order. Returns "ok", "needs_order" or "skipped"."""
    raws = [Path(r) for r in raws]
    if len(raws) != 2:
        raise ValueError("clone needs exactly 2 takes (one per side)")
    stem = f"{raws[0].stem}_clone" + ("_together" if together is True else "")
    work = ROOT_EDITS / stem
    work.mkdir(parents=True, exist_ok=True)
    takes = [analyze_take(r, k, together is True) for k, r in enumerate(raws)]
    if not script_path and scripts:
        script_path = pick_script(takes, scripts)
    script = read_script(script_path) if script_path else None
    if together == "auto":
        together = same_hook(takes)
    if script:  # files in the wrong order? the script says who says what
        cov = lambda t, k: label_by_script(t["kept"], script, k)[1]
        if cov(takes[0], 1) + cov(takes[1], 0) > cov(takes[0], 0) + cov(takes[1], 1):
            takes.reverse()
            raws.reverse()
            for k, t in enumerate(takes):
                t["k"] = k
    for t in takes:
        make_lines(t, script)
    # which side is each take on? (files can come in either order)
    fa, fb = gray_frames(takes[0]["src"]), gray_frames(takes[1]["src"])
    side_score = person_side(fa, fb)
    left = 0 if side_score >= 0 else 1
    seam, seam_stats = find_seam(*((fa, fb) if left == 0 else (fb, fa)))   # alignment check only
    runs = order_lines(takes, script)
    lines = [ln for _, lns in runs for ln in lns]
    if len(lines) < 2:
        summary.append(f"- **{stem}**: skipped, found {len(lines)} line(s); need both takes talking.")
        return "skipped"
    if not script:
        na, nb = (sum(1 for ln in t["lines"] if not ln["hook"]) for t in takes)
        if abs(na - nb) > 1:
            # He paused in the middle of his own turns (showing the product), so the takes split
            # into very different numbers of lines and A/B/A/B would scramble the conversation.
            # Don't guess (IMG_1930/1931, 2026-11-18: 6 vs 17 lines).
            summary.append(f"- **{stem}**: NOT edited, lines don't line up ({na} vs {nb}): needs the script "
                           f"(iCloud Drive › TikTok Scripts) or Claude to put them in order.")
            return "needs_order"
    S = SETTINGS
    fr_ = lambda t: int(round(t * E.FPS))
    gap = int(round(S["turn_gap_ms"] / 1000 * E.FPS))
    maskp = work / "mask.pgm"
    # ONE master timeline: every output frame maps to (take, source frame). Audio always comes
    # from the same frames as the picture, so nothing can slide out of sync.
    parts, plan, run_stats, timeline, looped_runs = [], [], [], [], []
    out_k, prev_x = 0, None
    for ri, (k, lns) in enumerate(runs):
        tl, tr, out = work / f"run{ri:02d}_L.mov", work / f"run{ri:02d}_R.mov", work / f"run{ri:02d}.mov"
        if k == "both":
            hl, hr = (lns[0], lns[1]) if left == 0 else (lns[1], lns[0])
            kl, kr = fr_(hl["pieces"][0][0]), fr_(hr["pieces"][0][0])
            n = max(fr_(hl["pieces"][-1][1]) - kl, fr_(hr["pieces"][-1][1]) - kr)
            E.cut_frames(takes[hl["take"]]["src"], kl, n, tl, declick_ms=S["declick_ms"])
            E.cut_frames(takes[hr["take"]]["src"], kr, n, tr, declick_ms=S["declick_ms"])
            x, rst = choose_split(span_frames(tl, 0, n / E.FPS), span_frames(tr, 0, n / E.FPS), prev_x)
            mix = work / f"run{ri:02d}_mix.wav"
            mix_together(tl, tr, n, mix)
            straight_mask(x, maskp)
            blend(tl, tr, maskp, n, out, mix)
            mix.unlink()
            timeline += [(out_k, n, hl["take"], kl, "left"), (out_k, n, hr["take"], kr, "right")]
            plan.append(dict(talker="both", start=round(out_k / E.FPS, 2), seconds=round(n / E.FPS, 2),
                             split=x, lines=[ln["text"] for ln in lns]))
        else:
            spk, lis = takes[k], takes[1 - k]
            pieces = [p for ln in lns for p in ln["pieces"]]
            if gap and ri < len(runs) - 1:   # optional beat after each turn: his own real footage
                pieces[-1] = (pieces[-1][0], min(spk["dur"], pieces[-1][1] + gap / E.FPS))
            pieces = [(a, b) for a, b in pieces if fr_(b) > fr_(a)]
            spk_file = E.render_pieces(spk["src"], pieces, [0] * len(pieces), work, tag=f"r{ri:02d}_",
                                       declick_ms=S["declick_ms"])
            n = sum(fr_(b) - fr_(a) for a, b in pieces)
            prev = [ln for r in runs[:ri] for ln in r[1] if ln["take"] == lis["k"]]
            nxt = [ln for r in runs[ri + 1:] for ln in r[1] if ln["take"] == lis["k"]]
            r0 = prev[-1]["pieces"][-1][1] + 0.1 if prev else 0.0
            r1 = nxt[0]["pieces"][0][0] - 0.15 if nxt else lis["dur"]
            if r1 <= r0:  # lines said out of order vs the script
                r0, r1 = 0.0, lis["dur"]
            cuts, c = [], 0
            for a, b in pieces:
                c += fr_(b) - fr_(a)
                cuts.append(c)
            lp = listener_plan(lis, (r0, r1), n, cuts)
            if lp:
                looped = False
                chunks = []
                for ci, (k0, cnt) in enumerate(lp):
                    cf = work / f"run{ri:02d}_c{ci}.mov"
                    E.cut_frames(lis["src"], k0, cnt, cf, audio=False)
                    chunks.append(cf)
                E.concat(chunks, tl)
                for cf in chunks:
                    cf.unlink()
                g0, glen = lp[0][0] / E.FPS, n / E.FPS
            else:   # last resort, flagged: the take has too little quiet footage
                g0, glen = pick_listening(lis, (r0, r1), n / E.FPS)
                looped = listener_clip(lis["src"], fr_(g0), n, int(round(glen * E.FPS)), tl)
                lp = [(fr_(g0), int(round(glen * E.FPS)))]
            if looped:
                looped_runs.append(round(out_k / E.FPS, 1))
            spk_left = k == left
            f_spk, f_lis = span_frames(spk_file, 0, n / E.FPS), span_frames(tl, 0, n / E.FPS)
            x, rst = choose_split(*((f_spk, f_lis) if spk_left else (f_lis, f_spk)), prev_x)
            straight_mask(x, maskp)
            blend(*((spk_file, tl) if spk_left else (tl, spk_file)), maskp, n, out, spk_file)
            spk_file.unlink()
            o = out_k
            for a, b in pieces:
                timeline.append((o, fr_(b) - fr_(a), k, fr_(a), "left" if spk_left else "right"))
                o += fr_(b) - fr_(a)
            plan.append(dict(talker="left" if spk_left else "right", take=spk["raw"].name,
                             start=round(out_k / E.FPS, 2), seconds=round(n / E.FPS, 2), split=x,
                             lines=[ln["text"] for ln in lns],
                             listening_from=[[round(a / E.FPS, 2), round(c / E.FPS, 2)] for a, c in lp],
                             listener_repeated=looped))
        for f in (tl, tr):
            if f.exists():
                f.unlink()
        run_stats.append(rst)
        prev_x = x
        parts.append(out)
        out_k += n
    joined = work / "joined.mov"
    E.concat(parts, joined)
    for p in parts:
        p.unlink()
    maskp.unlink()
    out = E.ROOT / "final" / f"{stem}.mp4"
    E.finish(joined, out, normalize=False, crf=S["crf"], abr=S["audio_bitrate"])
    joined.unlink()
    # ---------- checks on the finished file ----------
    intended = [w for k, lns in runs for ln in (lns[:1] if k == "both" else lns) for w in ln["text"].split()]
    rep = E.qc(out, intended, work)            # words (Whisper re-listen), doubled words, silences, frames
    tech = file_checks(out, out_k)
    sync = sync_check(out, timeline, takes)
    preview_split(out, plan, work)
    warn, review = [], []
    if tech["problems"]:
        warn += tech["problems"]
    if sync["checked"] == 0:
        warn.append("lip-sync could not be measured")
    elif not sync["ok"]:
        warn.append(f"lip-sync off by up to {sync['worst_ms']} ms at {sync['worst_at']} s")
    if rep["letter_match"] < 0.93 or rep["doubled"]:
        warn.append(f"words: {rep['letter_match']:.0%} match, missing {rep['missing'][:3]}, doubled {rep['doubled']}")
    if rep["silences"]:
        review.append(f"quiet gaps over 0.12 s at {[round(a, 1) for a, _ in rep['silences'][:5]]} s")
    align = edge_match(fa, fb)   # fixed lines (ceiling, walls, headrests): ~0.85-0.9 when the phone didn't move
    if align < 0.6:
        warn.append(f"the camera seems to have moved between takes (edge match {align:.2f}); the split may show")
    crossing = [pl["start"] for pl, r in zip(plan, run_stats) if r and r["motion_on_seam"] > 25]
    if crossing:
        review.append(f"something crosses the split (product/arm may be cut) at {crossing} s")
    if looped_runs:
        review.append(f"not enough real listening footage; the listener plays back and forth at {looped_runs} s")
    if abs(side_score) < 0.5:
        warn.append("couldn't tell which side each take is on; used the file order (first = left)")
    if script and min(t["script_match"] or 0 for t in takes) < 0.6:
        warn.append(f"lines only partly matched the script ({[round(t['script_match'] or 0, 2) for t in takes]})")
    xs = [pl["split"] for pl in plan]
    fl_, fr2 = (fa, fb) if left == 0 else (fb, fa)
    empty = empty_seat_frames(out, np.array([min(xs) * TW - FEATHER / 4, max(xs) * TW + FEATHER / 4]), fl_, fr2)
    if empty:
        warn.append(f"one side shows an empty spot (other take's background) at {empty[:8]} s")
    lv = speech_levels(out, timeline, left)
    if lv and abs(lv["left_db"] - lv["right_db"]) > 6:
        review.append(f"one side is {abs(lv['left_db'] - lv['right_db']):.0f} dB louder (as recorded; nothing was changed)")
    ok = not warn
    rep.update(clone=dict(left=raws[left].name, right=raws[1 - left].name, side_score=round(side_score, 2),
                          splits=[pl["split"] for pl in plan], levels=lv),
               tech=tech, sync=sync, warnings=warn, review=review, ok=ok)
    (work / "plan.json").write_text(json.dumps(dict(
        takes=[r.name for r in raws], left=raws[left].name, settings=SETTINGS, runs=plan,
        retakes=[t["retakes"] for t in takes], timeline=timeline,
        trim_db=[[ln.get("trim_db") for ln in t["lines"]] for t in takes]), indent=1, default=str))
    (work / "qc.json").write_text(json.dumps(rep, indent=1, default=str))
    E.JOINED.parent.mkdir(exist_ok=True)
    E.JOINED.write_text(json.dumps(sorted(E.joined_members() | {r.name for r in raws})))
    flag = "" if ok else " ⚠️ **check this one**"
    summary.append(
        f"- **{stem}** (clone: {raws[left].name} left, {raws[1 - left].name} right) · {tech['duration']} s · "
        f"{len(lines)} lines · {sum(len(t['retakes']) for t in takes)} retakes removed · words {rep['letter_match']:.0%} · "
        f"lip-sync {'✓' if sync['ok'] else '✗'} (worst {sync['worst_ms']} ms over {sync['checked']} points){flag}"
        + (f"\n  - Problems: {'; '.join(warn)}" if warn else "")
        + (f"\n  - Look at: {'; '.join(review)}" if review else ""))
    return "ok"


def empty_seat_frames(out, seam, fl, fr):
    """Frames where one side shows an empty seat (the other take's background) instead of him.
    Left side is compared with the RIGHT take's still background (his seat is empty there), and
    the other way round. Returns times (s)."""
    out_f = gray_frames_all(out)
    lo, hi = int(seam.min()) - 12, int(seam.max()) + 12
    ref_l, ref_r = np.median(fr, 0)[:, :max(lo, 1)], np.median(fl, 0)[:, min(hi, TW - 1):]
    dl = np.abs(out_f[:, :, :max(lo, 1)] - ref_l).mean((1, 2))
    dr = np.abs(out_f[:, :, min(hi, TW - 1):] - ref_r).mean((1, 2))
    bad = (dl < 0.4 * np.median(dl)) | (dr < 0.4 * np.median(dr))
    return [round(i / E.FPS, 2) for i in np.flatnonzero(bad)]


def gray_frames_all(src):
    out = subprocess.run([E.FF, "-v", "error", "-i", str(src), "-vf", f"scale={TW}:{TH},format=gray",
                          "-f", "rawvideo", "-"], capture_output=True).stdout
    k = len(out) // (TW * TH)
    return np.frombuffer(out[: k * TW * TH], np.uint8).reshape(k, TH, TW).astype(np.float32)


# ---------- pairing a batch of AirDropped takes ----------
PAIR_MINUTES = 20     # both halves of one video are filmed within this many minutes
PAIR_EDGES = 0.80     # ceiling/headrest edge match: real pair 0.89, same car another day 0.65-0.68
PAIR_SIDE = 2.0       # he must be on opposite sides (real pair 8.7)


def shot_time(path):
    try:
        info = json.loads(E.sh([E.FP, "-v", "error", "-show_format", "-of", "json", str(path)]).stdout)
        tags = info["format"].get("tags", {})
        t = tags.get("com.apple.quicktime.creationdate") or tags.get("creation_time")
        import datetime as dt
        return dt.datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()
    except Exception:
        return Path(path).stat().st_mtime


def key_thumbs(path, n=12):
    """Gray thumbnails from keyframes only (fast on 4K HEVC)."""
    out = subprocess.run([E.FF, "-v", "error", "-skip_frame", "nokey", "-i", str(path), "-map", "0:v:0",
                          "-vf", f"scale={TW}:{TH},format=gray", "-fps_mode", "vfr", "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    k = len(out) // (TW * TH)
    if k == 0:
        return None
    f = np.frombuffer(out[: k * TW * TH], np.uint8).reshape(k, TH, TW).astype(np.float32)
    return f[np.linspace(0, k - 1, min(n, k)).astype(int)]


def edge_match(fa, fb):
    """How well the fixed stuff (ceiling, headrests, windows) lines up: same mount = ~0.9."""
    def edges(m):
        gy, gx = np.gradient(blur(m, 1))
        g = np.hypot(gx, gy)[: TH // 3]
        return g - g.mean()
    a, b = edges(np.median(fa, 0)), edges(np.median(fb, 0))
    return float((a * b).sum() / np.sqrt((a * a).sum() * (b * b).sum() + 1e-9))


def pair_takes(files):
    """Sort by when they were filmed; pair neighbours that are the same shot with him on opposite
    sides. Returns (pairs, leftovers with reasons). A random video never pairs."""
    info = []
    for f in files:
        th = key_thumbs(f)
        if th is not None:
            info.append(dict(f=Path(f), t=shot_time(f), th=th))
    info.sort(key=lambda x: x["t"])
    pairs, left, i = [], [], 0
    while i < len(info):
        a = info[i]
        if i + 1 < len(info):
            b = info[i + 1]
            gap = (b["t"] - a["t"]) / 60
            em = edge_match(a["th"], b["th"])
            side = person_side(a["th"], b["th"])
            if gap <= PAIR_MINUTES and em >= PAIR_EDGES and abs(side) >= PAIR_SIDE:
                pairs.append((a["f"], b["f"], dict(minutes=round(gap, 1), edges=round(em, 2), side=round(side, 1))))
                i += 2
                continue
            why = (f"next clip filmed {gap:.0f} min later" if gap > PAIR_MINUTES else
                   f"not the same shot as the next clip (edges {em:.2f})" if em < PAIR_EDGES else
                   "same side as the next clip")
        else:
            why = "no partner clip"
        left.append((a["f"], why))
        i += 1
    return pairs, left


def file_checks(out, frames):
    """Container/stream checks: size, frame rate, frame count, A/V length, black/frozen frames, clipping."""
    info = json.loads(E.sh([E.FP, "-v", "error", "-show_entries",
                            "stream=codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,nb_frames,duration,sample_rate",
                            "-of", "json", str(out)]).stdout)["streams"]
    v = next(x for x in info if x["codec_type"] == "video")
    a = next(x for x in info if x["codec_type"] == "audio")
    vd, ad = float(v["duration"]), float(a["duration"])
    probs = []
    if (v["width"], v["height"]) != (1080, 1920):
        probs.append(f"size {v['width']}x{v['height']}")
    if v["r_frame_rate"] != f"{E.FPS}/1" or v["avg_frame_rate"] != f"{E.FPS}/1":
        probs.append(f"frame rate {v['avg_frame_rate']}")
    if int(v["nb_frames"]) != frames:
        probs.append(f"{v['nb_frames']} frames, timeline has {frames}")
    if abs(vd - ad) > 1.5 / E.FPS:   # AAC adds ~21 ms of padding at the end; more than that = wrong
        probs.append(f"audio {ad:.3f} s vs video {vd:.3f} s")
    err = subprocess.run([E.FF, "-v", "info", "-i", str(out), "-vf",
                          "blackdetect=d=0.1:pix_th=0.05,freezedetect=n=0.0008:d=0.4", "-af", "volumedetect",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    black = re.findall(r"black_start:([\d.]+)", err)
    frozen = re.findall(r"freeze_start: ([\d.]+)", err)
    peak = float((re.findall(r"max_volume: (-?[\d.]+) dB", err) or ["-99"])[-1])
    if black:
        probs.append(f"black frames at {black[:5]} s")
    if frozen:
        probs.append(f"frozen picture at {frozen[:5]} s")
    if peak >= -0.1:
        probs.append(f"audio hits 0 dBFS (possible clipping), peak {peak} dB")
    return dict(duration=round(vd, 2), audio_duration=round(ad, 3), frames=int(v["nb_frames"]),
                fps=v["avg_frame_rate"], size=f"{v['width']}x{v['height']}", peak_db=peak,
                black=black, frozen=frozen, problems=probs)


def _gray(src, k, count, side, W=135, H=240):
    """Gray thumbnails of frames k..k+count-1, only the talker's outer 35% (away from the split)."""
    seek = ["-ss", f"{(k - 0.5) / E.FPS:.6f}"] if k > 0 else []
    # setpts: without it a seeked batch repeats its first frame (made the check read 1 frame late)
    raw = subprocess.run([E.FF, "-v", "error", *seek, "-i", str(src), "-frames:v", str(count),
                          "-vf", f"setpts=PTS-STARTPTS,scale={W}:{H},format=gray", "-fps_mode", "passthrough",
                          "-f", "rawvideo", "-"], capture_output=True).stdout
    f = np.frombuffer(raw[: (len(raw) // (W * H)) * W * H], np.uint8).reshape(-1, H, W).astype(np.float32)
    c = int(W * 0.35)
    return f[:, :, :c] if side == "left" else f[:, :, W - c:]


def sync_check(out, timeline, takes, max_points=36):
    """Lip-sync measured, not assumed. At points spread over the whole video (start, middle and
    end, every turn), find (1) which source frame the talker's picture really is, and (2) where
    the audio really comes from (cross-correlation with the original recording). Both should
    point at the same moment. Reports the worst gap in ms; pass = within one frame (33 ms)."""
    segs = [t for t in timeline if t[1] >= 10]
    if not segs:
        return dict(ok=False, checked=0, worst_ms=None, worst_at=None, points=[])
    pick = sorted(set(np.linspace(0, len(segs) - 1, min(max_points, len(segs))).round().astype(int)))
    out_audio = E.load_audio(out)
    pts = []
    for i in pick:
        o0, n, take, k0, side = segs[i]
        m = n // 2
        o, k = o0 + m, k0 + m
        # picture: best-matching source frame within +-4 frames
        ov = _gray(out, o, 1, side)
        sv = _gray(takes[take]["src"], max(0, k - 4), 9, side)
        if len(ov) == 0 or len(sv) == 0:
            continue
        vlag = int(np.argmin(np.abs(sv - ov[0]).mean((1, 2)))) - (4 if k >= 4 else k)
        # audio: cross-correlate 0.5 s of output with the original +-0.15 s
        sr = E.SR
        a = out_audio[int((o / E.FPS - 0.25) * sr):int((o / E.FPS + 0.25) * sr)]
        src_a = takes[take]["audio"]
        b0 = int((k / E.FPS - 0.25 - 0.15) * sr)
        b = src_a[max(0, b0):int((k / E.FPS + 0.25 + 0.15) * sr)]
        if len(a) < sr * 0.4 or len(b) < len(a) or np.std(a) < 1e-4:
            continue
        a = (a - a.mean()) / (a.std() + 1e-9)
        c = np.correlate(b - b.mean(), a, "valid")
        lag_i = int(np.argmax(c))
        peak = float(c[lag_i] / (np.sqrt(np.convolve((b - b.mean()) ** 2, np.ones(len(a)), "valid")[lag_i]) * np.sqrt(len(a)) + 1e-9))
        if peak < 0.6:
            continue  # too quiet / too noisy to measure here
        alag_ms = ((max(0, b0) + lag_i) / sr - (k / E.FPS - 0.25)) * 1000
        vlag_ms = vlag * 1000 / E.FPS
        pts.append(dict(t=round(o / E.FPS, 2), video_ms=round(vlag_ms), audio_ms=round(alag_ms), gap_ms=round(alag_ms - vlag_ms)))
    if not pts:
        return dict(ok=False, checked=0, worst_ms=None, worst_at=None, points=[])
    worst = max(pts, key=lambda p: abs(p["gap_ms"]))
    return dict(ok=abs(worst["gap_ms"]) <= 1000 / E.FPS + 1, checked=len(pts), worst_ms=abs(worst["gap_ms"]),
                worst_at=worst["t"], points=pts)


def speech_levels(out, timeline, left):
    """Average speech level (dBFS) of each side in the finished file - reported, never changed."""
    a = E.load_audio(out)
    lv = {"left": [], "right": []}
    for o0, n, take, k0, side in timeline:
        seg = a[int(o0 / E.FPS * E.SR):int((o0 + n) / E.FPS * E.SR)]
        if len(seg):
            lv[side].append(float(np.percentile(np.abs(seg), 95)))
    if not lv["left"] or not lv["right"]:
        return None
    db = lambda xs: round(20 * np.log10(np.median(xs) + 1e-9), 1)
    return dict(left_db=db(lv["left"]), right_db=db(lv["right"]))


def preview_split(out, plan, work):
    """qc_split.jpg: a frame from the middle of every turn with the split drawn in red."""
    tiles = []
    for i, pl in enumerate(plan[:12]):
        t = pl["start"] + pl["seconds"] / 2
        raw = subprocess.run([E.FF, "-v", "error", "-ss", f"{t:.2f}", "-i", str(out), "-frames:v", "1",
                              "-vf", "scale=180:320", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True).stdout
        if len(raw) != 180 * 320 * 3:
            continue
        img = np.frombuffer(raw, np.uint8).reshape(320, 180, 3).copy()
        x = int(pl["split"] * 180)
        img[:, max(0, x - 1):x + 1] = (255, 0, 0)
        tiles.append(img)
    if tiles:
        sheet = np.concatenate(tiles, 1)
        ppm = work / "qc_split.ppm"
        ppm.write_bytes(f"P6\n{sheet.shape[1]} {sheet.shape[0]}\n255\n".encode() + sheet.tobytes())
        E.sh([E.FF, "-y", "-v", "error", "-i", str(ppm), str(work / "qc_split.jpg")])
        ppm.unlink()


ROOT_EDITS = E.ROOT / "edits"
