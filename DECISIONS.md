# Decisions log
Newest at the bottom. Format: date: decision (why).

- 2026-11-15: Folder structure created (products, swipes, scripts, raw, edits, final, posted, skills, lessons, tools).
- 2026-11-15: Video files are git-ignored; only text, sheets and code are committed (repo size, privacy).
- 2026-11-15: The cloud session can't reach his logged-in browser. Daily Virals, TikTok and raw-footage steps run in a Claude Code session on his own computer, and git syncs the two.
- 2026-11-15: Home base is Izaiah's **Mac**, which can stay on. Daily Virals, TikTok browsing, raw drops and overnight edits run there. Overnight jobs run under `caffeinate -i` so the Mac doesn't sleep, without him changing any settings.
- 2026-11-15: One-paste Mac setup in tools/mac_setup.sh (Homebrew, ffmpeg, yt-dlp, Whisper, clone of the repo).
- 2026-11-15: Mac setup switched from Homebrew to **Miniforge in ~/miniforge3** (no password needed; Homebrew wanted his Mac password, which blocked setup). ffmpeg, yt-dlp, Python 3.12, faster-whisper and openpyxl live there. Scripts call tools as `~/miniforge3/bin/...` (or put it first on PATH), because the shell profile isn't changed.
- 2026-11-15: **Product research stays with ChatGPT** for now (it already does it). He shares ChatGPT's product list weekly; we use it for swipes and scripts. Claude's first focus is **editing** (biggest time sink). We take research over only if ChatGPT's list misses or costs him time.
- 2026-11-15: Edit-style reference creators: @iamsk8bordb, @dealswithkeelz, @bennettfinds.
- 2026-11-15: **No captions** on edits (his call; none of his 3 reference creators use them). Replaces the 2–4-word caption rule.
- 2026-11-15: **No top text** on edits (his call). Replaces the changing top-text rule. Scripts no longer need an on-screen top-text line.
- 2026-11-15: **Subtle zooms only on still shots** (about 108% when nothing has moved for 3+ s), replacing "punch-in on every other cut" (his call).
- 2026-11-15: Closest reference creator for his edits: **@dealswithkeelz** (his pick). Skit/comparison formats noted for scripts.
- 2026-11-15: Editor built (tools/edit.py, steps in skills/editing.md). Cut points come from the audio level, not Whisper's word edges (Whisper's were off by 100+ ms in testing). Retakes: last take wins. Product pop-in waits for product images.
- 2026-11-15: First real edit (IMG_1926): retake detection moved to word level (he restarts with no pause), stretched-word guard, speech threshold 0.45, QC on letter match. 55 s raw → 18 s final, all checks passed.
- 2026-11-15: **Zero dead space** (his feedback on the first edit: "no pauses between cuts"). Gap 0.12→0.09 s, padding 20/40→10/15 ms, nearest-frame rounding, 20 ms smoothed level so noise blips don't hold pauses open. IMG_1926: 18.1 s → 16.1 s; near-silence 20% → 9% (@dealswithkeelz: 10%).
- 2026-11-15: His footage is iPhone HDR (Dolby Vision/HLG). It now goes through Apple's avconvert (4K, tone-mapped) before editing; without that, colors were washed out. Short scraps (< 0.4 s) must hold a real word, which fixes the "flash before the real line" he saw at the end.
- 2026-11-15: **Combining clips:** every clip is its own video by default. When he says clips go together, we join them (`tools/edit.py --join`, in his order). He chose "just tell you" over a double clap or an album.

## 2026-11-17: Clone (split-screen) videos
- He asked for @dealswithkeelz-style "two of me" videos, fully automated. Built `tools/clone.py` (`edit.py --clone A B [--script]`).
- Method: locked-off phone, one take per side, blended along a seam through the background. **No body cut-out/masking**: more reliable and no fuzzy edges, but he must stay on his side of the middle. Cut-out masking (for crossing over / handing products across) only if he needs it later.
- Listening side = that take's quiet, still moments; plays back and forth if there isn't enough.
- Tested on fake takes only; needs a real 3–4 line test from him before he relies on it.

## 2026-11-18: Clone mode approved after his first real test
- He: "this is like exactly what I need… I like the overlay." Ask: tighter hand-offs, "back to back to back", no pauses between speakers. Done: line edges trimmed against each line's own voice level.
- Some videos have both characters say the hook together. **He tells us when**; `--together` does it. Default: not together.

## 2026-11-18: Clone style locked + auto-editing on
- He: "YES THIS VERSION IS PERFECT… exactly what I need moving forward." Reference: final/IMG_1922_clone_together.mp4. Every clone video matches it.
- Hook: said together automatically when both takes open with the same line; otherwise back-and-forth.
- Workflow: two files per video (one per seat), alternating seats so each pair is filmed a minute apart; AirDrop a whole batch. Pairing by filming time + same shot + opposite sides, so random AirDrops are never edited.
- Auto-edit on AirDrop turned on (launchd watcher, his OK). Finished videos also go to iCloud Drive › TikTok Edits.
- Three-person clones: not built. Car = needs cut-out masking (back seat overlaps); home with 3 side-by-side spots = same seam method, 2 seams. After 2-person is running in volume.

## 2026-11-18: Clone system v2 (his full spec)
- **Audio drift root cause:** `-ss/-t` piece cuts: video rounded to whole frames (up to +1 frame per piece), audio exact; joining + the loudness pass made audio creep ahead (first aid kit video: audio 0.57 s short; gift video: 0.17 s). Fix: frame-number cuts with exactly 1600 samples/frame, lossless intermediates, one master timeline. Verified: 0 ms lip-sync error at 27 points (0.7-48.9 s) and 7 points.
- **His rules now in code:** clone audio exactly as recorded (no normalize/limit/EQ/compression; only a 2 ms click guard at cuts, `declick_ms`); straight CapCut-style split, 10 px feather, default center, moves 35-65% per turn only to show a product; real listener footage (multiple real stretches before ever repeating; repeats get flagged); settings in `clone_settings.json`; QC measures lip-sync, frames, black/frozen, clipping, words, gaps, camera moved, split crossings.
- Pacing kept at his approved back-to-back (`turn_gap_ms` 0); adjustable.
- He doesn't need finished videos texted when we revise; delivery = iCloud Drive › TikTok Edits (+ shown in chat).

## 2026-11-24: Brand outreach to JoeToys (joetoyss.com)
- Iron Man helmets/suits maker (team of 7; Instagram @thearmorplace; info@joetoyss.com). He wants to make content for free because he loves the product.
- Pitch: no fee; ask for 1 helmet (MK5 voice-activated, $179 on sale) + a tracked discount/affiliate code so his videos earn and they can see the sales. Gmail draft made, not sent; he fills in his handle and video links.
- 2026-11-24 (update): Ask is "one product of your choice" + optional code/affiliate. Proof from FastMoss (estimates): Kodak Dock video 5.4M views, ~769 units; gloves 763K views, ~1,143 units. Channels: email + Instagram DM to @thearmorplace, plus ask @frankie_aka for a warm intro. Draft waits for his OK; after sending, one follow-up in 3 days if no reply, then stop.
- 2026-11-25: JoeToys said yes (email + IG DM): free MK5 helmet for a first collab, once he joins their affiliate program (joetoyss.goaffpro.com); they then make his discount code/link. He chose the black helmet. Reply drafted, waiting for his phone number + signup. Follow-up check cancelled (they replied).
