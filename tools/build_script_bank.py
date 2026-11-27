"""Rebuild scripts/script-bank.html and scripts/SCRIPT_BANK.md from scripts/bank.json.
Each script has an `added` date (YYYY-MM-DD). Each date gets its own color (oldest first:
yellow, orange, then pink, blue, green, purple). Proven scripts have added=null and a green border.
Nothing goes into bank.json without Izaiah's OK."""
import json, html, os, datetime
os.chdir(os.path.join(os.path.dirname(__file__), '..'))
e = html.escape
d = json.load(open('scripts/bank.json'))
COLORS = ['yellow', 'orange', 'pink', 'blue', 'green', 'purple']
dates = sorted({s['added'] for s in d if s.get('added')})
color = {dt: COLORS[i % len(COLORS)] for i, dt in enumerate(dates)}
def label(dt):
    # '2026-11-27' -> 'Nov 27'; '2026-11-27-2' -> 'Nov 27 · 2nd batch'
    base = datetime.date.fromisoformat(dt[:10]).strftime('%b %-d')
    return base + (f' · batch {dt[11:]}' if len(dt) > 10 else '')
today = json.load(open('scripts/today.json')) if os.path.exists('scripts/today.json') else None
tid = {i for g in today['groups'] for i in g['ids']} if today else set()
byid = {s['id']: s for s in d}

tabs = (['<button class="tab" data-f="today" type="button">Film today</button>'] if today else []) + ['<button class="tab on" data-f="all" type="button">All</button>',
        '<button class="tab" data-f="proven" type="button">Proven</button>']
tabs += [f'<button class="tab t-{color[dt]}" data-f="{dt}" type="button">{label(dt)}</button>' for dt in reversed(dates)]
legend = ' '.join(f'<span class="key k-{color[dt]}">{label(dt)}</span>' for dt in reversed(dates))

out, cur = [], None
for s in d:
    if s['p'] != cur:
        cur = s['p']; out.append(f'<h2>{e(cur)} <span class="pay">{e(s["pay"])}</span></h2>')
    words = sum(len(l.split()) for l in s['lines'] if not l.startswith('['))
    lis = ''.join(f'<li class="{"act" if l.startswith("[") else ""}">{e(l)}</li>' for l in s['lines'])
    if s['status'] == 'proven':
        cls, f, badge = 'proven', 'proven', '<span class="badge b-proven">PROVEN · 5.5M</span>'
    else:
        dt = s['added']; cls, f, badge = f'c-{color[dt]}', dt, f'<span class="badge">{label(dt)}</span>'
    out.append(f'<article class="card {cls}" id="s-{s["id"]}" data-f="{f}" data-today="{1 if s["id"] in tid else 0}"><div class="top"><span class="id">{s["id"]}</span>{badge}</div>'
               f'<p class="who">{e(s["who"])}</p><ol>{lis}</ol><p class="from">{e(s["from"])} · {words} words</p></article>')

CSS = """
/* One column, phone first. Each batch date has its own card color; tabs filter by date. */
:root{--bg:#fafaf7;--fg:#1c1c1a;--muted:#6b6a63;--line:#e3e1d8;--card:#fff;--act:#3d6b4a;
--yellow:#fff3a3;--yellow-e:#e8c400;--orange:#ffd9b0;--orange-e:#f08a1c;--pink:#ffd6e4;--pink-e:#e0457b;
--blue:#d4e6ff;--blue-e:#3a7be0;--green:#d6f2d9;--green-e:#3e9a4c;--purple:#e6dcff;--purple-e:#7b55d6;
--display:"Space Grotesk",system-ui,sans-serif;--body:"Inter",system-ui,sans-serif}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#151513;--fg:#f1f0ea;--muted:#a3a197;--line:#2e2d29;--card:#1d1d1a;--act:#8fc79e;
--yellow:#4a4110;--yellow-e:#d9b800;--orange:#4d2c0c;--orange-e:#f39a3a;--pink:#4a1a2b;--pink-e:#ef6b97;--blue:#16294a;--blue-e:#6aa0f0;--green:#173a1d;--green-e:#6cc47a;--purple:#2e2350;--purple-e:#a68af0;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#151513;--fg:#f1f0ea;--muted:#a3a197;--line:#2e2d29;--card:#1d1d1a;--act:#8fc79e;
--yellow:#4a4110;--yellow-e:#d9b800;--orange:#4d2c0c;--orange-e:#f39a3a;--pink:#4a1a2b;--pink-e:#ef6b97;--blue:#16294a;--blue-e:#6aa0f0;--green:#173a1d;--green-e:#6cc47a;--purple:#2e2350;--purple-e:#a68af0;color-scheme:dark}
body{background:var(--bg);color:var(--fg);font-family:var(--body);font-size:17px;line-height:1.45}
main{max-width:620px;margin:0 auto;padding-block:20px 60px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));display:flex;flex-direction:column;gap:14px}
h1{font-family:var(--display);font-size:1.7rem;margin:0;text-wrap:balance}
.lede{color:var(--muted);margin:0}
.key{display:inline-block;border-radius:4px;padding:0 6px;font-weight:600;color:var(--fg);border:2px solid}
.tabs{display:flex;gap:8px;flex-wrap:wrap}
.tab{font:600 .9rem var(--body);color:var(--fg);background:var(--card);border:1.5px solid var(--line);border-radius:99px;padding:5px 12px;cursor:pointer}
.tab.on{border-color:var(--fg)}
.tab:focus-visible{outline:2px solid var(--act);outline-offset:2px}
h2{font-family:var(--display);font-size:1.2rem;margin:18px 0 0;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.pay{font-family:var(--body);font-size:.85rem;color:var(--muted);font-weight:600}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.card.proven{border:2px solid var(--act)}
.top{display:flex;justify-content:space-between;align-items:center}
.id{font-family:var(--display);font-weight:700;font-size:1.05rem}
.badge{font-size:.72rem;font-weight:600;letter-spacing:.06em;text-transform:uppercase;border:1.5px solid currentColor;border-radius:99px;padding:1px 8px}
.b-proven{color:var(--act)}
.who{margin:6px 0 8px;font-weight:600}
ol{margin:0;padding-left:1.4em;display:flex;flex-direction:column;gap:4px}
li.act{color:var(--act);font-style:italic;list-style:none;margin-left:-1.4em}
.from{margin:10px 0 0;font-size:.8rem;color:var(--muted)}
.plan{background:var(--card);border:2px solid var(--fg);border-radius:10px;padding:14px 16px;display:flex;flex-direction:column;gap:12px}
.plan h2{margin:0}.plan h3{font-family:var(--display);font-size:1rem;margin:0}
.plan ol{gap:2px}.plan a{color:var(--fg);font-weight:600}
.plan ul{margin:4px 0 0;padding-left:1.2em;color:var(--muted);font-size:.9rem}
"""
for c in COLORS:
    CSS += f".c-{c}{{background:var(--{c});border:2px solid var(--{c}-e)}}.c-{c} .badge{{border-color:var(--{c}-e)}}.k-{c}{{background:var(--{c});border-color:var(--{c}-e)}}.tab.t-{c}{{background:var(--{c})}}.tab.t-{c}.on{{border-color:var(--{c}-e)}}\n"

