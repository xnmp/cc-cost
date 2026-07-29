from __future__ import annotations

import json
from pathlib import Path

from cc_cost.analysis import SessionAnalysis
from cc_cost.chart import build_chart
from cc_cost.theme import TerminalTheme, read_terminal_theme

_CSS = """
:root {
  color-scheme: __SCHEME__;
  --bg1: __BG__; --bg2: color-mix(in srgb, __BG__ 92%, __FG__);
  --panel: color-mix(in srgb, __BG__ 96%, __FG__); --text: __FG__;
  --muted: color-mix(in srgb, __FG__ 62%, __BG__);
  --axis2: color-mix(in srgb, __FG__ 82%, __BG__);
  --line: color-mix(in srgb, __FG__ 14%, transparent);
  --border: color-mix(in srgb, __FG__ 18%, transparent);
  --border2: color-mix(in srgb, __FG__ 27%, transparent);
  --track: color-mix(in srgb, __FG__ 22%, __BG__);
  --note: color-mix(in srgb, __FG__ 54%, __BG__);
  --tipbg: __FG__; --tiptext: __BG__;
  --tipbd: color-mix(in srgb, __BG__ 28%, transparent);
  --hover: color-mix(in srgb, __FG__ 10%, transparent);
  --selection-bg: __SEL_BG__; --selection-fg: __SEL_FG__;
  --cache-read: __CACHE_READ__;
}
* { box-sizing: border-box }
::selection { background: var(--selection-bg); color: var(--selection-fg) }
body { margin: 0; background: var(--bg1); color: var(--text);
  font-family: ui-sans-serif, system-ui, sans-serif; padding: 32px 24px;
  -webkit-font-smoothing: antialiased }
.wrap { max-width: 960px; margin: 0 auto }
.head { display: flex; justify-content: space-between; align-items: flex-end;
  gap: 16px; flex-wrap: wrap; margin-bottom: 18px }
h1 { margin: 0; font-size: 20px; font-weight: 650; letter-spacing: -.01em }
.sub { color: var(--muted); margin-top: 4px; font-size: 13px }
.crumb { display: flex; align-items: center; font-size: 12px; color: var(--muted);
  margin-bottom: 5px }
.chip { font-size: 11px; font-weight: 600; padding: 2px 9px; border-radius: 20px;
  letter-spacing: .02em; white-space: nowrap }
.cx { appearance: none; border: 0; padding: 0; background: transparent;
  color: inherit; font: inherit; cursor: pointer }
.cx:hover { color: var(--text); text-decoration: underline }
.cx:focus-visible, .backbtn:focus-visible, .tgl input:focus-visible + .tr,
.mini:focus-visible { outline: 2px solid var(--selection-bg); outline-offset: 3px }
.cs { margin: 0 6px; opacity: .5 }
.big { text-align: right; line-height: 1 }
.big .amt { font-size: 32px; font-weight: 700; letter-spacing: -.02em }
.big .cap { color: var(--muted); font-size: 11px; text-transform: uppercase;
  letter-spacing: .08em; margin-top: 4px }
.panel { background: var(--panel); border: 1px solid var(--border);
  border-radius: 14px; padding: 16px 18px;
  box-shadow: 0 1px 0 var(--line) inset, 0 8px 24px color-mix(in srgb, __BG__ 65%, transparent) }
.bar { display: flex; justify-content: space-between; align-items: center;
  gap: 16px; flex-wrap: wrap; margin-bottom: 10px }
.sw { width: 11px; height: 11px; border-radius: 3px; display: inline-block; flex: none }
.backbtn { background: var(--border); border: 1px solid var(--border2);
  color: var(--axis2); font-size: 12px; padding: 4px 11px; border-radius: 8px; cursor: pointer }
.backbtn:hover { background: var(--hover); color: var(--text) }
.row { display: flex; align-items: center; gap: 9px }
.row .lb { flex: 1 }
.row b { font-variant-numeric: tabular-nums }
.row .pct { color: var(--muted); width: 48px; text-align: right;
  font-variant-numeric: tabular-nums }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px }
.card h2 { color: var(--muted); font-size: 11px; text-transform: uppercase;
  letter-spacing: .06em; margin: 0 0 12px; font-weight: 600 }
.col { display: flex; flex-direction: column; gap: 9px; font-size: 14px }
.kv { font-size: 14px; line-height: 2.05 }
.tot { display: flex; gap: 9px; border-top: 1px solid var(--line);
  padding-top: 9px; margin-top: 3px; font-weight: 600 }
.tgl { display: inline-flex; align-items: center; gap: 9px; cursor: pointer;
  font-size: 13px; color: var(--axis2); user-select: none; position: relative }
.tgl input { position: absolute; width: 1px; height: 1px; opacity: 0 }
.tr { width: 38px; height: 21px; border-radius: 21px; background: var(--track);
  position: relative; transition: .15s; flex: none }
.tr::after { content: ""; position: absolute; top: 2px; left: 2px; width: 17px;
  height: 17px; border-radius: 50%; background: var(--text); transition: .15s }
.tgl input:checked + .tr { background: var(--cache-read) }
.tgl input:checked + .tr::after { transform: translateX(17px) }
.mini { margin: 2px 0 6px; cursor: pointer; display: none }
.mini svg { display: block; width: 100%; border-radius: 6px;
  background: color-mix(in srgb, __BG__ 72%, transparent) }
.scroll { overflow-x: auto }
svg rect { transition: opacity .1s }
svg rect:hover { opacity: .82 }
svg rect.clk { cursor: pointer }
svg rect.clk:hover { opacity: .66 }
svg rect.clk:focus { outline: none; stroke: var(--selection-fg); stroke-width: 2 }
svg .gl { stroke: var(--line) }
svg .axt { fill: var(--muted) }
svg .axt2 { fill: var(--axis2) }
svg .sep { fill: var(--panel) }
.tip { position: fixed; pointer-events: none; background: var(--tipbg);
  border: 1px solid var(--tipbd); color: var(--tiptext); font-size: 12px;
  padding: 5px 9px; border-radius: 7px; display: none; z-index: 20;
  max-width: 340px; box-shadow: 0 6px 20px color-mix(in srgb, __BG__ 70%, transparent) }
.inspect { width: min(1180px, calc(100vw - 32px)); height: min(92vh, 1000px);
  max-width: none; max-height: none; padding: 0; color: var(--text); background: var(--panel);
  border: 1px solid var(--border2); border-radius: 14px;
  box-shadow: 0 18px 60px color-mix(in srgb, __BG__ 55%, transparent) }
.inspect[open] { display: grid; grid-template-rows: auto minmax(0, 1fr) }
.inspect::backdrop { background: color-mix(in srgb, __BG__ 72%, transparent) }
.ih { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start;
  padding: 18px 22px; background: var(--panel);
  border-bottom: 1px solid var(--border) }
.ih h2 { margin: 0; font-size: 19px; letter-spacing: -.015em }
.imeta { color: var(--muted); font-size: 12px; margin-top: 4px }
.iclose { border: 1px solid var(--border2); background: var(--border); color: var(--text);
  border-radius: 8px; min-width: 64px; padding: 7px 12px; cursor: pointer }
.iclose:hover { background: var(--hover) }
.iclose:focus-visible { outline: 2px solid var(--selection-bg); outline-offset: 2px }
.ibody { min-height: 0; overflow: auto; padding: 20px 24px 32px; scrollbar-gutter: stable }
.inote { max-width: 78ch; color: var(--note); font-size: 12px; line-height: 1.6;
  margin: 0 0 20px }
.passgroup { max-width: 980px; margin: 0 auto 28px }
.passhead { color: var(--axis2); font-size: 11px; font-weight: 650; text-transform: uppercase;
  letter-spacing: .06em; margin: 24px 0 10px }
.passhead:first-child { margin-top: 0 }
.trace { width: min(84%, 780px); border: 1px solid var(--border2); border-radius: 12px;
  overflow: hidden; margin: 0 0 12px; background: var(--hover) }
.trace.user { margin-left: auto; background: color-mix(in srgb, var(--selection-bg) 13%, var(--panel));
  border-color: color-mix(in srgb, var(--selection-bg) 35%, var(--border)) }
.trace.assistant { margin-right: auto;
  background: color-mix(in srgb, var(--cache-read) 10%, var(--panel));
  border-color: color-mix(in srgb, var(--cache-read) 30%, var(--border)) }
.trace.tool { width: 100%; max-width: none; border-color: var(--border);
  border-radius: 8px; background: color-mix(in srgb, __BG__ 70%, transparent) }
.trace.other { margin-right: auto; background: var(--hover) }
.tracehead { display: flex; gap: 8px; align-items: baseline; padding: 6px 10px;
  background: var(--hover); color: var(--muted); font-size: 11px }
.trace.user .tracehead, .trace.assistant .tracehead { padding: 8px 12px }
.trace.tool .tracehead { background: transparent; padding: 5px 9px }
.tracehead b { color: var(--axis2); font-weight: 650 }
.trace pre { margin: 0; padding: 12px; overflow: auto; white-space: pre-wrap;
  overflow-wrap: anywhere; color: var(--text);
  font: 12px/1.6 ui-monospace, SFMono-Regular, Consolas, monospace }
.trace.message pre { font-family: ui-sans-serif, system-ui, sans-serif; font-size: 14px;
  line-height: 1.6; padding: 14px 16px 16px }
.trace.tool pre { color: var(--axis2); font-size: 11px; line-height: 1.55; padding: 10px }
.jk { color: var(--cache-read) }
.js { color: var(--text) }
.jn { color: var(--axis2) }
.jl { color: var(--muted); font-weight: 650 }
.iempty { color: var(--muted); padding: 20px 0; text-align: center }
.note { color: var(--note); font-size: 12px; margin-top: 18px; line-height: 1.6 }
@media (max-width: 640px) {
  body { padding: 20px 12px }
  .grid { grid-template-columns: 1fr }
  .head { align-items: flex-start }
  .big { text-align: left }
  .bar > div { gap: 10px !important }
  .inspect { width: calc(100vw - 8px); height: 96vh; border-radius: 10px }
  .ih { padding: 14px }
  .ibody { padding: 16px 12px 24px }
  .trace { width: calc(100% - 18px) }
  .trace.tool { width: 100% }
}
"""

