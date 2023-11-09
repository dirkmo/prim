all: test.tf.toml

base.tok.toml: base.cf
	python3 tokenizer.py -i $< -o $@

base.tf.toml: base.tok.toml
	python3 tokenforth.py -i $< -o $@

test.tok.toml: test.cf base.tf.toml
	python3 tokenizer.py -i $< -o $@ -it base.tf.toml

test.tf.toml: test.tok.toml
	python3 tokenforth.py -i $< -o $@

clean:
	rm -f *.toml
