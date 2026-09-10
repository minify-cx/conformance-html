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
 # Record only sources that were actually checked out and used for
 # extraction. The sync lock records what `sync` last checked out, which is
 # stale when a corpus is pinned manually to reproduce a retained checkpoint;
 # results must carry the revision the extraction truly used. A configured
 # source that was never acquired (for example the html5lib-tests reference
 # pin) is reported separately by configured_references() and is never shown
 # as synchronized.
 state={}; spec=load(ROOT/'config/sources.json')
 for name,s in spec.items():
  dst=ROOT/s['path']; old=lock().get(name,{})
  if (dst/'.git').exists():
   try: rev=subprocess.check_output(['git','rev-parse','HEAD'],cwd=dst,text=True).strip()
   except Exception: rev=old.get('revision','')
   state[name]={'url':s.get('url',old.get('url','')),'revision':rev,'synced_at':old.get('synced_at',now())}
 return state
def configured_references():
 # Configured but never-acquired provenance pins. These do not supply cases
 # and are not synchronized; they carry no synced_at so the result cannot be
 # mistaken for a checkout that participated in the run.
 refs={}; spec=load(ROOT/'config/sources.json')
 for name,s in spec.items():
  dst=ROOT/s['path']
  if not (dst/'.git').exists() and s.get('revision'):
   refs[name]={'url':s.get('url',''),'revision':s['revision']}
 return refs
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

def minifier_identity(exe):
 # Structured, self-identifying minifier metadata: product name, semantic
 # version, exact git commit (from the checkout that produced the binary) and
 # the raw --version string.
 probe=subprocess.run([str(exe),'--version'],capture_output=True,text=True)
 text=(probe.stdout or probe.stderr or '').strip()
 m=re.search(r'(\d+\.\d+\.\d+)',text)
 commit=None
 parent=Path(exe).resolve().parent
 if (parent/'.git').exists():
  r=subprocess.run(['git','-C',str(parent),'rev-parse','HEAD'],capture_output=True,text=True)
  if r.returncode==0: commit=r.stdout.strip()
 return {'name':'Minify++','version':m.group(1) if m else text,'version_string':text,'commit':commit,'path':str(exe)}

def parser_identity():
 # Comparison is performed by the installed Python html5lib package, not by
 # the html5lib-tests repository. Record the installed parser version so the
 # provenance of every canonical projection is explicit.
 try:
  import html5lib
  version=getattr(html5lib,'__version__','unknown')
 except Exception:
  version='unavailable'
 return {'name':'html5lib','version':version}
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
 if not preserves_conditional_comments(source,output):
  # Conditional comments (`<!--[if`, `<!--#`, `<!--!`) are deliberately
  # preserved by Minify++ because they carry runtime meaning, but the DOM
  # canonicalizer drops comment nodes entirely. This auxiliary assertion
  # closes that blind spot. Ordinary comments remain outside semantic
  # comparison per the documented normalization policy.
  return 'dom-difference',{'reason':'conditional-comment-loss','before':before,'after':after}
 return 'pass',{}
def preserved_comment_sequence(text):
 # Ordered list of preserved conditional/SSI/license comments. These marker
 # families match the Minify++ html() preserve policy: `<!--[if`, `<!--#`
 # and `<!--!`.
 seq=[]; i=0
 while True:
  start=text.find('<!--',i)
  if start<0: break
  end=text.find('-->',start+4)
  if end<0: break
  comment=text[start:end+3]
  if comment.startswith('<!--[if') or comment.startswith('<!--#') or comment.startswith('<!--!'):
   seq.append(comment)
  i=end+3
 return seq
def preserves_conditional_comments(before,after):
 # Compare the ordered preserved-comment sequences exactly so removal,
 # alteration, duplicate loss, insertion and reordering are all detected,
 # not just "the string appears somewhere".
 return preserved_comment_sequence(before)==preserved_comment_sequence(after)
