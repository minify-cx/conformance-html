# Minify++ HTML Conformance

Independent HTML conformance evidence for Minify++. The harness pins Web Platform Tests, extracts standalone HTML documents under WPT's HTML tree, minifies them in batches, parses original and output with html5lib, and compares canonical DOM trees. Upstream tests are acquired on demand and are not vendored.

```sh
python3 -m pip install html5lib
make smoke
make sync extract html
make dashboard
```

Use `extract-html --limit 1000` while iterating. Results are retained as `results/latest.json` and timestamped history. Statuses are `pass`, `dom-difference`, `parser-rejected`, `source-rejected`, and `minify-error`. The first adapter excludes fragment tests because they require a contextual fragment parser. Confirmed product defects belong in Minify++'s permanent regression suite.

The Nift dashboard is built from a completed snapshot; it is not live while tests run.
