#!/usr/bin/env python3
"""Izaiah's auto-editor. Rules: CLAUDE.md Part 5 + skills/edit-spec.md.

Usage (on the Mac):
    export PATH=~/miniforge3/bin:$PATH
    python tools/edit.py raw/IMG_1234.MOV            # one file
    python tools/edit.py raw/                         # everything in raw/ not yet edited
    python tools/edit.py raw/x.MOV --no-split         # don't split on claps
    python tools/edit.py --join raw/a.MOV raw/b.MOV   # several clips -> one video
    python tools/edit.py --clone raw/a.MOV raw/b.MOV [--script s.txt]   # split-screen "two of me"
    python tools/edit.py --clone-batch raw/*.MOV                   # pair many takes, edit every pair

For each raw file:
  1. Split on claps (one clap between videos) into separate takes.
  2. Whisper with word timestamps.
  3. Drop fillers ("um", "uh"), false starts and repeated lines (keeps the LAST take).
  4. Split on any gap between words > 0.12 s, pad 20 ms before / 40 ms after,
     cut at the quietest 10 ms between words, never mid-word, snap to 1/30 s.
  5. Subtle zoom (~108%) only where the picture has been still for 3+ s.
  6. Export 1080x1920, 30 fps, H.264 CRF 16, AAC, -16 LUFS / -1.5 dBTP.
  7. QC: re-transcribe and diff, silencedetect at cuts, frames at hook / middle / end.
Outputs: final/<name>.mp4, edits/<name>/ (plan.json, qc.json, frames), and a line in
final/SUMMARY-YYYY-MM-DD.md. No captions, no top text (his calls).
"""
import argparse, datetime, difflib, json, re, subprocess, sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
BIN = Path.home() / "miniforge3" / "bin"
FF, FP = str(BIN / "ffmpeg"), str(BIN / "ffprobe")
SR = 16000
FPS = 30
GAP = 0.09           # split on gaps bigger than this (s). Was 0.12; he wants zero dead space (2026-11-15)
PRE, POST = 0.010, 0.015  # was 20/40 ms; tightened for zero dead space (2026-11-15)
ZOOM = 1.08
STILL_SECS = 3.0
FILLERS = {"um", "uh", "umm", "uhh", "erm", "hmm", "mm", "ah"}
SOFT_END = re.compile(r"(s|sh|ly|ch|ce|se|ss|x|z|f|th)$")
VIDEO_EXT = {".mov", ".mp4", ".m4v"}

_model = None


def model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel("small.en", device="cpu", compute_type="int8")
    return _model


