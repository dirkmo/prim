cmake_minimum_required(VERSION 3.12)
cmake_policy(SET CMP0074 NEW)
project(prim-simulator)

find_package(VERILATOR HINTS $ENV{VERILATOR_ROOT} ${VERILATOR_ROOT})
if (NOT verilator_FOUND)
  message(FATAL_ERROR "Verilator was not found. Either install it, or set the VERILATOR_ROOT environment variable")
endif()

# find_package(Curses REQUIRED)
# include_directories(${CURSES_INCLUDE_DIR})

# Create a new executable target that will contain all your sources
add_executable(simulator sim.cpp)


# Add the Verilated circuit to the target
verilate(simulator TRACE # COVERAGE
#INCLUDE_DIRS "../rtl" "../sim"
VERILATOR_ARGS "+define+SIM=1"
SOURCES prim.v)

# target_link_libraries(simulator PUBLIC ${CURSES_LIBRARIES} readline)

add_custom_target(assemble
    COMMAND ${PROJECT_SOURCE_DIR}/../src/primasm.py -i ${PROJECT_SOURCE_DIR}/test.asm -o ${CMAKE_BINARY_DIR}/test.bin
    COMMAND xxd -g1 ${CMAKE_BINARY_DIR}/test.bin
)

add_custom_target(simulate
    COMMAND ${PROJECT_BINARY_DIR}/simulator -i ${CMAKE_BINARY_DIR}/test.bin
    DEPENDS assemble
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
