#!/usr/bin/env python3
from __future__ import annotations

import argparse, json, sys, time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HTML = """<!doctype html><meta charset='utf-8'><title>Docker Topology Live</title><style>
body{margin:0;background:#06111f;color:#e5eefb;font-family:system-ui,sans-serif}main{height:100vh;display:grid;grid-template-rows:auto auto 1fr;gap:12px;padding:18px}h1{margin:0;font-size:36px}.bar,.cards{display:flex;gap:10px;flex-wrap:wrap}.card,aside,#graph{border:1px solid #334155;background:#0f172acc;border-radius:18px}.card{padding:12px 18px}.card b{display:block;font-size:24px}button,input{border:1px solid #334155;background:#111827;color:#e5eefb;border-radius:12px;padding:10px}.work{min-height:0;display:grid;grid-template-columns:1fr 360px;gap:12px}#graph{min-height:0}canvas{width:100%;height:100%}aside{padding:14px;overflow:auto}pre{white-space:pre-wrap;font-size:12px}@media(max-width:900px){.work{grid-template-columns:1fr}aside{max-height:260px}}
</style><main><header><p style='color:#22d3ee;letter-spacing:.14em'>Docker-Topology-Live</p><h1>Local Docker Digital Twin</h1><div class='bar'><input id='q' placeholder='filter'><button id='r'>Refresh</button><button id='fit'>Fit</button></div></header><section class='cards'><div class='card'><b id='nodes'>0</b>nodes</div><div class='card'><b id='containers'>0</b>containers</div><div class='card'><b id='running'>0</b>running</div><div class='card'><b id='networks'>0</b>networks</div><div class='card'><b id='links'>0</b>links</div><div class='card'><b id='mode'>live</b>mode</div></section><section class='work'><div id='graph'><canvas id='c'></canvas></div><aside><h2>Inspector</h2><pre id='out'>click a node</pre></aside></section></main><script>
let topo={nodes:[],links:[]},q='',sel=null,c=document.getElementById('c'),ctx=c.getContext('2d');
const $=id=>document.getElementById(id);function color(n){if(q&&!(`${n.id} ${n.label} ${n.kind} ${n.status||''} ${n.image||''}`.toLowerCase().includes(q)))return '#334155';return n.kind==='network'?'#22d3ee':n.status==='running'?'#34d399':n.status==='exited'?'#fb7185':'#a78bfa'}
async function load(){let r=await fetch('/api/topology',{cache:'no-store'});topo=await r.json();layout(true);summary();draw()}function summary(){let s=topo.summary||{};$('nodes').textContent=s.nodes||topo.nodes.length;$('containers').textContent=s.containers||0;$('running').textContent=s.runningContainers||0;$('networks').textContent=s.networks||0;$('links').textContent=s.links||topo.links.length;$('mode').textContent='live'}
function layout(force=false){let w=c.clientWidth,h=c.clientHeight;topo.nodes.forEach((n,i)=>{if(!force&&n.x)return;let a=i/Math.max(topo.nodes.length,1)*Math.PI*2,rad=Math.min(w,h)*(n.kind==='network'?.25:.38);n.x=w/2+Math.cos(a)*rad;n.y=h/2+Math.sin(a)*rad})}
function draw(){let w=c.clientWidth,h=c.clientHeight,d=devicePixelRatio||1;if(c.width!==w*d||c.height!==h*d){c.width=w*d;c.height=h*d;ctx.setTransform(d,0,0,d,0,0);layout()}ctx.clearRect(0,0,w,h);let by=new Map(topo.nodes.map(n=>[n.id,n]));ctx.lineWidth=1.4;for(let l of topo.links){let a=by.get(l.source),b=by.get(l.target);if(!a||!b)continue;ctx.strokeStyle='#64748b99';ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke()}for(let n of topo.nodes){let r=n.kind==='network'?15:11;ctx.fillStyle=color(n);ctx.shadowColor=color(n);ctx.shadowBlur=14;ctx.beginPath();ctx.arc(n.x,n.y,r,0,Math.PI*2);ctx.fill();ctx.shadowBlur=0;ctx.fillStyle='#e5eefb';ctx.textAlign='center';ctx.font='12px system-ui';ctx.fillText(n.label||n.id,n.x,n.y+r+16)}requestAnimationFrame(draw)}
c.onclick=e=>{let rect=c.getBoundingClientRect(),x=e.clientX-rect.left,y=e.clientY-rect.top;for(let i=topo.nodes.length-1;i>=0;i--){let n=topo.nodes[i];if(Math.hypot(n.x-x,n.y-y)<20){sel=n;$('out').textContent=JSON.stringify(n,null,2);break}}};$('q').oninput=e=>q=e.target.value.toLowerCase().trim();$('r').onclick=load;$('fit').onclick=()=>layout(true);load();setInterval(load,2500);
</script>"""

