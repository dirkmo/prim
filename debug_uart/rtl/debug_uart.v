// One operation at a time; a cooperative host waits for every response.
// For R, the next request may be sent after receiving the third hex digit.
module debug_uart(
    input i_clk, i_reset,
    input [7:0] i_rx_data,
    input i_rx_valid,
    output [7:0] o_tx_data,
    output o_tx_valid,
    input i_tx_ready,
    output o_halt,
    output reg o_run, o_step, o_reset_cpu,
    input [1:0] i_uart_status,
    input i_halted, i_break_reason, i_break_event,
    input [15:0] i_pc,
    output [15:0] o_addr, o_data,
    output [1:0] o_bs,
    output o_we,
    input i_ack,
    input [15:0] i_data
);
localparam IDLE=0, BUS=1, HALTING=2, STEPPING=3, RESETTING=4, RESET_WAIT=5;
localparam NONE=0, ADDRESS=1, BYTE=2, WORD=3;
reg [2:0] state;
reg [1:0] mode;
reg [1:0] nibble;
reg [15:0] pointer, value;
reg word_access, writing;
// Response serializer: optional prefix and zero, one, two or four low-first nibbles.
reg [2:0] remaining;
reg prefix;
reg status_reply;
reg [15:0] reply;
reg break_pending;
wire response = prefix || remaining != 0;
wire [3:0] digit = reply[3:0];
wire [6:0] hexchar = digit < 10 ? 7'd48 + {3'b0, digit} : 7'd87 + {3'b0, digit};
assign o_tx_valid = response || break_pending;
assign o_tx_data = {1'b1, response ? (prefix ? (status_reply ? 7'd84 : 7'd75) : hexchar) : 7'd66};
assign o_halt = state == HALTING || state == RESET_WAIT;
assign o_addr = pointer;
assign o_data = value;
assign o_bs = state == BUS && i_halted ? (word_access ? 2'b11 : 2'b01) : 2'b00;
assign o_we = writing;
wire [7:0] c = {1'b0, i_rx_data[6:0]};
wire is_hex = (c >= "0" && c <= "9") || (c >= "a" && c <= "f");
wire [3:0] hexvalue = c[6] ? c[3:0] + 4'd9 : c[3:0];
wire command = c == "A" || c == "r" || c == "R" || c == "w" || c == "W" ||
               c == "H" || c == "G" || c == "S" || c == "Z" || c == "P" || c == "?" || c == "q";
always @(posedge i_clk) begin
    o_run <= 0; o_step <= 0; o_reset_cpu <= 0;
    if (i_reset) begin
        state <= IDLE; mode <= NONE; nibble <= 0; pointer <= 0; value <= 0;
        prefix <= 0; remaining <= 0; break_pending <= 0;
        status_reply <= 0; writing <= 0; word_access <= 0; reply <= 0;
    end else begin
        if (o_tx_valid && i_tx_ready) begin
            if (prefix) prefix <= 0;
            else if (remaining != 0) begin
                remaining <= remaining - 1'b1;
                reply <= {4'b0, reply[15:4]};
            end else break_pending <= 0;
        end
        // Set wins over sending: even a one-clock CPU pulse is retained.
        if (i_break_event) break_pending <= 1;
        case (state)
            BUS: if (i_ack) begin
                pointer <= pointer + (word_access ? 16'd2 : 16'd1);
                prefix <= writing; status_reply <= 0;
                remaining <= writing ? 0 : (word_access ? 4 : 2);
                reply <= i_data;
                state <= IDLE;
            end
            RESET_WAIT: if (i_halted) begin o_reset_cpu <= 1; state <= RESETTING; end
            HALTING, STEPPING, RESETTING: if (i_halted && !o_step && !o_reset_cpu) begin
                prefix <= 1; status_reply <= 0; remaining <= 0; state <= IDLE;
            end
            default: if (i_rx_valid && i_rx_data[7]) begin
                if (command) begin
                    mode <= NONE; nibble <= 0;
                    case (c)
                        "A": mode <= ADDRESS;
                        "w": mode <= BYTE;
                        "W": mode <= WORD;
                        "r", "R": begin
                            writing <= 0; word_access <= c == "R"; state <= BUS;
                        end
                        "H": state <= HALTING;
                        "G": begin o_run <= 1; prefix <= 1; status_reply <= 0; end
                        "S": begin o_step <= 1; state <= STEPPING; end
                        "Z": state <= RESET_WAIT;
                        "P": begin prefix <= 1; status_reply <= 0; remaining <= 4; reply <= i_pc; end
                        "q": begin
                            prefix <= 1; status_reply <= 0; remaining <= 1;
                            reply <= {14'b0, i_uart_status};
                        end
                        "?": begin
                            prefix <= 1; status_reply <= 1; remaining <= 1;
                            reply <= {14'b0, i_break_reason, i_halted};
                        end
                        default: ;
                    endcase
                end else if (is_hex && mode != NONE) begin
                    if (mode == ADDRESS) pointer[nibble*4 +: 4] <= hexvalue;
                    else value[nibble*4 +: 4] <= hexvalue;
                    nibble <= nibble + 1'b1;
                    if ((mode == BYTE && nibble == 1) || (mode == WORD && nibble == 3)) begin
                        nibble <= 0; writing <= 1; word_access <= mode == WORD; state <= BUS;
                    end
                end
            end
        endcase
    end
end
endmodule
