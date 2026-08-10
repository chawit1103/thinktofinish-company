PYTHON ?= python3

.PHONY: test smoke doctor pilot autopilot-check

test:
	PYTHONPATH=. $(PYTHON) -m pytest -q

smoke:
	$(PYTHON) scripts/mcp-smoke.py

doctor:
	./scripts/doctor.sh

pilot:
	@echo "Usage: ./scripts/create-pilot.sh /absolute/path/to/git-project [board-slug]"

autopilot-check:
	$(PYTHON) scripts/kanban-handoff-autopilot.py --self-test
	$(PYTHON) -m py_compile scripts/kanban-state-snapshot.py
	bash -n scripts/enable-kanban-autopilot.sh