_SHELL = """
<main class="wrap">
<header class="head">
  <div><nav id="crumb" class="crumb" aria-label="Chart breadcrumb"></nav>
    <div style="display:flex;align-items:center;gap:10px">
      <h1 id="title"></h1><span id="modelchip" class="chip"></span>
    </div>
    <div id="subtitle" class="sub"></div>
  </div>
  <div class="big"><div class="amt" id="total"></div><div class="cap" id="cap">total spend</div></div>
</header>
<section class="panel" aria-labelledby="title">
  <div class="bar">
    <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
      <button id="back" class="backbtn" type="button" onclick="goBack()">&larr; back</button>
      <label class="tgl"><input type="checkbox" id="perstep" onchange="setBase()">
        <span class="tr" aria-hidden="true"></span>per-pass bars</label>
      <label class="tgl"><input type="checkbox" id="norm" checked onchange="setMode()">
        <span class="tr" aria-hidden="true"></span><span id="normlbl">normalize by passes</span></label>
      <label class="tgl"><input type="checkbox" id="subs" checked onchange="toggleSubs()">
        <span class="tr" aria-hidden="true"></span>show subagents</label>
    </div>
  </div>
  <div id="mini" class="mini" tabindex="0" role="group"
    aria-label="Chart overview; double-click to reset zoom"></div>
  <div id="scroll" class="scroll"><div id="chart" aria-live="polite"></div></div>
</section>
<div class="grid">
  <section class="panel card"><h2>cost breakdown</h2><div class="col" id="breakdown"></div></section>
  <section class="panel card"><h2>summary</h2><div class="kv" id="summary"></div></section>
</div>
<aside class="note">Bars = cost per <b id="unitn">turn</b> (toggle: divide by pass count, or raw),
stacked by component; subagent segments use model colors. Hover for exact cost; click or press Enter
on a subagent segment to open its graph. <b>Zoom:</b> scroll around the cursor, drag across the
minimap, or double-click/Escape to reset. Output includes reasoning/thinking tokens.
Theme: <b id="themeName"></b>, read from <span id="themeSource"></span>.</aside>
</main>
<div id="tip" class="tip" role="tooltip"></div>
<dialog id="inspect" class="inspect" aria-labelledby="ititle">
  <div class="ih"><div><h2 id="ititle"></h2><div id="imeta" class="imeta"></div></div>
    <button id="iclose" class="iclose" type="button">close</button></div>
  <div class="ibody"><p id="inote" class="inote"></p><div id="icontent"></div></div>
</dialog>
"""

