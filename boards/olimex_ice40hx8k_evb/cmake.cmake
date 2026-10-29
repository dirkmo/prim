# Included by the root build; board tools are needed only for board targets.
find_program(NEXTPNR_ICE40_EXECUTABLE nextpnr-ice40)
find_program(ICEPACK_EXECUTABLE icepack)
find_program(ICEPROG_EXECUTABLE iceprog)
set(OLIMEX_ICEPROG_DEVICE "" CACHE STRING "Optional iceprog -d device selector")
set(OLIMEX_ICEPROG_INTERFACE "A" CACHE STRING "UM-FT2232H interface used for programming")
set(OLIMEX_BOARD_DIR "${PROJECT_SOURCE_DIR}/boards/olimex_ice40hx8k_evb")
# Board builds are configured with -B build/olimex_ice40hx8k_evb.
set(OLIMEX_OUTPUT_DIR "${CMAKE_BINARY_DIR}")
file(GLOB OLIMEX_RTL CONFIGURE_DEPENDS
    "${PROJECT_SOURCE_DIR}/cpu/rtl/*.v"
    "${PROJECT_SOURCE_DIR}/timer/rtl/*.v"
    "${PROJECT_SOURCE_DIR}/system/rtl/*.v"
    "${PROJECT_SOURCE_DIR}/debug_uart/rtl/*.v")
if(YOSYS_EXECUTABLE AND NEXTPNR_ICE40_EXECUTABLE AND ICEPACK_EXECUTABLE)
    add_custom_command(OUTPUT "${OLIMEX_OUTPUT_DIR}/prim.bin"
        COMMAND ${Python3_EXECUTABLE} "${OLIMEX_BOARD_DIR}/build.py" build
            --output "${OLIMEX_OUTPUT_DIR}" --yosys "${YOSYS_EXECUTABLE}"
            --nextpnr "${NEXTPNR_ICE40_EXECUTABLE}" --icepack "${ICEPACK_EXECUTABLE}"
        DEPENDS ${OLIMEX_RTL} "${OLIMEX_BOARD_DIR}/top.v"
            "${OLIMEX_BOARD_DIR}/board.pcf" "${OLIMEX_BOARD_DIR}/build.py"
        VERBATIM)
    add_custom_target(fpga_bitstream DEPENDS "${OLIMEX_OUTPUT_DIR}/prim.bin")
    if(ICEPROG_EXECUTABLE)
        set(OLIMEX_DEVICE_ARGS)
        if(OLIMEX_ICEPROG_DEVICE)
            list(APPEND OLIMEX_DEVICE_ARGS --device "${OLIMEX_ICEPROG_DEVICE}")
        endif()
        add_custom_target(fpga_program
            COMMAND ${Python3_EXECUTABLE} "${OLIMEX_BOARD_DIR}/build.py" program
                "${OLIMEX_OUTPUT_DIR}/prim.bin" --iceprog "${ICEPROG_EXECUTABLE}"
                --interface "${OLIMEX_ICEPROG_INTERFACE}" ${OLIMEX_DEVICE_ARGS}
            DEPENDS fpga_bitstream
            USES_TERMINAL VERBATIM)
    endif()
endif()
add_test(NAME olimex_board_checks
    COMMAND ${Python3_EXECUTABLE} "${OLIMEX_BOARD_DIR}/test_board.py"
        --iverilog ${IVERILOG_EXECUTABLE} --vvp ${VVP_EXECUTABLE})
add_test(NAME olimex_host_checks
    COMMAND ${Python3_EXECUTABLE} "${OLIMEX_BOARD_DIR}/test_host.py")
