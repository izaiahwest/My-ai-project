# Skill: Product research (Daily Virals → hierarchy.xlsx)

**Runs on:** a Claude Code session on Izaiah's computer, using Claude in Chrome (his logged-in Daily Virals). The cloud session can't log in.

## Steps
1. Read CLAUDE.md Part 1. Open `products/research.csv` if it exists. **Only research products not already in it.**
2. Open Daily Virals → Product research → filter **Hidden Gem**, **Last 7 days**, **US**.
3. Go through **every page**. Keep a running count: pages checked, products seen.
4. **Pass 1** (from the list view): skip makeup, 0 units in 7 days, and more than about 500K lifetime units. Still write each skipped product to research.csv with `drop_reason` so it lands on the Dropped tab.
5. **Pass 2** (open each survivor): product, link, category, price, commission %, lifetime units, units in the last 7 days, creators promoting, and views of the top 3 videos (plus the creator size of those videos).
6. Judge **saturation** (Low/Medium/High per CLAUDE.md), **fits_me** (yes/no), **videos_per_day** (car / desk / rooms / hooks: gadgets 5–10, single-use personal care 1), **why**, **angle**, and the best **swipe_link** (the top video from the smallest account).
7. Anything not shown on the page stays **empty**. Never estimate.
8. Run `python3 tools/build_hierarchy.py`, which writes products/hierarchy.xlsx.
9. In chat: pages and products checked, how many were dropped and why, then the top 5 with the first video to film for each.
10. Log the run in DECISIONS.md (date, pages, products, top 5).

## research.csv columns
product, link, category, price, commission_pct, lifetime_units, units_7d, creators, top3_views, saturation, fits_me, videos_per_day, why, angle, swipe_link, status, notes, drop_reason, first_seen