JS = """<script>
(function(){
var tabs=[].slice.call(document.querySelectorAll('.tab'));
function show(f){
  tabs.forEach(function(t){t.classList.toggle('on',t.dataset.f===f);});
  var head=null,any=false;
  [].slice.call(document.querySelectorAll('main > h2, main > .card')).forEach(function(el){
    if(el.tagName==='H2'){if(head)head.hidden=!any;head=el;any=false;return;}
    var vis=f==='all'||el.dataset.f===f||(f==='today'&&el.dataset.today==='1'); el.hidden=!vis; if(vis)any=true;
  });
  if(head)head.hidden=!any;
  try{localStorage.setItem('bank-tab',f);}catch(e){}
}
tabs.forEach(function(t){t.addEventListener('click',function(){show(t.dataset.f);});});
var saved=document.querySelector('.tab[data-f=today]')?'today':'all';try{saved=localStorage.getItem('bank-tab')||saved;}catch(e){}
if(!tabs.some(function(t){return t.dataset.f===saved;}))saved='all';
show(saved);
})();
</script>"""

plan = ''
if today:
    gs = ''
    for g in today['groups']:
        items = ''.join(f'<li><a href="#s-{i}">{i}</a> · {e(byid[i]["p"])} · {e(byid[i]["who"].split(" · ")[0])}</li>' for i in g['ids'])
        tips = ''.join(f'<li>{e(t)}</li>' for t in g['tips'])
        gs += f'<div><h3>{e(g["who"])}</h3><ol>{items}</ol><ul>{tips}</ul></div>'
    rules = ''.join(f'<li>{e(r)}</li>' for r in today['rules'])
    plan = f'<section class="plan" aria-label="Film today"><h2>Film today · {label(today["date"])} <span class="pay">{e(today["goal"])}</span></h2>{gs}<ul>{rules}</ul></section>'
page = f"""<title>WestFaveFinds Script Bank</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Inter:wght@400;600&display=swap">
<style>{CSS}</style>
<main>
<h1>WestFaveFinds Script Bank</h1>
<p class="lede">Your style: double-meaning hook, then a calm walkthrough. Film one, clap, film the next. Green lines are actions. Each day's batch has its own color: {legend}</p>
{plan}
<div class="tabs" role="group" aria-label="Show scripts from">{''.join(tabs)}</div>
{chr(10).join(out)}
<p class="from">Say "I actually just put it on sale" only when the sale is live. Keep hooks at this level; an explicit version can get the video restricted. Solo Stove: never light it in or right next to the car, and don't pick it up once it's lit. Never film while driving.</p>
</main>
{JS}"""
open('scripts/script-bank.html', 'w').write(page)

md = ['# Script bank · WestFaveFinds', '', 'Each batch is marked with its date. ✅ = proven. [Brackets] = actions.', '']
if today:
    md += [f"## Film today · {label(today['date'])} ({today['goal']})", '']
    for g in today['groups']:
        md += [f"**{g['who']}**", ''] + [f"{n}. {i} · {byid[i]['p']} · {byid[i]['who'].split(' · ')[0]}" for n, i in enumerate(g['ids'], 1)] + [''] + [f'- {t}' for t in g['tips']] + ['']
    md += [f'- {r}' for r in today['rules']] + ['']
cur = None
for s in d:
    if s['p'] != cur: cur = s['p']; md += [f'## {cur} ({s["pay"]})', '']
    tag = '✅ proven' if s['status'] == 'proven' else f"{label(s['added'])} ({color[s['added']]})"
    md += [f"**{s['id']}** · {tag} · {s['who']}", ''] + [f'- {l}' for l in s['lines']] + ['', f"_{s['from']}_", '']
open('scripts/SCRIPT_BANK.md', 'w').write('\n'.join(md))
print(len(d), 'scripts;', color)
