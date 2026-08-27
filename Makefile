# Makefile

usage:
	@echo "usage:"
	@echo "\tmake build"
	@echo "\tmake test"
	@echo "\tmake test-only"
	@echo "\tmake test-plus"
	@echo "\tmake local-dev"

build:
	@echo "***************************************************************************"
	@echo "*** uv build"
	@echo "***************************************************************************"
	PYTHONWARNINGS=error uv build

test:
	@echo "***************************************************************************"
	@echo "*** Running coverage tests and collect the coverage data"
	@echo "***************************************************************************"
	uv run coverage run -m pytest -vs tests/

	@echo "\n"
	@echo "## Create an HTML report of the coverage of the files"
	uv run coverage html

	@echo "\n"
	@echo "## Report coverage statistics on modules"
	uv run coverage report -m

test-only:
	@echo "***************************************************************************"
	@echo "*** Install test dependency-group ONLY"
	@echo "***************************************************************************"
	uv sync --no-install-project --only-group test

test-plus:
	@echo "***************************************************************************"
	@echo "*** Install dependency-groups for CICD"
	@echo "***************************************************************************"
	uv sync --no-install-project --only-group test --only-group security

local-dev:
	@echo "***************************************************************************"
	@echo "*** Install all dependencies"
	@echo "***************************************************************************"
	uv sync --all-groups

.PHONY: help build test local-dev test-only test-plus
