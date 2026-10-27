"""Small, local TokenForth playground; no optional dependencies."""
import argparse
import contextlib
import io
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import tempfile

from . import compiler
from .artifacts import load_program
from .cpu import Prim
from .assembler import PrimAsm
from .tokens import Token
from .isa import PrimOpcodes as Op, export_tokenforth_opcodes
from .tokenizer import tokenize_document, stringToNumber, scan


class PreviewPaused(Exception):
    """The requested runtime instruction boundary has been reached."""


class PreviewCPU(Prim):
    """Track logical depths without changing the hardware CPU's circular stacks."""
    def __init__(self, memory, limit=20000, steps=None):
        super().__init__(memory)
        self.depth = self.rdepth = 0
        self.remaining = limit
        self.steps = steps
        self.executed = 0
        self.last_instruction = None

    def dpush(self, value):
        if self.depth >= self.DS_SIZE:
            raise ValueError('Datenstack voll (16 Werte)')
        super().dpush(value)
        self.depth += 1

    def dpop(self):
        self.T()
        self.depth -= 1
        return super().dpop()

    def T(self):
        if self.depth < 1:
            raise ValueError('Datenstack leer: Eingabewert fehlt')
        return super().T()

    def N(self):
        if self.depth < 2:
            raise ValueError('Datenstack: mindestens zwei Werte erforderlich')
        return super().N()

    def rpush(self, value):
        if self.rdepth >= self.RS_SIZE:
            raise ValueError('Returnstack voll')
        super().rpush(value)
        self.rdepth += 1

    def rpop(self):
        if not self.rdepth:
            raise ValueError('Returnstack leer')
        self.rdepth -= 1
        return super().rpop()

    def step(self):
        if self.steps is not None and self.executed >= self.steps:
            raise PreviewPaused()
        if self.remaining <= 0:
            raise RuntimeError('Schrittlimit erreicht (20000 Schritte)')
        self.remaining -= 1
        instruction = self.instruction_at_pc()
        result = super().step()
        self.last_instruction = instruction
        self.executed += 1
        return result

    def instruction_at_pc(self):
        pc = self._pc
        opcode = self.read8(pc) & 0x7f
        size = 3 if opcode == Op.PUSH else 2 if opcode == Op.PUSH8 else 1
        data = [self.read8((pc + i) & 0xffff) for i in range(size)]
        try:
            instruction = PrimAsm.disassemble(data, pc)[0][2]
        except (KeyError, IndexError):
            instruction = 'DATA'
        return {'address': pc, 'bytes': data, 'instruction': instruction, 'labels': [],
                'source': self.source_lookup(pc) if hasattr(self, 'source_lookup') else None}

    def values(self):
        return [self._ds[(self._dsp - self.depth + 1 + i) % self.DS_SIZE]
                for i in range(self.depth)]


class PreviewMemory(compiler.Mif):
    def __init__(self, initial=None):
        super().__init__(initial)
        self.output = bytearray()

    def write8(self, address, value):
        if address & 0xffff == 0xffff:
            self.output.append(value & 255)
        else:
            super().write8(address, value)


def preview(source, stack='', library=None, steps=None, tokens=None):
    # The existing compiler prints dictionary diagnostics; keep HTTP use quiet.
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            return _preview(source, stack, library, steps, tokens)
        except (ValueError, RuntimeError) as exc:
            return {'error': str(exc)}


