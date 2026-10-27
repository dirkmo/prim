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
from .tokenizer import tokenize_document, stringToNumber


class PreviewCPU(Prim):
    """Track logical depths without changing the hardware CPU's circular stacks."""
    def __init__(self, memory, limit=20000):
        super().__init__(memory)
        self.depth = self.rdepth = 0
        self.remaining = limit

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
        if self.remaining <= 0:
            raise RuntimeError('Schrittlimit erreicht (20000 Schritte)')
        self.remaining -= 1
        return super().step()

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


def preview(source, stack='', library=None):
    # The existing compiler prints dictionary diagnostics; keep HTTP use quiet.
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            return _preview(source, stack, library)
        except (ValueError, RuntimeError) as exc:
            return {'error': str(exc)}


def _preview(source, stack, library):
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
    runtime_cpu = PreviewCPU(memory)
    seed(runtime_cpu)
    start = compiler.HERE_FETCH(memory)
    in_definition = immediate = definition_code = False
    decoded = compiler.decode_tokens(document.tokens)
    error = None
    for index, (offset, tag, value) in enumerate(decoded):
        end = decoded[index + 1][0] if index + 1 < len(decoded) else len(document.tokens)
        token = document.tokens[offset:end]
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
                runtime_cpu.dpush(memory.dictionary.S[-1])
            else:
                compiler.interpret([Token.MODE, Token.MODE_IMMEDIATE, *token], runtime_cpu)
            if tag == Token.BUILDIN and not immediate:
                in_definition = False
        except (ValueError, RuntimeError) as exc:
            error = str(exc)
            break
    if error is None and ((in_definition and definition_code) or immediate):
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
                            'labels': labels.get(address, [])})
        address += size
    result = {
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
                             self.library if use_library else None)
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
