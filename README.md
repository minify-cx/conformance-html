# Minify++ HTML Conformance

Independent HTML conformance evidence for Minify++. The harness pins Web Platform Tests, extracts standalone HTML documents under WPT's HTML tree, minifies them in batches, parses original and output with html5lib, and compares canonical DOM trees. Upstream tests are acquired on demand and are not vendored.

```sh
python3 -m pip install html5lib
make smoke
make sync extract html
make dashboard
```

Use `extract-html --limit 1000` while iterating. Results are retained as `results/latest.json` and timestamped history. Statuses are `pass`, `dom-difference`, `parser-rejected`, `source-rejected`, and `minify-error`. Support/resource paths and unresolved WPT server/generator templates are explicitly excluded and counted during extraction. Confirmed product defects belong in Minify++'s permanent regression suite.

The Nift dashboard is built from a completed snapshot; it is not live while tests run.

## Retained complete checkpoint

At WPT revision `aed18189e54793ee12286eb96509e87df27f52dd`, the complete
adapter selected 9,651 documents and all 9,651 preserved the canonical semantic
DOM after Minify++. Extraction separately counted 588 support/template-path
files, 240 unresolved server/generator templates and 28 non-UTF-8 inputs. The
campaign found multiple real HTML scanner defects; each was fixed in Minify++
and reduced into its product smoke suite before the final rerun.
