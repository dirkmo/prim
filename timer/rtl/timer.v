// Standalone 16-bit timer. All state uses i_clk; the divider is a clock enable.
module timer #(
    parameter integer DIVISOR = 50000
)(
    input wire i_clk,
    input wire i_reset,
    input wire i_cs,
    input wire i_we,
    input wire [1:0] i_addr,
    input wire [1:0] i_be,
    input wire [15:0] i_wdata,
    output reg [15:0] o_rdata,
    output reg o_irq
);
reg [15:0] count, compare;
reg [2:0] csr;

wire write_reg = i_cs && i_we && (|i_be) && i_addr != 2'b11;
wire tick;
wire [15:0] incremented = count + 16'd1;

generate
    if (DIVISOR == 1) begin : no_divider
        assign tick = 1'b1;
    end else begin : with_divider
        localparam integer DIV_WIDTH = DIVISOR > 1 ? $clog2(DIVISOR) : 1;
        localparam [DIV_WIDTH-1:0] DIV_LAST = DIVISOR[DIV_WIDTH-1:0] - 1'b1;
        reg [DIV_WIDTH-1:0] divider;
        wire [15:0] written_count = {i_be[1] ? i_wdata[15:8] : count[15:8],
                                     i_be[0] ? i_wdata[7:0] : count[7:0]};
        wire restart_divider = write_reg && i_addr == 2'b00 && written_count == 0;
        assign tick = divider == DIV_LAST;
        always @(posedge i_clk) begin
            // Disabled time does not contribute to the next counting interval.
            if (i_reset || !csr[0] || restart_divider || tick)
                divider <= 0;
            else
                divider <= divider + 1'b1;
        end
    end
endgenerate

always @* begin
    o_rdata = 16'b0;
    if (i_cs) begin
        case (i_addr)
            2'b00: o_rdata = count;
            2'b01: o_rdata = compare;
            2'b10: o_rdata = {13'b0, csr};
            default: o_rdata = 16'b0;
        endcase
    end
end

always @(posedge i_clk) begin
    if (i_reset) begin
        count <= 0;
        compare <= 0;
        csr <= 0;
        o_irq <= 0;
    end else begin
        o_irq <= 0;
        // A valid register write wins over counting and interrupt generation.
        if (write_reg) begin
            case (i_addr)
                2'b00: begin
                    if (i_be[0]) count[7:0] <= i_wdata[7:0];
                    if (i_be[1]) count[15:8] <= i_wdata[15:8];
                end
                2'b01: begin
                    if (i_be[0]) compare[7:0] <= i_wdata[7:0];
                    if (i_be[1]) compare[15:8] <= i_wdata[15:8];
                end
                2'b10: if (i_be[0]) csr <= i_wdata[2:0];
                default: begin end
            endcase
        end else if (csr[0] && tick) begin
            if (count != compare) begin
                count <= incremented;
                if (csr[2] && incremented == compare) o_irq <= 1;
            end else if (csr[1] && compare != 16'b0) begin
                count <= 0;
            end
        end
    end
end

// No hardware is needed for constant parameter validation.
`ifndef SYNTHESIS
initial begin
    if (DIVISOR < 1)
        $fatal(1, "timer: DIVISOR must be positive");
end
`endif
endmodule