_JS = r"""
let base="root", stack=["root"], mode="per_step", showSubs=true;
let win=null, winKey=null, CH={padL:64,band:10,s0:0}, msel=null;

function fmt(u){if(u>=1)return "$"+u.toFixed(2);var c=u*100;if(c>=10)return Math.round(c)+"c";if(c>=1)return c.toFixed(1)+"c";return c>0?"<1c":"0c";}
function esc(s){return (""+(s==null?"":s)).replace(/[&<>"]/g,function(m){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[m];});}
function mh(m){return MODEL_HEX[m]||SUBHEX;}
function cur(){return NODES[stack[stack.length-1]];}
function curKey(){return stack[stack.length-1];}
function tipEl(){return document.getElementById("tip");}
function contW(){return document.getElementById("scroll").clientWidth||900;}
function segsFor(bar,div){
  var out=COMPS.map(function(c){var raw=bar.comps[c[0]];return {key:c[0],color:c[2],v:raw/div,raw:raw,type:c[1],sub:false};});
  if(showSubs)bar.subs.forEach(function(s){out.push({color:mh(s.model),v:s.total/div,raw:s.total,type:s.model+" subagent — "+s.label,sub:true,id:s.id});});
  return out;
}
function barTotal(b){var d=(mode==="per_step"&&b.steps)?b.steps:1;return segsFor(b,d).reduce(function(a,x){return a+x.v;},0);}
function ensureWin(node){var k=curKey();if(winKey!==k||!win){win={s:0,e:Math.max(0,node.bars.length-1)};winKey=k;}
  if(win.e>node.bars.length-1)win.e=Math.max(0,node.bars.length-1);if(win.s<0)win.s=0;if(win.s>win.e)win.s=win.e;}
function render(){
  var node=cur();document.getElementById("title").textContent=node.title;
  var chip=document.getElementById("modelchip");
  if(node.model){var mc=mh(node.model);chip.textContent=node.model;chip.style.display="";
    chip.style.color=mc;chip.style.background="color-mix(in srgb, "+mc+" 14%, transparent)";
    chip.style.border="1px solid color-mix(in srgb, "+mc+" 45%, transparent)";}
  else chip.style.display="none";
  document.getElementById("subtitle").textContent=node.subtitle||"";
  document.getElementById("total").textContent=fmt(node.total);
  document.getElementById("cap").textContent=node.kind==="turn"?"total spend":"subtree spend";
  document.getElementById("unitn").textContent=node.kind;
  document.getElementById("back").style.display=stack.length>1?"":"none";
  document.getElementById("crumb").innerHTML=stack.map(function(k,i){return '<button type="button" class="cx" onclick="jump('+i+')">'+esc(i===0?"session":NODES[k].title)+"</button>";}).join('<span class="cs" aria-hidden="true">›</span>');
  var norm=document.getElementById("norm"),stepKind=node.kind!=="turn";
  norm.disabled=stepKind;norm.parentElement.style.opacity=stepKind?".4":"";
  norm.parentElement.style.cursor=stepKind?"default":"pointer";
  document.getElementById("normlbl").textContent=stepKind?"per pass (already finest grain)":"normalize by passes";
  buildStats(node);redraw(node);
}
function redraw(node){drawChart(node);buildMini(node);}
function crow(c,l,amt,total){return '<div class="row"><span class="sw" style="background:'+c+'"></span><span class="lb">'+esc(l)+"</span><b>"+fmt(amt)+'</b><span class="pct">'+(total?(amt/total*100).toFixed(1):"0.0")+"%</span></div>";}
function inspectField(comp){return comp==="output"?"output":comp==="input"?"input":"cached";}
function jsonMarkup(text){
  var value;try{value=JSON.parse(text);}catch(e){return null;}
  var pretty=JSON.stringify(value,null,2);
  return pretty.replace(/("(?:\\u[a-fA-F0-9]{4}|\\[^u]|[^\\"])*"(?:\s*:)?|\b(?:true|false|null)\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g,function(token){
    var cls=/^"/.test(token)?(/:\s*$/.test(token)?"jk":"js"):/^(true|false|null)$/.test(token)?"jl":"jn";
    return '<span class="'+cls+'">'+esc(token)+'</span>';
  });
}
function traceClass(block){
  if(block.kind==="message")return "message "+(block.role==="user"?"user":block.role==="assistant"?"assistant":"other");
  if(block.kind==="tool_call"||block.kind==="tool_result")return "tool";
  return "other";
}
function traceBody(block){
  var json=(block.kind==="tool_call"||block.kind==="tool_result")?jsonMarkup(block.text):null;
  return json===null?esc(block.text):json;
}
function openInspect(barIndex,comp){
  var bar=cur().bars[barIndex],ids=bar.pass_ids||[],field=inspectField(comp),tokens=0;
  var labels={input:"uncached input",cache_read:"cache read",cache_write:"cache write",output:"output"};
  var sections=ids.map(function(id,n){var p=PASSES[id];if(!p)return "";tokens+=p.usage[comp]||0;
    var blocks=p[field]||[],head='<div class="passhead">pass '+(n+1)+' · '+esc(p.model)+'</div>';
    if(!blocks.length)return '<section class="passgroup">'+head+'<div class="iempty">No readable content was recorded for this pass.</div></section>';
    return '<section class="passgroup">'+head+blocks.map(function(b){var label=b.label||b.kind.replace("_"," ");
      return '<article class="trace '+traceClass(b)+'"><div class="tracehead"><b>'+esc(label)+'</b><span>'+esc(b.role)+'</span></div><pre>'+traceBody(b)+'</pre></article>';}).join("")+"</section>";
  }).join("");
  var cached=field==="cached",truncated=ids.some(function(id){return PASSES[id]&&PASSES[id].cached_truncated;});
  document.getElementById("ititle").textContent=labels[comp]+" content";
  document.getElementById("imeta").textContent=tokens.toLocaleString()+" billed tokens · "+ids.length+" pass"+(ids.length===1?"":"es");
  document.getElementById("inote").textContent=cached
    ? "Recorded context preview for each pass"+(truncated?", limited to roughly the last 2,000 tokens.":".")+" Provider transcripts expose counts, not token IDs or exact cache boundaries."
    : "Readable transcript content associated with this billed segment. The provider token count is exact; hidden or provider-assembled prompt content may not be present in the transcript.";
  document.getElementById("icontent").innerHTML=sections||'<div class="iempty">No readable content was recorded for this segment.</div>';
  document.getElementById("inspect").showModal();
}
function buildStats(node){
  var total=node.total||1e-12;
  var rows=COMPS.map(function(c){return crow(c[2],c[1],node.comp_tot[c[0]],total);});
  MODELS.forEach(function(m){if(node.submodel[m])rows.push(crow(mh(m),"subagent · "+m,node.submodel[m],total));});
  rows.push('<div class="tot"><span style="flex:1">total</span><b>'+fmt(node.total)+'</b><span style="width:48px"></span></div>');
  document.getElementById("breakdown").innerHTML=rows.join("");
  var nb=node.bars.length,steps=node.steps,subs=node.sub_steps||0,unit=node.kind;
  var kv=(node.kind==="turn"?"turns":"passes")+"&nbsp;&nbsp;<b>"+nb+"</b><br>";
  if(node.kind==="turn")kv+="passes&nbsp;&nbsp;<b>"+steps+"</b><br>";
  if(subs)kv+="subagent passes&nbsp;&nbsp;<b>"+subs+"</b><br>";
  kv+="avg cost / "+unit+"&nbsp;&nbsp;<b>"+fmt(node.total/(nb||1))+"</b><br>";
  kv+="avg cost / pass&nbsp;&nbsp;<b>"+fmt(node.total/(((node.kind==="turn"?steps:nb)+subs)||1))+"</b>";
  document.getElementById("summary").innerHTML=kv;
}
function drawChart(node){
  ensureWin(node);var bars=node.bars,turnKind=node.kind==="turn",s0=win.s,e0=win.e,m=e0-s0+1;
  var cont=contW(),padL=64,padR=turnKind?52:20,padT=16,padB=30,plotH=300;
  var band=(cont-padL-padR)/Math.max(1,m),barW=Math.max(2,Math.min(band*.66,44));
  var plotW=m*band,W=cont,H=padT+plotH+padB;CH={padL:padL,band:band,s0:s0};
  var heights=[];for(var i=s0;i<=e0&&i<bars.length;i++)heights.push(barTotalDiv(bars[i]));
  var maxCost=Math.max.apply(null,heights.concat([1e-9])),maxSteps=1;
  for(var i=s0;i<=e0&&i<bars.length;i++)maxSteps=Math.max(maxSteps,bars[i].steps);
  function yc(v){return padT+plotH*(1-v/maxCost);}function ys(v){return padT+plotH*(1-v/maxSteps);}
  var s=['<svg width="'+W+'" height="'+H+'" viewBox="0 0 '+W+" "+H+'" aria-label="'+esc(node.title)+' chart">'];
  [0,.25,.5,.75,1].forEach(function(f){var y=padT+plotH*(1-f);
    s.push('<line x1="'+padL+'" y1="'+y.toFixed(1)+'" x2="'+(padL+plotW)+'" y2="'+y.toFixed(1)+'" class="gl"/>');
    s.push('<text x="'+(padL-8)+'" y="'+(y+4).toFixed(1)+'" text-anchor="end" font-size="11" class="axt">'+fmt(maxCost*f)+"</text>");
    if(turnKind)s.push('<text x="'+(padL+plotW+8)+'" y="'+(y+4).toFixed(1)+'" font-size="11" fill="'+STEPS+'">'+Math.round(maxSteps*f)+"</text>");
  });
  var labelEvery=Math.max(1,Math.round(30/band));
  for(var i=s0;i<=e0&&i<bars.length;i++){var b=bars[i],k=i-s0,cx=padL+k*band+band/2,x=cx-barW/2;
    var div=(mode==="per_step"&&b.steps)?b.steps:1,segs=segsFor(b,div).filter(function(g){return g.v>0;}),acc=0;
    segs.forEach(function(g,j){var y0=yc(acc),y1=yc(acc+g.v),h=Math.max(0,y0-y1),r=(j===segs.length-1)?4:0;
      var label=g.type+" · "+fmt(g.raw)+(g.sub?" · open subagent":"");
      var attr='data-tip="'+esc(label)+'"';
      if(g.sub)attr+=' class="clk" data-id="'+esc(g.id)+'" tabindex="0" role="button" aria-label="'+esc(label)+'"';
      else attr+=' class="clk" data-comp="'+g.key+'" data-bi="'+i+'" tabindex="0" role="button" aria-label="'+esc("inspect "+g.type+" content")+'"';
      s.push('<rect x="'+x.toFixed(1)+'" y="'+y1.toFixed(1)+'" width="'+barW.toFixed(1)+'" height="'+h.toFixed(1)+'" rx="'+r+'" fill="'+g.color+'" '+attr+"></rect>");
      if(r&&h>r)s.push('<rect x="'+x.toFixed(1)+'" y="'+(y1+r).toFixed(1)+'" width="'+barW.toFixed(1)+'" height="'+(h-r).toFixed(1)+'" fill="'+g.color+'" pointer-events="none" aria-hidden="true"></rect>');
      if(j<segs.length-1&&h>1.5)s.push('<rect x="'+x.toFixed(1)+'" y="'+(y1-.6).toFixed(1)+'" width="'+barW.toFixed(1)+'" height="1.3" class="sep" pointer-events="none"></rect>');acc+=g.v;
    });
    if(k%labelEvery===0)s.push('<text x="'+cx.toFixed(1)+'" y="'+(padT+plotH+16)+'" text-anchor="middle" font-size="10" class="axt">'+b.label+"</text>");
  }
  if(turnKind){var pts=[];for(var i=s0;i<=e0&&i<bars.length;i++){var k=i-s0;pts.push((padL+k*band+band/2).toFixed(1)+","+ys(bars[i].steps).toFixed(1));}
    s.push('<polyline points="'+pts.join(" ")+'" fill="none" stroke="'+STEPS+'" stroke-width="2" opacity=".9"/>');
    for(var i=s0;i<=e0&&i<bars.length;i++){var k=i-s0,cx=padL+k*band+band/2;s.push('<circle cx="'+cx.toFixed(1)+'" cy="'+ys(bars[i].steps).toFixed(1)+'" r="3" fill="'+STEPS+'" data-tip="'+esc("turn "+bars[i].label+": "+bars[i].steps+" passes")+'"></circle>');}}
  var mid=padT+plotH/2,yl=turnKind?(mode==="per_step"?"cost / pass":"cost / turn"):"cost / pass";
  s.push('<text x="15" y="'+mid+'" font-size="12" class="axt2" transform="rotate(-90 15 '+mid+')" text-anchor="middle">'+yl+"</text>");
  if(turnKind)s.push('<text x="'+(W-13)+'" y="'+mid+'" font-size="12" fill="'+STEPS+'" transform="rotate(90 '+(W-13)+" "+mid+')" text-anchor="middle">passes</text>');
  s.push('<text x="'+(padL+plotW/2).toFixed(0)+'" y="'+(H-6)+'" font-size="12" class="axt2" text-anchor="middle">'+(turnKind?"turn":"pass")+"</text></svg>");
  document.getElementById("chart").innerHTML=s.join("");
}
function barTotalDiv(b){var d=(mode==="per_step"&&b.steps)?b.steps:1;return segsFor(b,d).reduce(function(a,x){return a+x.v;},0);}
function buildMini(node){
  var mini=document.getElementById("mini"),n=node.bars.length;if(n<8){mini.style.display="none";mini.innerHTML="";return;}mini.style.display="block";
  var W=contW(),Hm=40,mb=W/n,full=node.bars.map(barTotalDiv),maxC=Math.max.apply(null,full.concat([1e-9]));
  var s=['<svg width="'+W+'" height="'+Hm+'" viewBox="0 0 '+W+" "+Hm+'" preserveAspectRatio="none" aria-hidden="true">'];
  node.bars.forEach(function(b,i){var div=(mode==="per_step"&&b.steps)?b.steps:1,acc=0;
    segsFor(b,div).filter(function(g){return g.v>0;}).forEach(function(g){var h=(g.v/maxC)*(Hm-5),y=Hm-3-(acc/maxC)*(Hm-5)-h;
      s.push('<rect x="'+(i*mb).toFixed(2)+'" y="'+y.toFixed(2)+'" width="'+Math.max(.6,mb-.35).toFixed(2)+'" height="'+h.toFixed(2)+'" fill="'+g.color+'"/>');acc+=g.v;});});
  var vx=win.s*mb,vw=(win.e-win.s+1)*mb;
  s.push('<rect x="0" y="0" width="'+vx.toFixed(1)+'" height="'+Hm+'" fill="var(--bg1)" opacity=".72"/>');
  s.push('<rect x="'+(vx+vw).toFixed(1)+'" y="0" width="'+(W-vx-vw).toFixed(1)+'" height="'+Hm+'" fill="var(--bg1)" opacity=".72"/>');
  s.push('<rect x="'+vx.toFixed(1)+'" y=".5" width="'+vw.toFixed(1)+'" height="'+(Hm-1)+'" fill="var(--hover)" stroke="var(--text)" stroke-width="1" rx="3"/></svg>');mini.innerHTML=s.join("");
}
function miniBarAt(e){var mini=document.getElementById("mini"),r=mini.getBoundingClientRect(),n=cur().bars.length;return Math.max(0,Math.min(n-1,Math.floor(((e.clientX-r.left)/r.width)*n)));}
function showTip(e){var t=e.target,d=t&&t.getAttribute&&t.getAttribute("data-tip"),tip=tipEl();if(!d){tip.style.display="none";return;}tip.textContent=d;tip.style.display="block";var x=e.clientX+13,y=e.clientY+13,w=tip.offsetWidth;if(x+w>window.innerWidth-8)x=e.clientX-w-13;tip.style.left=x+"px";tip.style.top=y+"px";}
function openAgent(id){if(id){stack.push(id);tipEl().style.display="none";render();}}
function goBack(){if(stack.length>1){stack.pop();render();}}
function jump(i){if(i<stack.length-1){stack=stack.slice(0,i+1);render();}}
function setBase(){base=document.getElementById("perstep").checked?"root_steps":"root";stack=[base];win=null;render();}
function setMode(){if(document.getElementById("norm").disabled)return;mode=document.getElementById("norm").checked?"per_step":"total";render();}
function toggleSubs(){showSubs=document.getElementById("subs").checked;render();}
function resetZoom(){var node=cur();win={s:0,e:Math.max(0,node.bars.length-1)};redraw(node);}
(function(){
  document.getElementById("themeName").textContent=THEME.name;document.getElementById("themeSource").textContent=THEME.source;
  var chart=document.getElementById("chart");chart.addEventListener("mousemove",showTip);chart.addEventListener("mouseleave",function(){tipEl().style.display="none";});
  chart.addEventListener("click",function(e){var t=e.target;if(!t||!t.getAttribute)return;var id=t.getAttribute("data-id"),comp=t.getAttribute("data-comp");if(id)openAgent(id);else if(comp)openInspect(Number(t.getAttribute("data-bi")),comp);});
  chart.addEventListener("keydown",function(e){if(e.key!=="Enter"&&e.key!==" ")return;var t=e.target;if(!t||!t.getAttribute)return;var id=t.getAttribute("data-id"),comp=t.getAttribute("data-comp");if(id){e.preventDefault();openAgent(id);}else if(comp){e.preventDefault();openInspect(Number(t.getAttribute("data-bi")),comp);}});
  chart.addEventListener("dblclick",resetZoom);chart.addEventListener("wheel",function(e){e.preventDefault();var node=cur(),r=chart.getBoundingClientRect(),pos=CH.s0+(e.clientX-r.left-CH.padL)/CH.band,m=win.e-win.s+1,f=e.deltaY>0?1.25:.8,nm=Math.max(3,Math.min(node.bars.length,Math.round(m*f))),ns=Math.round(pos-(pos-win.s)*(nm/m));ns=Math.max(0,Math.min(node.bars.length-nm,ns));win={s:ns,e:ns+nm-1};redraw(node);},{passive:false});
  var mini=document.getElementById("mini");mini.addEventListener("dblclick",resetZoom);mini.addEventListener("keydown",function(e){if(e.key==="Enter"||e.key===" "){e.preventDefault();resetZoom();}});
  mini.addEventListener("mousedown",function(e){e.preventDefault();msel={a:miniBarAt(e),moved:false};});
  window.addEventListener("mousemove",function(e){if(!msel)return;var b=miniBarAt(e);if(b!==msel.a)msel.moved=true;var node=cur();win={s:Math.min(msel.a,b),e:Math.max(msel.a,b)};redraw(node);});
  window.addEventListener("mouseup",function(){msel=null;});document.addEventListener("keydown",function(e){if(e.key!=="Escape"||document.getElementById("inspect").open)return;var node=cur();if(win&&(win.s>0||win.e<node.bars.length-1))resetZoom();else goBack();});
  document.getElementById("iclose").addEventListener("click",function(){document.getElementById("inspect").close();});
  document.getElementById("inspect").addEventListener("click",function(e){if(e.target===this)this.close();});
  var rt;window.addEventListener("resize",function(){clearTimeout(rt);rt=setTimeout(function(){redraw(cur());},120);});render();
})();
"""


