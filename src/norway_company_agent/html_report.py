"""Self-contained HTML viewer: search companies, see every fact with its source and date."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Signalpost profiles</title>
<style>
:root{--bg:#faf8f3;--card:#fff;--ink:#1d1d1b;--muted:#6b6862;--line:#e4e0d6;--ok:#2f6b3a;--warn:#9a6a00;--bad:#a03a2c;--na:#8a867d;--link:#24508f}
@media (prefers-color-scheme:dark){:root{--bg:#1a1917;--card:#23221f;--ink:#ecebe7;--muted:#a6a39b;--line:#3a3834;--link:#8db4ea}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 Georgia,'Iowan Old Style',serif}
header{padding:20px 16px 8px;max-width:1000px;margin:auto}h1{font-size:22px;margin:0 0 4px}
.meta{color:var(--muted);font:13px/1.4 system-ui,sans-serif}
.bar{position:sticky;top:0;background:var(--bg);padding:10px 16px;max-width:1000px;margin:auto;display:flex;gap:8px;flex-wrap:wrap;z-index:2;border-bottom:1px solid var(--line)}
input,select{font:14px system-ui,sans-serif;padding:8px 10px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink)}
input{flex:1;min-width:180px}
main{max-width:1000px;margin:auto;padding:8px 16px 40px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;margin:12px 0;padding:14px 16px}
.card h2{font-size:18px;margin:0}.org{color:var(--muted);font:13px system-ui,sans-serif}
.summary{margin:8px 0}
.badges{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0;font:12px system-ui,sans-serif}
.b{border:1px solid var(--line);border-radius:999px;padding:2px 8px}
.b.available{color:var(--ok);border-color:var(--ok)}.b.ambiguous,.b.blocked{color:var(--warn);border-color:var(--warn)}
.b.failed{color:var(--bad);border-color:var(--bad)}.b.not_available,.b.not_applicable{color:var(--na)}
details{margin-top:6px}summary{cursor:pointer;font:14px system-ui,sans-serif;color:var(--link)}
table{width:100%;border-collapse:collapse;font:13px/1.4 system-ui,sans-serif;margin-top:6px}
td{border-top:1px solid var(--line);padding:6px 4px;vertical-align:top;word-break:break-word}
td.f{color:var(--muted);width:24%}td.s{width:22%}a{color:var(--link)}
.chg{font:13px system-ui,sans-serif;color:var(--warn)}
@media (max-width:600px){td.f{width:30%}td.s{display:block;width:auto;border-top:0;padding-top:0}}
</style></head><body>
<header><h1>Signalpost company profiles</h1><div class="meta" id="meta"></div></header>
<div class="bar"><input id="q" placeholder="Search name, org number, city, job title…" aria-label="Search">
<select id="f" aria-label="Filter"><option value="">All companies</option><option value="website">Has verified website</option>
<option value="hiring">Hiring</option><option value="activity">Has dated activity</option><option value="changes">Changed since last run</option>
<option value="failed">Failed</option></select></div>
<main id="list"></main>
<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
document.getElementById('meta').textContent=`Run ${D.run_id} · ${D.rows.length} companies · every fact links to its source`;
const fmt=v=>{if(v==null)return'';if(typeof v!=='object')return E(v);if(v.title&&v.url)return `<a href="${E(v.url)}" rel="noopener" target="_blank">${E(v.title)}</a>${v.published?' · '+E(v.published):''}${v.closing_date?' · closes '+E(v.closing_date):''}${v.location?' · '+E(v.location):''}`;
if('amount' in v)return `${E(Number(v.amount).toLocaleString('nb-NO'))} ${E(v.currency||'')} ${v.year?'('+E(v.year)+')':''}`;if(v.name&&v.role)return `${E(v.name)} — ${E(v.role)}`;
if(v.platform)return `<a href="${E(v.url)}" target="_blank" rel="noopener">${E(v.platform)}</a>`;return E(Object.values(v).filter(x=>x!=null&&typeof x!=='object').join(', '))};
function card(r){const ev=Object.fromEntries(r.evidence.map(e=>[e.id,e]));const rows=r.claims.map(c=>{const e=ev[c.evidence_ids[0]]||{};
return `<tr><td class="f">${E(c.field)}</td><td>${fmt(c.value)}${c.reporting_period?'<br><span class="org">period '+E(c.reporting_period)+'</span>':''}${c.carried_forward?' <span class="chg">(carried from last run)</span>':''}</td><td class="s"><a href="${E(e.source_url)}" target="_blank" rel="noopener">source</a><br><span class="org">${E((e.retrieved_at||'').slice(0,10))} · ${E(e.source_class)}</span></td></tr>`}).join('');
const badges=Object.entries(r.sections).map(([k,s])=>`<span class="b ${E(s.state)}" title="${E(s.note||'')}">${E(k.replace('_',' '))}: ${E(s.state.replace('_',' '))}${s.count?' ('+s.count+')':''}</span>`).join('');
const chg=(r.changes||[]).length?`<div class="chg">${r.changes.length} change(s) since last run: ${E([...new Set(r.changes.map(c=>c.type))].join(', '))}</div>`:'';
return `<article class="card"><h2>${E(r.legal_identity.name||r.organisation_number)}</h2><div class="org">${E(r.organisation_number)} · ${E(r.status)}</div>
<p class="summary">${E(r.summary)}</p>${chg}<div class="badges">${badges}</div>
<details><summary>${r.claims.length} facts with sources</summary><table>${rows}</table></details></article>`}
const hay=r=>(r.organisation_number+' '+(r.legal_identity.name||'')+' '+r.summary+' '+r.claims.map(c=>JSON.stringify(c.value)).join(' ')).toLowerCase();
const H=D.rows.map(hay);
function render(){const q=document.getElementById('q').value.toLowerCase().trim(),f=document.getElementById('f').value;const out=[];
D.rows.forEach((r,i)=>{if(q&&!H[i].includes(q))return;if(f==='changes'&&!(r.changes||[]).length)return;if(f==='failed'&&r.status!=='failed')return;
if(['website','hiring','activity'].includes(f)&&r.sections[f].state!=='available')return;if(out.length<300)out.push(card(r))});
document.getElementById('list').innerHTML=out.join('')||'<p class="meta">No matches.</p>'}
document.getElementById('q').addEventListener('input',render);document.getElementById('f').addEventListener('change',render);render();
</script></body></html>"""


def write_html(path: Path, envelopes: list[dict[str, Any]], *, run_id: str) -> None:
    rows = [{k: e.get(k) for k in ("organisation_number", "status", "legal_identity", "sections", "claims", "evidence", "summary", "changes")} for e in envelopes]
    data = json.dumps({"run_id": run_id, "rows": rows}, ensure_ascii=False, default=str).replace("</", "<\\/")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PAGE.replace("__DATA__", data), encoding="utf-8")
