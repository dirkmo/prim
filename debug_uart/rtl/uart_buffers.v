// One CPU RX register and one pending CPU TX byte, independent of debug traffic.
module uart_buffers(
    input i_clk, i_reset,
    input [7:0] i_rx_data,
    input i_rx_valid, i_input_read,
    output reg [6:0] o_input_data,
    output [3:0] o_csr,
    input [7:0] i_csr_data,
    input i_csr_write,
    output reg o_irq, o_rx_irq, o_tx_irq,
    input [6:0] i_output_data,
    input i_output_valid,
    output o_output_ready,
    output reg [6:0] o_tx_data,
    output o_tx_valid,
    input i_tx_ready
);
// CSR: bit 0 RXAVAIL, bit 1 TXFREE (read-only), bit 2 RXIE, bit 3 TXIE.
reg received, pending, rxie, txie;
assign o_csr = {txie, rxie, !pending, received};
assign o_output_ready = !i_reset && !pending;
assign o_tx_valid = !i_reset && pending;
always @(posedge i_clk) begin
    if (i_reset) begin
        o_input_data <= 0; received <= 0;
        o_tx_data <= 0; pending <= 0;
        rxie <= 0; txie <= 0; o_irq <= 0; o_rx_irq <= 0; o_tx_irq <= 0;
    end else begin
        // Event pulses use the enables from before this edge. No retroactive IRQ.
        o_irq <= (rxie && i_rx_valid && !i_rx_data[7]) ||
                 (txie && o_tx_valid && i_tx_ready);
        o_rx_irq <= rxie && i_rx_valid && !i_rx_data[7];
        o_tx_irq <= txie && o_tx_valid && i_tx_ready;
        if (i_csr_write) begin
            rxie <= i_csr_data[2]; txie <= i_csr_data[3];
        end
        if (i_input_read) received <= 0;
        // New reception wins over consumption; reads retain the last byte.
        if (i_rx_valid && !i_rx_data[7]) begin
            o_input_data <= i_rx_data[6:0]; received <= 1;
        end
        if (o_tx_valid && i_tx_ready) pending <= 0;
        if (i_output_valid && o_output_ready) begin
            o_tx_data <= i_output_data; pending <= 1;
        end
    end
end
endmodule
