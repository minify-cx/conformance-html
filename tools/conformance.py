#!/usr/bin/env python3
"""Independent HTML conformance runner for Minify++."""
import argparse, datetime, hashlib, html, json, re, shutil, subprocess, tempfile, time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; RESULTS=ROOT/'results/latest.json'
def now(): return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
def load(p): return json.loads(Path(p).read_text())
def save(p,v): p=Path(p); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def lock():
 p=ROOT/'.state/sources.lock.json'; return load(p) if p.exists() else {}
def actual_revisions():
 # Record the revision actually checked out for each configured source. The
 # sync lock records what `sync` last checked out, which is stale when a
 # corpus is pinned manually to reproduce a retained checkpoint; results must
 # carry the revision the extraction truly used.
 state={}; spec=load(ROOT/'config/sources.json')
 for name,s in spec.items():
  dst=ROOT/s['path']; old=lock().get(name,{})
  if (dst/'.git').exists():
   try: rev=subprocess.check_output(['git','rev-parse','HEAD'],cwd=dst,text=True).strip()
   except Exception: rev=old.get('revision','')
   state[name]={'url':s.get('url',old.get('url','')),'revision':rev,'synced_at':old.get('synced_at',now())}
 return state
def sync():
 spec=load(ROOT/'config/sources.json')['wpt']; dst=ROOT/spec['path']; dst.parent.mkdir(parents=True,exist_ok=True)
 if dst.exists(): subprocess.run(['git','fetch','--prune','origin',spec['branch']],cwd=dst,check=True); subprocess.run(['git','checkout','--detach','FETCH_HEAD'],cwd=dst,check=True)
 else: subprocess.run(['git','clone','--filter=blob:none','--no-tags','--sparse',spec['url'],str(dst)],check=True)
 subprocess.run(['git','sparse-checkout','set','html'],cwd=dst,check=True)
 rev=subprocess.check_output(['git','rev-parse','HEAD'],cwd=dst,text=True).strip(); state=lock(); state['wpt']={'url':spec['url'],'revision':rev,'synced_at':now()}; save(ROOT/'.state/sources.lock.json',state); print(rev)
def dat_cases(path):
 tests=[]; cur=None; section=None
 for line in path.read_text(encoding='utf-8').splitlines(keepends=True):
  tag=line.rstrip()
  if tag in ('#data','#errors','#document','#document-fragment','#script-on','#script-off'):
   section=tag
   if tag=='#data':
    if cur: tests.append(cur)
    cur={'html':''}
   continue
  if not cur: continue
  if section=='#data': cur['html']+=line
  elif section=='#document': cur['document']=cur.get('document','')+line
  elif section=='#document-fragment': cur['fragment']=True
 if cur: tests.append(cur)
 return tests
def extract(source,out,limit):
 rows=[]; skipped={}
 for p in sorted((source/'html').rglob('*.html')):
  if any(part in {'resources','support','templates'} for part in p.parts):
   skipped['support-or-template-path']=skipped.get('support-or-template-path',0)+1; continue
  try: text=p.read_text(encoding='utf-8')
  except UnicodeDecodeError:
   skipped['non-utf8']=skipped.get('non-utf8',0)+1; continue
  if '{{' in text or '{%' in text or '{#' in text:
   skipped['unresolved-server-template']=skipped.get('unresolved-server-template',0)+1; continue
  rel=p.relative_to(source).as_posix(); ident=hashlib.sha256(f'{rel}\0{text}'.encode()).hexdigest()[:16]
  rows.append({'id':ident,'suite':'wpt-html-parse','source':rel,'index':0,'html':text})
  if limit and len(rows)>=limit: break
 out.parent.mkdir(parents=True,exist_ok=True); out.write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in rows)); save(out.with_suffix('.summary.json'),{'eligible':len(rows),'skipped':skipped}); print(json.dumps({'eligible':len(rows),'skipped':skipped},sort_keys=True))
def binary(value):
 p=Path(value).expanduser()
 if p.exists(): return p.resolve()
 found=shutil.which(value)
 if not found: raise SystemExit(f'executable not found: {value}')
 return Path(found)
