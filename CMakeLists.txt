cmake_minimum_required(VERSION 3.12)
cmake_policy(SET CMP0074 NEW)
project(prim-simulator)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Some Command Line Tools installations keep libc++ headers only in the SDK.
if(APPLE)
    include(CheckIncludeFileCXX)
    check_include_file_cxx(cstdint PRIM_HAS_CSTDINT)
    if(NOT PRIM_HAS_CSTDINT)
        execute_process(COMMAND xcrun --show-sdk-path
            OUTPUT_VARIABLE PRIM_MACOS_SDK OUTPUT_STRIP_TRAILING_WHITESPACE
            RESULT_VARIABLE PRIM_SDK_RESULT)
        if(PRIM_SDK_RESULT EQUAL 0 AND EXISTS "${PRIM_MACOS_SDK}/usr/include/c++/v1/cstdint")
            include_directories(SYSTEM "${PRIM_MACOS_SDK}/usr/include/c++/v1")
        else()
            message(FATAL_ERROR "C++ standard headers missing; repair the Xcode Command Line Tools installation")
        endif()
    endif()
endif()

# Prefer the editable project environment; callers can override explicitly.
if(NOT DEFINED Python3_EXECUTABLE AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/.venv/bin/python")
    set(Python3_EXECUTABLE "${CMAKE_CURRENT_SOURCE_DIR}/.venv/bin/python")
endif()
find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)
execute_process(COMMAND ${Python3_EXECUTABLE} -c "import prim.artifacts"
    RESULT_VARIABLE PRIM_PYTHON_RESULT OUTPUT_QUIET ERROR_QUIET)
if(NOT PRIM_PYTHON_RESULT EQUAL 0)
    message(FATAL_ERROR "Install the Python package first: ${Python3_EXECUTABLE} -m pip install -e ${CMAKE_CURRENT_SOURCE_DIR}")
endif()
find_program(IVERILOG_EXECUTABLE iverilog)
find_program(VVP_EXECUTABLE vvp)
if(NOT IVERILOG_EXECUTABLE OR NOT VVP_EXECUTABLE)
    message(FATAL_ERROR "Icarus Verilog (iverilog and vvp) is required for SRAM controller tests")
endif()

find_package(VERILATOR HINTS $ENV{VERILATOR_ROOT} ${VERILATOR_ROOT})
if (NOT verilator_FOUND)
  message(FATAL_ERROR "Verilator was not found. Either install it, or set the VERILATOR_ROOT environment variable")
endif()

# find_package(Curses REQUIRED)
# include_directories(${CURSES_INCLUDE_DIR})

# Create a new executable target that will contain all your sources
add_executable(simulator cpu/tests/sim.cpp)

enable_testing()
add_test(NAME control_flow_regressions
    COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/cpu/tests/control_flow_regressions.py
        --simulator $<TARGET_FILE:simulator>)
add_test(NAME python_rtl_comparison
    COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/cpu/tests/compare.py
        --simulator $<TARGET_FILE:simulator>)
add_test(NAME comparison_checks
    COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/cpu/tests/test_compare.py
        --simulator $<TARGET_FILE:simulator>)
add_test(NAME memory_handshake_checks
    COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/cpu/tests/test_memory.py
        --simulator $<TARGET_FILE:simulator>)
add_test(NAME sram_controller_checks
    COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/system/tests/test_sram.py
        --iverilog ${IVERILOG_EXECUTABLE} --vvp ${VVP_EXECUTABLE})
add_test(NAME uart_io_checks
    COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/system/tests/test_io.py
        --iverilog ${IVERILOG_EXECUTABLE} --vvp ${VVP_EXECUTABLE})
add_test(NAME tokenforth_end_to_end
    COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/system/tests/test_tokenforth.py
        --iverilog ${IVERILOG_EXECUTABLE} --vvp ${VVP_EXECUTABLE})
add_test(NAME debug_uart_checks
    COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/system/tests/test_debug_uart.py
        --iverilog ${IVERILOG_EXECUTABLE} --vvp ${VVP_EXECUTABLE})
add_test(NAME debug_uart_host_checks
    COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/debug_uart/tests/test_host.py)
add_test(NAME uart_session_checks
    COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/debug_uart/tests/test_session.py)
add_test(NAME cpu_debug_checks
    COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/cpu/tests/test_debug_cpu.py
        --iverilog ${IVERILOG_EXECUTABLE} --vvp ${VVP_EXECUTABLE})
add_test(NAME uart_component_checks
    COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/debug_uart/tests/test_rtl.py
        --iverilog ${IVERILOG_EXECUTABLE} --vvp ${VVP_EXECUTABLE})
add_test(NAME timer_checks
    COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/timer/tests/test_timer.py
        --iverilog ${IVERILOG_EXECUTABLE} --vvp ${VVP_EXECUTABLE})
add_test(NAME top_makefile_checks
    COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/tests/test_makefile.py)
add_test(NAME test_harness_checks
    COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/tests/test_support.py)


# The CPU simulator deliberately links no system or UART sources.
verilate(simulator TRACE_VCD
    INCLUDE_DIRS "${PROJECT_SOURCE_DIR}/cpu/rtl"
    VERILATOR_ARGS "+define+SIM=1"
    SOURCES cpu/rtl/prim.v)

add_custom_target(genopcodes
    COMMAND ${Python3_EXECUTABLE} -m prim.isa ${PROJECT_SOURCE_DIR}/cpu/rtl/opcodes.v
)


add_custom_target(assemble
    COMMAND ${Python3_EXECUTABLE} -m prim.assembler -i ${PROJECT_SOURCE_DIR}/cpu/tests/test.asm -o ${CMAKE_BINARY_DIR}/test.bin
    COMMAND xxd -g1 ${CMAKE_BINARY_DIR}/test.bin
)

add_custom_target(disassemble
    COMMAND ${Python3_EXECUTABLE} -m prim.assembler -d ${CMAKE_BINARY_DIR}/test.bin
)

add_custom_target(simulate
    COMMAND ${PROJECT_BINARY_DIR}/simulator -i ${CMAKE_BINARY_DIR}/test.bin
    DEPENDS assemble
    DEPENDS disassemble
    DEPENDS genopcodes
    DEPENDS simulator
    COMMENT "Executing simulation..."
)

add_custom_target(wave
    COMMAND gtkwave -S ${PROJECT_SOURCE_DIR}/cpu/tests/addsignals.tcl ${CMAKE_BINARY_DIR}/trace.vcd
    DEPENDS simulate)

add_custom_target(iverilog
    COMMAND ${IVERILOG_EXECUTABLE} -Wall -I ${PROJECT_SOURCE_DIR}/cpu/rtl
        -s Prim -o ${CMAKE_BINARY_DIR}/prim.vvp ${PROJECT_SOURCE_DIR}/cpu/rtl/prim.v)

find_program(YOSYS_EXECUTABLE yosys)
if(YOSYS_EXECUTABLE)
    add_custom_target(yosys
        COMMAND ${YOSYS_EXECUTABLE} -s ${PROJECT_SOURCE_DIR}/system/synth.ys
        WORKING_DIRECTORY ${PROJECT_SOURCE_DIR}
        VERBATIM)
endif()

include(boards/olimex_ice40hx8k_evb/cmake.cmake)
