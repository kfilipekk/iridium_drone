# Top-level Makefile for NAVCORE-SoOP
#
# Standard entry points for verification, firmware build, and simulation workflows.

SHELL     := /bin/bash
PY        ?= python3
APVENV_PY := $(HOME)/.cache/navcore/apvenv/bin/python3

.PHONY: all help check preflight test-soop arm-soop sitl-check doc-check sitl-run clean

all: help

help:
	@echo "NAVCORE-SoOP Build & Verification Targets:"
	@echo "  make check          - Run full preflight verification suite"
	@echo "  make test-soop      - Build and run host C tests for Doppler solver & SGP4"
	@echo "  make arm-soop       - Cross-compile Doppler solver & SGP4 for STM32H743"
	@echo "  make sitl-check     - Validate SITL scenario results against shipped parameters"
	@echo "  make doc-check      - Verify doc figures, links, and generated tables"
	@echo "  make sitl-run       - Execute full 21-scenario SITL suite in ArduCopter (~50 min)"
	@echo "  make clean          - Clean compiled build artifacts"

check: preflight

preflight:
	$(PY) tools/preflight.py

test-soop:
	cd firmware/soop && $(MAKE) host
	$(PY) tools/check_soop_sgp4.py
	$(PY) tools/check_soop_c.py

arm-soop:
	cd firmware/soop && $(MAKE) arm

sitl-check:
	$(PY) tools/check_sitl.py

doc-check:
	$(PY) tools/check_doc_figures.py
	$(PY) tools/check_links.py
	$(PY) tools/gen_doc_tables.py --check

sitl-run:
	nice -n 10 bash sitl/run_scenarios.sh
	$(PY) tools/check_sitl.py --record

clean:
	cd firmware/soop && $(MAKE) clean
