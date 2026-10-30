"""Compile ordered TokenForth sources into one CPU memory image."""
import argparse
import contextlib
import io
from pathlib import Path
import tempfile

from .artifacts import export_section, save
from .compiler import compile_tokens, DEFAULT_MAX_IMMEDIATE_STEPS
from .isa import export_tokenforth_opcodes
from .tokenizer import tokenize_document


def build_files(filenames, *, base=True,
                max_immediate_steps=DEFAULT_MAX_IMMEDIATE_STEPS):
    """Carry each file's compiled dictionary and memory into the next file."""
    sources = [Path(filename) for filename in filenames]
    if not sources:
        raise ValueError('At least one .cf source is required')
    for source in sources:
        if source.suffix != '.cf':
            raise ValueError(f'Expected a .cf source: {source}')
    library = None

    def compile_file(source):
        nonlocal library
        document = tokenize_document(source.read_text(encoding='utf-8'),
                                     library, filename=str(source))
        library = compile_tokens(document, max_immediate_steps=max_immediate_steps,
                                 filename=str(source))

    # The compiler's dictionary diagnostics are not build output.
    with contextlib.redirect_stdout(io.StringIO()), tempfile.TemporaryDirectory() as directory:
        if base:
            source_dir = Path(__file__).resolve().parents[1]
            for name in ('bootstrap.cf', 'base.cf'):
                if not (source_dir / name).is_file():
                    raise ValueError('Base sources are missing; run from an editable '
                                     'repository install or use --no-base')
            opcodes = Path(directory) / 'opcodes.cf'
            export_tokenforth_opcodes(opcodes)
            for source in (source_dir / 'bootstrap.cf', opcodes, source_dir / 'base.cf'):
                compile_file(source)
        for source in sources:
            compile_file(source)
    return library


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sources', nargs='+', type=Path,
                        help='.cf files in dependency order')
    parser.add_argument('-o', '--output', type=Path,
                        help='Binary image (default: build/software/<last source>.bin)')
    parser.add_argument('--no-base', action='store_true',
                        help='Skip bootstrap, generated opcode words and base.cf')
    parser.add_argument('--toml', type=Path,
                        help='Also save the compiled image and dictionary for the debugger')
    parser.add_argument('--max-immediate-steps', type=int,
                        default=DEFAULT_MAX_IMMEDIATE_STEPS,
                        help='Maximum CPU steps per immediate execution (default: 100000)')
    args = parser.parse_args(argv)
    output = args.output or Path('build/software') / (args.sources[-1].stem + '.bin')
    try:
        if args.max_immediate_steps < 1:
            raise ValueError('--max-immediate-steps must be positive')
        destinations = [output] + ([args.toml] if args.toml else [])
        protected = {source.resolve() for source in args.sources}
        source_dir = Path(__file__).resolve().parents[1]
        protected.update((source_dir / name).resolve() for name in ('bootstrap.cf', 'base.cf'))
        if any(path.resolve() in protected for path in destinations):
            raise ValueError('Output must not overwrite a source file')
        if args.toml and args.toml.resolve() == output.resolve():
            raise ValueError('Binary and TOML outputs must use different paths')
        image = build_files(args.sources, base=not args.no_base,
                            max_immediate_steps=args.max_immediate_steps)
        for path in destinations:
            path.parent.mkdir(parents=True, exist_ok=True)
        export_section(image, 'memory', output)
        if args.toml:
            save(image, args.toml)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    print(f'Built {output} ({len(image.memory)} bytes)')


if __name__ == '__main__':
    main()
