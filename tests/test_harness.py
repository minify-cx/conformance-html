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
 def test_conditional_comment_preservation_detected(self):
  # The DOM canonicalizer drops comment nodes, so a removed or changed
  # conditional comment must be caught by the auxiliary preservation check.
  cond='<!--[if IE]>x<![endif]-->'
  self.assertTrue(h.preserves_conditional_comments(cond,cond))
  self.assertFalse(h.preserves_conditional_comments(cond,'<p>x</p>'))
  self.assertFalse(h.preserves_conditional_comments(cond,'<!--[if lt IE 9]>x<![endif]-->'))
  # Ordinary comments may be removed; only conditional markers are checked.
  self.assertTrue(h.preserves_conditional_comments('<!-- ordinary -->',''))
  # And the full classify() path must go red when a conditional comment is lost.
  self.assertEqual(h.classify(cond+'<p>a</p>','<p>a</p>',None)[0],'dom-difference')
  self.assertEqual(h.classify(cond+'<p>a</p>',cond+'<p>a</p>',None)[0],'pass')
if __name__=='__main__': unittest.main()
