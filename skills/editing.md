# Skill: Edit his raw footage (overnight or on demand)

**Runs on:** Izaiah's Mac (tools in `~/miniforge3/bin`). Rules: CLAUDE.md Part 5 + `skills/edit-spec.md`.

## Getting footage in
- He AirDrops from his iPhone. AirDrop always lands in `~/Downloads`. Move new `.MOV`/`.MP4` files from `~/Downloads` into `raw/` (ask him which ones if anything in Downloads looks unrelated).
- One file can hold many videos: **one clap between videos**. The editor splits on claps automatically.

## Run
```bash
cd ~/My-ai-project && export PATH=~/miniforge3/bin:$PATH
caffeinate -i python tools/edit.py raw/          # everything in raw/ not already in final/
python tools/edit.py raw/IMG_1234.MOV --redo     # redo one file
python tools/edit.py raw/IMG_1234.MOV --no-split # a file with no claps that got split wrongly
```
Speed (tested 2026-11-15 on his Mac, 55 s of iPhone 4K/60 HEVC): about 1.5 min per minute of raw after a one-time proxy convert. 10 minutes of raw takes about 15–20 minutes.

## What it does (tools/edit.py)
0. Converts the iPhone file once to a 1080×1920/30 proxy (`edits/<name>/proxy.mov`), always using the first (normal) audio track, not the spatial-audio one. **iPhone HDR (HLG/Dolby Vision) goes through Apple's `avconvert` (Preset3840x2160) first.** Without that, colors come out flat and washed out. Output is tagged bt709.
1. Whisper (small.en) with word timestamps, once per file.
2. Clap split: sharp, loud peaks outside speech.
3. Picks words: drops "um/uh", stutters ("so so", but not across a sentence break) and **earlier attempts of a repeated line (keeps the last take)**. Works word by word, because he restarts mid-flow with no pause ("because every time… because every time…").
4. Cuts by the **audio level**, not Whisper's edges: splits on silence > 0.09 s (20 ms smoothed level, blips under 50 ms ignored), 10 ms before / 15 ms after, nearest-frame rounding (plus 60 ms on soft endings like s/sh/ly), meets dropped words at the quietest 10 ms, snaps to the 1/30 s grid without crossing into a dropped word.
5. Subtle zoom: 108% punch-in at a cut, or a slow push-in on one long still piece, only when the picture has been still for 3+ s.
6. Export 1080×1920, 30 fps, H.264 CRF 16, AAC 192k, -16 LUFS, limiter at -2 dBTP.
6b. Scrap check: pieces under 0.4 s must contain a real word (voice detector + Whisper; "Thank you." on noise is a known Whisper invention and doesn't count). Pieces under 0.1 s apart in the source are joined, so there are no 2-frame jumps.
7. QC on every video (`edits/<name>/qc.json` + `qc_hook/middle/end.jpg`): re-transcribe and diff (≥ 90% match), no doubled words he didn't say, no silences ≥ 0.12 s at -40 dB, loudness within 1 LU of -16. Fails get "⚠️ check this one" in the summary.

## After the run
- Look at each `qc_*.jpg` and every ⚠️ item. Fix or redo before calling it done.
- `final/SUMMARY-YYYY-MM-DD.md`: one line per video (length, cuts, zooms, retakes removed, hook). Add anything that needs him at the top.
- Move nothing out of `raw/` until he's happy with the edits.

## Not built yet
- **Product pop-in** (product image for about 1 s when he names it). Needs a product image per product (from the TikTok Shop listing). Build once we have his first real batch.
- Picking the best take by delivery (right now: last take wins).

## Known limits (from testing)
- First real clip (IMG_1926, 2026-11-15): 55 s raw → 18 s final, 6 retakes removed, all QC passed. Fixes it needed: word-level retake detection; a guard for words Whisper stretches over a sigh; speech threshold raised to 0.45 between noise and speech (a stray "bruh" leaked through at 0.3).
- QC compares **letters**, not words (Whisper re-hears "Melissa" as "Alyssa"; that's not a cut problem). Pass = 93%+.
- Still untested: car noise, claps on real footage, zooms on real footage (this clip had constant movement, so 0 zooms).
