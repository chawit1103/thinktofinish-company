PYTHON ?= python3

.PHONY: test smoke doctor pilot

test:
	PYTHONPATH=. $(PYTHON) -m pytest -q

smoke:
	$(PYTHON) scripts/mcp-smoke.py

doctor:
	./scripts/doctor.sh

pilot:
	@echo "Usage: ./scripts/create-pilot.sh /absolute/path/to/git-project [board-slug]"