def minify(cases,exe):
 outputs={}; errors={}
 with tempfile.TemporaryDirectory() as td:
  entries=[]
  for i,c in enumerate(cases):
   p=Path(td)/f'case-{i:06d}.html'; p.write_text(c['html']); entries.append((c,p))
  def group(items):
   cp=subprocess.run([str(exe),*[str(p) for _,p in items]],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   produced=[(c,p,p.with_name(p.stem+'.min.html')) for c,p in items]
   if cp.returncode==0 and all(out.exists() for _,_,out in produced):
    for c,_,out in produced: outputs[c['id']]=out.read_text()
   elif len(items)>1:
    mid=len(items)//2; group(items[:mid]); group(items[mid:])
   else:
    c,_,out=produced[0]
    if out.exists(): outputs[c['id']]=out.read_text()
    else: errors[c['id']]=(cp.stderr or cp.stdout or 'no output produced')[-2000:]
  for start in range(0,len(entries),500): group(entries[start:start+500])
 return outputs,errors
def canonical(text):
 try:
  import html5lib
  root=html5lib.parse(text,treebuilder='etree',namespaceHTMLElements=True)
  def walk(n,preserve=False):
   if not isinstance(n.tag,str): return None
   local=str(n.tag).rsplit('}',1)[-1]; preserve=preserve or local in {'pre','textarea','script','style'}
   children=[]
   nodes=list(n)
   block={'body','p','div','section','article','aside','header','footer','main','nav','li','dt','dd','h1','h2','h3','h4','h5','h6'}
   def add_text(value):
    if not value: return
    if children and children[-1][0]=='text': children[-1][1]+=value
    else: children.append(['text',value])
   if n.text: add_text(n.text)
   for pos,c in enumerate(nodes):
    item=walk(c,preserve)
    if item is not None: children.append(item)
    if c.tail: add_text(c.tail)
   if not preserve:
    for child in children:
     if child[0]=='text': child[1]=re.sub(r'\s+',' ',child[1])
    children=[child for child in children if child[0]!='text' or child[1].strip()]
    if children and children[0][0]=='text' and (local=='body' or (len(children)==1 and local in block)): children[0][1]=children[0][1].lstrip()
    if children and children[-1][0]=='text' and (local=='body' or (len(children)==1 and local in block)): children[-1][1]=children[-1][1].rstrip()
   return ['element',str(n.tag),sorted((str(k),v) for k,v in n.attrib.items()),children]
  return {'ok':True,'tree':walk(root)}
 except Exception as e: return {'ok':False,'error':str(e)}
def classify(source,output,error):
 if error: return 'minify-error',{'error':error}
 before,after=canonical(source),canonical(output)
 if not before['ok']: return 'source-rejected',{'before':before}
 if not after['ok']: return 'parser-rejected',{'after':after}
 if before['tree']!=after['tree']: return 'dom-difference',{'before':before,'after':after}
 return 'pass',{}
def execute(cases_path,exe,result):
 cases=[json.loads(x) for x in cases_path.read_text().splitlines() if x.strip()]; started=time.time(); outputs,errors=minify(cases,exe); rows=[]; counts={}
 for c in cases:
  status,evidence=classify(c['html'],outputs.get(c['id'],''),errors.get(c['id'])); counts[status]=counts.get(status,0)+1
  row={k:c[k] for k in ('id','suite','source','index')}; row['status']=status
  if status!='pass': row.update(input=c['html'],output=outputs.get(c['id']),evidence=evidence)
  rows.append(row)
 payload={'schema_version':1,'format':'html','generated_at':now(),'duration_seconds':round(time.time()-started,3),'source_revisions':actual_revisions(),'minifier':{'path':str(exe)},'total':len(rows),'counts':counts,'results':rows}; save(result,payload); save(ROOT/'results/history'/f'{datetime.datetime.now(datetime.timezone.utc):%Y%m%dT%H%M%SZ}.json',payload); print(json.dumps(counts,sort_keys=True))
 return 1 if any(counts.get(x) for x in ('minify-error','parser-rejected','dom-difference')) else 0
def dashboard(result):
 data=load(result); cards=''.join(f'<li><strong>{html.escape(k)}</strong><span>{v}</span></li>' for k,v in sorted(data['counts'].items())); bad=[r for r in data['results'] if r['status']!='pass'][:200]
 rows=''.join(f"<tr><td>{html.escape(r['status'])}</td><td>{html.escape(r['source'])}</td><td><code>{r['id']}</code></td></tr>" for r in bad) or '<tr><td colspan="3">No non-pass cases.</td></tr>'
 g=ROOT/'generated/latest.html'; g.parent.mkdir(exist_ok=True); g.write_text(f'<section class="hero"><p class="eyebrow">HTML conformance</p><h1>Minify++ against html5lib</h1><p>{data["total"]} independent tree-construction cases. Generated {data["generated_at"]}.</p></section><ul class="stats">{cards}</ul><section><h2>Non-pass evidence</h2><table><thead><tr><th>Status</th><th>Source</th><th>ID</th></tr></thead><tbody>{rows}</tbody></table></section>')
 shutil.copy2(result,ROOT/'public/results/latest.json'); subprocess.run(['nift','build-all'],cwd=ROOT,check=True)
def main():
 p=argparse.ArgumentParser(); s=p.add_subparsers(dest='cmd',required=True); s.add_parser('sync')
 e=s.add_parser('extract-html'); e.add_argument('--source',type=Path,default=ROOT/'.state/upstreams/wpt'); e.add_argument('--output',type=Path,default=ROOT/'work/wpt-html.jsonl'); e.add_argument('--limit',type=int)
 for name in ('run-html','smoke'):
  q=s.add_parser(name); q.add_argument('--minify-bin',default='../minify/minify'); q.add_argument('--results',type=Path,default=RESULTS); q.add_argument('--dashboard',action='store_true')
  if name=='run-html': q.add_argument('--cases',type=Path,default=ROOT/'work/wpt-html.jsonl')
 d=s.add_parser('dashboard'); d.add_argument('--results',type=Path,default=RESULTS); a=p.parse_args()
 if a.cmd=='sync': sync(); return 0
 if a.cmd=='extract-html': extract(a.source,a.output,a.limit); return 0
 if a.cmd=='dashboard': dashboard(a.results); return 0
 exe=binary(a.minify_bin)
 if a.cmd=='smoke':
  cases=[{'id':'basic','suite':'smoke','source':'basic','index':0,'html':'<!doctype html>\n<html><head><title>x</title></head><body><p>Hello <b>world</b></p></body></html>'},{'id':'raw','suite':'smoke','source':'raw','index':0,'html':'<!doctype html><script>const x = "</script-not>";</script><pre> a  b </pre>'}]; path=ROOT/'work/smoke-html.jsonl'; path.parent.mkdir(exist_ok=True); path.write_text(''.join(json.dumps(x)+'\n' for x in cases))
 else: path=a.cases
 rc=execute(path,exe,a.results)
 if a.dashboard: dashboard(a.results)
 return rc
if __name__=='__main__': raise SystemExit(main())
