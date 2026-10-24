PYTHON ?= python3

.PHONY: all extract build render export test serve

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
	$(PYTHON) -m http.server 8080 --directory viewer
