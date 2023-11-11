all: test.tf.toml interpreter.tf.toml test.tok

base.tok.toml: base.cf
	python3 tokenizer.py -i $< -o $@

base.tf.toml: base.tok.toml
	python3 tokenforth.py -i $< -o $@

test.tok.toml: test.cf base.tf.toml
	python3 tokenizer.py -i $< -o $@ -it base.tf.toml

test.tf.toml: test.tok.toml
	python3 tokenforth.py -i $< -o $@

test.tok: test.tok.toml
	python3 binexport.py -i $< -o $@ -s tokens

interpreter.tok.toml: interpreter.cf base.tf.toml
	python3 tokenizer.py -i $< -o $@ -it base.tf.toml

interpreter.tf.toml: interpreter.tok.toml
	python3 tokenforth.py -i $< -o $@

clean:
	rm -f *.toml
