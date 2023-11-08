test.tok: test.cf base
	python3 tokenizer.py -i $< -o $@ -d base.bin.sym

test.bin: test.tok base.bin base.tok.sym
	python3 tokenforth.py -i $< -o $@ -d base.tok.sym -g base.bin

base: base.bin

base.tok: base.cf
	python3 tokenizer.py -i $< -o $@

base.bin: base.tok
	python3 tokenforth.py -i $< -o $@ -d base.tok.sym

clean:
	rm -f *.bin *.tok *.toml *.sym
