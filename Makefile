# Project entrypoint. Hardware actions are explicit targets, never default goals.
.DEFAULT_GOAL := help
.DELETE_ON_ERROR:
ROOT := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
-include $(ROOT)/config.local.mk

PYTHON ?= $(ROOT)/.venv/bin/python
SYSTEM_PYTHON ?= python3
CMAKE ?= cmake
CTEST ?= ctest
BOARD ?= olimex_ice40hx8k_evb
BUILD_DIR ?= $(ROOT)/build
SRC_BUILD_DIR ?= $(BUILD_DIR)/src
SOFTWARE_DIR ?= $(BUILD_DIR)/software
SIM_BUILD_DIR ?= $(BUILD_DIR)/sim
FPGA_BUILD_DIR ?= $(BUILD_DIR)/$(BOARD)
PROGRAM ?= $(ROOT)/src/examples/hello.cf
ASM ?= $(ROOT)/cpu/tests/test.asm
IMAGE ?= $(SOFTWARE_DIR)/$(basename $(notdir $(PROGRAM))).bin
ASM_IMAGE ?= $(SOFTWARE_DIR)/$(basename $(notdir $(ASM))).asm.bin
PORT ?=
TIMEOUT ?= 2
SKIP_UART_MMIO ?= 0
VERIFY ?= 0
WRITE_DELAY ?= 0
ICEPROG_DEVICE ?=
ICEPROG_INTERFACE ?= A
JOBS ?= 2
TEST_ARGS ?=

