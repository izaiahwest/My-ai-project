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
label = lambda dt: datetime.date.fromisoformat(dt).strftime('%b %-d')

tabs = ['<button class="tab on" data-f="all" type="button">All</button>',
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
    done = f'<button class="done" type="button" data-id="{s["id"]}" aria-pressed="false">Done</button>'
    out.append(f'<article class="card {cls}" id="{s["id"]}" data-f="{f}"><div class="top"><span class="id">{s["id"]}</span><span class="right">{badge}{done}</span></div>'
               f'<p class="who">{e(s["who"])}</p><ol>{lis}</ol><p class="from">{e(s["from"])} · {words} words</p></article>')

# Today's filming list (scripts/plan.json): links to each card, with its own Done state.
plan_html = ''
if os.path.exists('scripts/plan.json'):
    pl = json.load(open('scripts/plan.json')); byid = {s['id']: s for s in d}
    def rows(ids):
        return ''.join(f'<li data-id="{i}"><a href="#{i}"><b>{i}</b> · {e(byid[i]["p"])} · {e(byid[i]["who"].split(" · ")[0].replace("Hook: ", ""))}</a></li>'
                       for i in ids if i in byid)
    plan_html = (f'<section class="plan"><h2>{e(pl["title"])}</h2><p class="from">{e(pl.get("note", ""))}</p>'
                 f'<ol>{rows(pl["items"])}</ol>'
                 + (f'<h3>{e(pl["bonus_title"])}</h3><ol>{rows(pl["bonus"])}</ol>' if pl.get('bonus') else '')
                 + '<p class="count" id="count"></p></section>')

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
article ol{list-style:none;counter-reset:ln}
article li:not(.act){counter-increment:ln}
article li:not(.act)::before{content:counter(ln) ". ";position:absolute;margin-left:-1.4em;color:var(--muted);font-variant-numeric:tabular-nums}
li.act{color:var(--act);font-style:italic;margin-left:-1.4em}
.from{margin:10px 0 0;font-size:.8rem;color:var(--muted)}
.right{display:flex;gap:8px;align-items:center}
.done{font:600 .85rem var(--body);color:var(--fg);background:var(--card);border:1.5px solid var(--fg);border-radius:8px;padding:6px 12px;cursor:pointer;min-height:34px}
.done:focus-visible{outline:2px solid var(--act);outline-offset:2px}
.card.is-done{filter:grayscale(1);opacity:.45}
.card.is-done .done{background:var(--fg);color:var(--bg)}
.plan{background:var(--card);border:2px solid var(--fg);border-radius:10px;padding:4px 16px 14px}
.plan h2{margin-top:10px}.plan h3{font-family:var(--display);font-size:1rem;margin:14px 0 6px}
.plan ol{gap:6px}.plan a{color:var(--fg);text-decoration:none}.plan a b{text-decoration:underline}
.plan li.is-done{opacity:.4;text-decoration:line-through}
.count{margin:10px 0 0;font-weight:600}
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
    var vis=f==='all'||el.dataset.f===f; el.hidden=!vis; if(vis)any=true;
  });
  if(head)head.hidden=!any;
  try{localStorage.setItem('bank-tab',f);}catch(e){}
}
tabs.forEach(function(t){t.addEventListener('click',function(){show(t.dataset.f);});});
var saved='all';try{saved=localStorage.getItem('bank-tab')||'all';}catch(e){}
if(!tabs.some(function(t){return t.dataset.f===saved;}))saved='all';
show(saved);
var KEY='bank-done',done={};
try{done=JSON.parse(localStorage.getItem(KEY)||'{}')||{};}catch(e){}
var planIds=[].slice.call(document.querySelectorAll('.plan li[data-id]')).map(function(li){return li.dataset.id;});
function paint(){
  [].slice.call(document.querySelectorAll('.done')).forEach(function(b){
    var on=!!done[b.dataset.id]; b.textContent=on?'Done ✓':'Done'; b.setAttribute('aria-pressed',on);
    var c=b.closest('.card'); if(c)c.classList.toggle('is-done',on);
  });
  [].slice.call(document.querySelectorAll('.plan li[data-id]')).forEach(function(li){li.classList.toggle('is-done',!!done[li.dataset.id]);});
  var n=planIds.filter(function(i){return done[i];}).length, c=document.getElementById('count');
  if(c)c.textContent=n+' of '+planIds.length+' filmed';
}
document.addEventListener('click',function(ev){
  var b=ev.target.closest('.done'); if(!b)return;
  if(done[b.dataset.id])delete done[b.dataset.id]; else done[b.dataset.id]=1;
  try{localStorage.setItem(KEY,JSON.stringify(done));}catch(e){}
  paint();
});
paint();
[].slice.call(document.querySelectorAll('.plan a')).forEach(function(a){a.addEventListener('click',function(){show('all');});});
})();
</script>"""

page = f"""<title>WestFaveFinds Script Bank</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Inter:wght@400;600&display=swap">
<style>{CSS}</style>
<main>
<h1>WestFaveFinds Script Bank</h1>
<p class="lede">Your style: double-meaning hook, then a calm walkthrough. Film one, clap, film the next. Green lines are actions. Tap Done when you've filmed one (tap again to undo). Each day's batch has its own color: {legend}</p>
<div class="tabs" role="group" aria-label="Show scripts from">{''.join(tabs)}</div>
{plan_html}
{chr(10).join(out)}
<p class="from">Say "I actually just put it on sale" only when the sale is live. Keep hooks at this level; an explicit version can get the video restricted. Solo Stove: never light it in or right next to the car, and don't pick it up once it's lit. Never film while driving.</p>
</main>
{JS}"""
open('scripts/script-bank.html', 'w').write(page)

md = ['# Script bank · WestFaveFinds', '', 'Each batch is marked with its date. ✅ = proven. [Brackets] = actions.', '']
cur = None
for s in d:
    if s['p'] != cur: cur = s['p']; md += [f'## {cur} ({s["pay"]})', '']
    tag = '✅ proven' if s['status'] == 'proven' else f"{label(s['added'])} ({color[s['added']]})"
    md += [f"**{s['id']}** · {tag} · {s['who']}", ''] + [f'- {l}' for l in s['lines']] + ['', f"_{s['from']}_", '']
open('scripts/SCRIPT_BANK.md', 'w').write('\n'.join(md))
print(len(d), 'scripts;', color)
