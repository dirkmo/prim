# RTL simulation

Requirements: CMake, Verilator, a C++17 compiler, and Python 3. On macOS,
install the Xcode Command Line Tools. CMake falls back to the active SDK's
libc++ headers if the compiler cannot find them automatically.

From the repository root, build the simulator and run the existing regressions:

```sh
python3 rtl/control_flow_regressions.py
```

This configures and builds in `build/rtl` on every invocation, so changes to the
RTL and C++ sources are picked up. It does not use the old `rtl/build` cache.
The simulator writes `trace.vcd` into its build directory.

The equivalent explicit workflow is:

```sh
cmake -S rtl -B build/rtl
cmake --build build/rtl
ctest --test-dir build/rtl --output-on-failure
```

CTest uses the simulator from that build without rebuilding it. To run the
regressions against another existing build:

```sh
python3 rtl/control_flow_regressions.py --simulator /path/to/simulator
```

The cases check selected final register values against fixed expectations.
They do not yet compare each instruction with the Python CPU model or validate
the external RAM controller in `memory.v`.
