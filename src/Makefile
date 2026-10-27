PYTHON ?= python3

all: test.tf.toml interpreter.tf.toml test.tok

base.tok.toml: base.cf
	$(PYTHON) -m prim tokenize -i $< -o $@

base.tf.toml: base.tok.toml
	$(PYTHON) -m prim compile -i $< -o $@

test.tok.toml: test.cf base.tf.toml
	$(PYTHON) -m prim tokenize -i $< -o $@ -it base.tf.toml

test.tf.toml: test.tok.toml
	$(PYTHON) -m prim compile -i $< -o $@

test.tok: test.tok.toml
	$(PYTHON) -m prim export -i $< -o $@ -s tokens

interpreter.tok.toml: interpreter.cf base.tf.toml
	$(PYTHON) -m prim tokenize -i $< -o $@ -it base.tf.toml

interpreter.tf.toml: interpreter.tok.toml
	$(PYTHON) -m prim compile -i $< -o $@

clean:
	rm -f *.toml
