PYTHON ?= python3

.PHONY: test smoke doctor pilot bootstrap-company compatibility-check boundary-check transition-check

test:
	PYTHONPATH=. $(PYTHON) -m pytest -q

smoke:
	$(PYTHON) scripts/mcp-smoke.py

doctor:
	./scripts/doctor.sh

bootstrap-company:
	./scripts/bootstrap-company.sh

compatibility-check:
	./scripts/compatibility-check.sh

boundary-check:
	$(PYTHON) scripts/runtime-boundary-check.py

pilot:
	@echo "Usage: ./scripts/create-pilot.sh /absolute/path/to/git-project [board-slug]"

# Legacy-board compatibility only; new projects use Hermes native review/rework.
transition-check:
	$(PYTHON) scripts/kanban-transition-engine.py --self-test
	$(PYTHON) -m py_compile scripts/kanban-transition-engine.py
	@for script in scripts/*.sh; do bash -n "$$script"; done
