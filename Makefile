PYTHON ?= python3

.PHONY: test smoke doctor pilot transition-check

test:
	PYTHONPATH=. $(PYTHON) -m pytest -q

smoke:
	$(PYTHON) scripts/mcp-smoke.py

doctor:
	./scripts/doctor.sh

pilot:
	@echo "Usage: ./scripts/create-pilot.sh /absolute/path/to/git-project [board-slug]"

transition-check:
	$(PYTHON) scripts/kanban-transition-engine.py --self-test
	$(PYTHON) -m py_compile scripts/kanban-transition-engine.py
	@for script in scripts/*.sh; do bash -n "$$script"; done