def now(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
def sid(x): return str(x or 'unknown')[:12]
def normalize(p):
    nodes={n['id']:n for n in p.get('nodes',[]) if n.get('id')}; links={(l.get('source'),l.get('target'),l.get('kind','link'),l.get('label','')):l for l in p.get('links',[]) if l.get('source') and l.get('target')}
    ns=sorted(nodes.values(),key=lambda n:(n.get('kind',''),n.get('label',''))); ls=sorted(links.values(),key=lambda l:(l.get('source',''),l.get('target','')))
    bykind={}; bystatus={}
    for n in ns:
        k=n.get('kind','unknown'); bykind[k]=bykind.get(k,0)+1
        if k=='container': bystatus[n.get('status','unknown')]=bystatus.get(n.get('status','unknown'),0)+1
    p.update(schemaVersion='1.0',generatedAt=p.get('generatedAt') or now(),nodes=ns,links=ls,summary={'nodes':len(ns),'links':len(ls),'containers':bykind.get('container',0),'runningContainers':bystatus.get('running',0),'networks':bykind.get('network',0),'byKind':bykind,'byContainerStatus':bystatus})
    p.setdefault('source',{'engine':'docker','host':'local'}); p.setdefault('warnings',[]); return p

def sample():
    return normalize({'source':{'engine':'sample','host':'demo'},'nodes':[{'id':'network:front','label':'front','kind':'network','driver':'bridge'},{'id':'network:back','label':'back','kind':'network','driver':'bridge','internal':True},{'id':'container:gateway','label':'gateway','kind':'container','status':'running','image':'nginx:alpine'},{'id':'container:api','label':'api','kind':'container','status':'running','image':'python:3.12-alpine'},{'id':'container:redis','label':'redis','kind':'container','status':'running','image':'redis:7-alpine'},{'id':'container:worker','label':'worker-crashed','kind':'container','status':'exited','image':'python:3.12-alpine'}],'links':[{'source':'container:gateway','target':'network:front','kind':'attached-to','label':'172.24.0.10'},{'source':'container:api','target':'network:front','kind':'attached-to','label':'172.24.0.20'},{'source':'container:api','target':'network:back','kind':'attached-to','label':'172.25.0.20'},{'source':'container:redis','target':'network:back','kind':'attached-to','label':'172.25.0.30'},{'source':'container:worker','target':'network:back','kind':'attached-to','label':'last: 172.25.0.40'}]})

def scan(all_containers=True):
    import docker
    client=docker.from_env(); client.ping(); nodes=[]; links=[]; lookup={}
    for net in client.networks.list():
        a=getattr(net,'attrs',{}) or {}; raw=str(getattr(net,'id',None) or a.get('Id') or getattr(net,'name','network')); name=str(getattr(net,'name',None) or a.get('Name') or sid(raw)); nid='network:'+sid(raw); lookup[name]=lookup[raw]=lookup[sid(raw)]=nid; nodes.append({'id':nid,'label':name,'kind':'network','driver':a.get('Driver','unknown'),'scope':a.get('Scope','unknown'),'internal':bool(a.get('Internal',False))})
    for c in client.containers.list(all=all_containers):
        a=getattr(c,'attrs',{}) or {}; raw=str(getattr(c,'id',None) or a.get('Id') or getattr(c,'name','container')); cid='container:'+sid(raw); image=getattr(c,'image',None); tags=getattr(image,'tags',[]) or []; nodes.append({'id':cid,'label':str(getattr(c,'name',None) or a.get('Name','container')).lstrip('/'),'kind':'container','status':str(getattr(c,'status',None) or a.get('State',{}).get('Status','unknown')),'image':str(tags[0] if tags else (a.get('Config') or {}).get('Image') or 'unknown')})
        for name,ep in ((a.get('NetworkSettings') or {}).get('Networks') or {}).items(): ep=ep or {}; links.append({'source':cid,'target':lookup.get(name,'network:'+sid(ep.get('NetworkID') or name)),'kind':'attached-to','label':ep.get('IPAddress') or ep.get('GlobalIPv6Address') or ''})
    return normalize({'source':{'engine':'docker','host':'local'},'nodes':nodes,'links':links})

def write(p,path,compact=False):
    s=json.dumps(p,ensure_ascii=False,separators=(',',':') if compact else None,indent=None if compact else 2)
    if path=='-': print(s)
    else: open(path,'w',encoding='utf-8').write(s+'\n'); print(f"wrote {path} ({p['summary']['nodes']} nodes, {p['summary']['links']} links)")

def serve(host,port,use_sample):
    class H(BaseHTTPRequestHandler):
        def log_message(self,fmt,*args): print(f"{self.address_string()} - {fmt%args}")
        def do_GET(self):
            path=self.path.split('?',1)[0]
            if path in ('/','/index.html'): return self.send(HTML.encode(),'text/html; charset=utf-8')
            if path=='/api/topology':
                try: p=sample() if use_sample else scan()
                except Exception as e: p=sample(); p['warnings'].append(str(e))
                return self.send(json.dumps(p,ensure_ascii=False).encode(),'application/json; charset=utf-8')
            if path=='/healthz': return self.send(b'{"ok":true}','application/json')
            self.send_error(404)
        def send(self,b,typ): self.send_response(200); self.send_header('Content-Type',typ); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    print(f'Docker-Topology-Live: http://{host}:{port}'); ThreadingHTTPServer((host,port),H).serve_forever()

def main(argv=None):
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd')
    s=sub.add_parser('scan'); s.add_argument('-o','--output',default='topology.json'); s.add_argument('--running-only',action='store_true'); s.add_argument('--compact',action='store_true'); s.add_argument('--sample-on-error',action='store_true'); s.add_argument('--stats',action='store_true')
    s=sub.add_parser('sample'); s.add_argument('-o','--output',default='topology.json'); s.add_argument('--compact',action='store_true')
    s=sub.add_parser('serve'); s.add_argument('--host',default='127.0.0.1'); s.add_argument('--port',type=int,default=8000); s.add_argument('--sample',action='store_true'); s.add_argument('--stats',action='store_true'); s.add_argument('--poll-interval',type=float,default=2.0); s.add_argument('--running-only',action='store_true')
    sub.add_parser('doctor'); a=p.parse_args(argv)
    if a.cmd is None: a.cmd='scan'; a.output='topology.json'; a.running_only=False; a.compact=False; a.sample_on_error=False; a.stats=False
    try:
        if a.cmd=='sample': write(sample(),a.output,a.compact)
        elif a.cmd=='scan':
            try: pld=scan(not a.running_only)
            except Exception:
                if not a.sample_on_error: raise
                pld=sample()
            write(pld,a.output,a.compact)
        elif a.cmd=='serve': serve(a.host,a.port,a.sample)
        elif a.cmd=='doctor': scan(False); print('Docker daemon reachable')
        return 0
    except Exception as e: print(str(e),file=sys.stderr); return 2
if __name__=='__main__': raise SystemExit(main())
