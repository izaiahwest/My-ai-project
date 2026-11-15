# Edit spec (v0.2: style questions answered; waiting on a test edit)

Built from Izaiah's 3 reference creators, top 3 videos each by views (pulled 2026-11-15):

| Creator | Video | Views | Length | Cuts* | Words/sec | Loudness |
|---|---|---|---|---|---|---|
| @iamsk8bordb | Korean skincare (PDRN + copper) | 217.6K | 45.9 s | 17 | 4.97 | -27.0 LUFS |
| @iamsk8bordb | Unbrush Nightmare collab | 62.6K | 47.6 s | 8 | 5.00 | -24.9 |
| @iamsk8bordb | Unbrush "better than last year" | 49.7K | 46.6 s | 11 | 5.23 | -26.1 |
| @dealswithkeelz | Rich / middle / poor boyfriend camera | 2.5M | 50.2 s | 10 | 4.86 | -15.5 |
| @dealswithkeelz | Boyfriend camera v2 | 2.2M | 56.3 s | 14 | 4.78 | -16.6 |
| @dealswithkeelz | Pore strip on strawberry | 901.8K | 53.7 s | 7 | 4.23 | -16.4 |
| @bennettfinds | Squishies "take them apart" | 789.8K | 39.3 s | 5 | 4.30 | -15.2 |
| @bennettfinds | Squishies "kids throw them" | 351.4K | 37.0 s | 4 | 5.08 | -15.9 |
| @bennettfinds | Advent calendar skit | 318.8K | 36.6 s | 10 | 4.70 | -21.5 |

*Cuts = camera-angle or scene changes found automatically. Jump cuts inside the same shot are mostly not counted, so the real number is higher.

## What they all do (measured)
- **Talking from frame 1.** First word at 0.0 s in all 9. No intro, no logo, no silence.
- **Dense talking.** 4.2–5.2 words per second, and 84–100% of the video has speech. Every pause is cut.
- **Length 37–56 s.** Average about 46 s.
- **Hook = one line that says who it's for or what's going on**, said straight to camera:
  - Problem / "who it's for": "If your cheeks look like this, you need…", "If your kids love squishies, but…"
  - News / scarcity: "…just released their brand new limited edition…"
  - Skit setup: "I'm the rich boyfriend. I'm the middle class boyfriend…"
- **The product does the visual work.** Something new on screen about every 1–3 s, but mostly from him moving the product (pushing it to the lens, swapping colors, throwing it), not from editing tricks.
- **Product right up to the lens** often, filling most of the frame (@iamsk8bordb does this constantly).
- **Simple setting, same spot each video**: desk or kitchen counter, phone on a stand at chest height.
- **Shape**: hook (0–3 s) → unbox or show it → 2–4 features, each with a demo → price/scarcity ("almost sold out", "for that price today") → tap-the-cart CTA.

## What they DON'T do (this conflicts with CLAUDE.md; Izaiah decides)
- **No word-by-word captions** in any of the 9. CLAUDE.md says "captions the whole way, 2–4 words".
- **Top text only sometimes, and small**: @dealswithkeelz uses a label per section ("💰Rich boyfriend💰", "Mid-class boyfriend", "Poor boyfriend❌"). @bennettfinds's skit has one small line the whole time ("What kids ACTUALLY want"). @iamsk8bordb uses none.
- **No obvious digital punch-ins.** The "zoom" feel comes from leaning in and pushing the product to the camera. CLAUDE.md says punch in about 110% on every other cut.
- Extras seen once each: a picture-in-picture before/after (@iamsk8bordb skincare) and photo samples popped over the frame (@dealswithkeelz camera).

## Proposed rules for Izaiah's edits (pending his call)
1. Keep every CLAUDE.md cutting rule: cut all silences (gaps > 0.12 s), keep the best take, cut "um" and false starts, no cut mid-word, frame-grid cuts. This matches the 4–5 words/sec density.
2. Start on the first word at 0.0 s.
3. Target 35–55 s.
4. Captions: **none** (Izaiah, 2026-11-15). No word-by-word captions, same as the reference creators.
5. Top text: **none** (Izaiah, 2026-11-15).
6. Punch-in: **subtle zooms only when the shot is still** (Izaiah, 2026-11-15). If nothing on screen has moved for more than 3 s, punch in to about 108% at the next cut (or a slow push-in if there's no cut), then back to 100% at the cut after. Never on shots where the product is already moving or pushed to the lens.
7. Product pop-in (image) when he names it: keep, about 1 s.
8. Audio -16 LUFS, true peak ≤ -1.5 dBTP (matches @dealswithkeelz and @bennettfinds; @iamsk8bordb runs quiet at about -26).
9. Export 1080×1920, 30 fps, H.264, CRF ~16, AAC.

## Open questions for Izaiah (ask one at a time)
1. ~~Captions~~ → answered: **no captions**.
2. ~~Top text~~ → answered: **no top text**.
3. ~~Punch-ins~~ → answered: **subtle zooms when the shot is still for 3+ s**.
4. ~~Closest creator~~ → answered: **@dealswithkeelz**.

## Closest reference: @dealswithkeelz (Izaiah, 2026-11-15)
What that means for the edit (with his no-captions / no-top-text calls):
- 50–56 s, about 4.2–4.9 words/sec, speech 84–91% of the runtime.
- Loudness around -16 LUFS (we normalize to -16, peak ≤ -1.5 dBTP).
- A cut or a new product angle about every 4–7 s. Product held close to the camera, often filling the frame.
- Bright, clean kitchen/home setting, camera at chest height, him centered.
- Format leans on comparisons and skits ("rich / middle class / poor boyfriend", "which one's better?"). That's a **script** choice (Part 3), not an edit setting. Noted for script writing.
- Seen once: real photo samples popped over the frame when talking about the camera's photos. Our "show the product when he names it" rule covers the same idea.

Status: style questions all answered. Next: test edit on his footage, then iterate until he says it's right.
