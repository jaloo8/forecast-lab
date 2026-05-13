.PHONY: help install install-hooks sync test lint type check fmt ingest backtest paper dashboard bootstrap bootstrap-secrets edit-secrets keygen-age clean

PY := uv run

help:
	@echo "Common commands:"
	@echo "  make install         Install dependencies via uv"
	@echo "  make install-hooks   Install the pre-commit hooks locally"
	@echo "  make sync            Sync .venv to pyproject.toml"
	@echo "  make test            Run pytest"
	@echo "  make lint        Run ruff"
	@echo "  make type        Run mypy --strict"
	@echo "  make fmt         Format with ruff"
	@echo "  make check       lint + type + test"
	@echo ""
	@echo "  make bootstrap          Initialize DuckDB schema"
	@echo "  make bootstrap-secrets  Decrypt secrets.enc.yaml -> .env (see docs/SECRETS.md)"
	@echo "  make edit-secrets       Open the encrypted secrets file in \$$EDITOR"
	@echo "  make keygen-age         Generate a fresh age keypair (one-time per machine)"
	@echo "  make ingest             One-shot data ingest"
	@echo "  make backtest STRATEGY=weather_v1"
	@echo "  make paper              Start paper trader"
	@echo "  make dashboard          Start Streamlit dashboard"
	@echo ""
	@echo "  make live --i-understand-the-risks   PHASE 5+ ONLY (refuses without gate)"

install:
	uv sync

install-hooks:
	$(PY) pre-commit install
	@echo "pre-commit installed. Hooks will now run on every `git commit`."

sync: install

test:
	$(PY) pytest

lint:
	$(PY) ruff check .

type:
	$(PY) mypy src/kq

fmt:
	$(PY) ruff format .
	$(PY) ruff check . --fix

check: lint type test

bootstrap:
	$(PY) python scripts/bootstrap_db.py

bootstrap-secrets:
	$(PY) python scripts/bootstrap_secrets.py

edit-secrets:
	@command -v sops >/dev/null 2>&1 || (echo "sops not installed -- see docs/SECRETS.md"; exit 1)
	sops secrets.enc.yaml

keygen-age:
	@command -v age-keygen >/dev/null 2>&1 || (echo "age-keygen not installed -- see docs/SECRETS.md"; exit 1)
	@# Per-OS key path: sops 3.12+ on macOS reads from ~/Library/Application Support/sops/age/keys.txt
	@# (Apple's standard config dir); Linux/WSL keeps the XDG ~/.config path. Detect OS and use the
	@# canonical location so `sops` finds the key without needing a symlink or SOPS_AGE_KEY_FILE env.
	@if [ "$$(uname -s)" = "Darwin" ]; then \
		KEY_DIR="$$HOME/Library/Application Support/sops/age"; \
	else \
		KEY_DIR="$$HOME/.config/sops/age"; \
	fi; \
	KEY_FILE="$$KEY_DIR/keys.txt"; \
	mkdir -p "$$KEY_DIR"; \
	if [ -f "$$KEY_FILE" ] || [ -f "$$HOME/.config/sops/age/keys.txt" ] || [ -f "$$HOME/Library/Application Support/sops/age/keys.txt" ]; then \
		echo "Refusing to overwrite an existing key. Looked in:"; \
		echo "  $$HOME/.config/sops/age/keys.txt"; \
		echo "  $$HOME/Library/Application Support/sops/age/keys.txt"; \
		exit 1; \
	fi; \
	age-keygen -o "$$KEY_FILE"; \
	chmod 600 "$$KEY_FILE"; \
	echo ""; \
	echo "Key written to: $$KEY_FILE"; \
	echo "Public key (paste into .sops.yaml):"; \
	grep "public key" "$$KEY_FILE"

ingest:
	$(PY) python -m kq ingest

ingest-weather:
	$(PY) python -m kq ingest-weather

ingest-metar:
	$(PY) python -m kq ingest-metar

ingest-kalshi:
ifdef EVENT_TICKER
	$(PY) python -m kq ingest-kalshi --event-ticker $(EVENT_TICKER)
else
	$(PY) python -m kq ingest-kalshi
endif

backfill-weather:
	@test -n "$(START)" -a -n "$(END)" || (echo "usage: make backfill-weather START=YYYY-MM-DD END=YYYY-MM-DD"; exit 1)
	$(PY) python -m kq backfill-weather --start $(START) --end $(END)

backfill-observed:
	@test -n "$(START)" -a -n "$(END)" || (echo "usage: make backfill-observed START=YYYY-MM-DD END=YYYY-MM-DD"; exit 1)
	$(PY) python -m kq backfill-observed --start $(START) --end $(END)

train-weather:
	$(PY) python -m kq train-weather $(if $(LEAD_DAYS),--lead-days $(LEAD_DAYS),)

backtest:
	@test -n "$(STRATEGY)" || (echo "usage: make backtest STRATEGY=weather_v1"; exit 1)
	$(PY) python -m kq backtest --strategy $(STRATEGY)

paper:
	$(PY) python -m kq paper

dashboard:
	$(PY) streamlit run src/kq/dashboard/streamlit_app.py

live:
	@echo "Live trading gated behind Phase 5 criteria in CLAUDE.md §5. Refusing."
	@exit 1

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
