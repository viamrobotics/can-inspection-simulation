.PHONY: help lint fix install-dev

# Python files to lint
PYTHON_FILES := *.py

help:
	@echo "Available commands:"
	@echo "  make lint        - Run ruff linter on Python files (errors only)"
	@echo "  make fix         - Auto-fix linting issues"
	@echo "  make install-dev - Install development dependencies (ruff)"

lint:
	ruff check $(PYTHON_FILES)

fix:
	ruff check --fix $(PYTHON_FILES)

install-dev:
	pip install ruff