def _scheme(theme: TerminalTheme) -> str:
    color = theme.background
    if not color.startswith("#"):
        return "normal"
    red, green, blue = (int(color[index : index + 2], 16) for index in (1, 3, 5))
    luminance = (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255
    return "dark" if luminance < 0.5 else "light"


def _themed_css(theme: TerminalTheme) -> str:
    replacements = {
        "__SCHEME__": _scheme(theme),
        "__BG__": theme.background,
        "__FG__": theme.foreground,
        "__SEL_BG__": theme.selection_background,
        "__SEL_FG__": theme.selection_foreground,
        "__CACHE_READ__": theme.chart_colors["cache_read"],
    }
    result = _CSS
    for marker, value in replacements.items():
        result = result.replace(marker, value)
    return result


def _json_for_script(value: object) -> str:
    return (
        json.dumps(value)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def render_interactive_html(
    analysis: SessionAnalysis,
    path: Path,
    *,
    theme: TerminalTheme | None = None,
) -> None:
    active_theme = theme or read_terminal_theme()
    nodes, passes, model_colors, models = build_chart(
        analysis, active_theme.model_colors
    )
    components = (
        ("cache_read", "cache read", active_theme.chart_colors["cache_read"]),
        ("cache_write", "cache write", active_theme.chart_colors["cache_write"]),
        ("output", "output", active_theme.chart_colors["output"]),
        ("input", "input", active_theme.chart_colors["input"]),
    )
    config = (
        "const NODES="
        + _json_for_script(nodes)
        + ";const PASSES="
        + _json_for_script(passes)
        + ";const COMPS="
        + _json_for_script(components)
        + ";const MODEL_HEX="
        + _json_for_script(model_colors)
        + ";const MODELS="
        + _json_for_script(models)
        + ";const SUBHEX="
        + _json_for_script(active_theme.chart_colors["fallback_subagent"])
        + ";const STEPS="
        + _json_for_script(active_theme.chart_colors["steps"])
        + ";const THEME="
        + _json_for_script({"name": active_theme.name, "source": active_theme.source})
        + ";"
    )
    document = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="color-scheme" content="{_scheme(active_theme)}">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Session cost</title><style>"
        + _themed_css(active_theme)
        + "</style></head><body>"
        + _SHELL
        + "<script>"
        + config
        + _JS
        + "</script></body></html>"
    )
    path.write_text(document, encoding="utf-8")
