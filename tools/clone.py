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


def analyze_take(raw, k):
    src = E.make_proxy(Path(raw))
    t = dict(raw=Path(raw), src=src, k=k, dur=E.probe(src))
    t["audio"] = E.load_audio(src)
    t["words"] = E.transcribe(t["audio"])
    t["env"] = E.env_ms(t["audio"])
    t["kept"], _, t["retakes"] = E.choose_words(t["words"])
    return t


def make_lines(t, script):
    kept = t["kept"]
    labels, cover = label_by_script(kept, script, t["k"]) if script else (None, None)
    t["script_match"] = cover
    groups = []
    for i, w in enumerate(kept):
        new = (not groups or (labels is not None and labels[i] != groups[-1]["key"])
               or (labels is None and w["s"] - groups[-1]["words"][-1]["e"] >= LINE_GAP))
        if new:
            groups.append(dict(key=labels[i] if labels else len(groups), words=[]))
        groups[-1]["words"].append(w)
    t["lines"] = []
    for g in groups:
        pcs = E.build_pieces(t["words"], g["words"], t["env"], 0.0, t["dur"])
        pcs, _ = E.clean_pieces(pcs, t["audio"])
        if pcs:
            t["lines"].append(dict(take=t["k"], key=g["key"], pieces=pcs, text=" ".join(w["w"] for w in g["words"])))
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
    a, b = takes[0]["lines"], takes[1]["lines"]
    if script:
        return sorted(a + b, key=lambda ln: (ln["key"], ln["take"]))
    out = []
    for i in range(max(len(a), len(b))):  # A, B, A, B... (take 1 talks first)
        out += a[i:i + 1] + b[i:i + 1]
    return out


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
        lis = "[1:v]setpts=PTS-STARTPTS[lis]"
    else:  # not enough quiet footage: play it forward then backward, repeated
        n = max(1, round(2 * glen * E.FPS))
        loops = math.ceil(dur / (2 * glen)) + 1
        lis = (f"[1:v]setpts=PTS-STARTPTS,split[f][r];[r]reverse[rv];[f][rv]concat=n=2:v=1:a=0,"
               f"loop=loop={loops}:size={n}:start=0,setpts=N/{E.FPS}/TB[lis]")
    L, R = ("[0:v]", "[lis]") if spk_left else ("[lis]", "[0:v]")
    fc = (f"{lis};[2:v]format=gray[m];{R}[m]alphamerge[ra];"
          f"{L}[ra]overlay=0:0:shortest=1:format=auto,format=yuv420p[v]")
    E.sh([E.FF, "-y", "-v", "error", "-i", str(spk_file),
          "-ss", f"{g0:.4f}", "-t", f"{glen + 0.1:.4f}", "-i", str(lis_src),
          "-loop", "1", "-i", str(mask),
          "-filter_complex", fc, "-map", "[v]", "-map", "0:a", "-t", f"{dur:.4f}",
          "-c:v", "libx264", "-crf", "10", "-preset", "veryfast", "-pix_fmt", "yuv420p",
          "-c:a", "pcm_s16le", str(out)])


def process_clone(raws, summary, script_path=None):
    raws = [Path(r) for r in raws]
    if len(raws) != 2:
        raise ValueError("clone needs exactly 2 takes (one per side)")
    stem = f"{raws[0].stem}_clone"
    work = ROOT_EDITS / stem
    work.mkdir(parents=True, exist_ok=True)
    script = read_script(script_path) if script_path else None
    takes = [analyze_take(r, k) for k, r in enumerate(raws)]
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
    lines = order_lines(takes, script)
    if len(lines) < 2:
        summary.append(f"- **{stem}**: skipped, found {len(lines)} line(s); need both takes talking.")
        return
    runs = []
    for ln in lines:
        if runs and runs[-1][0] == ln["take"]:
            runs[-1][1].append(ln)
        else:
            runs.append((ln["take"], [ln]))
    parts, plan = [], []
    for ri, (k, lns) in enumerate(runs):
        spk, lis = takes[k], takes[1 - k]
        pieces = [p for ln in lns for p in ln["pieces"]]
        spk_file = E.render_pieces(spk["src"], pieces, [0] * len(pieces), work, tag=f"r{ri:02d}_")
        d = E.probe(spk_file)
        prev = [ln for r in runs[:ri] if r[0] == lis["k"] for ln in r[1]]
        nxt = [ln for r in runs[ri + 1:] if r[0] == lis["k"] for ln in r[1]]
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
    intended = [w for ln in lines for w in ln["text"].split()]
    rep = E.qc(out, intended, work)
    seam_preview(out, seam, work)
    warn = []
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
        retakes=[t["retakes"] for t in takes]), indent=1))
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
