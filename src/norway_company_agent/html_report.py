"""Self-contained HTML viewer: a company directory where every fact links to its source and date."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Signalpost profiles</title>
<style>
:root{--bg:#f6f3ec;--panel:#fffdf9;--ink:#1f1d1a;--muted:#6d6860;--line:#e6e0d4;--soft:#f1ece2;--accent:#8a2433;--accent-soft:#f6e8ea;
--ok:#2d6a3e;--ok-soft:#e6f1e8;--warn:#8a5a00;--warn-soft:#f8eed9;--bad:#a23a2c;--bad-soft:#f8e4e0;--na:#8b867c;--link:#25508c;
--serif:Georgia,'Iowan Old Style','Times New Roman',serif;--sans:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#171614;--panel:#211f1c;--ink:#ece9e3;--muted:#a59f95;--line:#38342f;--soft:#2a2724;
--accent:#e0808c;--accent-soft:#3a2327;--ok:#7cc48d;--ok-soft:#1f3325;--warn:#e0b25c;--warn-soft:#3a2f1a;--bad:#ec8d7f;--bad-soft:#3d221e;--na:#8f897f;--link:#8fb6ec}}
:root[data-theme="dark"]{--bg:#171614;--panel:#211f1c;--ink:#ece9e3;--muted:#a59f95;--line:#38342f;--soft:#2a2724;
--accent:#e0808c;--accent-soft:#3a2327;--ok:#7cc48d;--ok-soft:#1f3325;--warn:#e0b25c;--warn-soft:#3a2f1a;--bad:#ec8d7f;--bad-soft:#3d221e;--na:#8f897f;--link:#8fb6ec}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--ink)}
body{font:15px/1.5 var(--sans)}a{color:var(--link)}button,select,input{font:inherit;color:inherit}
.top{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line)}
.top-in{max-width:1280px;margin:auto;padding:12px 16px;display:flex;gap:16px;align-items:center}
.brand{display:flex;gap:10px;align-items:center;min-width:max-content}
.mark{width:26px;height:26px;border-radius:6px;background:var(--accent);display:grid;place-items:center;color:#fff;font:700 15px var(--serif)}
.brand b{font:700 20px var(--serif);display:block;line-height:1}.brand small{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.search{flex:1;position:relative}.search input{width:100%;padding:10px 40px 10px 14px;border:1px solid var(--line);border-radius:10px;background:var(--panel)}
.search kbd{position:absolute;right:10px;top:50%;transform:translateY(-50%);font-size:11px;color:var(--muted);border:1px solid var(--line);border-radius:5px;padding:1px 6px}
.theme{border:1px solid var(--line);background:var(--panel);border-radius:8px;padding:8px 10px;cursor:pointer}
.wrap{max-width:1280px;margin:auto;padding:16px}
.stats{display:grid;grid-template-columns:repeat(6,1fr);background:var(--panel);border:1px solid var(--line);border-radius:12px;margin-bottom:16px}
.stat{padding:12px 14px;border-left:1px solid var(--line)}.stat:first-child{border-left:0}
.stat span{display:block;font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.stat b{display:block;font:700 18px/1.25 var(--serif);margin-top:2px}.stat em{font-style:normal;font-size:12px;color:var(--muted)}
.grid{display:grid;grid-template-columns:330px 1fr;gap:16px;align-items:start}
.dir{background:var(--panel);border:1px solid var(--line);border-radius:12px;position:sticky;top:76px;max-height:calc(100vh - 92px);display:flex;flex-direction:column}
.dir-h{padding:14px 14px 10px;border-bottom:1px solid var(--line)}
.kicker{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--accent);font-weight:700}
.dir-h h2{font:700 24px var(--serif);margin:2px 0 0;display:flex;justify-content:space-between;align-items:baseline}.dir-h h2 small{font:600 13px var(--sans);color:var(--muted)}
.dir-h p{margin:2px 0 10px;font-size:12.5px;color:var(--muted)}
.ctl{display:flex;gap:8px}.ctl select{flex:1;padding:7px 8px;border:1px solid var(--line);border-radius:8px;background:var(--panel);font-size:13px}
.list{overflow:auto;flex:1}
.item{display:flex;gap:8px;justify-content:space-between;align-items:center;width:100%;text-align:left;padding:10px 14px;border:0;border-bottom:1px solid var(--line);background:none;cursor:pointer;border-left:3px solid transparent}
.item:hover{background:var(--soft)}.item.on{background:var(--accent-soft);border-left-color:var(--accent)}
.item b{display:block;font-size:13.5px;font-weight:650}.item small{display:block;font-size:11.5px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:220px}
.pill{font-size:11px;font-weight:700;border-radius:999px;padding:2px 8px;white-space:nowrap;background:var(--soft);color:var(--muted)}
.pill.hi{background:var(--ok-soft);color:var(--ok)}.pill.mid{background:var(--warn-soft);color:var(--warn)}.pill.bad{background:var(--bad-soft);color:var(--bad)}
.more{padding:10px 14px;font-size:12px;color:var(--muted)}
.detail{background:var(--panel);border:1px solid var(--line);border-radius:12px;min-width:0}
.hero{padding:20px 22px 16px;display:grid;grid-template-columns:1fr auto;gap:16px;border-bottom:1px solid var(--line)}
.hero h1{font:700 32px/1.1 var(--serif);margin:4px 0 6px;overflow-wrap:anywhere}.sub{font-size:13px;color:var(--muted)}
.desc{font:16px/1.55 var(--serif);margin:10px 0 8px;max-width:62ch}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
.chip{font-size:11.5px;border:1px solid var(--line);border-radius:999px;padding:3px 9px;display:inline-flex;gap:6px;align-items:center}
.chip::before{content:"";width:6px;height:6px;border-radius:50%;background:var(--na)}.chip.ok::before{background:var(--ok)}.chip.warn::before{background:var(--warn)}.chip.bad::before{background:var(--bad)}
.meter{text-align:right;min-width:150px}.meter b{font:700 30px var(--serif)}.meter span{font-size:12px;color:var(--muted)}
.meter p{margin:0;font-size:12px;color:var(--ok);font-weight:600}.bars{display:flex;gap:4px;justify-content:flex-end;margin-top:8px}
.bars i{width:22px;height:4px;border-radius:2px;background:var(--line)}.bars i.on{background:var(--ok)}
.back{display:none;margin:12px 16px 0;border:1px solid var(--line);background:var(--panel);border-radius:8px;padding:6px 10px;cursor:pointer}
.tabs{display:flex;gap:4px;overflow-x:auto;padding:0 14px;border-bottom:1px solid var(--line);position:sticky;top:64px;background:var(--panel);z-index:2}
.tabs a{padding:11px 9px;font-size:13px;font-weight:600;color:var(--muted);text-decoration:none;white-space:nowrap;border-bottom:2px solid transparent}
.tabs a:hover{color:var(--ink);border-bottom-color:var(--accent)}
.kpis{display:grid;grid-template-columns:repeat(3,1fr);border-bottom:1px solid var(--line)}
.kpi{padding:14px 18px;border-right:1px solid var(--line);border-bottom:1px solid var(--line)}.kpi:nth-child(3n){border-right:0}
.kpi span{display:block;font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.kpi b{display:block;font:700 22px/1.2 var(--serif);margin-top:3px}.kpi em{font-style:normal;font-size:12px;color:var(--muted)}
.kpi b.none{color:var(--na);font-size:16px}
section{padding:20px 22px;border-bottom:1px solid var(--line);scroll-margin-top:110px}section:last-child{border-bottom:0}
.sh{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin-bottom:12px}
.sh h3{font:700 22px var(--serif);margin:0}.sh span{font-size:12px;color:var(--muted)}
.cards{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
.card{border:1px solid var(--line);border-radius:10px;padding:10px 12px;background:var(--bg)}
.card b{display:block;font-size:14px}.card small{display:block;font-size:12px;color:var(--muted)}
.empty{font-size:13.5px;color:var(--muted);background:var(--soft);border-radius:10px;padding:12px 14px}
.empty.warn{background:var(--warn-soft);color:var(--warn)}.empty.bad{background:var(--bad-soft);color:var(--bad)}
.src{font-size:11.5px;margin-left:4px;color:var(--muted);text-decoration:none;border-bottom:1px dotted var(--muted)}
.src:hover{color:var(--link);border-color:var(--link)}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:600}td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.tw{overflow-x:auto}
.feed{list-style:none;margin:0;padding:0}.feed li{padding:10px 0;border-bottom:1px solid var(--line)}.feed li:last-child{border-bottom:0}
.feed b{font-weight:650}.feed small{display:block;color:var(--muted);font-size:12px}
.date{display:inline-block;font-size:11px;font-weight:700;color:var(--accent);background:var(--accent-soft);border-radius:5px;padding:1px 6px;margin-right:6px}
.summary{font:16px/1.6 var(--serif);margin:0 0 10px}
ul.unk{margin:6px 0 0;padding-left:18px;font-size:13.5px;color:var(--muted)}
.kv{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}.kv .card span{display:block;font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.kv .card b{font-size:15px;overflow-wrap:anywhere}
.state{font-weight:700;font-size:12.5px}.state.available{color:var(--ok)}.state.ambiguous,.state.blocked{color:var(--warn)}.state.failed{color:var(--bad)}
.state.not_available,.state.not_applicable{color:var(--na)}
details.ev{margin-top:10px}details.ev summary{cursor:pointer;font-size:13px;font-weight:600;color:var(--link)}
.mono{font-family:ui-monospace,Consolas,monospace;font-size:12px;overflow-wrap:anywhere}
.chg{border-left:3px solid var(--warn);padding:6px 10px;background:var(--warn-soft);border-radius:0 8px 8px 0;margin:6px 0;font-size:13px}
.foot{font-size:12px;color:var(--muted);text-align:center;padding:18px}
@media (max-width:1000px){.stats{grid-template-columns:repeat(3,1fr)}.stat:nth-child(4){border-left:0}.stat:nth-child(n+4){border-top:1px solid var(--line)}}
@media (max-width:820px){
 .grid{grid-template-columns:1fr}.dir{position:static;max-height:none}.list{max-height:none}
 body.show-detail .dir{display:none}body:not(.show-detail) .detail{display:none}.back{display:inline-block}
 .hero{grid-template-columns:1fr}.meter{text-align:left}.bars{justify-content:flex-start}.hero h1{font-size:26px}
 .kpis{grid-template-columns:repeat(2,1fr)}.kpi:nth-child(3n){border-right:1px solid var(--line)}.kpi:nth-child(2n){border-right:0}
 .top-in{flex-wrap:wrap;gap:10px}.search{order:3;flex-basis:100%}.brand{flex:1}
 .cards,.kv{grid-template-columns:1fr}.tabs{top:112px}.dir{top:auto}.brand small{display:none}.search kbd{display:none}section{padding:16px}
 .stats{grid-template-columns:repeat(2,1fr)}.stat{border-left:0;border-top:1px solid var(--line)}.stat:nth-child(-n+2){border-top:0}.stat:nth-child(2n){border-left:1px solid var(--line)}
}
</style></head><body>
<header class="top"><div class="top-in">
 <div class="brand"><div class="mark">S</div><div><b>Signalpost</b><small>Norwegian company research</small></div></div>
 <label class="search"><input id="q" type="search" placeholder="Search company, organisation number, industry, place, job…" aria-label="Search companies"><kbd>/</kbd></label>
 <button class="theme" id="theme" type="button" aria-label="Toggle dark mode">◐</button>
</div></header>
<div class="wrap">
 <div class="stats" id="stats"></div>
 <div class="grid">
  <aside class="dir">
   <div class="dir-h"><div class="kicker">Company directory</div><h2>Companies <small id="count"></small></h2>
    <p>Every fact links to the page or register it came from.</p>
    <div class="ctl"><select id="sort" aria-label="Sort"><option value="data">Most data found</option><option value="input">Input order</option><option value="name">Name A–Z</option><option value="revenue">Highest revenue</option></select>
    <select id="filter" aria-label="Filter"><option value="">All companies</option><option value="website">Verified website</option><option value="hiring">Hiring</option><option value="activity">Dated activity</option><option value="profiles">Social profiles</option><option value="changes">Changed since last run</option><option value="ambiguous">Withheld (ambiguous)</option><option value="failed">Failed</option></select></div>
   </div>
   <div class="list" id="list" role="listbox" aria-label="Companies"></div>
  </aside>
  <main class="detail" id="detail" aria-live="polite"></main>
 </div>
 <div class="foot" id="foot"></div>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent),ROWS=D.rows;
const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const U=u=>{try{const x=new URL(String(u));return /^https?:$/.test(x.protocol)?x.href:null}catch(e){return null}};
const A=(u,t)=>{const h=U(u);return h?`<a href="${E(h)}" target="_blank" rel="noopener noreferrer">${E(t??u)}</a>`:E(t??u)};
const day=s=>String(s||'').slice(0,10);
const NB=new Intl.NumberFormat('nb-NO');
const money=v=>{if(v==null)return null;const n=Number(v),a=Math.abs(n),s=n<0?'−':'';if(a>=1e9)return s+(a/1e9).toFixed(1)+'B';if(a>=1e6)return s+(a/1e6).toFixed(1)+'M';if(a>=1e3)return s+Math.round(a/1e3)+'k';return s+NB.format(a)};
const AREAS=[['annual_accounts','Annual accounts'],['leadership','Leadership'],['workplaces','Locations'],['website','Company website'],['hiring_activity','Hiring & activity']];
const STATE_TXT={available:'Included',not_available:'Not found',not_applicable:'Not applicable',ambiguous:'Withheld — company match not certain',blocked:'Blocked by source',failed:'Source failed this run'};
const METRICS=[['revenue','Revenue'],['operating_result','Operating result'],['profit_before_tax','Profit before tax'],['annual_result','Annual result'],['assets','Total assets'],['equity','Equity'],['debt','Debt']];
const VERIFY={org_number_on_site:'Our organisation number is shown on the site',legal_name_on_registry_linked_site:'Site is linked from the official register and shows the full legal name',legal_name_and_address_on_site:'Site shows the full legal name and the registered address'};
const FOUND={registry_link:'Linked in the official register',domain_guess:'Found by checking domains matching the legal name'};

function prep(r){
 const ev=Object.fromEntries((r.evidence||[]).map(e=>[e.id,e]));const by={};
 for(const c of r.claims||[])(by[c.field]=by[c.field]||[]).push(c);
 const s=r.sections||{},st=k=>(s[k]||{}).state;
 const area={annual_accounts:st('annual_accounts'),leadership:st('leadership'),workplaces:st('workplaces'),website:st('website'),
  hiring_activity:(st('hiring')==='available'||st('activity')==='available')?'available':(st('hiring')||st('activity'))};
 const score=AREAS.filter(([k])=>area[k]==='available').length;
 const li=r.legal_identity||{},addr=li.address||{};
 const fin={};for(const[m]of METRICS)for(const c of by['financials.'+m]||[]){const y=c.value.year;(fin[y]=fin[y]||{})[m]=c}
 const years=Object.keys(fin).sort().reverse();
 const rev=years.length&&fin[years[0]].revenue?fin[years[0]].revenue.value.amount:null;
 const hay=[r.organisation_number,li.name,addr.poststed,addr.kommune,(li.industry||{}).beskrivelse,r.summary,
  ...(by.job_posting||[]).map(c=>c.value.title),...(by['leadership.role']||[]).map(c=>c.value.name),
  ...(by.official_website||[]).map(c=>c.value)].join(' ').toLowerCase();
 return {r,ev,by,s,area,score,li,addr,fin,years,rev,hay};
}
const P=ROWS.map(prep);
let sel=null;

function srcLink(p,c){const e=p.ev[(c.evidence_ids||[])[0]];if(!e)return'';const h=U(e.source_url);
 const tip=`${e.source_class||''} · retrieved ${day(e.retrieved_at)}${e.claim_span?' · “'+String(e.claim_span).slice(0,140)+'”':''}`;
 return h?`<a class="src" href="${E(h)}" target="_blank" rel="noopener noreferrer" title="${E(tip)}">source</a>`:''}

function stats(){
 const n=P.length,c=k=>P.filter(p=>p.s[k]&&p.s[k].state==='available').length;
 const guess=P.filter(p=>p.s.website&&p.s.website.state==='available'&&p.s.website.found_by==='domain_guess').length;
 const withheld=P.filter(p=>p.s.website&&p.s.website.state==='ambiguous').length;
 const failed=P.filter(p=>p.r.status==='failed').length;
 const claims=P.reduce((a,p)=>a+(p.r.claims||[]).length,0),withEv=P.reduce((a,p)=>a+(p.r.claims||[]).filter(c=>(c.evidence_ids||[]).some(i=>p.ev[i])).length,0);
 const changes=P.reduce((a,p)=>a+(p.r.changes||[]).length,0);
 const runDay=day((ROWS[0]&&ROWS[0].run&&ROWS[0].run.completed_at)||'');
 const cell=(l,b,e)=>`<div class="stat"><span>${l}</span><b>${b}</b>${e?`<em>${e}</em>`:''}</div>`;
 document.getElementById('stats').innerHTML=
  cell('This run',E(D.run_id),`${n} companies${runDay?' · '+runDay:''}`)+
  cell('Results returned',`${n} / ${n}`,failed?`${failed} failed, still reported`:'none dropped')+
  cell('Verified websites',c('website'),`${guess} found by domain check · ${withheld} withheld`)+
  cell('Hiring · activity',`${c('hiring')} · ${c('activity')}`,'companies with dated items')+
  cell('Facts with evidence',`${withEv===claims?'100%':Math.round(100*withEv/Math.max(claims,1))+'%'}`,`${NB.format(claims)} facts`)+
  cell('Changes since last run',changes,P.some(p=>(p.r.refresh||{}).mode==='diff')?'compared with previous run':'first run');
 document.getElementById('foot').textContent=`Signalpost agent · run ${D.run_id} · official data from Brønnøysundregistrene (NLOD) · company websites as published by the companies`;
}

function list(){
 const q=document.getElementById('q').value.trim().toLowerCase(),f=document.getElementById('filter').value,so=document.getElementById('sort').value;
 let rows=P.filter(p=>{if(q&&!q.split(/\s+/).every(t=>p.hay.includes(t)))return false;
  if(f==='changes')return (p.r.changes||[]).length>0;if(f==='failed')return p.r.status==='failed';
  if(f==='ambiguous')return Object.values(p.s).some(x=>x.state==='ambiguous');if(f==='profiles')return (p.s.company_profiles||{}).state==='available';
  if(f)return (p.s[f]||{}).state==='available';return true});
 if(so==='data')rows=rows.slice().sort((a,b)=>b.score-a.score||(b.r.claims||[]).length-(a.r.claims||[]).length);
 if(so==='name')rows=rows.slice().sort((a,b)=>String(a.li.name).localeCompare(String(b.li.name),'nb'));
 if(so==='revenue')rows=rows.slice().sort((a,b)=>(b.rev??-Infinity)-(a.rev??-Infinity));
 document.getElementById('count').textContent=rows.length===P.length?P.length:`${rows.length} of ${P.length}`;
 const show=rows.slice(0,400);
 document.getElementById('list').innerHTML=show.map(p=>{const cls=p.r.status==='failed'?'bad':p.score>=4?'hi':p.score>=2?'mid':'';
  return `<button class="item${sel===p?' on':''}" data-org="${E(p.r.organisation_number)}" role="option" aria-selected="${sel===p}"><span><b>${E(p.li.name||p.r.organisation_number)}</b>
  <small>${E([p.addr.poststed||p.addr.kommune,(p.li.industry||{}).beskrivelse].filter(Boolean).join(' · ')||p.r.organisation_number)}</small></span>
  <span class="pill ${cls}">${p.r.status==='failed'?'failed':p.score+'/5 data'}</span></button>`}).join('')
  +(rows.length>show.length?`<div class="more">Showing 400 of ${rows.length}. Search to narrow down.</div>`:'')+(rows.length?'':'<div class="more">No companies match.</div>');
 return rows;
}

function kpi(l,v,sub){return `<div class="kpi"><span>${l}</span>${v==null||v===''?'<b class="none">Not found</b>':`<b>${v}</b>`}${sub?`<em>${sub}</em>`:''}</div>`}
function empty(state,note,what){const cls=state==='ambiguous'||state==='blocked'?'warn':state==='failed'?'bad':'';
 return `<div class="empty ${cls}">${E(STATE_TXT[state]||'Not found')}${note?' — '+E(note):''}${what?'. '+E(what):''}</div>`}

function detail(p){
 const r=p.r,li=p.li,b=p.by,s=p.s,ind=(li.industry||{}).beskrivelse;
 const site=(b.official_website||[])[0],descr=(b.company_description||[])[0],brand=(b.public_brand||[])[0];
 const jobs=b.job_posting||[],news=(b.news_item||[]).slice().sort((x,y)=>String(y.value.published).localeCompare(String(x.value.published)));
 const roles=b['leadership.role']||[],places=b.workplace||[],profiles=b.company_profile||[],group=b['group.related_entity']||[];
 const y0=p.years[0],F=y0?p.fin[y0]:{},amt=m=>F[m]?F[m].value.amount:null;
 const emp=(b.registered_employees||[])[0];
 const chips=[];
 if(y0)chips.push(['ok',`Annual accounts ${y0}`]);
 chips.push(site?['ok','Verified website']:s.website&&s.website.state==='ambiguous'?['warn','Website withheld']:['','No verified website']);
 if(profiles.length)chips.push(['ok',`${profiles.length} social profile${profiles.length>1?'s':''}`]);
 chips.push(jobs.length?['ok',`${jobs.length} job posting${jobs.length>1?'s':''}`]:['','No job postings found']);
 if(news.length)chips.push(['ok',`${news.length} dated update${news.length>1?'s':''}`]);
 if((r.changes||[]).length)chips.push(['warn',`${r.changes.length} change${r.changes.length>1?'s':''} since last run`]);
 if(r.status==='failed')chips.push(['bad','Run failed for this company']);
 const done=r.run&&r.run.completed_at;

 let h=`<button class="back" type="button" id="back">← All companies</button>
 <div class="hero"><div><div class="kicker">${E(ind||'Industry not registered')}</div><h1>${E(li.name||r.organisation_number)}</h1>
 <div class="sub">Organisation ${E(r.organisation_number)} · ${E(li.legal_form||'')}${p.addr.poststed?' · '+E(p.addr.poststed):''}${brand&&brand.value&&brand.value!==li.name?' · public name “'+E(brand.value)+'”':''}</div>
 ${descr?`<p class="desc">${E(descr.value)} ${srcLink(p,descr)}</p>`:''}
 <div class="chips">${chips.map(([c,t])=>`<span class="chip ${c}">${E(t)}</span>`).join('')}</div>
 <div class="sub">${done?'Checked '+E(day(done))+' · ':''}Hover or open any “source” link to verify a fact</div></div>
 <div class="meter"><b>${p.score}</b> <span>of 5 data areas</span><p>${p.score===5?'Data found in all five areas':p.score?'Data found in '+p.score+' area'+(p.score>1?'s':''):'No data found'}</p>
 <div class="bars">${AREAS.map(([k,l])=>`<i class="${p.area[k]==='available'?'on':''}" title="${E(l)}: ${E(STATE_TXT[p.area[k]]||'Not found')}"></i>`).join('')}</div></div></div>
 <nav class="tabs" aria-label="Sections"><a href="#s-overview">Overview</a><a href="#s-fin">Financials</a><a href="#s-lead">Leadership</a><a href="#s-loc">Locations</a><a href="#s-hire">Hiring & activity</a><a href="#s-run">Run evidence</a><a href="#s-src">Sources found</a></nav>
 <div class="kpis">${kpi('Latest revenue',money(amt('revenue')),y0?'NOK · '+y0:'')}${kpi('Operating result',money(amt('operating_result')),y0||'')}${kpi('Annual result',money(amt('annual_result')),y0||'')}
 ${kpi('Employees in register',emp?NB.format(emp.value):null,'Official company record')}${kpi('Registered workplaces',places.length||null,'Official subunits')}${kpi('Job postings found',(s.hiring||{}).state==='available'?jobs.length:null,site?'From the company’s own site':'No verified site to check')}</div>`;

 h+=`<section id="s-overview"><div class="sh"><h3>Company overview</h3><span>Written only from the facts below</span></div>
 <p class="summary">${E(r.summary)}</p>
 ${(r.changes||[]).length?r.changes.slice(0,12).map(c=>`<div class="chg"><b>${E(String(c.type).replace(/_/g,' '))}</b> · ${E(c.claim_key||'')}</div>`).join(''):''}
 ${(r.unknowns||[]).length?`<b style="font-size:13px">Not found or not confirmed</b><ul class="unk">${r.unknowns.map(u=>`<li>${E(u)}</li>`).join('')}</ul>`:''}
 <div class="kv" style="margin-top:14px">
  <div class="card"><span>Registered address</span><b>${E([(p.addr.adresse||[]).join(', '),[p.addr.postnummer,p.addr.poststed].filter(Boolean).join(' ')].filter(Boolean).join(', ')||'Not registered')}</b>${(b.business_address||[])[0]?srcLink(p,b.business_address[0]):''}</div>
  <div class="card"><span>Official website</span><b>${site?A(site.value)+' '+srcLink(p,site):(s.website||{}).state==='ambiguous'?'Withheld — could not prove it is this company':'Not found'}</b>${site?`<small>${E(VERIFY[(s.website||{}).verification]||s.website.verification||'')}</small>`:''}</div>
  <div class="card"><span>Industry</span><b>${E(ind||'Not registered')}</b><small>${E((li.industry||{}).kode||'')}</small></div>
  <div class="card"><span>Company profiles</span><b>${profiles.length?profiles.map(c=>A(c.value.url,c.value.platform)).join(' · '):'None linked from a verified site'}</b>${profiles.length?'<small>Linked from the company’s verified website</small>':''}</div>
 </div></section>`;

 h+=`<section id="s-fin"><div class="sh"><h3>Financials</h3><span>Filed annual accounts · Regnskapsregisteret</span></div>`;
 if(p.years.length){h+=`<div class="tw"><table><thead><tr><th>NOK</th>${p.years.map(y=>`<th class="n">${E(y)}</th>`).join('')}</tr></thead><tbody>${METRICS.map(([m,l])=>
  `<tr><td>${l}</td>${p.years.map(y=>{const c=p.fin[y][m];return `<td class="n">${c?NB.format(c.value.amount)+srcLink(p,c):'<span style="color:var(--na)">—</span>'}</td>`}).join('')}</tr>`).join('')}</tbody></table></div>
  <p class="sub" style="margin-top:8px">“—” means the figure was not in the filing. Missing figures are never shown as zero.${F.revenue&&F.revenue.reporting_period?' Latest period: '+E(F.revenue.reporting_period)+'.':''}</p>`}
 else h+=empty((s.annual_accounts||{}).state,(s.annual_accounts||{}).note);
 h+=`</section>`;

 h+=`<section id="s-lead"><div class="sh"><h3>Leadership</h3><span>Registered roles · Enhetsregisteret</span></div>${roles.length?`<div class="cards">${roles.map(c=>
  `<div class="card"><b>${E(c.value.name)}</b><small>${E(c.value.role)}${c.effective_at?' · since '+E(day(c.effective_at)):''} ${srcLink(p,c)}</small></div>`).join('')}</div>`:empty((s.leadership||{}).state,(s.leadership||{}).note)}
  ${group.length?`<div class="sh" style="margin-top:16px"><h3 style="font-size:17px">Group relations</h3><span>Labelled, never merged</span></div><div class="cards">${group.map(c=>
  `<div class="card"><b>${E(c.value.name)}</b><small>${E(c.value.organisation_number)} · ${E(String(c.value.relation||'').replace(/_/g,' '))} ${srcLink(p,c)}</small></div>`).join('')}</div>`:''}</section>`;

 h+=`<section id="s-loc"><div class="sh"><h3>Locations</h3><span>Registered workplaces</span></div>${places.length?`<div class="cards">${places.map(c=>{const a=c.value.address||{};
  return `<div class="card"><b>${E(c.value.name)}</b><small>${E([(a.adresse||[]).join(', '),[a.postnummer,a.poststed].filter(Boolean).join(' ')].filter(Boolean).join(', '))} ${srcLink(p,c)}</small></div>`}).join('')}</div>`:empty((s.workplaces||{}).state,(s.workplaces||{}).note)}</section>`;

 h+=`<section id="s-hire"><div class="sh"><h3>Hiring & public activity</h3><span>Company-owned pages, dated items only</span></div>
 <b style="font-size:14px">Job postings</b>${jobs.length?`<ul class="feed">${jobs.map(c=>{const v=c.value;return `<li>${v.date_posted?`<span class="date">${E(v.date_posted)}</span>`:''}<b>${A(v.url,v.title)}</b> ${srcLink(p,c)}
  <small>${E([v.location,v.closing_date?'closes '+v.closing_date:'',v.hiring_organization].filter(Boolean).join(' · '))}</small></li>`}).join('')}</ul>`:empty((s.hiring||{}).state,(s.hiring||{}).note)}
 <b style="font-size:14px;display:block;margin-top:16px">Dated updates</b>${news.length?`<ul class="feed">${news.map(c=>`<li><span class="date">${E(c.value.published)}</span><b>${A(c.value.url,c.value.title)}</b> ${srcLink(p,c)}</li>`).join('')}</ul>`:empty((s.activity||{}).state,(s.activity||{}).note)}</section>`;

 const w=s.website||{},att=r.attempts||[],ops=r.operations||{},webEv=site?p.ev[(site.evidence_ids||[])[0]]:null;
 h+=`<section id="s-run"><div class="sh"><h3>Run & identity evidence</h3><span>Why company-site facts were published or withheld</span></div><div class="kv">
  <div class="card"><span>Website identity</span><b class="state ${E(w.state)}">${w.state==='available'?'Exact company · published':E(STATE_TXT[w.state]||'Not found')}</b><small>${E(VERIFY[w.verification]||w.note||'')}</small></div>
  <div class="card"><span>How the site was found</span><b>${E(FOUND[w.found_by]||(site?'—':'No site found'))}</b></div>
  <div class="card"><span>Requests · runtime</span><b>${E(ops.requests??'—')} · ${ops.runtime_ms!=null?(ops.runtime_ms/1000).toFixed(1)+' s':'—'}</b><small>Third-party cost $${E(ops.third_party_cost_usd??0)}</small></div>
  <div class="card"><span>Refresh</span><b>${(r.refresh||{}).mode==='diff'?((r.changes||[]).length?r.changes.length+' material change'+(r.changes.length>1?'s':''):'No changes since last run'):'First run'}</b><small>${E((r.refresh||{}).previous_run_id?'Compared with '+r.refresh.previous_run_id:'')}</small></div>
  ${webEv?`<div class="card" style="grid-column:1/-1"><span>Website snapshot hash</span><b class="mono">${E(webEv.content_sha256)}</b><small>Retrieved ${E(day(webEv.retrieved_at))} · “${E(String(webEv.claim_span||'').slice(0,200))}”</small></div>`:''}
 </div>
 ${att.length?`<details class="ev"><summary>Website attempts (${att.length})</summary><div class="tw"><table><thead><tr><th>Strategy</th><th>Candidate</th><th>Result</th></tr></thead><tbody>${att.map(a=>
  `<tr><td>${E(a.strategy)}</td><td class="mono">${E(a.url||a.domain||'')}</td><td>${E(a.status||'')}${a.verified?' · verified':''}${a.reason?' · '+E(a.reason):''}</td></tr>`).join('')}</tbody></table></div></details>`:''}
 ${(r.errors||[]).length?`<details class="ev" open><summary>Errors (${r.errors.length})</summary><ul class="unk">${r.errors.map(e=>`<li>${E(e.stage)}: ${E(e.message)}</li>`).join('')}</ul></details>`:''}
 </section>`;

 const SRC=[['legal_identity','Company record'],['annual_accounts','Financials'],['leadership','Leadership'],['workplaces','Locations'],['group','Group relations'],['website','Company website'],['company_profiles','Social profiles'],['hiring','Job postings'],['activity','Dated activity']];
 const found=SRC.filter(([k])=>(s[k]||{}).state==='available').length;
 h+=`<section id="s-src"><div class="sh"><h3>Sources found</h3><span>${found} of ${SRC.length} checked</span></div><div class="tw"><table><tbody>${SRC.map(([k,l])=>{const x=s[k]||{};
  return `<tr><td>${l}</td><td>${E(x.note||'')}</td><td class="n"><span class="state ${E(x.state)}">${E(STATE_TXT[x.state]||'—')}</span></td></tr>`}).join('')}</tbody></table></div>
 <details class="ev"><summary>All ${(r.claims||[]).length} facts with their evidence</summary><div class="tw"><table><thead><tr><th>Field</th><th>Value</th><th>Source</th></tr></thead><tbody>${(r.claims||[]).map(c=>{const e=p.ev[(c.evidence_ids||[])[0]]||{};
  const v=typeof c.value==='object'&&c.value?Object.entries(c.value).filter(([,x])=>x!=null&&typeof x!=='object').map(([k,x])=>k+': '+x).join(' · '):c.value;
  return `<tr><td>${E(c.field)}</td><td>${E(v)}${c.reporting_period?`<br><small class="sub">period ${E(c.reporting_period)}</small>`:''}${c.carried_forward?'<br><small class="sub">carried from last run</small>':''}</td>
  <td>${A(e.source_url,(U(e.source_url)?new URL(e.source_url).hostname:'source'))}<br><small class="sub">${E(e.source_class||'')} · ${E(day(e.retrieved_at))}</small></td></tr>`}).join('')}</tbody></table></div></details></section>`;

 const el=document.getElementById('detail');el.innerHTML=h;
 document.getElementById('back').onclick=()=>{document.body.classList.remove('show-detail');history.replaceState(null,'',location.pathname);window.scrollTo(0,0)};
}

function choose(p,push){sel=p;detail(p);document.querySelectorAll('.item').forEach(b=>{const on=b.dataset.org===p.r.organisation_number;b.classList.toggle('on',on);b.setAttribute('aria-selected',on)});
 if(push)history.replaceState(null,'','#org='+p.r.organisation_number)}
document.getElementById('list').addEventListener('click',ev=>{const b=ev.target.closest('.item');if(!b)return;const p=P.find(x=>x.r.organisation_number===b.dataset.org);
 if(p){choose(p,true);document.body.classList.add('show-detail');if(window.matchMedia('(max-width:820px)').matches)window.scrollTo(0,0);else document.getElementById('detail').scrollIntoView({block:'start'})}});
['q','sort','filter'].forEach(id=>document.getElementById(id).addEventListener(id==='q'?'input':'change',()=>{list()}));
document.addEventListener('keydown',e=>{if(e.key==='/'&&document.activeElement.tagName!=='INPUT'){e.preventDefault();document.getElementById('q').focus()}});
const themeBtn=document.getElementById('theme');let theme=null;try{theme=localStorage.getItem('sp-theme')}catch(e){}
if(theme)document.documentElement.dataset.theme=theme;
themeBtn.onclick=()=>{const dark=document.documentElement.dataset.theme?document.documentElement.dataset.theme==='dark':matchMedia('(prefers-color-scheme:dark)').matches;
 const next=dark?'light':'dark';document.documentElement.dataset.theme=next;try{localStorage.setItem('sp-theme',next)}catch(e){}};
stats();
addEventListener('hashchange',()=>{const h=location.hash.match(/org=(\d{9})/),t=h&&P.find(p=>p.r.organisation_number===h[1]);if(t&&t!==sel){choose(t,false);document.body.classList.add('show-detail')}});
const m=location.hash.match(/org=(\d{9})/);const start=m&&P.find(p=>p.r.organisation_number===m[1]);
list();if(start){choose(start,false);document.body.classList.add('show-detail')}else if(P.length){const first=document.querySelector('.item');choose(P.find(p=>p.r.organisation_number===first.dataset.org),false)}
</script></body></html>"""


def write_html(path: Path, envelopes: list[dict[str, Any]], *, run_id: str) -> None:
    keys = ("organisation_number", "status", "run", "legal_identity", "public_brand", "sections", "claims", "evidence",
            "summary", "unknowns", "refresh", "changes", "errors", "operations", "attempts")
    rows = [{k: e.get(k) for k in keys} for e in envelopes]
    data = json.dumps({"run_id": run_id, "rows": rows}, ensure_ascii=False, default=str).replace("</", "<\\/")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PAGE.replace("__DATA__", data), encoding="utf-8")
