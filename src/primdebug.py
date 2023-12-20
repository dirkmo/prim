#! /usr/bin/env python3

import argparse
from blessed import Terminal
from prim import *
from primasm import *
from primconsts import *
import signal
import sys
import toml
import tomlfix

# TODO
# - step back


class Mif(MemoryIf):
    def __init__(self, init=None, tx=None, uart_rx_init=None):
        self._mem = bytearray(0x10000)
        self._resetmem = None
        self._tx = tx
        self.uart_fifo_rx = []
        if init is not None:
            l = len(init)
            self._mem[0:l] = init
            self._resetmem = bytearray(self._mem)
        if uart_rx_init:
            self.uart_fifo_rx = list(uart_rx_init)

    def reset(self):
        if self._resetmem is not None:
            self._mem = bytearray(self._resetmem)

    def read8(self, addr):
        addr &= 0xffff
        if addr == 0xfffe:
            return len(self.uart_fifo_rx) > 0
        elif addr == 0xffff:
            return self.uart_fifo_rx.pop(0) if len(self.uart_fifo_rx) else 0
        return self._mem[addr]

    def read16(self, addr):
        return self.read8(addr) | (self.read8(addr+1) << 8)

    def write8(self, addr, value):
        addr &= 0xffff
        value &= 0xff
        if addr == 0xffff:
            if self._tx is not None:
                self._tx(value)
        else:
            self._mem[addr] = int(value)

    def write16(self, addr, value):
        self.write8(addr, value & 0xff)
        self.write8(addr+1, (value >> 8) & 0xff)

    def uart_rx(self, dat):
        self.uart_fifo_rx.append(dat)


