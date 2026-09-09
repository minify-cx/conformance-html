PYTHON ?= python3
MINIFY_BIN ?= ../minify/minify
.PHONY: test smoke sync extract html dashboard
test:
	$(PYTHON) -m unittest discover -s tests -v
	$(PYTHON) -m py_compile tools/conformance.py
smoke:
	$(PYTHON) tools/conformance.py smoke --minify-bin "$(MINIFY_BIN)"
sync:
	$(PYTHON) tools/conformance.py sync
extract:
	$(PYTHON) tools/conformance.py extract-html
html:
	$(PYTHON) tools/conformance.py run-html --minify-bin "$(MINIFY_BIN)"
dashboard:
	$(PYTHON) tools/conformance.py dashboard
