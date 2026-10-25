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

find_package(Python3 REQUIRED COMPONENTS Interpreter)

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


# Add the Verilated circuit to the target
verilate(simulator TRACE # COVERAGE
#INCLUDE_DIRS "../rtl" "../sim"
VERILATOR_ARGS "+define+SIM=1"
SOURCES prim.v)

# target_link_libraries(simulator PUBLIC ${CURSES_LIBRARIES} readline)

add_custom_target(genopcodes
    COMMAND ${PROJECT_SOURCE_DIR}/../src/primconsts.py ${PROJECT_SOURCE_DIR}/opcodes.v
)


add_custom_target(assemble
    COMMAND ${PROJECT_SOURCE_DIR}/../src/primasm.py -i ${PROJECT_SOURCE_DIR}/test.asm -o ${CMAKE_BINARY_DIR}/test.bin
    COMMAND xxd -g1 ${CMAKE_BINARY_DIR}/test.bin
)

add_custom_target(disassemble
    COMMAND ${PROJECT_SOURCE_DIR}/../src/primasm.py -d ${CMAKE_BINARY_DIR}/test.bin
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