# Quote paths/values as shell data, including single quotes and shell metacharacters.
shq = '$(subst ','"'"',$(1))'
PYTHON_EXEC = $(if $(findstring /,$(PYTHON)),$(abspath $(PYTHON)),$(PYTHON))
SRC_OUT := $(abspath $(SRC_BUILD_DIR))
SW_OUT := $(abspath $(SOFTWARE_DIR))
SIM_OUT := $(abspath $(SIM_BUILD_DIR))
FPGA_OUT := $(abspath $(FPGA_BUILD_DIR))
PROGRAM_SOURCE := $(abspath $(PROGRAM))
ASM_SOURCE := $(abspath $(ASM))
IMAGE_FILE := $(abspath $(IMAGE))
ASM_FILE := $(abspath $(ASM_IMAGE))
PROGRAM_NAME := $(basename $(notdir $(PROGRAM)))
ASM_NAME := $(basename $(notdir $(ASM)))
TOKENS := $(SW_OUT)/$(PROGRAM_NAME).tok.toml
COMPILED := $(SW_OUT)/$(PROGRAM_NAME).tf.toml
PROGRAM_IMAGE := $(SW_OUT)/$(PROGRAM_NAME).bin
BASE := $(SRC_OUT)/base.tf.toml
HOST = $(ROOT)/boards/$(BOARD)/host.py
TOOL_SOURCES := $(wildcard $(ROOT)/src/prim/*.py) $(ROOT)/pyproject.toml $(ROOT)/Makefile
SKIP_FLAG = $(if $(filter 1,$(SKIP_UART_MMIO)),--skip-uart-mmio,)
VERIFY_FLAG = $(if $(filter 1,$(VERIFY)),--verify,)
HOST_COMMAND = $(call shq,$(PYTHON_EXEC)) $(call shq,$(HOST)) --port $(call shq,$(PORT)) --timeout $(call shq,$(TIMEOUT))

.PHONY: help all setup check-tools check-python check-board check-port check-image check-skip check-verify \
 software base image _image asm disasm configure-fpga bitstream flash resources \
 configure-sim sim test test-python test-rtl test-makefile status uart-status halt stop \
 run step reset-halt pc sram-check upload load-run uart-console console-help clean FORCE

help:
	@printf '%s\n' \
	 'Prim project targets (default: this help; no build or hardware access)' \
	 '  all            Build software, selected image and bitstream; no hardware I/O' \
	 '  setup          Create .venv using setup.sh, then install pyserial' \
	 '  check-tools    Check Python packages and software/FPGA tools' \
	 '  software       Build existing src/Makefile outputs' \
	 '  base           Build bootstrap, opcode words and base library' \
	 '  image          Compile PROGRAM=.cf and export its 64-KiB CPU memory image' \
	 '  asm            Assemble ASM=.asm into ASM_IMAGE' \
	 '  disasm         Disassemble the raw binary selected by IMAGE' \
	 '  bitstream      Configure/build the board bitstream; enforce timing' \
	 '  flash          Build if needed, then erase/program/verify FPGA SPI flash' \
	 '  resources      Build if needed and show synthesized/routed resource usage' \
	 '  sim            Configure/build the standalone CPU simulator' \
	 '  test           Run Python checks and all CTest suites' \
	 '  test-python    Run src/ Python and shared test-helper checks' \
	 '  test-rtl       Build simulator and run CTest (optional TEST_ARGS)' \
	 '  test-makefile  Run isolated top-level Makefile workflow tests' \
	 '  status uart-status halt stop run step reset-halt pc sram-check' \
	 '                 Run one CPU/debug operation; requires PORT' \
	 '  upload         Load existing IMAGE; optional VERIFY=1; leave CPU halted' \
	 '  load-run       Build PROGRAM image, load and RUN; optional VERIFY=1' \
	 '  uart-console   Continuous CPU/debug console; requires PORT' \
	 '  console-help   All console commands/keybindings; no port needed' \
	 '  clean          Remove the four managed build trees; preserve .venv/source' \
	 '' \
	 'Variables: PYTHON BOARD PROGRAM ASM IMAGE ASM_IMAGE PORT TIMEOUT JOBS' \
	 '  SKIP_UART_MMIO=1 explicitly omits/reports FFFE/FFFF while loading' \
	 '  VERIFY=1 enables optional readback verification after loading' \
	 '  WRITE_DELAY=0.001 inserts a 1-ms pause between streamed word writes' \
	 '  ICEPROG_DEVICE and ICEPROG_INTERFACE select the programmer (not PORT)' \
	 '  BUILD_DIR SRC_BUILD_DIR SOFTWARE_DIR SIM_BUILD_DIR FPGA_BUILD_DIR' \
	 'Optional local settings: config.local.mk (not tracked)' \
	 '' \
	 'Examples:' \
	 '  make image PROGRAM=src/examples/hello.cf' \
	 '  make flash' \
	 '  make upload IMAGE=program.bin PORT=/dev/serial/by-id/your-uart' \
	 '  make load-run PORT=/dev/serial/by-id/your-uart SKIP_UART_MMIO=1' \
	 '  make uart-console PORT=/dev/serial/by-id/your-uart'

all: software image bitstream

setup:
	bash $(call shq,$(ROOT)/setup.sh)
	$(call shq,$(ROOT)/.venv/bin/python) -m pip install pyserial

check-python:
	@$(call shq,$(PYTHON_EXEC)) -c 'import prim.artifacts' || { printf '%s\n' 'Install the project first: make setup (or select an installed PYTHON).' >&2; exit 1; }

check-tools:
	$(call shq,$(SYSTEM_PYTHON)) $(call shq,$(ROOT)/tools/project.py) check-tools --python $(call shq,$(PYTHON_EXEC)) \
	 --tools $(call shq,$(CMAKE)) $(call shq,$(CTEST)) $(call shq,$(MAKE)) c++ verilator iverilog vvp yosys nextpnr-ice40 icepack iceprog

check-board:
	@test $(call shq,$(BOARD)) = olimex_ice40hx8k_evb || { printf '%s\n' $(call shq,Unsupported BOARD=$(BOARD); supported: olimex_ice40hx8k_evb) >&2; exit 1; }

check-port:
	@test -n $(call shq,$(strip $(PORT))) || { printf '%s\n' 'PORT is required; use the separate USB-UART adapter, e.g. PORT=/dev/serial/by-id/your-uart.' >&2; exit 1; }

check-skip:
	@case $(call shq,$(SKIP_UART_MMIO)) in 0|1) ;; *) printf '%s\n' 'SKIP_UART_MMIO must be 0 or 1.' >&2; exit 1;; esac

check-verify:
	@case $(call shq,$(VERIFY)) in 0|1) ;; *) printf '%s\n' 'VERIFY must be 0 or 1.' >&2; exit 1;; esac

check-image:
	@test -f $(call shq,$(IMAGE_FILE)) || { printf '%s\n' $(call shq,Image not found: $(IMAGE_FILE); run make image or specify IMAGE.) >&2; exit 1; }

base: check-python
	$(MAKE) --no-print-directory -C $(call shq,$(ROOT)/src) PYTHON=$(call shq,$(PYTHON_EXEC)) OUT_DIR=$(call shq,$(SRC_OUT)) base.tf.toml

software: base
	$(MAKE) --no-print-directory -C $(call shq,$(ROOT)/src) PYTHON=$(call shq,$(PYTHON_EXEC)) OUT_DIR=$(call shq,$(SRC_OUT)) all

# src/Makefile owns the base graph. Re-enter after it completes so timestamps
# are evaluated against the freshly built base, without recompiling unchanged inputs.
image: base
	$(MAKE) --no-print-directory -f $(call shq,$(ROOT)/Makefile) _image

_image: $(PROGRAM_IMAGE)

# A missing base can also be handled during make -n / direct file-target builds.
$(BASE):
	$(MAKE) --no-print-directory -C $(call shq,$(ROOT)/src) PYTHON=$(call shq,$(PYTHON_EXEC)) OUT_DIR=$(call shq,$(SRC_OUT)) base.tf.toml

# Track source identity, not just basename/mtime: PROGRAM may switch between
# two older files of the same name. Unchanged selection preserves timestamps.
$(SW_OUT)/.$(PROGRAM_NAME).source: FORCE
	@mkdir -p $(call shq,$(SW_OUT))
	@printf '%s\n' $(call shq,$(PROGRAM_SOURCE)) | cmp -s - $(call shq,$@) || printf '%s\n' $(call shq,$(PROGRAM_SOURCE)) > $(call shq,$@)

$(TOKENS): $(PROGRAM_SOURCE) $(BASE) $(TOOL_SOURCES) $(SW_OUT)/.$(PROGRAM_NAME).source
	@mkdir -p $(call shq,$(SW_OUT))
	$(call shq,$(PYTHON_EXEC)) -m prim tokenize -i $(call shq,$(PROGRAM_SOURCE)) -it $(call shq,$(BASE)) -o $(call shq,$@)

$(COMPILED): $(TOKENS) $(TOOL_SOURCES)
	$(call shq,$(PYTHON_EXEC)) -m prim compile -i $(call shq,$<) -o $(call shq,$@)

$(PROGRAM_IMAGE): $(COMPILED) $(TOOL_SOURCES)
	@mkdir -p $(call shq,$(@D))
	$(call shq,$(PYTHON_EXEC)) -m prim export -i $(call shq,$<) -s memory -o $(call shq,$@)

$(SW_OUT)/.$(ASM_NAME).asm-source: FORCE
	@mkdir -p $(call shq,$(SW_OUT))
	@printf '%s\n' $(call shq,$(ASM_SOURCE)) | cmp -s - $(call shq,$@) || printf '%s\n' $(call shq,$(ASM_SOURCE)) > $(call shq,$@)

asm: check-python $(ASM_FILE)

$(ASM_FILE): $(ASM_SOURCE) $(TOOL_SOURCES) $(SW_OUT)/.$(ASM_NAME).asm-source
	@mkdir -p $(call shq,$(@D))
	$(call shq,$(PYTHON_EXEC)) -m prim asm -i $(call shq,$(ASM_SOURCE)) -o $(call shq,$@)

disasm: check-python check-image
	$(call shq,$(PYTHON_EXEC)) -m prim asm -d $(call shq,$(IMAGE_FILE))

configure-fpga: check-python check-board
	$(call shq,$(CMAKE)) -S $(call shq,$(ROOT)) -B $(call shq,$(FPGA_OUT)) \
	 -DPython3_EXECUTABLE=$(call shq,$(PYTHON_EXEC)) \
	 -DOLIMEX_ICEPROG_DEVICE=$(call shq,$(ICEPROG_DEVICE)) -DOLIMEX_ICEPROG_INTERFACE=$(call shq,$(ICEPROG_INTERFACE))

bitstream: configure-fpga
	$(call shq,$(CMAKE)) --build $(call shq,$(FPGA_OUT)) --target fpga_bitstream --parallel $(call shq,$(JOBS))

flash: configure-fpga
	$(call shq,$(CMAKE)) --build $(call shq,$(FPGA_OUT)) --target fpga_program --parallel $(call shq,$(JOBS))

resources: bitstream
	$(call shq,$(SYSTEM_PYTHON)) $(call shq,$(ROOT)/tools/project.py) resources --build-dir $(call shq,$(FPGA_OUT))

configure-sim: check-python
	$(call shq,$(CMAKE)) -S $(call shq,$(ROOT)) -B $(call shq,$(SIM_OUT)) -DPython3_EXECUTABLE=$(call shq,$(PYTHON_EXEC))

sim: configure-sim
	$(call shq,$(CMAKE)) --build $(call shq,$(SIM_OUT)) --target simulator --parallel $(call shq,$(JOBS))

test: test-python test-rtl

test-python: check-python
	$(call shq,$(PYTHON_EXEC)) -m unittest discover -s $(call shq,$(ROOT)/src) -p 'test*.py'
	$(call shq,$(PYTHON_EXEC)) -m unittest discover -s $(call shq,$(ROOT)/tests) -p 'test*.py'

test-rtl: sim
	$(call shq,$(CTEST)) --test-dir $(call shq,$(SIM_OUT)) --output-on-failure $(TEST_ARGS)

test-makefile: check-python
	$(call shq,$(PYTHON_EXEC)) $(call shq,$(ROOT)/tests/test_makefile.py)

status uart-status halt run step reset-halt pc sram-check uart-console: check-port check-python check-board
	$(HOST_COMMAND) $(if $(filter uart-console,$@),console,$@)

stop: halt

console-help: check-python check-board
	$(call shq,$(PYTHON_EXEC)) $(call shq,$(HOST)) console --help

upload: check-port check-python check-board check-image check-skip check-verify
	$(HOST_COMMAND) load $(call shq,$(IMAGE_FILE)) $(SKIP_FLAG) $(VERIFY_FLAG) --write-delay $(call shq,$(WRITE_DELAY))

load-run: check-port check-python check-board check-skip check-verify
	$(MAKE) --no-print-directory -f $(call shq,$(ROOT)/Makefile) image
	$(HOST_COMMAND) load $(call shq,$(PROGRAM_IMAGE)) $(SKIP_FLAG) $(VERIFY_FLAG) --write-delay $(call shq,$(WRITE_DELAY)) --run

clean:
	$(call shq,$(SYSTEM_PYTHON)) $(call shq,$(ROOT)/tools/project.py) clean \
	 $(call shq,$(SRC_OUT)) $(call shq,$(SW_OUT)) $(call shq,$(SIM_OUT)) $(call shq,$(FPGA_OUT))

FORCE:
