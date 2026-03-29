SHELL := /bin/bash

.PHONY: sync install clean test test-unit-tests test-doctest build ty ruff type_check lint pre_commit format

sync:
	uv sync --all-extras

install:
	uv run src/onair_monitor/monitor.py --install-autostart

install_service:
	uv run src/onair_monitor/monitor.py --install-service


clean:
	rm -rf dist
	rm -rf .artifacts
	rm -rf .mypy_cache
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +


test: test-unit-tests test-doctest

test-unit-tests:
	uv run --no-sources pytest tests

test-doctest:
	uv run --no-sources pytest src

build:
	uv build

ty:
	uv run ty check

ruff:
	uv run --no-sources ruff format --target-version py312 src tests
	uv run --no-sources ruff check --fix --exit-non-zero-on-fix src tests

type_check: ty

lint: ruff type_check

pre_commit:
	pre-commit run --all-files

format:
	# format all code
	uv run ruff format
