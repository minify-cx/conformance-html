import importlib.util,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; spec=importlib.util.spec_from_file_location('h',ROOT/'tools/conformance.py'); h=importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
class Tests(unittest.TestCase):
 def test_dat_parser(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'x.dat'; p.write_text('#data\n<p>x\n#errors\n#document\n| <html>\n#data\n<b>y\n#errors\n#document-fragment\ndiv\n#document\n| <b>\n'); rows=h.dat_cases(p); self.assertEqual(rows[0]['html'],'<p>x\n'); self.assertTrue(rows[1]['fragment'])
 def test_dom_equivalence(self):
  self.assertEqual(h.classify('<p class="x">a</p>',"<p class=x>a",None)[0],'pass'); self.assertEqual(h.classify('<p>a</p>','<p>b</p>',None)[0],'dom-difference')
 def test_error(self): self.assertEqual(h.classify('x','', 'boom')[0],'minify-error')
 def test_parser_provenance(self):
  identity=h.parser_identity()
  self.assertEqual(identity['name'],'html5lib')
  self.assertTrue(isinstance(identity['version'],str) and identity['version'] and identity['version']!='unavailable',
   'installed html5lib package version must be recorded for comparison provenance')
  # source_revisions must only contain actually-checked-out sources, and the
  # never-acquired html5lib-tests pin must live in references WITHOUT any
  # fabricated synced_at value.
  revs=h.actual_revisions(); refs=h.configured_references()
  # html5lib-tests is never reported as a synchronized source even if a WPT
  # checkout is present; it appears only in references without synced_at.
  self.assertNotIn('html5lib-tests',revs)
  self.assertIn('html5lib-tests',refs)
  self.assertNotIn('synced_at',refs['html5lib-tests'])
  self.assertIn('revision',refs['html5lib-tests'])
 def test_conditional_comment_preservation_detected(self):
  # The DOM canonicalizer drops comment nodes, so preserved conditional
  # comments must be checked by the auxiliary ordered-sequence comparison.
  cond='<!--[if IE]>x<![endif]-->'
  other='<!--#include file="x"-->'
  # preserved
  self.assertTrue(h.preserves_conditional_comments(cond,cond))
  # removal
  self.assertFalse(h.preserves_conditional_comments(cond,'<p>x</p>'))
  # alteration
  self.assertFalse(h.preserves_conditional_comments(cond,'<!--[if lt IE 9]>x<![endif]-->'))
  # duplicate loss
  self.assertFalse(h.preserves_conditional_comments(cond+cond,cond))
  # insertion
  self.assertFalse(h.preserves_conditional_comments(cond,cond+cond))
  # reordering
  self.assertFalse(h.preserves_conditional_comments(cond+other,other+cond))
  # ordinary comments may be removed; only conditional markers are checked
  self.assertTrue(h.preserves_conditional_comments('<!-- ordinary -->',''))
  # and the full classify() path must go red when a conditional comment is lost
  self.assertEqual(h.classify(cond+'<p>a</p>','<p>a</p>',None)[0],'dom-difference')
  self.assertEqual(h.classify(cond+'<p>a</p>',cond+'<p>a</p>',None)[0],'pass')


class IdentityTests(unittest.TestCase):
    def test_parser_oracle_identity(self):
        o = h.oracle_identity() if hasattr(h, "oracle_identity") else h.parser_identity()
        self.assertIn("name", o)
        self.assertTrue(o.get("version"))

    def test_dashboard_identity_propagation(self):
        import json, tempfile
        base = {"counts": {"pass": 1}, "source_revisions": {},
                "minifier": {"name": "Minify++", "version": "1.1.2", "commit": "x"*40},
                "oracle": {"name": "o", "version": "1"}, "generated_at": "2026-01-01T00:00:00Z"}
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td/"res.json").write_text(json.dumps(base))
            (td/"pub.json").write_text(json.dumps(base))
            (td/"index.html").write_text("<h1>ok</h1>")
            h.verify_dashboard(td/"res.json", td/"index.html", td/"pub.json")
            bad = dict(base); bad["minifier"] = {"name": "Minify++", "version": "1.1.1", "commit": "y"*40}
            (td/"pub.json").write_text(json.dumps(bad))
            with self.assertRaises(SystemExit):
                h.verify_dashboard(td/"res.json", td/"index.html", td/"pub.json")

    def test_minifier_identity_reads_git_commit(self):
        import subprocess, tempfile
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            subprocess.run(["git", "init", "-q"], cwd=td, check=True)
            subprocess.run(["git", "config", "user.email", "t@t"], cwd=td, check=True)
            subprocess.run(["git", "config", "user.name", "t"], cwd=td, check=True)
            exe = td/"minify"
            exe.write_text("#!/bin/sh\necho 'Minify++ 1.1.2'\n")
            exe.chmod(0o755)
            subprocess.run(["git", "add", "minify"], cwd=td, check=True)
            subprocess.run(["git", "commit", "-qm", "c"], cwd=td, check=True)
            ident = h.minifier_identity(exe)
            self.assertEqual(ident["name"], "Minify++")
            self.assertEqual(ident["version"], "1.1.2")
            self.assertTrue(ident["commit"])

if __name__=='__main__': unittest.main()
