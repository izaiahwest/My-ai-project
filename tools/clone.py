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
FEATHER = 80        # px (of 1080) soft blend across the seam
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


def write_mask(seam, path, W=1080, H=1920):
    """Gray mask: 0 = left take, 255 = right take, soft ramp across the seam."""
    s = W / TW
    ys = np.linspace(0, len(seam) - 1, H)
    xs = np.interp(ys, np.arange(len(seam)), seam) * s + s / 2
    alpha = np.clip((np.arange(W)[None, :] - xs[:, None]) / FEATHER + 0.5, 0, 1)
    path.write_bytes(f"P5\n{W} {H}\n255\n".encode() + (alpha * 255).round().astype(np.uint8).tobytes())


# ---------- lines ----------
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


def eff_s(w):
    """Whisper sometimes stretches a word back over a long pause ("no" lasting 8 s); use a
    believable start for it."""
    return max(w["s"], w["e"] - 1.3 * expect(w)) if w["e"] - w["s"] > 1.6 * expect(w) else w["s"]


def first_group(words):
    for i in range(1, len(words)):
        if eff_s(words[i]) - words[i - 1]["e"] >= LINE_GAP:
            return i
    return len(words)


def analyze_take(raw, k, together=False):
    src = E.make_proxy(Path(raw))
    t = dict(raw=Path(raw), src=src, k=k, dur=E.probe(src))
    t["audio"] = E.load_audio(src)
    t["words"] = E.transcribe(t["audio"])
    t["env"] = E.env_ms(t["audio"])
    set_kept(t, together)
    return t


def set_kept(t, together):
    if together:
        # the hook is said by both at once: it's its own line, never a "retake" of a later line
        i = first_group(t["words"])
        k1, _, r1 = E.choose_words(t["words"][:i])
        k2, _, r2 = E.choose_words(t["words"][i:])
        t["kept"], t["retakes"], t["hook_n"] = k1 + k2, r1 + r2, len(k1)
    else:
        t["kept"], _, t["retakes"] = E.choose_words(t["words"])
        t["hook_n"] = 0


def same_hook(takes):
    """Both takes open with the same line -> say it together (his call 2026-11-18: together
    when the lines match, normal back-and-forth when they don't)."""
    for t in takes:
        set_kept(t, True)
    h = [letters(w["w"] for w in t["kept"][:t["hook_n"]]) for t in takes]
    ok = all(t["hook_n"] >= 2 for t in takes) and difflib.SequenceMatcher(None, h[0], h[1], autojunk=False).ratio() >= 0.75
    if not ok:
        for t in takes:
            set_kept(t, False)
    return ok


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
               or (labels is None and eff_s(w) - groups[-1]["words"][-1]["e"] >= LINE_GAP))
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


# ---------- render ----------
def composite(spk_file, spk_left, lis_src, g0, glen, dur, mask, out):
    """Talker on their side, listener on the other, blended through the mask."""
    if glen + 1e-3 >= dur:
        lis = f"[1:v]fps={E.FPS},setpts=PTS-STARTPTS[lis]"
    else:  # not enough quiet footage: play it forward then backward, repeated
        n = max(1, round(2 * glen * E.FPS))
        loops = math.ceil(dur / (2 * glen)) + 1
        lis = (f"[1:v]fps={E.FPS},setpts=PTS-STARTPTS,split[f][r];[r]reverse[rv];[f][rv]concat=n=2:v=1:a=0,"
               f"loop=loop={loops}:size={n}:start=0,setpts=N/{E.FPS}/TB[lis]")
    L, R = ("[spk]", "[lis]") if spk_left else ("[lis]", "[spk]")
    # Every stream re-timed to start at 0. Without this the talker's half was missing its first
    # frame at each switch, so the bare other take (an EMPTY seat) flashed for a frame - his
    # "pop in" (2026-11-18).
    fc = (f"[0:v]fps={E.FPS},setpts=PTS-STARTPTS[spk];{lis};"
          f"[2:v]fps={E.FPS},setpts=PTS-STARTPTS,format=gray[m];{R}[m]alphamerge[ra];"
          f"{L}[ra]overlay=0:0:eof_action=repeat:format=auto,format=yuv420p[v]")
    E.sh([E.FF, "-y", "-v", "error", "-i", str(spk_file),
          "-ss", f"{g0:.4f}", "-t", f"{glen + 0.1:.4f}", "-i", str(lis_src),
          "-loop", "1", "-framerate", str(E.FPS), "-i", str(mask),
          "-filter_complex", fc, "-map", "[v]", "-map", "0:a", "-t", f"{dur:.4f}",
          "-c:v", "libx264", "-crf", "10", "-preset", "veryfast", "-pix_fmt", "yuv420p",
          "-c:a", "pcm_s16le", str(out)])


