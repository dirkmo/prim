// Pin-independent CPU + SRAM controller + timer + shared CPU/debug UART.
module prim_system #(
    parameter integer CLK_HZ = 100000000,
    parameter integer READ_CYCLES = 2,
    parameter integer WRITE_CYCLES = 2,
    parameter integer START_HALTED = 0,
    parameter integer TIMER_DIVISOR = 50000,
    parameter integer VGA_ENABLE = 0
)(
    input i_clk,
    input i_reset,
    input i_rx,
    output o_tx,
    output o_halted,
    output [1:0] o_leds,
    output [15:0] ram_addr,
    inout [15:0] ram_data,
    output ram_cs_n,
    output ram_oe_n,
    output ram_we_n,
    output o_vga_hsync, o_vga_vsync, o_vga_pixel, o_vga_active
);
wire [15:0] addr, to_mem, from_mem, cpu_addr, cpu_data, debug_addr, debug_data, pc;
wire [1:0] bs, cpu_bs, debug_bs;
wire we, ack, cpu_we, debug_we, halted, halt_request, run_request, step_request, reset_cpu;
wire break_reason, break_event, cpu_ack, debug_ack, output_valid, output_ready;
wire [6:0] output_data, input_data;
wire [3:0] uart_csr;
wire [7:0] uart_csr_data;
wire uart_csr_write, uart_irq;
wire input_read, timer_irq;
assign o_halted = halted;
bus_mux bus(.i_halted(halted), .i_cpu_addr(cpu_addr), .i_cpu_data(cpu_data),
    .i_cpu_bs(cpu_bs), .i_cpu_we(cpu_we), .i_debug_addr(debug_addr), .i_debug_data(debug_data),
    .i_debug_bs(debug_bs), .i_debug_we(debug_we), .o_addr(addr), .o_data(to_mem),
    .o_bs(bs), .o_we(we), .i_ack(ack), .o_cpu_ack(cpu_ack), .o_debug_ack(debug_ack));
Prim cpu(.i_clk(i_clk), .i_reset(i_reset), .o_addr(cpu_addr), .o_dat(cpu_data),
         .i_dat(from_mem), .o_bs(cpu_bs), .o_we(cpu_we), .i_ack(cpu_ack), .i_irq(timer_irq | uart_irq),
         .i_halt(halt_request), .i_run(run_request), .i_step(step_request),
         .i_debug_reset(reset_cpu || (i_reset && START_HALTED)), .o_halted(halted), .o_pc(pc),
         .o_break_reason(break_reason), .o_break_event(break_event));
debug_uart_link #(.CLK_HZ(CLK_HZ)) uart(.i_clk(i_clk), .i_reset(i_reset), .i_rx(i_rx), .o_tx(o_tx),
    .o_input_data(input_data), .o_uart_csr(uart_csr),
    .i_csr_data(uart_csr_data), .i_csr_write(uart_csr_write), .o_irq(uart_irq), .i_input_read(input_read),
    .i_output_data(output_data), .i_output_valid(output_valid), .o_output_ready(output_ready),
    .o_halt(halt_request), .o_run(run_request), .o_step(step_request), .o_reset_cpu(reset_cpu),
    .i_halted(halted), .i_break_reason(break_reason), .i_break_event(break_event), .i_pc(pc),
    .o_addr(debug_addr), .o_data(debug_data), .o_bs(debug_bs), .o_we(debug_we),
    .i_ack(debug_ack), .i_data(from_mem));
memory_io #(.READ_CYCLES(READ_CYCLES), .WRITE_CYCLES(WRITE_CYCLES),
            .TIMER_DIVISOR(TIMER_DIVISOR), .VGA_ENABLE(VGA_ENABLE)) io(
    .i_clk(i_clk), .i_reset(i_reset), .i_addr(addr), .i_cpu_to_mem(to_mem),
    .i_input_data(input_data), .i_uart_csr(uart_csr),
    .o_uart_csr_data(uart_csr_data), .o_uart_csr_write(uart_csr_write), .o_input_read(input_read),
    .o_leds(o_leds), .o_timer_irq(timer_irq),
    .o_vga_hsync(o_vga_hsync), .o_vga_vsync(o_vga_vsync),
    .o_vga_pixel(o_vga_pixel), .o_vga_active(o_vga_active),
    .o_output_data(output_data), .o_output_valid(output_valid), .i_output_ready(output_ready),
    .i_bs(bs), .i_we(we), .o_mem_to_cpu(from_mem), .o_ack(ack),
    .ram_addr(ram_addr), .ram_data(ram_data), .ram_cs_n(ram_cs_n),
    .ram_oe_n(ram_oe_n), .ram_we_n(ram_we_n));
endmodule