def _preview(source, stack, library, steps, tokens):
    if tokens is not None and (type(tokens) is not int or not 0 <= tokens <= 65536):
        raise ValueError('Ungültige Tokenanzahl (0..65536)')
    if tokens is not None and steps is not None:
        raise ValueError('Token- und CPU-Schritte bitte getrennt wählen')
    if steps is not None and (type(steps) is not int or not 0 <= steps <= 20000):
        raise ValueError("Ungültige Schrittzahl (0..20000)")
    if not isinstance(source, str) or not isinstance(stack, str):
        raise ValueError('Definition und Startstack müssen Text sein')
    document = tokenize_document(source, library, filename='<Editor>')
    old_count = len(library.symbols) if library else 2
    memory = PreviewMemory(document.memory)
    memory.dictionary = compiler.Dictionary(document.symbols, document.string_literals,
                                            document.number_literals)
    if not document.memory:
        compiler.init(memory)
    def seed(cpu):
        for value in stack.split():
            number = stringToNumber(value)
            if number is None:
                raise ValueError(f'Ungültiger Stackwert: {value}')
            cpu.dpush(number)

    compile_cpu = PreviewCPU(memory)
    runtime_cpu = PreviewCPU(memory, steps=steps)
    seed(runtime_cpu)
    start = compiler.HERE_FETCH(memory)
    in_definition = immediate = definition_code = False
    decoded = compiler.decode_tokens(document.tokens)
    error = None
    paused = False
    token_paused = False
    processed_tokens = 0
    next_token = None
    fragments = [f for f in scan(source) if f.kind not in ('whitespace', 'comment', 'line_comment') and f.s.strip()]
    source_map = {}
    current_source = None
    def source_lookup(pc):
        if pc in source_map:
            return source_map[pc]
        # For library code, walk outward to the nearest call originating in the editor.
        for depth in range(runtime_cpu.rdepth):
            return_pc = runtime_cpu._rs[(runtime_cpu._rsp - depth) % runtime_cpu.RS_SIZE]
            if (return_pc - 1) & 0xffff in source_map:
                return source_map[(return_pc - 1) & 0xffff]
        return current_source
    runtime_cpu.source_lookup = source_lookup
    line_offsets = [0]
    for line in source.splitlines(keepends=True):
        line_offsets.append(line_offsets[-1] + len(line))
    ignored = (Token.WHITESPACE, Token.COMMENT_BRACES, Token.COMMENT_BACKSLASH)
    for index, (offset, tag, value) in enumerate(decoded):
        if tag not in ignored:
            fragment = fragments[processed_tokens]
            position = line_offsets[fragment.linenum - 1] + fragment.column - 1
            current_source = {'text': fragment.s, 'start': position, 'end': position + len(fragment.s),
                              'line': fragment.linenum, 'column': fragment.column}
            if tokens is not None and processed_tokens >= tokens:
                fragment = fragments[processed_tokens]
                position = sum(len(line) for line in source.splitlines(keepends=True)[:fragment.linenum - 1]) + fragment.column - 1
                token_paused = True
                next_token = {'text': fragment.s, 'start': position, 'end': position + len(fragment.s),
                              'line': fragment.linenum, 'column': fragment.column}
                break
            processed_tokens += 1
        end = decoded[index + 1][0] if index + 1 < len(decoded) else len(document.tokens)
        token = document.tokens[offset:end]
        before_here = compiler.HERE_FETCH(memory)
        try:
            if tag == Token.MODE:
                immediate = value == Token.MODE_IMMEDIATE
                continue
            if tag == Token.DEFINITION:
                if immediate or (in_definition and definition_code):
                    raise ValueError('Neue Definition vor Abschluss der vorherigen Definition')
                in_definition = True
                definition_code = False
            if tag == Token.BUILDIN and not immediate and not in_definition:
                raise ValueError('Unerwartetes ; außerhalb einer Definition')
            if in_definition and tag in (Token.WORD_CALL, Token.WORD_ADDRESS, Token.NUMBER,
                                          Token.MNEMONIC, Token.STRING):
                definition_code = True
            if immediate:
                compiler.interpret([Token.MODE, Token.MODE_IMMEDIATE, *token], compile_cpu)
            elif in_definition or tag in (Token.LIT_NUMBER, Token.LIT_STRING, Token.LIT_ADDRESS):
                compiler.interpret(token, compile_cpu)
            elif tag == Token.STRING:
                compiler.interpret(token, compile_cpu)
                compiler.execute(runtime_cpu, compiler.getPushOps(memory.dictionary.S[-1]))
            else:
                compiler.interpret([Token.MODE, Token.MODE_IMMEDIATE, *token], runtime_cpu)
            for address in range(before_here, compiler.HERE_FETCH(memory)):
                source_map[address] = current_source
            if tag == Token.BUILDIN and not immediate:
                in_definition = False
        except PreviewPaused:
            paused = True
            break
        except (ValueError, RuntimeError) as exc:
            error = str(exc)
            break
    if not paused and not token_paused and error is None and ((in_definition and definition_code) or immediate):
        error = 'Eingabe unvollständig: ' + ('schließendes ] fehlt' if immediate else '; fehlt')
    finish = compiler.HERE_FETCH(memory)
    # Only entries encountered before an error have initialized addresses.
    count = (compiler.Consts.DICT - memory.read16(compiler.Consts.LATEST)) // 2
    entries = [
        {'index': index, 'name': name,
         'address': compiler.fetchFromIndex(memory, index), 'new': index >= old_count}
        for index, name in enumerate(document.symbols[:count])
    ]
    labels = {}
    for entry in entries:
        labels.setdefault(entry['address'], []).append(entry['name'])
    boundaries = sorted({*labels, start, finish})
    disassembly = []
    address = min([start, *labels])
    while address < finish:
        opcode = memory.read8(address) & 0x7f
        size = 3 if opcode == Op.PUSH else 2 if opcode == Op.PUSH8 else 1
        boundary = next((end for end in boundaries if end > address), finish)
        size = min(size, boundary - address)
        is_data = address in memory.dictionary.N or address in memory.dictionary.S
        if address in memory.dictionary.N:
            size = min(2, boundary - address)
        elif address in memory.dictionary.S:
            size = min(1 + memory.read8(address), boundary - address)
        data = list(memory._mem[address:address + size])
        try:
            instruction = 'DATA' if is_data else PrimAsm.disassemble(data, address)[0][2]
        except (KeyError, IndexError):
            instruction = 'DATA'
        if not is_data and opcode in (Op.PUSH, Op.PUSH8) and len(data) == (3 if opcode == Op.PUSH else 2):
            target = data[1] + (data[2] * 256 if len(data) == 3 else 0)
            if target in labels:
                instruction += '  (' + ', '.join(labels[target]) + ')'
        disassembly.append({'address': address, 'bytes': data, 'instruction': instruction,
                            'labels': labels.get(address, []), 'source': source_map.get(address)})
        address += size
    current_instruction = runtime_cpu.instruction_at_pc() if paused else None
    for instruction in (current_instruction, runtime_cpu.last_instruction):
        if instruction is not None:
            instruction['labels'] = labels.get(instruction['address'], [])
            owners = [entry for entry in entries if entry['address'] <= instruction['address'] < finish]
            instruction['word'] = max(owners, key=lambda entry: entry['address'])['name'] if owners else None
    result = {
        'token_paused': token_paused, 'tokens': processed_tokens, 'next_token': next_token,
        'paused': paused, 'steps': runtime_cpu.executed,
        'pc': runtime_cpu._pc if paused else None, 'current_instruction': current_instruction,
        'last_instruction': runtime_cpu.last_instruction,
        'return_stack': [runtime_cpu._rs[(runtime_cpu._rsp - runtime_cpu.rdepth + 1 + i) % runtime_cpu.RS_SIZE]
                         for i in range(runtime_cpu.rdepth)],
        'compiler_stack': compile_cpu.values(), 'stack': runtime_cpu.values(),
        'here': finish, 'disassembly': [row for row in disassembly if row['address'] >= start],
        'all_disassembly': disassembly,
        'dictionary': entries,
    }
    if error:
        result['error'] = error
    return result


