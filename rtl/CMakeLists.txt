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
if(NOT DEFINED Python3_EXECUTABLE AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/../.venv/bin/python")
    set(Python3_EXECUTABLE "${CMAKE_CURRENT_SOURCE_DIR}/../.venv/bin/python")
endif()
find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)
execute_process(COMMAND ${Python3_EXECUTABLE} -c "import prim.artifacts"
    RESULT_VARIABLE PRIM_PYTHON_RESULT OUTPUT_QUIET ERROR_QUIET)
if(NOT PRIM_PYTHON_RESULT EQUAL 0)
    message(FATAL_ERROR "Install the Python package first: ${Python3_EXECUTABLE} -m pip install -e ${CMAKE_CURRENT_SOURCE_DIR}/..")
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
add_executable(simulator sim.cpp)

enable_testing()
add_test(NAME control_flow_regressions
    COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/control_flow_regressions.py
        --simulator $<TARGET_FILE:simulator>)
add_test(NAME python_rtl_comparison
    COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/compare.py
        --simulator $<TARGET_FILE:simulator>)
add_test(NAME comparison_checks
    COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/test_compare.py
        --simulator $<TARGET_FILE:simulator>)
add_test(NAME memory_handshake_checks
    COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/test_memory.py
        --simulator $<TARGET_FILE:simulator>)
add_test(NAME sram_controller_checks
    COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/test_sram.py
        --iverilog ${IVERILOG_EXECUTABLE} --vvp ${VVP_EXECUTABLE})
add_test(NAME uart_io_checks
    COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/test_io.py
        --iverilog ${IVERILOG_EXECUTABLE} --vvp ${VVP_EXECUTABLE})
add_test(NAME tokenforth_end_to_end
    COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/test_tokenforth.py
        --iverilog ${IVERILOG_EXECUTABLE} --vvp ${VVP_EXECUTABLE})
add_test(NAME debug_uart_checks
    COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/test_debug_uart.py
        --iverilog ${IVERILOG_EXECUTABLE} --vvp ${VVP_EXECUTABLE})
add_test(NAME debug_uart_host_checks
    COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/../src/test_debug_uart.py)
add_test(NAME test_harness_checks
    COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/test_support.py)


# Add the Verilated circuit to the target
verilate(simulator TRACE # COVERAGE
#INCLUDE_DIRS "../rtl" "../sim"
VERILATOR_ARGS "+define+SIM=1"
SOURCES prim.v)

# target_link_libraries(simulator PUBLIC ${CURSES_LIBRARIES} readline)

add_custom_target(genopcodes
    COMMAND ${Python3_EXECUTABLE} -m prim.isa ${PROJECT_SOURCE_DIR}/opcodes.v
)


add_custom_target(assemble
    COMMAND ${Python3_EXECUTABLE} -m prim.assembler -i ${PROJECT_SOURCE_DIR}/test.asm -o ${CMAKE_BINARY_DIR}/test.bin
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
    COMMAND cp ${PROJECT_SOURCE_DIR}/.gtkwaverc ${PROJECT_SOURCE_DIR}/build
    COMMAND gtkwave -S ${PROJECT_SOURCE_DIR}/addsignals.tcl ${PROJECT_SOURCE_DIR}/build/trace.vcd
    DEPENDS simulate
)

add_custom_target(iverilog
    COMMAND iverilog -Wall -I ${PROJECT_SOURCE_DIR} ${PROJECT_SOURCE_DIR}/prim.v
)

add_custom_target(yosys
	COMMAND yosys -Wall -p "synth_ice40 -dsp" ${PROJECT_SOURCE_DIR}/prim.v
)
