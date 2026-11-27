"""Rebuild scripts/script-bank.html and scripts/SCRIPT_BANK.md from scripts/bank.json.
status: new (yellow), bank (plain), proven (green). Before adding a batch, set old 'new' to 'bank'."""
import json, html, sys, os
os.chdir(os.path.join(os.path.dirname(__file__), '..'))
NEW_LABEL = sys.argv[1] if len(sys.argv) > 1 else 'NEW'
d = json.load(open('scripts/bank.json')); e = html.escape
page = open('scripts/script-bank.html').read()
head = page[:page.index('<h2>')]
out, cur = [], None
for s in d:
    if s['p'] != cur:
        cur = s['p']; out.append(f'<h2>{e(cur)} <span class="pay">{e(s["pay"])}</span></h2>')
    words = sum(len(l.split()) for l in s['lines'] if not l.startswith('['))
    lis = ''.join(f'<li class="{"act" if l.startswith("[") else ""}">{e(l)}</li>' for l in s['lines'])
    badge = {'new': f'<span class="badge">{e(NEW_LABEL)}</span>', 'proven': '<span class="badge proven">PROVEN · 5.5M</span>', 'bank': ''}[s['status']]
    out.append(f'<article class="card {s["status"]}"><div class="top"><span class="id">{s["id"]}</span>{badge}</div>'
               f'<p class="who">{e(s["who"])}</p><ol>{lis}</ol><p class="from">{e(s["from"])} · {words} words</p></article>')
tail = ('<p class="from">Say "I actually just put it on sale" only when the sale is live. Keep hooks at this level; '
        'an explicit version can get the video restricted. Solo Stove: never light it in or right next to the car.</p>\n</main>')
open('scripts/script-bank.html', 'w').write(head + '\n'.join(out) + '\n' + tail)
md = ['# Script bank · WestFaveFinds', '', f'<mark>Yellow = {NEW_LABEL}</mark>. [Brackets] = actions.', '']
cur = None
for s in d:
    if s['p'] != cur: cur = s['p']; md += [f'## {cur} ({s["pay"]})', '']
    t = f"**{s['id']}** · {s['who']}"
    md += [f'<mark>{t}</mark>' if s['status'] == 'new' else t + (' ✅' if s['status'] == 'proven' else ''), '']
    md += [f'- {l}' for l in s['lines']] + ['', f"_{s['from']}_", '']
open('scripts/SCRIPT_BANK.md', 'w').write('\n'.join(md))
print(len(d), 'scripts')
