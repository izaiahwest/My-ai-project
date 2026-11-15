# Decisions log
Newest at the bottom. Format: date: decision (why).

- 2026-11-15: Folder structure created (products, swipes, scripts, raw, edits, final, posted, skills, lessons, tools).
- 2026-11-15: Video files are git-ignored; only text, sheets and code are committed (repo size, privacy).
- 2026-11-15: The cloud session can't reach his logged-in browser. Daily Virals, TikTok and raw-footage steps run in a Claude Code session on his own computer, and git syncs the two.
- 2026-11-15: Home base is Izaiah's **Mac**, which can stay on. Daily Virals, TikTok browsing, raw drops and overnight edits run there. Overnight jobs run under `caffeinate -i` so the Mac doesn't sleep, without him changing any settings.
- 2026-11-15: One-paste Mac setup in tools/mac_setup.sh (Homebrew, ffmpeg, yt-dlp, Whisper, clone of the repo).
- 2026-11-15: Mac setup switched from Homebrew to **Miniforge in ~/miniforge3** (no password needed; Homebrew wanted his Mac password, which blocked setup). ffmpeg, yt-dlp, Python 3.12, faster-whisper and openpyxl live there. Scripts call tools as `~/miniforge3/bin/...` (or put it first on PATH), because the shell profile isn't changed.
