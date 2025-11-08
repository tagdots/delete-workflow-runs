# Makefile

usage:
	@echo "usage:"
	@echo "\tmake build"
	@echo "\tmake test"
	@echo "\tmake test-install"

build:
	@echo "***************************************************************************"
	@echo "*** Upgrade to the latest python build"
	@echo "***************************************************************************"
	python -m pip install -U uv
	python -m uv pip install -U pip
	python -m uv pip install -U build

	@echo "\n"
	@echo "***************************************************************************"
	@echo "*** Build software package"
	@echo "***************************************************************************"
	PYTHONWARNINGS=error python -m build

	@echo "\n"
	@echo "***************************************************************************"
	@echo "*** Install package into the current active Python environment"
	@echo "***************************************************************************"
	python -m uv pip install -e .

test:
	@echo "***************************************************************************"
	@echo "*** Running coverage tests"
	@echo "***************************************************************************"
	coverage run

	@echo "\n"
	@echo "## Create an HTML report of the coverage of the files"
	coverage html

	@echo "\n"
	@echo "## Report coverage statistics on modules"
	coverage report

test-install:
	@echo "***************************************************************************"
	@echo "*** Install test dependencies into current active Python env"
	@echo "***************************************************************************"
	python -m pip install -U uv
	python -m uv pip install -U pip
	python -m uv pip install -e .[test]

.PHONY: help build test test-install
