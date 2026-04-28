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

check: lint typecheck test
	@echo ""
	@echo "✓ all checks passed"

lock:
	uv pip compile pyproject.toml -o requirements.lock
