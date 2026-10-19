#top-level Makefile for NAVCORE-SoOP

SHELL     := /bin/bash
PY        ?= python3
APVENV_PY := $(HOME)/.cache/navcore/apvenv/bin/python3
export KICAD_TOOLS ?= $(HOME)/Code/kicad-tools
KT        := $(PY) $(KICAD_TOOLS)

.PHONY: all help check preflight test-soop arm-soop sitl-check doc-check sitl-run bundle renders step clean

all: help

help:
	@echo "NAVCORE-SoOP Build & Verification Targets:"
	@echo "  make check          - Run full preflight verification suite"
	@echo "  make test-soop      - Build and run host C tests for Doppler solver & SGP4"
	@echo "  make arm-soop       - Cross-compile Doppler solver & SGP4 for STM32H743"
	@echo "  make sitl-check     - Validate SITL scenario results against shipped parameters"
	@echo "  make doc-check      - Verify doc figures, links, and generated tables"
	@echo "  make sitl-run       - Execute full 21-scenario SITL suite in ArduCopter (~50 min)"
	@echo "  make bundle         - Rebuild gerbers, BOM/CPL and the JLCPCB order bundle"
	@echo "  make renders        - Re-render the tracked board pictures and the pad map"
	@echo "  make step           - Export the board to STEP and GLB with every model"
	@echo "  make clean          - Clean compiled build artifacts"

check: preflight

preflight:
	$(PY) tools/preflight.py

test-soop:
	cd firmware/soop && $(MAKE) host
	$(PY) tools/check_soop.py sgp4
	$(PY) tools/check_soop.py solver
	$(PY) tools/check_soop.py dsp
	$(PY) tools/check_soop.py nav

arm-soop:
	cd firmware/soop && $(MAKE) arm

sitl-check:
	$(PY) tools/check_firmware.py sitl

doc-check:
	$(PY) tools/check_order.py doc_figures
	$(PY) tools/check_order.py links
	$(PY) tools/gen_doc_tables.py --check

sitl-run:
	nice -n 10 bash sitl/run_scenarios.sh
	$(PY) tools/check_firmware.py sitl --record

bundle:
	$(KT)/fab.py bundle

renders:
	$(KT)/fab.py render
	$(PY) tools/gen_padmap.py

step:
	$(KT)/fab.py export

clean:
	cd firmware/soop && $(MAKE) clean
