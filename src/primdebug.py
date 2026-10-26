"""Compatibility entry point for the optional Prim debugger."""
if __name__ == '__main__':
    from prim.cli import debug_main
    debug_main()
else:
    from prim.debugger import *
