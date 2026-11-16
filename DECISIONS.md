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
