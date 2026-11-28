# Adding scripts to the bank

**Use the Clone Script Bank (https://claude.ai/artifact/3fqEkHYrKgG29yvWH922JA) from 2026-11-28.** Add scripts as docs in its `scripts` collection (fields: product, productOrder, title, caption, style, format, kind, isNew, added, beats[{t, lines[{who: A|B|You|dir, text}]}], notes, order, filmed; for a shoot day add shoot=YYYY-MM-DD, shootNo, shootOrder). Each shoot date gets its own tab. The steps below are for the old WestFaveFinds bank.
0. Send the new scripts to Izaiah in chat first. Only add the ones he approves.
1. Append the approved scripts to scripts/bank.json with `"added": "YYYY-MM-DD"` (each date gets its own color; oldest yellow, then orange, pink, blue…).
2. Fields: id, p, pay, status ("bank" or "proven"), added, who, from, lines ([brackets] = actions).
3. Update scripts/plan.json (title, items, optional bonus), then run `python3 tools/build_script_bank.py`.
4. Publish scripts/script-bank.html to the same artifact (https://claude.ai/artifact/Td2VFriLcRp89RDCcjq48T), then commit.
5. Start every batch from his proven structure (swipes/2026-11-24-westfavefinds-kodak-dock.md): double-meaning hook, then a calm native walkthrough.