def default_library():
    """Build the repository's base once at startup, without stale build artifacts."""
    source_dir = Path(__file__).resolve().parents[1]
    if not (source_dir / 'bootstrap.cf').is_file():
        raise ValueError('Basisquellen fehlen. Bitte --library <base.tf.toml> angeben.')
    with contextlib.redirect_stdout(io.StringIO()), tempfile.TemporaryDirectory() as directory:
        opcodes = Path(directory) / 'opcodes.cf'
        export_tokenforth_opcodes(opcodes)
        library = None
        for path in (source_dir / 'bootstrap.cf', opcodes, source_dir / 'base.cf'):
            library = compiler.compile_tokens(tokenize_document(
                path.read_text(encoding='utf-8'), library, filename=str(path)))
    return library


class Handler(BaseHTTPRequestHandler):
    library = None

    def do_GET(self):
        if self.path != '/':
            self.send_error(404)
            return
        self.reply(200, Path(__file__).with_name('live.html').read_bytes(), 'text/html; charset=utf-8')

    def do_POST(self):
        if self.path != '/preview':
            self.send_error(404)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 65536:
                raise ValueError('Eingabe zu groß oder leer')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Ungültige Anfrage')
            use_library = data.get('base_words', True)
            if not isinstance(use_library, bool):
                raise ValueError('Basiswörter muss ein boolescher Wert sein')
            result = preview(data.get('source'), data.get('stack', ''),
                             self.library if use_library else None, steps=data.get('steps'), tokens=data.get('tokens'))
        except (ValueError, RuntimeError) as exc:
            result = {'error': str(exc)}
        self.reply(200, json.dumps(result).encode(), 'application/json')

    def reply(self, status, body, content_type):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(description='Lokaler TokenForth Live-Editor')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--library', help='Andere Bibliothek (.tf.toml); Standard: Basisbibliothek')
    args = parser.parse_args(argv)
    try:
        Handler.library = load_program(args.library) if args.library else default_library()
        server = HTTPServer(('127.0.0.1', args.port), Handler)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f'TokenForth Live: http://127.0.0.1:{server.server_port} (Ctrl+C beendet)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
