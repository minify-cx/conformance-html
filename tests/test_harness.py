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
if __name__=='__main__': unittest.main()