def composite_together(src_l, s_l, src_r, s_r, dur, mask, out):
    """Hook said by both at once: each side plays its own take, voices mixed, starts lined up."""
    fc = (f"[0:v]fps={E.FPS},setpts=PTS-STARTPTS[l];[1:v]fps={E.FPS},setpts=PTS-STARTPTS[r];"
          f"[2:v]fps={E.FPS},setpts=PTS-STARTPTS,format=gray[m];"
          f"[r][m]alphamerge[ra];[l][ra]overlay=0:0:eof_action=repeat:format=auto,format=yuv420p[v];"
          f"[0:a][1:a]amix=inputs=2:normalize=0,afade=t=in:d=0.004,"
          f"afade=t=out:st={max(0, dur - 0.006):.3f}:d=0.006[a]")
    E.sh([E.FF, "-y", "-v", "error", "-ss", f"{s_l:.4f}", "-t", f"{dur + 0.1:.4f}", "-i", str(src_l),
          "-ss", f"{s_r:.4f}", "-t", f"{dur + 0.1:.4f}", "-i", str(src_r),
          "-loop", "1", "-framerate", str(E.FPS), "-i", str(mask),
          "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-t", f"{dur:.4f}", "-ar", "48000", "-ac", "2",
          "-c:v", "libx264", "-crf", "10", "-preset", "veryfast", "-pix_fmt", "yuv420p",
          "-c:a", "pcm_s16le", str(out)])


