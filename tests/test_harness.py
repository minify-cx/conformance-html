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
if __name__=='__main__': unittest.main()
