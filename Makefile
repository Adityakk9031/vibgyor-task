PYTHON ?= python3

.PHONY: all extract build render export test serve ai-bases ai-package

all:
	$(PYTHON) build.py all

extract:
	$(PYTHON) build.py extract

build:
	$(PYTHON) build.py build

render:
	$(PYTHON) build.py render

export:
	$(PYTHON) build.py export

test:
	$(PYTHON) -m pytest -v

serve:
	$(PYTHON) -m http.server 8090 --directory viewer

ai-bases:
	$(PYTHON) -m pipeline.render_ai_bases all

ai-package:
	$(PYTHON) -m pipeline.package_ai_inputs