def process_clone(raws, summary, script_path=None, together="auto"):
    """together: True / False, or "auto" = together when both takes open with the same line."""
    raws = [Path(r) for r in raws]
    if len(raws) != 2:
        raise ValueError("clone needs exactly 2 takes (one per side)")
    stem = f"{raws[0].stem}_clone" + ("_together" if together is True else "")
    work = ROOT_EDITS / stem
    work.mkdir(parents=True, exist_ok=True)
    script = read_script(script_path) if script_path else None
    takes = [analyze_take(r, k, together is True) for k, r in enumerate(raws)]
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
    seam, seam_stats = find_seam(*((fa, fb) if left == 0 else (fb, fa)))
    mask = work / "mask.pgm"
    write_mask(seam, mask)
    runs = order_lines(takes, script)
    lines = [ln for _, lns in runs for ln in lns]
    if len(lines) < 2:
        summary.append(f"- **{stem}**: skipped, found {len(lines)} line(s); need both takes talking.")
        return
    parts, plan = [], []
    for ri, (k, lns) in enumerate(runs):
        if k == "both":
            hl, hr = (lns[0], lns[1]) if left == 0 else (lns[1], lns[0])
            sl, sr = hl["pieces"][0][0], hr["pieces"][0][0]
            d = round(max(hl["pieces"][-1][1] - sl, hr["pieces"][-1][1] - sr) * E.FPS) / E.FPS
            out = work / f"run{ri:02d}.mov"
            composite_together(takes[hl["take"]]["src"], sl, takes[hr["take"]]["src"], sr, d, mask, out)
            parts.append(out)
            plan.append(dict(talker="both", seconds=round(d, 2), lines=[ln["text"] for ln in lns]))
            continue
        spk, lis = takes[k], takes[1 - k]
        pieces = [p for ln in lns for p in ln["pieces"]]
        spk_file = E.render_pieces(spk["src"], pieces, [0] * len(pieces), work, tag=f"r{ri:02d}_")
        d = E.probe(spk_file)
        prev = [ln for r in runs[:ri] for ln in r[1] if ln["take"] == lis["k"]]
        nxt = [ln for r in runs[ri + 1:] for ln in r[1] if ln["take"] == lis["k"]]
        r0 = prev[-1]["pieces"][-1][1] + 0.1 if prev else 0.0
        r1 = nxt[0]["pieces"][0][0] - 0.15 if nxt else lis["dur"]
        if r1 <= r0:  # lines said out of order vs the script
            r0, r1 = 0.0, lis["dur"]
        g0, glen = pick_listening(lis, (r0, r1), d)
        out = work / f"run{ri:02d}.mov"
        composite(spk_file, k == left, lis["src"], g0, glen, d, mask, out)
        spk_file.unlink()
        parts.append(out)
        plan.append(dict(talker="left" if k == left else "right", take=spk["raw"].name, seconds=round(d, 2),
                         lines=[ln["text"] for ln in lns], listening_from=[round(g0, 2), round(glen, 2)],
                         back_and_forth=glen + 1e-3 < d))
    joined = work / "joined.mov"
    E.concat(parts, joined)
    for p in parts:
        p.unlink()
    out = E.ROOT / "final" / f"{stem}.mp4"
    E.finish(joined, out)
    joined.unlink()
    # a hook said together is heard once
    intended = [w for k, lns in runs for ln in (lns[:1] if k == "both" else lns) for w in ln["text"].split()]
    rep = E.qc(out, intended, work)
    seam_preview(out, seam, work)
    warn = []
    fl_, fr_ = (fa, fb) if left == 0 else (fb, fa)
    empty = empty_seat_frames(out, seam, fl_, fr_)
    if empty:
        warn.append(f"one side shows an empty seat at {empty[:8]} s (a 'pop in')")
    if seam_stats["background_diff"] > 18:  # 13.5 on his first real car test with a clean seam (hair near it)
        warn.append("the two takes don't line up (phone moved or the light changed); the middle may show a line")
    if seam_stats["motion_on_seam"] > 25:
        warn.append("something crosses the middle; an arm or product may get cut off there")
    if abs(side_score) < 0.5:
        warn.append("couldn't tell which side each take is on; used the file order (first = left)")
    if script and min(t["script_match"] or 0 for t in takes) < 0.6:
        warn.append(f"lines only partly matched the script ({[round(t['script_match'] or 0, 2) for t in takes]})")
    rep["clone"] = dict(left=raws[left].name, right=raws[1 - left].name, seam=seam_stats,
                        side_score=round(side_score, 2), warnings=warn)
    rep["ok"] = rep["ok"] and not warn
    (work / "plan.json").write_text(json.dumps(dict(
        takes=[r.name for r in raws], left=raws[left].name, seam=seam_stats, runs=plan,
        retakes=[t["retakes"] for t in takes],
        trim_db=[[ln.get("trim_db") for ln in t["lines"]] for t in takes], empty_seat_frames=empty), indent=1))
    (work / "qc.json").write_text(json.dumps(rep, indent=1))
    E.JOINED.parent.mkdir(exist_ok=True)
    E.JOINED.write_text(json.dumps(sorted(E.joined_members() | {r.name for r in raws})))
    flag = "" if rep["ok"] else " ⚠️ **check this one**"
    summary.append(
        f"- **{stem}** (clone: {raws[left].name} left, {raws[1 - left].name} right) · {rep['duration']} s · "
        f"{len(lines)} lines · {sum(len(t['retakes']) for t in takes)} retakes removed · "
        f"words {rep['letter_match']:.0%} · {rep['lufs']} LUFS{flag}"
        + (f"\n  - Issues: {'; '.join(warn)}" if warn else "")
        + (f"\n  - QC: doubled {rep['doubled']}, silences {rep['silences'][:3]}, missing {rep['missing'][:3]}"
           if not (rep["letter_match"] >= 0.93 and not rep["doubled"] and not rep["silences"]) else ""))


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


def seam_preview(out, seam, work):
    """qc_seam.jpg: middle frame with the seam drawn in red, for checking by eye."""
    d = E.probe(out)
    raw = subprocess.run([E.FF, "-v", "error", "-ss", f"{d / 2:.2f}", "-i", str(out), "-frames:v", "1",
                          "-vf", "scale=540:960", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True).stdout
    img = np.frombuffer(raw, np.uint8).reshape(960, 540, 3).copy()
    ys = np.linspace(0, len(seam) - 1, 960)
    xs = (np.interp(ys, np.arange(len(seam)), seam) * 540 / TW).astype(int)
    for y, x in enumerate(xs):
        img[y, max(0, x - 1):x + 2] = (255, 0, 0)
    ppm = work / "qc_seam.ppm"
    ppm.write_bytes(b"P6\n540 960\n255\n" + img.tobytes())
    E.sh([E.FF, "-y", "-v", "error", "-i", str(ppm), str(work / "qc_seam.jpg")])
    ppm.unlink()


ROOT_EDITS = E.ROOT / "edits"