def sh(args, **kw):
    r = subprocess.run(args, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise RuntimeError(f"{args[0]} failed:\n{r.stderr[-2000:]}")
    return r


def probe(path):
    info = json.loads(sh([FP, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]).stdout)
    return float(info["format"]["duration"])


def load_audio(path, start=0.0, dur=None):
    args = [FF, "-v", "error", "-ss", f"{start:.3f}"]
    if dur:
        args += ["-t", f"{dur:.3f}"]
    # iPhone files carry a 2nd "spatial audio" (APAC) track; always use the first, normal one
    args += ["-i", str(path), "-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    out = subprocess.run(args, capture_output=True).stdout
    return np.frombuffer(out, dtype=np.float32)


def transcribe(path_or_audio):
    segs, _ = model().transcribe(path_or_audio, word_timestamps=True, vad_filter=False,
                                 condition_on_previous_text=False)
    return [dict(s=w.start, e=w.end, w=w.word.strip(), p=w.probability) for s in segs for w in s.words]


def norm(w):
    return re.sub(r"[^a-z0-9']", "", w.lower())


# ---------- 1. clap split ----------
def find_claps(audio, words):
    """Claps: sharp, loud, short peaks outside speech. Returns times (s)."""
    hop = int(0.005 * SR)
    n = len(audio) // hop
    if n < 10:
        return []
    fr = audio[: n * hop].reshape(n, hop)
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-9)
    peak_db = np.percentile(db, 99.9)
    claps = []
    i = 10
    while i < n - 40:
        t = i * hop / SR
        before = db[max(0, i - 20):i].mean()
        after = db[i + 30:i + 40].mean()  # 150-200 ms later
        if db[i] > peak_db - 6 and db[i] - before > 20 and db[i] - after > 15:
            in_word = any(w["s"] - 0.05 <= t <= w["e"] + 0.05 for w in words)
            if not in_word:
                claps.append(t)
                i += 100  # 0.5 s refractory
                continue
        i += 1
    return claps


# ---------- 3. which words to keep ----------
def choose_words(words):
    """Walk the words in order. When he restarts a line (the next words repeat the start of
    something he just said), throw away the earlier attempt: the LAST take wins.
    He restarts mid-flow with no pause, so this works on words, not on pauses."""
    toks = [norm(w["w"]) for w in words]
    real = lambda x: toks[x] and toks[x] not in FILLERS

    def restart_at(kept, j):
        ahead = [toks[x] for x in range(j, min(j + 10, len(words))) if real(x)][:6]
        if len(ahead) < 2:
            return None
        best = None
        for p in range(max(0, len(kept) - 30), len(kept)):
            prev = [toks[x] for x in kept[p:p + 6]]
            exact = 0
            while exact < min(len(prev), len(ahead)) and prev[exact] == ahead[exact]:
                exact += 1
            finished = any(words[x]["w"].endswith((".", "?", "!")) for x in kept[p:-1])
            need = 4 if finished else 3
            fuzzy = (not finished and exact >= 2 and len(prev) >= 4 and len(ahead) >= 4
                     and difflib.SequenceMatcher(None, prev, ahead).ratio() >= 0.6)
            if exact >= need or fuzzy:
                best = p  # latest match = remove as little as possible
        return best

    kept, dropped, retakes = [], [], []
    for j in range(len(words)):
        if not real(j):
            dropped.append(words[j])
            continue
        prev = words[kept[-1]] if kept else None
        if (prev and toks[kept[-1]] == toks[j] and len(toks[j]) > 1   # "so so", not "...to it. It is..."
                and not prev["w"].endswith((".", "?", "!", ",")) and words[j]["s"] - prev["e"] < 0.4):
            dropped.append(words[j])
            continue
        p = restart_at(kept, j)
        if p is not None:
            gone = kept[p:]
            # "...gift. No, I have the best..." - Whisper often stretches the word right before a
            # restart ("no" lasting 8 s). That word really starts the new attempt: keep it.
            lead = None
            if len(gone) >= 2:
                w0 = words[gone[-1]]
                if (words[j]["s"] - w0["e"] < 0.15
                        and w0["e"] - w0["s"] > 1.6 * (0.15 + 0.085 * len(toks[gone[-1]]))):
                    lead = gone.pop()
            retakes.append(" ".join(words[x]["w"] for x in gone))
            dropped += [words[x] for x in gone]
            kept = kept[:p] + ([lead] if lead is not None else [])
        kept.append(j)
    return [words[x] for x in kept], dropped, retakes


# ---------- 4. cut points ----------
def env_ms(audio):
    hop = SR // 1000
    n = len(audio) // hop
    return np.sqrt((audio[: n * hop].reshape(n, hop) ** 2).mean(1))


def quietest(env, a, b, width=10):
    """Start time (s) of the quietest `width` ms window inside [a, b]."""
    ia, ib = int(a * 1000), int(b * 1000)
    if ib - ia <= width:
        return (a + b) / 2
    seg = env[ia:ib]
    sums = np.convolve(seg, np.ones(width), "valid")
    return (ia + int(np.argmin(sums)) + width / 2) / 1000


def snap(t):
    return round(t * FPS) / FPS


def speech_threshold(env, t0, t1):
    """Level (linear) that separates his voice from room/car noise in this take."""
    db = 20 * np.log10(env[int(t0 * 1000):int(t1 * 1000)] + 1e-9)
    noise, speech = np.percentile(db, 10), np.percentile(db, 90)
    # 0.45 of the way from noise to speech (tuned on his first real clip, 2026-11-15:
    # 0.3 let room noise bridge the gap between a stray "bruh" and the next line)
    return 10 ** (max(noise + 0.45 * (speech - noise), noise + 6) / 20)


def build_pieces(words_all, kept, env, t0, dur):
    """Return [(start, end)] source times to keep.
    Whisper decides WHICH words stay; the audio level decides WHERE to cut (Whisper's
    word edges are often off by 100+ ms)."""
    if not kept:
        return []
    thr = speech_threshold(env, t0, dur)
    idx = {id(w): i for i, w in enumerate(words_all)}
    # runs of consecutive kept words (no dropped word in between)
    runs, cur = [], [kept[0]]
    for w in kept[1:]:
        if idx[id(w)] == idx[id(cur[-1])] + 1:
            cur.append(w)
        else:
            runs.append(cur)
            cur = [w]
    runs.append(cur)
    pieces = []
    for r in runs:
        first, last = r[0], r[-1]
        i0, i1 = idx[id(first)], idx[id(last)]
        # hard limits: never reach into a dropped neighbour word; meet it at the quietest 10 ms
        if i0 > 0:
            pe = words_all[i0 - 1]["e"]
            lo = quietest(env, min(pe, first["s"]), max(pe, first["s"])) if abs(first["s"] - pe) > 0.012 else pe
        else:
            lo = t0
        if i1 + 1 < len(words_all):
            ns = words_all[i1 + 1]["s"]
            hi = quietest(env, min(last["e"], ns), max(last["e"], ns)) if abs(ns - last["e"]) > 0.012 else ns
        else:
            hi = dur
        lo, hi = max(lo, first["s"] - 0.3, t0), min(hi, last["e"] + 0.35, dur)
        # Whisper sometimes stretches a word over a sigh or noise ("because" lasting 1.5 s).
        # If a word is far longer than it should be, only trust the end near the next word.
        expect = lambda w: 0.15 + 0.085 * len(norm(w["w"]))
        stretched_first = first["e"] - first["s"] > 1.6 * expect(first)
        if stretched_first:
            lo = max(lo, first["e"] - 1.3 * expect(first))
        if last["e"] - last["s"] > 1.6 * expect(last):
            hi = min(hi, last["s"] + 1.3 * expect(last) + POST)
        if hi - lo < 0.05:  # a one-word line Whisper stretched at both ends: fall back to its own times
            lo, hi = max(t0, first["s"]), min(dur, max(last["e"], first["s"] + 0.1))
        # voiced regions inside the window, split on silences > GAP
        ia, ib = int(lo * 1000), int(hi * 1000)
        # 20 ms smoothed level: single 1 ms noise spikes (rustle, breath, clicks) must not
        # count as talking. (Unsmoothed, they chained together and kept 0.5-0.8 s pauses.)
        sm = np.convolve(env[max(0, ia - 10):ib + 10], np.ones(20) / 20, "same")[ia - max(0, ia - 10):][: ib - ia]
        voiced = sm > thr
        # blobs of sound, dropping blips under 50 ms
        blobs, k = [], 0
        while k < len(voiced):
            if voiced[k]:
                j = k
                while j < len(voiced) and voiced[j]:
                    j += 1
                if j - k >= 50:
                    blobs.append([k, j])
                k = j
            else:
                k += 1
        # join blobs separated by less than GAP (normal gaps inside a sentence)
        regions = []
        for b in blobs:
            if regions and b[0] - regions[-1][1] < GAP * 1000:
                regions[-1][1] = b[1]
            else:
                regions.append(b)
        regions = [((ia + a) / 1000, (ia + b) / 1000) for a, b in regions]
        regions = [g for g in regions if g[1] - g[0] >= 0.04] or [(first["s"], last["e"])]
        if stretched_first and len(r) >= 2:
            # Whisper's timing for that word is junk. The real word runs into the next one,
            # so drop any separate sound (sigh, "uh", lip smack) that sits before it.
            nxt = r[1]["s"]
            regions = [g for g in regions if g[1] >= nxt - 0.15 or g[0] >= nxt - 0.6] or regions
        soft = SOFT_END.search(norm(last["w"])) is not None
        tail_thr = thr * 0.5  # about 6 dB under the speech threshold: a fading "s"/"sh"
        for n, (a, b) in enumerate(regions):
            e = b + POST
            if soft and n == len(regions) - 1:
                # let a soft ending finish, but only while there's still sound
                k = int(b * 1000)
                while k < int((b + 0.1) * 1000) and k < len(env) and env[k] > tail_thr:
                    k += 1
                e = max(e, k / 1000 + 0.01)
            s = max(lo, a - PRE)
            e = min(hi, e)
            # frame grid: round to the NEAREST frame (rounding outward added up to 2 frames of
            # dead air per cut). The 20 ms smoothing already starts ~10 ms before the sound and
            # ends ~10 ms after, so nearest-frame rounding never clips a word.
            s = np.round(s * FPS) / FPS
            if s < lo - 1e-6:
                s = np.ceil(lo * FPS) / FPS
            e = np.round(e * FPS) / FPS
            if e > hi + 1e-6:
                e = np.floor(hi * FPS) / FPS
            s, e = float(s), float(e)
            if e - s >= 1 / FPS:
                pieces.append([round(s, 4), round(e, 4)])
    merged = []
    for p in pieces:
        if merged and p[0] <= merged[-1][1] + 1e-6:
            merged[-1][1] = max(merged[-1][1], p[1])
        else:
            merged.append(p)
    return [tuple(p) for p in merged]


# ---------- 5. stillness / zoom ----------
def motion_series(src, start, dur):
    """Mean abs frame difference at 10 fps on a 64x114 gray thumbnail."""
    w, h = 64, 114
    out = subprocess.run([FF, "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(src),
                          "-vf", f"fps=10,scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    fr = np.frombuffer(out, np.uint8)
    n = len(fr) // (w * h)
    if n < 2:
        return np.zeros(1)
    fr = fr[: n * w * h].reshape(n, h, w).astype(np.int16)
    return np.abs(np.diff(fr, axis=0)).mean((1, 2))


def plan_zooms(src, pieces):
    """Decide per piece: 0 = normal, 1 = punched in, 2 = slow push-in. Still = little motion for 3+ s."""
    MOVE = 4.0  # mean abs diff above this = something moving (tuned on reference clips)
    plan, still_run, zoomed = [], 0.0, False
    for s, e in pieces:
        m = motion_series(src, s, e - s)
        moving = (m > MOVE).mean() > 0.25
        d = e - s
        if moving:
            still_run, z = 0.0, 0
        elif still_run >= STILL_SECS:
            z = 0 if zoomed else 1      # alternate in/out on cuts while it stays still
            still_run = 0.0 if z == 1 else still_run + d
        elif d >= STILL_SECS:
            z = 2                       # one long still piece: slow push-in
            still_run = 0.0
        else:
            z = 0
            still_run += d
        zoomed = z == 1
        plan.append(z)
    return plan


# ---------- 6. render ----------
def render_pieces(src, pieces, zplan, work, tag="p"):
    """Cut the pieces out of src and join them (near-lossless). Returns the joined file."""
    parts = []
    for i, ((s, e), z) in enumerate(zip(pieces, zplan)):
        d = e - s
        base = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30"
        if z == 1:
            vf = f"{base},scale=iw*{ZOOM}:ih*{ZOOM},crop=1080:1920"
        elif z == 2:
            # slow push-in 100% -> 108% across the piece
            vf = (f"{base},scale=1620:2880,zoompan=z='1+{ZOOM - 1}*on/{max(1, int(d * FPS))}'"
                  f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30")
        else:
            vf = base
        af = f"afade=t=in:d=0.004,afade=t=out:st={max(0, d - 0.006):.3f}:d=0.006"
        p = work / f"{tag}{i:04d}.mov"
        sh([FF, "-y", "-v", "error", "-ss", f"{s:.4f}", "-t", f"{d:.4f}", "-i", str(src),
            "-map", "0:v:0", "-map", "0:a:0", "-vf", vf, "-af", af, "-ar", "48000", "-ac", "2",
            "-c:v", "libx264", "-crf", "10", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "pcm_s16le", str(p)])
        parts.append(p)
    joined = work / f"{tag}_joined.mov"
    concat(parts, joined)
    for p in parts:
        p.unlink()
    return joined


def concat(parts, out):
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{Path(p).resolve()}'\n" for p in parts))
    sh([FF, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)])
    lst.unlink()


def finish(joined, out_path):
    """Loudness: measure, apply one gain to hit -16 LUFS, then a true-peak limiter at about -2 dBTP.
    Final encode 1080x1920/30, H.264 CRF 16, AAC 192k, bt709."""
    r = subprocess.run([FF, "-i", str(joined), "-af", "ebur128", "-vn", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    measured = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", r)[-1])
    gain = -16.0 - measured
    for _ in range(3):  # the limiter eats some loudness on bumpy (car) audio: re-measure and top up
        af = (f"volume={gain:.2f}dB,aresample=192000,alimiter=limit={10 ** (-2.0 / 20):.4f}"
              f":attack=1:release=50:level=false,aresample=48000")
        tmp = Path(str(joined) + ".wav")
        sh([FF, "-y", "-v", "error", "-i", str(joined), "-vn", "-af", af, "-ar", "48000", str(tmp)])
        r = subprocess.run([FF, "-i", str(tmp), "-af", "ebur128", "-f", "null", "-"],
                           capture_output=True, text=True).stderr
        got = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", r)[-1])
        tmp.unlink()
        if abs(got + 16) <= 0.4:
            break
        gain += -16.0 - got
    sh([FF, "-y", "-v", "error", "-i", str(joined), "-af", af, "-ar", "48000",
        "-c:v", "libx264", "-crf", "16", "-preset", "slow", "-pix_fmt", "yuv420p", "-r", "30",
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
        "-movflags", "+faststart", "-c:a", "aac", "-b:a", "192k", str(out_path)])


def render(src, pieces, zplan, out_path, work):
    joined = render_pieces(src, pieces, zplan, work)
    finish(joined, out_path)
    joined.unlink()


# ---------- 7. QC ----------
def qc(out_path, intended, work):
    rep = {}
    words = transcribe(str(out_path))
    got = [norm(w["w"]) for w in words if norm(w["w"])]
    want = [norm(w) for w in intended if norm(w)]
    sm = difflib.SequenceMatcher(None, want, got)
    rep["word_match"] = round(sm.ratio(), 3)
    # letter-level match: "play mat" = "playmat", "Alyssa" ~ "Melissa" (Whisper re-hearing, not a cut)
    rep["letter_match"] = round(difflib.SequenceMatcher(None, "".join(want), "".join(got), autojunk=False).ratio(), 3)
    rep["missing"] = [" ".join(want[a:b]) for op, a, b, c, d in sm.get_opcodes() if op in ("delete", "replace")][:20]
    rep["extra"] = [" ".join(got[c:d]) for op, a, b, c, d in sm.get_opcodes() if op in ("insert", "replace")][:20]
    pairs = lambda xs: {(xs[i], xs[i + 1]) for i in range(len(xs) - 1) if xs[i] == xs[i + 1]}
    rep["doubled"] = sorted(a for a, _ in pairs(got) - pairs(want))  # doubles he didn't actually say
    sd = subprocess.run([FF, "-i", str(out_path), "-af", "silencedetect=n=-40dB:d=0.12", "-f", "null", "-"],
                        capture_output=True, text=True).stderr
    rep["silences"] = [(float(a), float(b)) for a, b in
                       re.findall(r"silence_start: ([\d.]+)[\s\S]*?silence_end: ([\d.]+)", sd)]
    lo = subprocess.run([FF, "-i", str(out_path), "-af", "ebur128=peak=true", "-f", "null", "-"],
                        capture_output=True, text=True).stderr
    rep["lufs"] = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", lo)[-1])
    rep["true_peak"] = float(re.findall(r"Peak:\s+(-?[\d.]+) dBFS", lo)[-1])
    d = probe(out_path)
    rep["duration"] = round(d, 2)
    for name, t in (("hook", 0.5), ("middle", d / 2), ("end", max(0, d - 1))):
        sh([FF, "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(out_path), "-frames:v", "1",
            "-vf", "scale=540:-1", str(work / f"qc_{name}.jpg")])
    rep["ok"] = (rep["letter_match"] >= 0.93 and not rep["doubled"] and not rep["silences"]
                 and abs(rep["lufs"] + 16) <= 1 and rep["true_peak"] <= -1.0)
    return rep


# ---------- driver ----------
def clean_pieces(pieces, audio):
    """1. Pieces almost touching in the source (< 0.1 s apart) become one: no 2-frame jump.
    2. Short pieces (< 0.4 s) must contain a real word. Whisper sometimes mis-times a word
       and leaves a scrap of a sigh or hand movement, which shows up as a flash of a
       different moment before the real line (his feedback, 2026-11-15)."""
    merged = []
    for s, e in pieces:
        if merged and s - merged[-1][1] < 0.1:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    out, scraps = [], []
    for s, e in merged:
        if e - s < 0.4:
            clip = audio[max(0, int((s - 0.05) * SR)):int((e + 0.05) * SR)]
            # voice-activity check first (Whisper alone invents "Thank you." on noise)
            segs, _ = model().transcribe(clip, word_timestamps=True, vad_filter=True,
                                         vad_parameters=dict(min_speech_duration_ms=80))
            got = [norm(w.word) for sg in segs for w in sg.words if w.probability >= 0.4]
            real_words = [g for g in got if g and g not in FILLERS]
            if not real_words or real_words in (["thank", "you"], ["you"], ["thanks"], ["bye"]):
                scraps.append([round(s, 2), round(e, 2)])
                continue
        out.append((s, e))
    return out, scraps


def edit_take(src, t0, t1, name, summary, audio, words_all):
    work = ROOT / "edits" / name
    work.mkdir(parents=True, exist_ok=True)
    out = ROOT / "final" / f"{name}.mp4"
    words = [w for w in words_all if w["s"] >= t0 - 0.05 and w["e"] <= t1 + 0.05]
    kept, dropped, retakes = choose_words(words)
    if len(kept) < 3:
        summary.append(f"- **{name}**: skipped, no usable speech found.")
        return
    env = env_ms(audio)
    pieces, scraps = clean_pieces(build_pieces(words, kept, env, t0, t1), audio)
    zplan = plan_zooms(src, pieces)
    (work / "plan.json").write_text(json.dumps(dict(
        source=str(src), span=[t0, t1], pieces=pieces, zooms=zplan,
        kept=" ".join(w["w"] for w in kept), dropped_retakes=retakes, dropped_scraps=scraps,
        dropped_words=[w["w"] for w in dropped]), indent=1))
    render(src, pieces, zplan, out, work)
    rep = qc(out, [w["w"] for w in kept], work)
    (work / "qc.json").write_text(json.dumps(rep, indent=1))
    flag = "" if rep["ok"] else " ⚠️ **check this one**"
    summary.append(
        f"- **{name}** · {rep['duration']} s · {len(pieces)} cuts · {sum(1 for z in zplan if z)} zooms · "
        f"{len(retakes)} retakes removed · words {rep['letter_match']:.0%} · {rep['lufs']} LUFS{flag}\n"
        f"  - Hook: \"{' '.join(w['w'] for w in kept[:14])}…\""
        + (f"\n  - Issues: doubled {rep['doubled']}, silences {rep['silences'][:3]}, missing {rep['missing'][:3]}"
           if not rep["ok"] else ""))


def make_proxy(src):
    """iPhone 4K/60 HEVC is slow to cut. Convert once to 1080x1920/30 (near-lossless) and edit from that."""
    work = ROOT / "edits" / src.stem
    work.mkdir(parents=True, exist_ok=True)
    proxy, tmp = work / "proxy.mov", work / "proxy_tmp.mov"
    if not proxy.exists():
        base = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30"
        trc = sh([FP, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=color_transfer",
                  "-of", "csv=p=0", str(src)]).stdout.strip().split(",")[0]
        vin = src
        if trc in ("arib-std-b67", "smpte2084"):
            # iPhone HDR (HLG / Dolby Vision). Without proper conversion colors come out flat
            # and washed out. Apple's own converter does the same tone-mapping the iPhone does
            # when sharing to a non-HDR app. 4K at about 25 Mbps, then we shrink it.
            vin = work / "sdr_tmp.mov"
            sh(["/usr/bin/avconvert", "--source", str(src), "--preset", "Preset3840x2160",
                "--output", str(vin), "--replace"])
        sh([FF, "-y", "-v", "error", "-i", str(vin), "-i", str(src),
            "-map", "0:v:0", "-map", "1:a:0", "-vf", base,
            "-c:v", "libx264", "-crf", "10", "-preset", "veryfast", "-g", "15", "-pix_fmt", "yuv420p",
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-c:a", "pcm_s16le", "-ar", "48000", "-shortest", str(tmp)])
        tmp.rename(proxy)
        if vin != src:
            vin.unlink()
    return proxy


JOINED = ROOT / "edits" / "joined.json"   # files that went into a joined video: skip them alone


def joined_members():
    return set(json.loads(JOINED.read_text())) if JOINED.exists() else set()


def process_joined(raws, summary):
    """Several clips -> ONE video, in the order given (he tells us which ones go together;
    by default every clip is its own video)."""
    raws = [Path(r) for r in raws]
    stem = f"{raws[0].stem}+{len(raws) - 1}"
    work = ROOT / "edits" / stem
    work.mkdir(parents=True, exist_ok=True)
    src = work / "proxy.mov"
    if not src.exists():
        proxies = [make_proxy(r) for r in raws]  # same format, so they join without re-encoding
        lst = work / "join.txt"
        lst.write_text("".join(f"file '{p.resolve()}'\n" for p in proxies))
        sh([FF, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(src)])
    JOINED.write_text(json.dumps(sorted(joined_members() | {r.name for r in raws})))
    process(raws[0], False, summary, src=src, stem=stem)


def process(raw, split, summary, src=None, stem=None):
    raw = Path(raw)
    stem = stem or raw.stem
    src = src or make_proxy(raw)
    dur = probe(src)
    spans = [(0.0, dur)]
    audio = load_audio(src)
    words = transcribe(audio)  # one pass for the whole file, reused per take
    if split:
        claps = find_claps(audio, words)
        if claps:
            edges = [0.0] + claps + [dur]
            spans = [(a + (0.15 if i else 0), b) for i, (a, b) in enumerate(zip(edges, edges[1:])) if b - a > 2]
    for i, (a, b) in enumerate(spans, 1):
        name = stem if len(spans) == 1 else f"{stem}_{i:02d}"
        print(f"editing {name} ({a:.1f}-{b:.1f}s)", flush=True)
        edit_take(src, a, b, name, summary, audio, words)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--no-split", action="store_true")
    ap.add_argument("--redo", action="store_true", help="re-edit files already in final/")
    ap.add_argument("--join", action="store_true",
                    help="put all the given clips together into ONE video, in the order given")
    ap.add_argument("--clone", action="store_true",
                    help="two takes from a phone that didn't move -> one split-screen 'two of me' video")
    ap.add_argument("--script", help="(clone) text file, lines like 'A: ...' / 'B: ...' (A = first take)")
    ap.add_argument("--together", action="store_true", help="(clone) force: both say the first line at once")
    ap.add_argument("--no-together", action="store_true", help="(clone) force: normal back-and-forth hook")
    ap.add_argument("--clone-batch", action="store_true",
                    help="many clone takes at once: pair them by filming time + same shot, edit each pair")
    a = ap.parse_args()
    files = []
    for x in map(Path, a.inputs):
        files += sorted(p for p in x.iterdir() if p.suffix.lower() in VIDEO_EXT) if x.is_dir() else [x]
    (ROOT / "final").mkdir(exist_ok=True)
    summary = []
    together = True if a.together else False if a.no_together else "auto"
    if a.clone or a.clone_batch:
        sys.modules.setdefault("edit", sys.modules[__name__])  # clone.py reuses this module
        import clone
        groups = [files]
        if a.clone_batch:
            pairs, left = clone.pair_takes(files)
            groups = [[x, y] for x, y, _ in pairs]
            summary += [f"- **{f.name}**: not edited ({why})" for f, why in left]
        for g in groups:
            try:
                clone.process_clone(g, summary, a.script, together)
            except Exception as e:
                summary.append(f"- **clone {[f.name for f in g]}**: FAILED: {e}")
        files = []
    if a.join:
        try:
            process_joined(files, summary)
        except Exception as e:
            summary.append(f"- **join {[f.name for f in files]}**: FAILED: {e}")
        files = []
    skip = joined_members()
    for f in files:
        if not a.redo and (any((ROOT / "final").glob(f"{f.stem}*.mp4")) or f.name in skip):
            print(f"skip {f.name} (already edited)")
            continue
        try:
            process(f, not a.no_split, summary)
        except Exception as e:  # keep going overnight; report it
            summary.append(f"- **{f.name}**: FAILED: {e}")
    if summary:
        day = datetime.date.today().isoformat()
        sp = ROOT / "final" / f"SUMMARY-{day}.md"
        head = "" if sp.exists() else f"# Edits {day}\n\n"
        with sp.open("a") as fh:
            fh.write(head + "\n".join(summary) + "\n")
        print("\n".join(summary))


if __name__ == "__main__":
    main()
