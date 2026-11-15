# CLAUDE.md — Izaiah's TikTok Shop Production Machine

Read this whole file at the start of every session. Then read `DECISIONS.md` and `lessons/LESSONS.md`.

## Who I work for
- **Izaiah**: TikTok Shop affiliate and short-form creator. Has a full-time job, so his time is the bottleneck.
- **Numbers he gave us** (don't change them, and only update them when he gives new ones):
  - About $7K/month from TikTok Shop over the last 2–3 months.
  - About $7.3K this month as of mid-November, since he started posting heavy.
  - Wants $15K this month. **The real goal is $10K/month for several months in a row**, which is the number that lets him go all in.
- **Volume**: 10–15 videos a day. ChatGPT is connected to his Google Calendar and blocks his posting time.
- **Tools**: Daily Virals (paid, logged in on his browser), ChatGPT ($20), Cut AI (cuts videos), repurpose.io (TikTok → Facebook), Claude ($20 now, moving to Max once editing runs daily).
- **Old swipe habit**: saves videos in TikTok's Saved tab and forgets them. The swipe file (Part 2) replaces this.
- **Season**: Q4, the best selling season. Everything should pay off **now**, not in a month.

## The standard (never stop short of this)
- Izaiah only **films raw content** (often in his car) and **makes final calls**. We do everything else.
- Target: **about 30 minutes of manual work a day**. He wakes up, films, and the machine does the rest.
- If a step still needs his hands, flag it and work out how to take it off him. Keep asking **"what would make this run without Izaiah?"** until the answer is "nothing, he just films."
- Don't let him settle for less, even if he says "it's fine".

## How we work with him
1. Do the heavy lifting. Only stop for approvals, logins, payments, or things only he knows.
2. Interview him **one question at a time**: short and easy to answer by voice. Ask how he wants the output to look, then build to that. Show him the bigger version and let him pick.
3. Go step by step and keep going without waiting for "go".
4. Write everything down in this folder. Record every decision in `DECISIONS.md`.
5. When something works, save it as a skill in `skills/` (markdown with the exact steps).
6. When he corrects us, write the lesson in `lessons/LESSONS.md` (what happened, why, the new check).
7. Use agents in parallel: research, editing and scripts at the same time.
8. **Never make up a number, a stat or a quote.** If we don't have it, say so and say how we'll get it. Missing data stays an empty cell, with "not shown" in Notes.

## Folders
`products/` research and hierarchy sheet · `swipes/` swipe markdown and index · `scripts/` daily script batches · `raw/` his footage drop · `edits/` work in progress · `final/` finished videos and the morning summary · `posted/` post log · `skills/` reusable procedures · `lessons/` corrections · `tools/` our code.

## Environment notes
- This repo also runs in a **cloud container** (Claude Code on the web). The cloud copy **cannot reach Izaiah's logged-in browser** (Daily Virals, TikTok) or AirDrop. Those steps run in a Claude Code session **on his own computer** (Claude Desktop + Claude in Chrome, or `claude remote-control` in this folder). Git keeps both copies in sync.
- Video files (raw/edits/final) are git-ignored. Only notes, scripts, sheets and code are committed.
- On the Mac, tools live in `~/miniforge3/bin` (python, ffmpeg, ffprobe, yt-dlp). Run with `export PATH=~/miniforge3/bin:$PATH` first; `/usr/bin/python3` is the old system one without our packages.

---

## PART 1 · Product research (weekly, then daily)
**Rules, most important first, in his words:**
1. **Momentum is #1.** Compare units sold in the last 7 days with lifetime units. 10,000 total with 2,000 in the last 7 days means few creators are on it yet and it's about to pop.
2. **Not saturated.** Stay away from products near 1M units sold, because there he's up against the top affiliates. "If people didn't buy from the best of the best video, why would they buy from mine?"
3. **Repeatable.** The holiday printer works because he can film it 10×/day. Hair products only work once a day (shower).
4. **Fits me.** No makeup. If his audience wouldn't believe him holding it, it's out.
5. **Q4**: favor gifts and holiday buys.

**Procedure**
- Daily Virals → Product research → **Hidden Gem** filter → **last 7 days** → **US**.
- Go through **every page** (a ChatGPT run did ~1,200 products over 100 pages). Count the pages and products checked.
- Pass 1, drop: makeup, 0 sales in 7 days, more than about 500,000 lifetime units.
- Pass 2, for each product pull: name, link, category, price, commission %, lifetime units, units in the last 7 days, creators promoting, and views on the top 3 videos.
- Saturation: **Low** = few creators for its volume and top videos from small or mid accounts. **Medium** = room left. **High** = hundreds of creators, top videos from big affiliates with millions of views, or near 1M lifetime units.
- Videos/day he could film: can he demo it in the car, at his desk, in different rooms, with different hooks? Gadgets and accessories 5–10, single-use personal care 1.
- If Kalodata or FastMoss is added, cross-check the top 20.

**Score /100 (formula; code in `tools/build_hierarchy.py`)**
- Momentum (max 40): 7-day ratio ≥20% → 40 · 10–20% → 25 · <10% → 10
- Saturation (max 25): Low 25 · Medium 12 · High 0
- Repeatable (max 20): videos/day × 2, capped at 20
- Fits me: 15 (a product that doesn't fit is dropped, not scored)
- Tie-break: higher $ per sale.

**Output** `products/hierarchy.xlsx`
- Tab **Hierarchy**: Rank · Product · TikTok Shop link · Category · Price · Commission % · $ per sale · Lifetime units · Units last 7 days · 7-day ratio · Creators promoting · Saturation · Fits me? · Videos a day I could film · Leverage score · Why it's high leverage · Video angle · Swipe video link · Status · Notes.
- Bold dark green header with white text, frozen header, clickable links, sorted by score (highest first).
- Tab **Dropped**: each cut product and the rule it failed.
- In chat: the top 5, with the first video to film for each.
- **Learning loop**: keep the sheet and research only new products on later runs. When he reports wins or flops, update Status with the reason and weight winners higher.

## PART 2 · Swipe file
- **Inputs**: he pastes a TikTok link plus a voice note on what he liked. We also pull fresh top videos for the top products every week.
- **Per video**: download to a temp folder (public videos only, never his login), transcribe word for word with Whisper, then write `swipes/YYYY-MM-DD-creator-product.md` with:
  - creator, link, posted date, views, likes, followers, views-to-followers ratio
  - product and TikTok Shop link if present
  - full transcript, word for word
  - the hook (first 1–3 s) word for word, plus the hook type (problem / reveal / reaction / question / "I can't believe" / price shock / …)
  - beat-by-beat structure with timestamps (hook, demo, proof, price/offer, CTA)
  - word count, length in seconds, number of cuts, on-screen text
  - why it worked, in plain words
  - his voice note, word for word
- `swipes/INDEX.md` ranked by **views-to-followers ratio**. Videos that blew up past the account's size won on content, and those are the ones we model.
- Delete the downloaded videos after transcribing. Keep only the transcripts and notes.

## PART 3 · Scripts
- For each top product, pick the 2–3 best-fitting swipes (same kind of product, same buyer, high ratio).
- Learn the thinking, not the words: what the hook promises, how fast it gets to the product, where the turn or proof lands, word count and length, and why someone buys at the end.
- Write HIS version: same structure, his words, his setting (often the car). **Never word for word.**
- Format: hook first, one line per cut, each line short enough for one breath. Under each script: the on-screen top text and the product moments to show.
- Batch a full day (10–15) on one phone-readable page, grouped by product: `scripts/YYYY-MM-DD.md`.
- Tailor from his voice notes and keep everything he approved. **Once a hook is approved, it stays word for word** (log it in `scripts/APPROVED_HOOKS.md`).

## PART 4 · Filming (his only job)
- Filming list per batch: product, script, where to film, what to hold.
- He films loose. Mistakes, restarts and dead space are fine, and if he messes up a line he says it again.
- **He claps once between videos.** We split long recordings on the claps (the loudest short peaks).
- He drops raw files in `raw/`. That's it.

## PART 5 · Editing (overnight)
- Build the style from scratch: ask for 3–5 reference creators, study their best videos frame by frame, and write `skills/edit-spec.md` (caption font/size/color/position, words per caption, top text and when it changes, zoom/punch-in frequency, how often something new happens on screen, product pop-ins and B-roll, music and volume, length, pacing, ending). Show him the spec and a test edit on his footage, and iterate until he says it's right.
- **Every edit, every time:**
  - Whisper with word timestamps.
  - Cut every silence between sentences. Split on any gap between words over **0.09 s**, trim each piece by audio level (20 ms smoothed) with about **10 ms before / 15 ms after** the words, rounding to the nearest frame (tightened 2026-11-15: he wants zero dead space, matching @dealswithkeelz), and start the opening instantly.
  - Never cut a word in half. Where a kept word meets a cut word, cut at the **quietest 10 ms** between them, and let soft endings (s, sh, ly) finish.
  - On repeated lines, keep the best take and cut the others completely, with no leftover first words.
  - Cut fluff: "um", false starts, detours.
  - Snap every cut to the **1/30 s frame grid** for video and audio.
  - **No captions** (his call, 2026-11-15, matching his reference creators). Whisper is still used for cutting and QC.
  - **No top text** (his call, 2026-11-15).
  - **Subtle zoom (about 108%) only when the shot is still for 3+ s** (his call, 2026-11-15). No zoom when the product is moving or already at the lens. Details in `skills/edit-spec.md`.
  - When he names the product or something on screen, show it (image or close-up) for about 1 s.
  - Something new on screen **about every 3 s**.
  - Audio at **-16 LUFS**, true peak **≤ -1.5 dBTP**.
  - Export **1080×1920, 30 fps, H.264, CRF ~16, AAC**.
- **QC before "done":** re-transcribe the final and diff it against the intended words (all present and whole, no doubled words like "so so"); run `silencedetect` at -40 dB / 0.12 s with nothing at a cut; check frames at the hook, a middle cut and the end.
- Storyboard only if he asks (every cut + caption + contact sheet). Otherwise go straight to final.
- **"Edit these overnight"**: process everything in `raw/` → `final/`, plus a one-page `final/SUMMARY-YYYY-MM-DD.md` (what was made, anything uncertain, anything that needs him). Changes come in words and we redo them.

## PART 6 · Posting
- Per final: caption and hashtags in his voice, with the affiliate link or product tag.
- Schedule about 1 hour apart across the day. Set up **Metricool** with him (TikTok + Instagram; he logs in, we do the rest). Keep repurpose.io → Facebook.
- Log in `posted/LOG.csv`: date, product, hook, post time, views at 24 h, views at 48 h, sales after 48 h.
- Weekly: use the winners to rank products and pick swipes. Report in **3 lines**: what worked, what didn't, what we're changing.

## PART 7 · His week (every Sunday)
One page: product hierarchy, scripts by day, filming blocks on Google Calendar around his job, swipes added, last week's results, anything that needs him. **Add the calendar blocks only after he says yes.**
