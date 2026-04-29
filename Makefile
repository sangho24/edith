.PHONY: install test run lint fmt typecheck eval check lock help

help:
	@echo "make install     # uv venv + 의존성 설치 (editable)"
	@echo "make test        # mock LLM으로 unit test"
	@echo "make run TASK=...# 실제 Claude API로 task 실행"
	@echo "make eval        # golden YAML 케이스 일괄 실행 (H4)"
	@echo "make lint        # ruff check"
	@echo "make fmt         # ruff format"
	@echo "make typecheck   # pyright"
	@echo "make check       # lint + typecheck + test (CI 풀세트)"
	@echo "make lock        # uv pip compile → requirements.lock"

install:
	uv venv
	uv pip install -e ".[dev]"

test:
	EDITH_LLM=mock uv run pytest

run:
	@if [ -z "$(TASK)" ]; then echo "usage: make run TASK=\"task text\""; exit 1; fi
	uv run harness run "$(TASK)"

lint:
	uv run ruff check harness tests

fmt:
	uv run ruff format harness tests

typecheck:
	uv run pyright harness tests

eval:
	uv run harness eval

dash:
	uv run harness dash --window 24

compile:
	uv run harness compile

compile-dry:
	uv run harness compile --dry-run

daily:
	uv run harness daily

cap:
	@if [ -z "$(TEXT)" ]; then echo "usage: make cap TEXT=\"...\""; exit 1; fi
	uv run harness cap "$(TEXT)"

today:
	uv run harness today

mail:
	uv run harness mail

brief:
	uv run harness brief

gh-cron-get:
	uv run harness gh-cron get

approve-list:
	uv run harness approve list

recall:
	@if [ -z "$(Q)" ]; then echo "usage: make recall Q=\"...\""; exit 1; fi
	uv run harness recall "$(Q)"

paper:
	@if [ -z "$(URL)" ]; then echo "usage: make paper URL=\"https://arxiv.org/abs/...\""; exit 1; fi
	uv run harness paper "$(URL)"

review-pr:
	@if [ -z "$(DIFF)" ]; then echo "usage: make review-pr DIFF=path/to/x.diff"; exit 1; fi
	uv run harness review-pr "$(DIFF)"

jd:
	@if [ -z "$(JD)" ]; then echo "usage: make jd JD=path/to/jd.txt"; exit 1; fi
	uv run harness jd "$(JD)"

weekly:
	uv run harness weekly

# ── F11 Home Hub (docker) ──

hub-up:
	cd docker && docker compose up -d --build

hub-down:
	cd docker && docker compose down

hub-logs:
	cd docker && docker compose logs -f --tail 100

hub-shell:
	cd docker && docker compose run --rm edith-shell

hub-restart:
	cd docker && docker compose restart

# ── F12 VPS Relay (배포는 VPS에서) ──

relay-up:
	cd vps && docker compose up -d --build

relay-logs:
	cd vps && docker compose logs -f --tail 100

relay-down:
	cd vps && docker compose down

install-daily:
	bash scripts/install_daily.sh install

uninstall-daily:
	bash scripts/install_daily.sh uninstall

test-daily:
	bash scripts/install_daily.sh test

# ── PR #18 — server.py LaunchAgent (부팅 시 자동 시작) ──

server-install:
	bash scripts/launchd/install.sh install

server-uninstall:
	bash scripts/launchd/install.sh uninstall

server-restart:
	bash scripts/launchd/install.sh restart

server-status:
	bash scripts/launchd/install.sh status

server-logs:
	bash scripts/launchd/install.sh logs

check: lint typecheck test
	@echo ""
	@echo "✓ all checks passed"

lock:
	uv pip compile pyproject.toml -o requirements.lock
