PYTHON ?= python3
OUT_DIR ?= ../build/src

# Include shared modules so compiler/tokenizer changes cannot leave stale images.
TOOL_SOURCES := $(wildcard prim/*.py) ../pyproject.toml Makefile
OUTPUT_NAMES := base.tok.toml base.tf.toml test.tok.toml test.tf.toml test.tok interpreter.tok.toml interpreter.tf.toml
OUTPUTS := $(addprefix $(OUT_DIR)/,$(OUTPUT_NAMES))

.PHONY: all clean $(OUTPUT_NAMES)
.DELETE_ON_ERROR:

all: $(OUT_DIR)/test.tf.toml $(OUT_DIR)/interpreter.tf.toml $(OUT_DIR)/test.tok

# Keep convenient targets such as `make base.tf.toml`.
$(OUTPUT_NAMES): %: $(OUT_DIR)/%

$(OUT_DIR):
	mkdir -p "$@"

$(OUT_DIR)/base.tok.toml: base.cf $(TOOL_SOURCES) | $(OUT_DIR)
	$(PYTHON) -m prim tokenize -i $< -o $@

$(OUT_DIR)/base.tf.toml: $(OUT_DIR)/base.tok.toml $(TOOL_SOURCES) | $(OUT_DIR)
	$(PYTHON) -m prim compile -i $< -o $@

$(OUT_DIR)/test.tok.toml: test.cf $(OUT_DIR)/base.tf.toml $(TOOL_SOURCES) | $(OUT_DIR)
	$(PYTHON) -m prim tokenize -i $< -o $@ -it $(OUT_DIR)/base.tf.toml

$(OUT_DIR)/test.tf.toml: $(OUT_DIR)/test.tok.toml $(TOOL_SOURCES) | $(OUT_DIR)
	$(PYTHON) -m prim compile -i $< -o $@

$(OUT_DIR)/test.tok: $(OUT_DIR)/test.tok.toml $(TOOL_SOURCES) | $(OUT_DIR)
	$(PYTHON) -m prim export -i $< -o $@ -s tokens

$(OUT_DIR)/interpreter.tok.toml: interpreter.cf $(OUT_DIR)/base.tf.toml $(TOOL_SOURCES) | $(OUT_DIR)
	$(PYTHON) -m prim tokenize -i $< -o $@ -it $(OUT_DIR)/base.tf.toml

$(OUT_DIR)/interpreter.tf.toml: $(OUT_DIR)/interpreter.tok.toml $(TOOL_SOURCES) | $(OUT_DIR)
	$(PYTHON) -m prim compile -i $< -o $@

clean:
	$(RM) $(OUTPUTS)