def execute(cases_path,exe,result):
 cases=[json.loads(x) for x in cases_path.read_text().splitlines() if x.strip()]; started=time.time(); outputs,errors=minify(cases,exe); rows=[]; counts={}
 for c in cases:
  status,evidence=classify(c['html'],outputs.get(c['id'],''),errors.get(c['id'])); counts[status]=counts.get(status,0)+1
  row={k:c[k] for k in ('id','suite','source','index')}; row['status']=status
  if status!='pass': row.update(input=c['html'],output=outputs.get(c['id']),evidence=evidence)
  rows.append(row)
 payload={'schema_version':1,'format':'html','generated_at':now(),'duration_seconds':round(time.time()-started,3),'source_revisions':actual_revisions(),'references':configured_references(),'parser':parser_identity(),'minifier':minifier_identity(exe),'oracle':parser_identity(),'total':len(rows),'counts':counts,'results':rows}; save(result,payload); save(ROOT/'results/history'/f'{datetime.datetime.now(datetime.timezone.utc):%Y%m%dT%H%M%SZ}.json',payload); print(json.dumps(counts,sort_keys=True))
 return 1 if any(counts.get(x) for x in ('minify-error','parser-rejected','dom-difference')) else 0
def dashboard(result):
 data=load(result); cards=''.join(f'<li><strong>{html.escape(k)}</strong><span>{v}</span></li>' for k,v in sorted(data['counts'].items())); bad=[r for r in data['results'] if r['status']!='pass'][:200]
 rows=''.join(f"<tr><td>{html.escape(r['status'])}</td><td>{html.escape(r['source'])}</td><td><code>{r['id']}</code></td></tr>" for r in bad) or '<tr><td colspan="3">No non-pass cases.</td></tr>'
 parser=data.get('parser',{}); parser_text=f"<p>Canonicalization parser: {html.escape(str(parser.get('name','html5lib')))} {html.escape(str(parser.get('version','unknown')))} (installed package).</p>" if parser else ''
 refs=data.get('references',{}); ref_text=''
 if refs:
  items=''.join(f"<li><strong>{html.escape(k)}</strong> <code>{html.escape(v.get('revision',''))[:12]}</code> (configured reference, not synchronized)</li>" for k,v in sorted(refs.items()))
  ref_text=f'<ul class="references">{items}</ul>'

 def provenance_text(data):
  min=data.get('minifier',{}); ora=data.get('oracle',{}); revs=data.get('source_revisions',{})
  bits=[f"<strong>Minify++</strong> {html.escape(str(min.get('version','')))}{(' ('+html.escape(str(min.get('commit',''))) )[:9]+')' if min.get('commit') else ''}",
        f"<strong>oracle</strong> {html.escape(str(ora.get('name','')))} {html.escape(str(ora.get('version','')))}"]
  for k,v in revs.items():
   bits.append(f"<strong>{html.escape(k)}</strong> <code>{html.escape(str(v.get('revision','')))[:12]}</code>")
  return '<p class="provenance">' + ' &middot; '.join(bits) + '</p>'
 provenance_text=provenance_text(data)

 g=ROOT/'generated/latest.html'; g.parent.mkdir(exist_ok=True); g.write_text(f'<section class="hero"><p class="eyebrow">HTML conformance</p><h1>Minify++ against html5lib</h1><p>{data["total"]} independent tree-construction cases. Generated {data["generated_at"]}.</p></section><ul class="stats">{cards}</ul>{parser_text}{ref_text}{provenance_text}<section><h2>Non-pass evidence</h2><table><thead><tr><th>Status</th><th>Source</th><th>ID</th></tr></thead><tbody>{rows}</tbody></table></section>')
 shutil.copy(result,ROOT/'public/results/latest.json'); subprocess.run(['nift','build','--all'],cwd=ROOT,check=True)
 verify_dashboard(result,ROOT/'public/index.html',ROOT/'public/results/latest.json')
def verify_dashboard(result_path,index_path,published_path):
 # Prove the freshly built dashboard reflects exactly this completed run: the
 # published JSON must carry the same counts, source revisions, parser and
 # generation timestamp, and the rendered page must contain no unresolved
 # Nift directives.
 data=load(result_path); pub=load(published_path)
 for key in ('counts','source_revisions','parser','minifier','oracle','generated_at'):
  if pub.get(key)!=data.get(key):
   raise SystemExit(f"dashboard mismatch: {key} differs between result and published copy")
 text=Path(index_path).read_text()
 for token in ('@path(','@pathto(','@input(','@content'):
  if token in text: raise SystemExit(f"unresolved Nift directive in dashboard: {token}")
 print("dashboard verified: published JSON matches run and page has no unresolved directives")
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
