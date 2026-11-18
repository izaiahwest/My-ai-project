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
python tools/edit.py --join raw/IMG_2001.MOV raw/IMG_2002.MOV   # several clips -> ONE video, in this order
python tools/edit.py --clone raw/IMG_2001.MOV raw/IMG_2002.MOV [--script script.txt]   # split-screen "two of me"
```
**Which clips go together:** by default **every clip is its own video** (still split on claps). When Izaiah says clips belong together ("2001 and 2002 are one video"), run `--join` with them in the order he gives. Joined clips are listed in `edits/joined.json` so `raw/` runs don't edit them again on their own.
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

## Clone videos (two of him on screen, @dealswithkeelz style), `tools/clone.py`
**How he films it** (tell him this if he asks):
1. Phone on a stand. **Don't touch it between takes.** Same light (parked car or indoors; no sun moving across).
2. Take 1: stand on one side, say character A's lines. After each line, leave a beat and react like you're listening.
3. Take 2: stand on the other side, say B's lines the same way.
4. Stand still about a second before the first line. **Stay on your side of the middle**; anything crossing it gets cut off at the seam.
5. **Hook said together** (both say the first line at once, then B answers): he tells us per video. Run with `--together`. Default = not together.
6. AirDrop both and say "clone, 2001 and 2002" (+ the script if there is one: lines like `A: ...` / `B: ...`, A = the character who talks first).

**What it does:** edits each take normally (ums, retakes, audio cuts) → splits into lines (on pauses of 0.8 s+, or by matching the script) → orders them A, B, A, B (or script order; with a script, file order doesn't matter) → finds which side each take is on from where he moves → finds a seam through matching, still background (can bend around an arm) → talker from their take, the other side shows that take's quiet moments (right after their last line); too little quiet footage plays back and forth → 80 px soft blend → join, loudness, export, QC. No zooms in clone videos (they'd break the seam).
**Extra QC** (`edits/<name>_clone/qc.json` → `clone`, plus `qc_seam.jpg` with the seam drawn in red): background difference on the seam > 18 = phone moved or light changed; motion on the seam > 25 = he crossed the middle; can't tell sides; script matched < 60%. Any of these = ⚠️.
**Tested 2026-11-17** on fake takes only (two figures, two computer voices, one retake, files given in the wrong order, with and without script): right sides, right order, invisible seam, words 99%, 25 s to edit. **First real test 2026-11-18** (IMG_1922 driver + IMG_1923 passenger, his own Christmas-gift skit, 2:55 to edit): clean seam through the headrest, correct A/B order. Fixes it needed: car noise was read as talking (listening footage now uses words + motion only), a stretched "no" before a restart now stays with the new attempt, loudness re-measured after the limiter. **Pop-in fix (2026-11-18):** the talker's half was missing its first frame at each switch, so the bare other take (an empty seat) flashed. All streams are now re-timed to 0 at 30 fps, and QC checks every frame for an empty seat on either side (`empty_seat_frames` in plan.json; any = ⚠️). **Edge trim v2:** cut 7 dB under the line's own voice, Whisper re-listens to the trimmed line, and if the first/last word isn't heard it backs off to 10, then 13 dB (`trim_db` in plan.json). Test: 9.2 s, gaps at switches 26–129 ms.
Tightening (his feedback 2026-11-18, "back to back to back"): each line's start/end is trimmed against that line's own voice level (10 dB under it, never more than 0.1 s into Whisper's first/last word); test went 11.0 s → 9.6 s, longest gap at any switch 74 ms, all words kept. **Don't pass a script he didn't actually read**: it scrambles the order; with no script, A/B alternation was right. 3-character skits (rich / middle / poor) aren't supported yet.

## Clone system v2 (2026-11-18, his full spec) — how it works now
- **Lip-sync root cause (fixed):** pieces were cut with `-ss/-t`; video snapped to whole frames and could gain a frame per piece while audio didn't, and the loudness pass then closed the gaps, so audio crept ahead (52 s video: audio 0.57 s short). Now `edit.cut_frames()` cuts by frame number with exactly 1600 audio samples per frame (48 kHz / 30 fps); every clip's audio and video are identical in length, so no drift can build up. Intermediates are lossless (x264 qp 0). Also fixes one-person edits (same function).
- **One master timeline:** plan.json `timeline` = (output frame, frames, take, source frame, side) for every piece; audio always comes from the same frames as the picture.
- **Audio as recorded:** no loudness normalization, limiter, EQ, compression or noise reduction in clone videos. Only a 2 ms ramp at each cut (stops clicks; `declick_ms`, 0 = off). The together hook adds both voices without changing levels. Export AAC 320k, 48 kHz.
- **Straight CapCut split:** vertical line, 160 px feather (10 px showed a hard line where the light differed between takes; his CapCut example uses a wide feather), default center; per turn it may move between 35% and 65% if that clearly shows more (product held toward the middle), and only at the turn change. Back to center when the center is fine.
- **Listener footage:** real quiet footage of him between his own lines; if one stretch is too short, several real stretches with switches on the talker's cuts; back-and-forth only as a flagged last resort.
- **Settings:** `clone_settings.json` at the project root (see `clone_settings.example.json`): split position/range, feather, center pull, turn gap, declick, CRF, audio bitrate.
- **QC on every video (qc.json):** 1080x1920, 30/1 fps, frame count = timeline, audio length = video length; black / frozen frames; audio clipping (peak ≥ -0.1 dBFS); **lip-sync measured** at up to 36 points across the whole video (picture matched to source frames + audio cross-correlated with the original; pass = within 33 ms); words (Whisper re-listen ≥ 93%, doubled words); gaps over 0.12 s; camera moved (edge match < 0.6); something crossing the split; listener repeated; side levels differing > 6 dB (reported, not changed); empty-spot frames. `qc_split.jpg` shows each turn's split in red.
- **Still needs eyes/ears:** natural feel of the pacing, whether a product is clearly shown, lip-sync on the together hook (two voices mixed: audio sync measured against the left take only).

## Auto-edit on AirDrop (clone videos), `tools/watch.py` (on since 2026-11-18, his OK)
- launchd agent `~/Library/LaunchAgents/com.izaiahwest.clonewatch.plist` runs `watch.py` when ~/Downloads changes and every 3 min. Log: `edits/watch.log`. State: `edits/watch_state.json`.
- Waits until AirDrop is done (nothing new or growing for 2 min), then pairs new videos: **filmed within 20 min + same shot (ceiling/headrest edge match ≥ 0.80; real pair 0.89, same car another day 0.65–0.68) + him on opposite sides**. AirDrop order doesn't matter. Random videos / screen recordings never pair, so they're never touched; unpaired clips are retried for 6 h, then ignored. Videos already in Downloads when it was switched on are ignored.
- **Notifications (his ask 2026-11-18, "I want to know that you're working"):** "Editing clone videos: got N clips → M videos" when it starts, "Video n of M ready" per video, "failed" / "Clips not edited" when something needs Claude. After a batch it keeps watching Downloads for 15 more minutes, so he can AirDrop, go film more, AirDrop again.
- Each pair → moved to raw/ → `clone.process_clone(..., together="auto")` → `final/` + **iCloud Drive › TikTok Edits** + Mac notification. Hook is said together automatically when both takes open with the same line (≥ 75% letter match); otherwise normal back-and-forth (his call 2026-11-18).
- **Pairing check is tuned on the car only** (edge match on the top third = car ceiling/headrests; other strips don't separate: same car another day scores up to 0.80 at the frame edges). Clips filmed in the last 24 h that don't pair trigger a Mac notification "Clips not edited… Message Claude". Then: edit them by hand with `--clone A B`, and re-tune `PAIR_EDGES` / `edge_match` on his first home (standing) footage.
- **Order safety (2026-11-18, IMG_1930/1931):** he paused 10-40 s mid-turn while showing products, so the passenger take split into 17 lines vs 6. Without a script, if the two takes' line counts differ by more than 1, the video is NOT edited and he's told to save the script in **iCloud Drive › TikTok Scripts** (lines `A: ...` / `B: ...`, or two names) or message Claude. With scripts in that folder, the best-matching one (≥ 60% of each side's words) is used automatically. Claude can also write the script from the two transcripts and run `--clone A B --script file`.
- **Moving seam:** the seam is re-found for every turn from that turn's two clips, so when he holds the product toward the middle the seam moves into the still side instead of cutting the product off.
- **Hook false starts** ("I'm definitely the boy-" before the real hook) are skipped: the hook is the best-matching stretch among each take's first 3.
- **Texts:** `~/.clonewatch.json` (not in the repo) holds his iMessage number. Texts start "TikTok Editor:" with the video attached. Texts to himself DON'T alert on his iPhone (Apple marks them read), so **phone alerts = Reminders** (his pick 2026-11-18): a reminder in his "TikTok Editor" list, due in 20 s, older ones ticked off. `tell()` = Mac pop-up + Reminders alert + text with the video. Tested from launchd: works, no permission block.
- Manual batch: `python tools/edit.py --clone-batch raw/IMG_2001.MOV raw/IMG_2002.MOV ...` (same pairing). Force the hook: `--together` / `--no-together`.
- Turn off: `launchctl bootout gui/$(id -u)/com.izaiahwest.clonewatch`. Turn on: `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.izaiahwest.clonewatch.plist`.
- **His locked style (2026-11-18, "this version is perfect"):** IMG_1922_clone_together. Every clone video must match it: tight line trims (7 dB, Whisper-checked), no empty-seat frames, no zooms, -16 LUFS. Don't change these defaults without asking him.

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
