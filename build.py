#!/usr/bin/env python3
"""Bangun index.html (satu file, 4 tab) dari src/*.html.
Tiap tool jalan di iframe srcdoc sendiri -> CSS/JS/ID tidak bentrok, chart diinisialisasi
saat tab pertama kali dibuka. Edit file di src/ lalu jalankan: python3 build.py"""
import json, pathlib
R = pathlib.Path(__file__).parent
rd = lambda n: (R/'src'/n).read_text(encoding='utf-8')

dash = rd('dashboard.html')
# versi dashboard per tab: sembunyikan tab-bar internal & paksa buka tab tertentu
def dash_tab(tab):
    inj = ("<style>.tabs{display:none!important}</style><script>addEventListener('DOMContentLoaded',function(){"
           "var b=document.querySelector('.tabbtn[data-t=\"%s\"]');if(b)b.click();});</script>" % tab)
    return dash.replace('</body>', inj + '</body>')

APPS = {
  'fuel':   dash_tab('tab-fuel'),
  'matrix': dash_tab('tab-matrix'),
  'sim':    rd('simulator.html'),
  'spx':    rd('spx.html'),
}
data = json.dumps(APPS, ensure_ascii=False).replace('</', '<\\/')

html = '''<!DOCTYPE html>
<html lang="id"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BTC Fundamental Hub</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@300;500&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{background:#fafaf8;color:#1a1714;font-family:'DM Mono',monospace;overflow:hidden}
.bar{position:fixed;top:0;left:0;right:0;height:48px;z-index:10;background:rgba(250,250,248,.96);backdrop-filter:blur(8px);border-bottom:1px solid #e0ddd8;display:flex;align-items:center;gap:6px;padding:0 14px;overflow-x:auto;white-space:nowrap}
.brand{font-family:'Cormorant Garamond',serif;font-size:19px;font-weight:500;margin-right:10px;color:#1a1714}
.brand em{color:#b8860b}
.t{font-family:inherit;font-size:11px;letter-spacing:.06em;padding:7px 13px;border:1px solid transparent;background:none;color:#6b6560;border-radius:3px;cursor:pointer}
.t:hover{color:#b8860b}
.t.on{color:#1a1714;border-color:#d0ccc5;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.t.on::after{content:'';display:block;height:2px;background:#b8860b;margin-top:3px;border-radius:2px}
.pane{position:fixed;top:48px;left:0;right:0;bottom:0;display:none}
.pane.on{display:block}
iframe{width:100%;height:100%;border:0;background:#fafaf8}
</style></head><body>
<div class="bar"><span class="brand">BTC <em>Fundamental</em></span>
<button class="t" data-k="fuel">Fuel Gauge</button>
<button class="t" data-k="matrix">Time Matrix 2027</button>
<button class="t" data-k="sim">500-Day Simulator</button>
<button class="t" data-k="spx">SPX Tracker</button></div>
<div id="panes"></div>
<script>
const APPS=__DATA__;
const keys=Object.keys(APPS), loaded={};
function show(k){
  if(!APPS[k])k='fuel';
  if(!loaded[k]){
    const p=document.createElement('div');p.className='pane';p.id='p-'+k;
    const f=document.createElement('iframe');f.title=k;
    f.setAttribute('allow','clipboard-write');
    f.srcdoc=APPS[k];p.appendChild(f);document.getElementById('panes').appendChild(p);loaded[k]=p;
  }
  keys.forEach(x=>{if(loaded[x])loaded[x].classList.toggle('on',x===k)});
  document.querySelectorAll('.t').forEach(b=>b.classList.toggle('on',b.dataset.k===k));
  try{history.replaceState(null,'','#'+k)}catch(e){}
  // chart di dalam iframe perlu tahu ukuran baru setelah tab ditampilkan
  setTimeout(()=>{try{loaded[k].querySelector('iframe').contentWindow.dispatchEvent(new Event('resize'))}catch(e){}},150);
}
document.querySelectorAll('.t').forEach(b=>b.addEventListener('click',()=>show(b.dataset.k)));
show(location.hash.slice(1)||'fuel');
</script></body></html>'''
(R/'index.html').write_text(html.replace('__DATA__', data), encoding='utf-8')
print('index.html', (R/'index.html').stat().st_size, 'bytes')
