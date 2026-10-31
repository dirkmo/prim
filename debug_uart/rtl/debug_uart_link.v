// Serial/debug subsystem. CPU control and bus ownership are external interfaces.
module debug_uart_link #(
    parameter integer CLK_HZ = 100000000
)(
    input i_clk, i_reset, i_rx,
    output o_tx,
    input [6:0] i_output_data,
    input i_output_valid,
    output o_output_ready,
    output [6:0] o_input_data,
    output [3:0] o_uart_csr,
    input [7:0] i_csr_data,
    input i_csr_write,
    output o_irq, o_rx_irq, o_tx_irq,
    input i_input_read,
    output o_halt, o_run, o_step, o_reset_cpu,
    input i_halted, i_break_reason, i_break_event,
    input [15:0] i_pc,
    output [15:0] o_addr, o_data,
    output [1:0] o_bs,
    output o_we,
    input i_ack,
    input [15:0] i_data
);
localparam integer CLKS_PER_BIT = (CLK_HZ + 57600) / 115200;
wire [7:0] rx_data, debug_data, tx_data;
wire rx_valid, debug_valid, debug_ready, tx_valid, tx_ready;
wire [6:0] buffered_data;
wire buffered_valid, buffered_ready;
uart_buffers buffers(.i_clk(i_clk), .i_reset(i_reset), .i_rx_data(rx_data), .i_rx_valid(rx_valid),
    .i_input_read(i_input_read), .o_input_data(o_input_data), .o_csr(o_uart_csr),
    .i_csr_data(i_csr_data), .i_csr_write(i_csr_write), .o_irq(o_irq),
    .o_rx_irq(o_rx_irq), .o_tx_irq(o_tx_irq),
    .i_output_data(i_output_data), .i_output_valid(i_output_valid), .o_output_ready(o_output_ready),
    .o_tx_data(buffered_data), .o_tx_valid(buffered_valid), .i_tx_ready(buffered_ready));
uart_rx #(.CLKS_PER_BIT(CLKS_PER_BIT)) rx(
    .i_clk(i_clk), .i_reset(i_reset), .i_rx(i_rx), .o_data(rx_data), .o_valid(rx_valid));
debug_uart debug(.i_clk(i_clk), .i_reset(i_reset), .i_rx_data(rx_data), .i_rx_valid(rx_valid),
    .o_tx_data(debug_data), .o_tx_valid(debug_valid), .i_tx_ready(debug_ready),
    .o_halt(o_halt), .o_run(o_run), .o_step(o_step), .o_reset_cpu(o_reset_cpu),
    .i_uart_status(o_uart_csr[1:0]), .i_halted(i_halted), .i_break_reason(i_break_reason), .i_break_event(i_break_event), .i_pc(i_pc),
    .o_addr(o_addr), .o_data(o_data), .o_bs(o_bs), .o_we(o_we), .i_ack(i_ack), .i_data(i_data));
uart_arbiter arbiter(.i_debug_data(debug_data), .i_debug_valid(debug_valid), .o_debug_ready(debug_ready),
    .i_output_data(buffered_data), .i_output_valid(buffered_valid), .o_output_ready(buffered_ready),
    .o_data(tx_data), .o_valid(tx_valid), .i_ready(tx_ready));
uart_tx #(.CLKS_PER_BIT(CLKS_PER_BIT)) tx(
    .i_clk(i_clk), .i_reset(i_reset), .i_data(tx_data), .i_valid(tx_valid), .o_ready(tx_ready), .o_tx(o_tx));
endmodule
