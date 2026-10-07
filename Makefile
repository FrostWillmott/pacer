.PHONY: help install install-hooks install-notifier uninstall-notifier check fix lint format typecheck test coverage pre-commit ci clean

help:
	@echo "Project Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install           - Install dependencies with uv"
	@echo "  make install-hooks     - Install pre-commit hooks"
	@echo "  make install-notifier  - Install/refresh the macOS notifier agent (launchd)"
	@echo "  make uninstall-notifier- Remove the macOS notifier agent"
	@echo ""
	@echo "Code Quality:"
	@echo "  make check         - Run all checks (lint + format + types + tests)"
	@echo "  make fix           - Auto-fix lint and format issues"
	@echo "  make lint          - Run linter (ruff check)"
	@echo "  make format        - Check formatting (ruff format --check)"
	@echo "  make typecheck     - Run type checker (mypy)"
	@echo "  make test          - Run tests"
	@echo "  make coverage      - Run tests with coverage report (fails under 70%)"
	@echo "  make pre-commit    - Run all pre-commit hooks"
	@echo "  make ci            - Full CI check locally"

install:
	uv sync

install-hooks:
	uv run pre-commit install

install-notifier:
	uv run python notifier/install_agent.py

uninstall-notifier:
	uv run python notifier/install_agent.py --uninstall

check: lint format typecheck test

fix:
	uv run ruff check --fix .
	uv run ruff format .

lint:
	uv run ruff check .

format:
	uv run ruff format --check .

typecheck:
	uv run mypy .

test:
	uv run pytest tests/ -v

coverage:
	uv run pytest tests/ --cov=app --cov-report=term-missing --cov-fail-under=70

pre-commit:
	uv run pre-commit run --all-files

ci:
	@echo "Running CI checks..."
	@$(MAKE) check
	@echo "All CI checks passed!"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .mypy_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