class PrimDebug:
    SHOW_CODE = 0
    SHOW_STACKS = 1
    SHOW_MESSAGES = 2
    SHOW_MEMORY = 3
    def __init__(self, cpu, term, symbols=None, numlits=None, strlits=None):
        self.cpu = cpu
        self.cpu._debug = self
        self.term = term
        self.symbolMap = self.genSymbolMap(symbols) # (addr, names) dictionary
        self.symbolNamesDict = dict((name,addr) for addr,name in self.symbolMap.items()) # (name: addr) dictionary
        self.strlits = strlits if strlits is not None else []
        self.numlits = numlits if numlits is not None else []
        self.messages = [] # messages shown in message area
        self.input = "" # user input
        self.breakpoints = set() # active breakpoints
        self.silentBreakpoints = set() # silent breakpoints for step-over
        self.run = False
        self.memViewAddr = 0
        self.memViewHeight = 16
        self.memViewNumBytes = 8
        self.memViewHightlight = set() # addresses being highlighted in memory view
        self.cpu._mif._tx = self.uart_rx_cb
        self.redrawEverything()
        PrimAsm.createLookup()

    def genSymbolMap(self, symbols):
        symbolMap = {}
        mif = self.cpu._mif
        for idx,sym in enumerate(symbols):
            addr = mif.read16(Consts.DICT-idx*2)
            symbolMap[addr] = sym
        return symbolMap

    def uart_rx_cb(self, dat):
        self.appendMessage(f"uart: {chr(dat)} ({dat:02x})")
        self.redraw.add(PrimDebug.SHOW_MESSAGES)

    def generateStackViewStr(self, prefix, stack, sp, stacksize, w):
        w -= len(prefix)
        s = self.term.bold + self.term.underline + f"{stack[sp % stacksize]:x}" + self.term.normal
        for i in range(1, stacksize):
            ns = f"{stack[(sp-i) % stacksize]:x} "
            if self.term.length(ns+s) >= w:
                break
            s = ns + s
        s = prefix + s
        l = self.term.length(s)
        if l < w:
            s += " " * (w - l)
        return s

    def showDataStack(self, x1, x2, y):
        s = self.generateStackViewStr("D: ", self.cpu._ds, self.cpu._dsp, Prim.DS_SIZE, x2 - x1)
        with self.term.location(x=x1, y=y):
            print(s, end="")

    def showReturnStack(self, x1, x2, y):
        s = self.generateStackViewStr("R: ", self.cpu._rs, self.cpu._rsp, Prim.RS_SIZE, x2 - x1)
        with self.term.location(x=x1, y=y):
            print(s, end="")

    def showCurrent(self, x1, x2, y):
        w = x2 - x1 + 1
        pc = self.cpu._pc
        s = f"PC {pc:04x}: {self.disassemble(pc)}"
        l = self.term.length(s)
        if l < w:
            s += " " * (w - l)
        print(self.term.move_xy(x1, y) + s, end='')

    def instructionLength(self, addr):
        ir = self.cpu._mif.read8(addr) & 0x7f
        if ir == PrimOpcodes.PUSH:
            return 3
        elif ir == PrimOpcodes.PUSH8:
            return 2
        return 1

    def addrPrevInstruction(self, addr):
        if addr > 2:
            if self.cpu._mif.read8(addr-3) == PrimOpcodes.PUSH:
                return addr - 3
        if addr > 1:
            if self.cpu._mif.read8(addr-2) == PrimOpcodes.PUSH8:
                return addr - 2
        return addr - 1

    def addrNextInstruction(self, addr):
        return addr + self.instructionLength(addr)

    def addrInStrLiterals(self, addr):
        # falls addr in a string literal range?
        for sladdr in self.strlits:
            if addr < sladdr:
                continue
            # range of string literal (cnt + chars)
            cnt = self.cpu._mif.read8(sladdr) # read string length
            if addr < sladdr + cnt + 1:
                return True
        return False

    def disassemble(self, addr, useSymbols=True):
        if addr in self.numlits:
            return f"LIT #{self.cpu._mif.read16(addr):x}"
        if self.addrInStrLiterals(addr):
            return "STR-LIT"
        opcode = self.cpu._mif.read8(addr)
        (ir, retbit) = (opcode & 0x7f, opcode & 0x80)
        s = PrimAsm.LOOKUP[ir] + (".RET" if retbit else "")
        if ir == PrimOpcodes.PUSH8:
            val = self.cpu._mif.read8(addr+1)
        elif ir == PrimOpcodes.PUSH:
            val = self.cpu._mif.read8(addr+1) | (self.cpu._mif.read8(addr+2) << 8)
        else:
            return s
        if useSymbols:
            nextIr = self.cpu._mif.read8(self.addrNextInstruction(addr)) & 0x7f
            if nextIr in [PrimOpcodes.JP, PrimOpcodes.JZ, PrimOpcodes.CALL, PrimOpcodes.BYTE_FETCH, PrimOpcodes.FETCH, PrimOpcodes.BYTE_STORE, PrimOpcodes.STORE] and val in self.symbolMap:
                s += " " + self.term.magenta(f"'{self.symbolMap[val]}") + f" (${val:x})"
            else:
                s += f" ${val:x}"
        else:
            s += f" ${val:x}"
        return s

    def showCode(self, x1, y1, x2, y2):
        h = y2 - y1 + 1
        w = x2 - x1 + 1
        addr = self.cpu._pc
        linecount = 0
        lines = []
        while addr >= 0 and linecount < h // 2:
            da = f"{addr:04x}:"
            for b in range(self.instructionLength(addr)):
                da += f" {self.cpu._mif.read8(addr + b):02x}"
            da += " " * (16 - len(da))
            da += self.disassemble(addr)
            lines.insert(0, da)
            linecount += 1
            if addr in self.symbolMap:
                lines.insert(0, f"{addr:04x}           " + self.term.red(":" + self.symbolMap[addr]))
                linecount += 1
            addr = self.addrPrevInstruction(addr)
        addr = self.addrNextInstruction(self.cpu._pc)
        while addr < 0x10000 and linecount < h:
            if addr in self.symbolMap:
                lines.append(f"{addr:04x}           " + self.term.red(":" + self.symbolMap[addr]))
                linecount += 1
            da = f"{addr:04x}:"
            for b in range(self.instructionLength(addr)):
                da += f" {self.cpu._mif.read8(addr + b):02x}"
            da += " " * (16 - len(da))
            da += self.disassemble(addr)
            lines.append(da)
            linecount += 1
            addr = self.addrNextInstruction(addr)
        for i,l in enumerate(lines):
            # BUG: l might be to long
            s = self.term.move_xy(x1, y1 + i) + l + " " * (w-self.term.length(l))
            if int(l[0:4],base=16) == self.cpu._pc:
                s = self.term.reverse(s)
            if int(l[0:4],base=16) in self.breakpoints:
                s = self.term.blue(s)
            print(s, end='')

    def showBox(self, x1, y1, x2, y2):
        w = x2 - x1
        print(self.term.move_xy(x1,y1) + "┌", end='')
        print("─" * (w-2) + "┐", end='')
        for y in range(y1+1, y2):
            print(self.term.move_xy(x1, y) + "│", end='')
            print(self.term.move_xy(x2, y) + "│", end='')
        print(self.term.move_xy(x1,y2) + "└", end='')
        print("─" * (w-2) + "┘", end='')
        # ├ ┤ ┬ ┴

    def showPrompt(self, x1, x2, y):
        w = x2 - x1
        prompt = "> " + self.input
        l = len(prompt)
        if l < w:
            prompt += " " * (w - l)
        else:
            prompt = prompt[l-w:]
            l = w
        print(self.term.move_xy(x1, y) + prompt, end='')
        print(self.term.move_xy(x1 + l, y), end='')

    def showHorizontalSplitline(self, x1, x2, y):
        print(self.term.move_xy(x1, y) + "├", end='')
        print("─" * (x2-x1-2) + "┤", end='')

    def showVerticalSplitline(self, x, y1, y2):
        print(self.term.move_xy(x, y1) + "┬", end='')
        for y in range(y1+1, y2):
            print(self.term.move_xy(x, y) + "│", end='')
        print(self.term.move_xy(x, y2) + "┴", end='')

    def showMemory(self, x1, y1, x2, y2):
        w = x2 - x1 + 1
        h = y2 - y1 + 1
        self.memViewAddr -= self.memViewAddr % self.memViewNumBytes # align
        start = max(0, self.memViewAddr)
        if start + h * self.memViewNumBytes > 0xffff:
            start = 0x10000 - h * self.memViewNumBytes
        total = ""
        for y in range(h):
            addr = start + y * self.memViewNumBytes
            s = self.term.move_xy(x1 + 2, y1 + y) + f"{addr:04x}:"
            chars = ""
            for a in range(self.memViewNumBytes):
                byteaddr = addr + a
                val = self.cpu._mif.read8(byteaddr)
                s += " "
                if byteaddr in self.memViewHightlight:
                    s += self.term.black_on_cyan(f"{val:02x}")
                    chars += self.term.black_on_cyan(chr(val) if chr(val).isprintable() else '.')
                else:
                    s += f"{val:02x}"
                    chars += (chr(val) if chr(val).isprintable() else '.')
            s = s + " " + chars
            total += self.term.truncate(s, w-3)
        print(total, end='')
        print(self.term.normal, end='')

    def appendMessage(self, msg=""):
        self.messages.append(msg)
        if len(self.messages) > 200:
            self.messages = self.messages[-200:]

    def showMessageArea(self, x1, y1, x2, y2):
        w = x2 - x1 + 1
        h = y2 - y1 + 1
        start = 0
        num = len(self.messages)
        if num - start > h:
            start = num - h
        for i in range(h):
            if start+i >= num:
                break
            print(self.term.move_xy(x1+2,y1+i) + self.messages[start+i][0:w-3], end='')

    def breakpointCmd(self, cmd):
        l = len(cmd)
        if l == 1:
            self.appendMessage("")
            if len(self.breakpoints) == 0:
                self.appendMessage("No breakpoints set.")
            else:
                self.appendMessage("List of breakpoints:")
                for bp in self.breakpoints:
                    s = f"${bp:x}"
                    if bp in self.symbolMap:
                        s+= " (" + self.symbolMap[bp] + ")"
                    self.appendMessage(s)
        elif l == 2:
            if cmd[1] in self.symbolNamesDict:
                addr = self.symbolNamesDict[cmd[1]]
            else:
                try:
                    addr = int(cmd[1], 16)
                except:
                    self.appendMessage(f"Invalid address ${cmd[1]}")
                    return
            if addr in self.breakpoints:
                self.breakpoints.remove(addr)
                self.appendMessage(f"Removed breakpoint at ${cmd[1]}")
            else:
                self.breakpoints.add(addr)
                self.appendMessage(f"Set breakpoint at ${cmd[1]}")

    def redrawEverything(self):
        self.redraw = set((PrimDebug.SHOW_CODE, PrimDebug.SHOW_STACKS, PrimDebug.SHOW_MESSAGES, PrimDebug.SHOW_MEMORY))

    def show(self):
        x2_code = min(self.term.width // 2, 45)
        code = PrimDebug.SHOW_CODE in self.redraw
        mem = PrimDebug.SHOW_MEMORY in self.redraw
        msgs = PrimDebug.SHOW_MESSAGES in self.redraw
        stacks = PrimDebug.SHOW_STACKS in self.redraw
        if len(self.redraw) == 4:
            print(self.term.clear, end='')
            self.showBox(0, 0, self.term.width, self.term.height-1)
            print(self.term.move_xy(2, 0) + " Prim Debugger ", end='')
            self.showHorizontalSplitline(0, self.term.width, self.term.height - 7)
            self.showVerticalSplitline(x2_code + 1, 0, self.term.height - 7)
            self.showHorizontalSplitline(0, self.term.width, self.term.height - 3)
            self.showHorizontalSplitline(x2_code + 1, self.term.width, 2+self.memViewHeight)
        if code:
            self.showCode(2, 1, x2_code, self.term.height-8)
        if stacks:
            self.showDataStack(2, self.term.width - 2, self.term.height-6)
            self.showReturnStack(2, self.term.width - 2, self.term.height-5)
            self.showCurrent(2, self.term.width - 2, self.term.height-4)
        if mem:
            self.showMemory(x2_code+1, 1, self.term.width-1, 1+self.memViewHeight)
        if msgs:
            self.showMessageArea(x2_code+1, 3+self.memViewHeight, self.term.width -1, self.term.height - 8)
        self.showPrompt(2, self.term.width - 2, self.term.height - 2)
        sys.stdout.flush()
        self.redraw = set()

    def printHelp(self):
        self.appendMessage('Available commands:')
        self.appendMessage()
        self.appendMessage('"break [addr|symbol]"  Set/remove/list breakpoints')
        self.appendMessage('"reset"                Reset CPU and memory')
        self.appendMessage('"run"                  Run program')
        self.appendMessage('"view <addr>"          Set memory view address')
        self.appendMessage('"hl [addr] [len]"      (Un-)highlight range in memory view')
        self.appendMessage('"r <addr> [len]"       Read from memory')
        self.appendMessage('"w <addr> <byte>..."   Write to memory')
        self.appendMessage()
        self.appendMessage('LEFT for single step')
        self.appendMessage('DOWN for step over')
        self.appendMessage('Prim mnemonics for direct execution (like "drop")')
        self.appendMessage('Enter number to push on data stack')
        self.appendMessage()

    def setupMemoryView(self, cmd):
        self.redraw.add(PrimDebug.SHOW_MEMORY)
        if len(cmd) < 2:
            self.appendMessage("Missing address")
            return
        try:
            addr = int(cmd[1], 16)
        except:
            self.appendMessage(f"Invalid address {cmd[1]}")
            return
        self.memViewAddr = addr

    def memoryViewMakeAddrVisible(self, addr):
        # move mem view base address so that addr is visible
        mvl = self.memViewHeight * self.memViewNumBytes
        start = self.memViewAddr
        stop = self.memViewAddr + mvl
        if addr < start or addr >= stop:
            self.memViewAddr = max(0, addr - mvl // 2)

    def highlightMemory(self, cmd):
        self.redraw.add(PrimDebug.SHOW_MEMORY)
        if len(cmd) < 2:
            self.memViewHightlight = set()
            return
        try:
            addr = int(cmd[1], 16)
        except:
            self.appendMessage(f"Invalid address {cmd[1]}")
            return
        cnt = 1
        if len(cmd) == 3:
            try:
                cnt = int(cmd[2], 16)
            except:
                self.appendMessage(f"Invalid length {cmd[2]}")
                return
        for a in range(addr, addr+cnt):
            if a in self.memViewHightlight:
                self.memViewHightlight.remove(a)
            else:
                self.memViewHightlight.add(a)
                if a == addr:
                    self.memoryViewMakeAddrVisible(a)

    def userReadMemoryCmd(self, cmd):
        if len(cmd) < 2:
            self.appendMessage(f"Missing address")
            return
        try:
            addr = int(cmd[1], 16)
        except:
            self.appendMessage(f"Invalid address {cmd[1]}")
            return
        l = 1
        if len(cmd) > 2:
            try:
                l = int(cmd[2], 16)
            except:
                pass
        self.appendMessage(f"Reading {l} bytes from ${addr:x}:")
        s = ""
        for a in range(addr, addr+l):
            val = self.cpu._mif.read8(a)
            s += f"{val:02x} "
        self.appendMessage(s)
        self.appendMessage()

    def userWriteMemoryCmd(self, cmd):
        self.redraw.add(PrimDebug.SHOW_MEMORY)
        if len(cmd) < 3:
            self.appendMessage(f"Missing parameters")
            return
        try:
            addr = int(cmd[1], 16)
        except:
            self.appendMessage(f"Invalid address {cmd[1]}")
            return
        data = []
        for c in cmd[2:]:
            try:
                data.append(int(c, 16))
            except:
                self.appendMessage(f"Invalid hex number {c}")
                return
        waddr = addr
        s = ""
        for d in data:
            s += f"{d:02x} "
            self.cpu._mif.write8(waddr, d)
            waddr += 1
        self.appendMessage(f"Writing to ${addr}:")
        self.appendMessage(f"{s[:-1]}")
        self.appendMessage()

    def userPrimExecute(self, cmd):
        self.redrawEverything()
        count = 0
        for c in cmd:
            try:
                val = int(c, 16)
                self.cpu.dpush(val)
                count += 1
                continue
            except:
                pass
            try:
                opcodes = PrimAsm.assemble(c)
                for op in opcodes:
                    self.cpu.execute(op)
                count += 1
            except:
                pass
        return count > 0

    def uartSendCmd(self, s):
        s = s.strip()
        s = s[s.index(' ')+1:]
        for c in s:
            self.cpu._mif.uart_rx(c)

    def userCommand(self):
        cmd = self.input.strip().split(' ')
        if len(cmd) < 1:
            return
        cmd[0] = cmd[0].lower()
        if cmd[0] == "break":
            self.breakpointCmd(cmd)
            self.redraw.add(PrimDebug.SHOW_CODE)
        elif cmd[0] == "help":
            self.printHelp()
        elif cmd[0] == "run":
            self.run = True
        elif cmd[0] == "reset":
            self.appendMessage("Reset CPU and memory.")
            self.cpu.reset()
            self.cpu._mif.reset()
            self.redrawEverything()
        elif cmd[0] == "view":
            self.setupMemoryView(cmd)
        elif cmd[0] == "hl":
            self.highlightMemory(cmd)
        elif cmd[0] == "r":
            self.userReadMemoryCmd(cmd)
        elif cmd[0] == "w":
            self.userWriteMemoryCmd(cmd)
        elif cmd[0] == "uart":
            self.uartSendCmd(self.input)
        elif self.userPrimExecute(cmd):
            pass
        else:
            self.appendMessage(f'Invalid command "{cmd[0]}"')
        self.redraw.add(PrimDebug.SHOW_MESSAGES)

    def handleInput(self, key):
        if key.code == self.term.KEY_ENTER:
            self.userCommand()
            self.input = ""
        elif key.code == self.term.KEY_BACKSPACE:
            self.input = self.input[0:-1]
        elif not key.is_sequence:
            self.input += key

    def onSilentBreakpoint(self):
        if self.cpu._pc in self.silentBreakpoints:
            self.silentBreakpoints.remove(self.cpu._pc)
            return True
        return False

    def onBreakpoint(self):
        return self.cpu._pc in self.breakpoints

    def debug(self):
        self.appendMessage("Welcome to Prim CPU Debugger.")
        self.appendMessage("")
        self.appendMessage('Type "help" for instructions.')
        self.appendMessage("")
        with self.term.fullscreen(), self.term.cbreak():
            while True:
                while self.run:
                    ir = self.cpu.step()
                    kbhit = self.term.kbhit(0)
                    bp = self.onSilentBreakpoint() or self.onBreakpoint()
                    if kbhit or (ir == PrimOpcodes.BREAK) or bp:
                        if kbhit:
                            self.term.inkey()
                        self.run = False
                        self.redrawEverything()
                        break
                    self.redraw.add(PrimDebug.SHOW_CODE)
                    self.redraw.add(PrimDebug.SHOW_STACKS)
                    self.show()
                self.show()
                key = self.term.inkey()
                if key.code == self.term.KEY_ESCAPE or key == '\x04': # 4: ctrl+d
                    break
                elif key.code == self.term.KEY_RIGHT:
                    self.cpu.step()
                    self.redraw.add(PrimDebug.SHOW_CODE)
                    self.redraw.add(PrimDebug.SHOW_STACKS)
                    self.redraw.add(PrimDebug.SHOW_MEMORY)
                elif key.code == self.term.KEY_DOWN:
                    if self.cpu._mif.read8(self.cpu._pc) == PrimOpcodes.CALL:
                        self.silentBreakpoints.add(self.addrNextInstruction(self.cpu._pc))
                        self.run = True
                    else:
                        self.cpu.step()
                        self.redraw.add(PrimDebug.SHOW_CODE)
                        self.redraw.add(PrimDebug.SHOW_STACKS)
                        self.redraw.add(PrimDebug.SHOW_MEMORY)
                else:
                    self.handleInput(key)


def debug(fn, uartfn):
    tomldata = toml.load(fn)
    tomldata["symbols"] = tomlfix.workaround(tomldata["symbols"])
    term = Terminal()

    try:
        with open(uartfn,"rb") as f:
            uart_data = f.read()
    except:
        uart_data = None

    cpu = Prim(Mif(tomldata["memory"], uart_rx_init=uart_data))
    debug = PrimDebug(cpu, term, tomldata["symbols"], tomldata["num-literals"], tomldata["string-literals"])

    def on_resize(sig, action):
        debug.redrawEverything()
        debug.show()
    signal.signal(signal.SIGWINCH, on_resize)

    debug.debug()


def main():
    parser = argparse.ArgumentParser(description='Prim Debugger')
    parser.add_argument("-i", help="Input TOML file", action="store", metavar="<input file>", type=str, required=False, dest="input_filename",default="src/interpreter.tf.toml")
    parser.add_argument("-u", help="UART input file", action="store", metavar="<input file>", type=str, required=False, dest="uart_filename",default="src/test.tok")
    args = parser.parse_args()

    debug(args.input_filename, args.uart_filename)


if __name__ == "__main__":
    main()