// Four procedural voices, one synchronous state RAM and one staging bank.
// See audio/registers.md for the MMIO and frame-boundary contract.
module audio #(
    parameter integer CLK_HZ = 25000000
)(
    input i_clk, i_reset, i_cs, i_we,
    input [3:0] i_addr,
    input [7:0] i_data,
    output reg [7:0] o_data,
    output o_ready,
    output o_pwm
);
// Configuration: decay[54:47], attack[46:39], duty[38:31], rate[30:7],
// volume[6:3], envelope-enable[2], waveform[1:0]. Shared by all voices.
reg [54:0] staging;
reg [3:0] master, pending, playing;
reg [1:0] voice, operation;
reg [3:0] frame_pending;
// Seven little-endian 16-bit words per voice, at voice*8 + word (word 7 spare):
// cfg[54:0], phase[78:55], level[82:79], envelope[84:83], elapsed[92:85],
// last serviced millisecond epoch[100:93], zero padding[111:101].
reg [15:0] state_ram [0:31];
reg [111:0] work;
reg [15:0] ram_data;
reg initializing;
reg [4:0] clear_addr;
reg [1:0] mix_voice;
reg [2:0] word_index;
localparam IDLE=4'd0, READ_WAIT=4'd1, READ_TAKE=4'd2,
           ENVELOPE=4'd3, COMMAND=4'd4, SAMPLE=4'd5,
           SCALE=4'd6, SUM=4'd7, STORE=4'd8;
reg [3:0] state;
wire [4:0] ram_addr = {mix_voice,word_index};
// A synchronous read and single synchronous write infer one iCE40 EBR.
// Reset clears only the 32 used words through the write port, never the array.
always @(posedge i_clk) begin
    ram_data <= state_ram[ram_addr];
    if (!i_reset) begin
        if (initializing) state_ram[clear_addr] <= 0;
        else if (state == STORE) state_ram[ram_addr] <= work[15:0];
    end
end
localparam integer MS_DIV = CLK_HZ / 1000;
localparam integer MS_BITS = MS_DIV <= 1 ? 1 : $clog2(MS_DIV);
reg [MS_BITS-1:0] ms_count;
reg [7:0] ms_epoch;
wire ms_tick = ms_count == MS_DIV-1;
reg [7:0] counter, duty, next_duty;
wire frame = counter == 0;
assign o_pwm = counter < duty;
// Pending commands own staging until their state has been written to RAM.
assign o_ready = !initializing && (!i_we || !(|pending));
always @* begin
    o_data = 0;
    case (i_addr)
        0: o_data = {4'b0,master};
        1: o_data = {6'b0,voice};
        2: o_data = {5'b0,staging[2:0]};
        3: o_data = {4'b0,staging[6:3]};
        4: o_data = staging[14:7];
        5: o_data = staging[22:15];
        6: o_data = staging[30:23];
        7: o_data = staging[38:31];
        8: o_data = staging[46:39];
        9: o_data = staging[54:47];
        11: o_data = {pending,playing};
        default: o_data = 0;
    endcase
end
wire [54:0] cfg = work[54:0];
wire [23:0] phase = work[78:55];
wire [3:0] level = work[82:79];
wire [1:0] envelope = work[84:83];
wire [7:0] elapsed = work[92:85];
wire [7:0] position = phase[23:16];
wire [7:0] triangle = phase[23] ? ~phase[22:15] : phase[22:15];
reg [14:0] lfsr;
reg signed [7:0] sample_value;
always @* begin
    if (mix_voice == 3) sample_value = lfsr[0] ? 8'sd127 : -8'sd127;
    else case (cfg[1:0])
        0: sample_value = position < cfg[38:31] ? 8'sd127 : -8'sd127;
        1: sample_value = $signed(triangle ^ 8'h80);
        2: sample_value = $signed(position ^ 8'h80);
        default: sample_value = 0;
    endcase
end
// Shared signed 8x4 shift/add scaler, adder and envelope datapath.
reg signed [12:0] multiplicand, product;
reg [3:0] multiplier;
reg [1:0] scale_bit;
reg signed [14:0] sum;
wire signed [14:0] mixed = sum + {{2{product[12]}},product};
wire signed [14:0] normalized = (mixed >>> 6) >>> master[3:2];
wire [24:0] advanced_phase = {1'b0,phase} + {1'b0,cfg[30:7]};
always @(posedge i_clk) begin
    if (i_reset) begin
        staging <= 0; master <= 0; voice <= 0; operation <= 0;
        pending <= 0; frame_pending <= 0; playing <= 0;
        initializing <= 1; clear_addr <= 0; state <= IDLE;
        counter <= 0; duty <= 128; next_duty <= 128;
        ms_count <= 0; ms_epoch <= 0;
        mix_voice <= 0; word_index <= 0; work <= 0; lfsr <= 1;
        sum <= 0; product <= 0; multiplicand <= 0;
        multiplier <= 0; scale_bit <= 0;
    end else begin
        counter <= counter + 1'b1;
        if (ms_tick) begin ms_count <= 0; ms_epoch <= ms_epoch + 1'b1; end
        else ms_count <= ms_count + 1'b1;
        if (initializing) begin
            clear_addr <= clear_addr + 1'b1;
            if (clear_addr == 31) initializing <= 0;
        end else if (frame) begin
            duty <= (!master[0] || master[1]) ? 8'd128 : next_duty;
            frame_pending <= pending;
            mix_voice <= 0; word_index <= 0; sum <= 0;
            state <= READ_WAIT;
        end else case (state)
            IDLE: begin end
            READ_WAIT: state <= READ_TAKE;
            READ_TAKE: begin
                work <= {ram_data,work[111:16]};
                if (word_index == 6) begin word_index <= 0; state <= ENVELOPE; end
                else begin word_index <= word_index + 1'b1; state <= READ_WAIT; end
            end
            ENVELOPE: begin
                // Every voice is visited each frame. Epoch differences are at
                // most one tick at supported clocks, including 8-bit wrap.
                work[100:93] <= ms_epoch;
                if (work[100:93] != ms_epoch && envelope != 0) begin
                    if (envelope == 1) begin
                        if (cfg[46:39] == 0 || elapsed >= cfg[46:39]-1'b1) begin
                            work[92:85] <= 0;
                            if (cfg[46:39] == 0 || level >= cfg[6:3]-1'b1) begin
                                work[82:79] <= cfg[54:47] == 0 ? 4'd0 : cfg[6:3];
                                work[84:83] <= cfg[54:47] == 0 ? 2'd0 : 2'd2;
                            end else work[82:79] <= level + 1'b1;
                        end else work[92:85] <= elapsed + 1'b1;
                    end else begin
                        if (cfg[54:47] == 0 || elapsed >= cfg[54:47]-1'b1) begin
                            work[92:85] <= 0;
                            if (cfg[54:47] == 0 || level <= 1) begin
                                work[82:79] <= 0; work[84:83] <= 0;
                            end else work[82:79] <= level - 1'b1;
                        end else work[92:85] <= elapsed + 1'b1;
                    end
                end
                state <= COMMAND;
            end
            COMMAND: begin
                if (frame_pending[mix_voice]) begin
                    if (operation == 2) begin
                        work[82:79] <= 0; work[84:83] <= 0; work[92:85] <= 0;
                    end else begin
                        work[54:0] <= staging;
                        if (operation == 1) begin
                            work[78:55] <= 0; work[92:85] <= 0;
                            work[100:93] <= ms_epoch;
                            if (mix_voice == 3) lfsr <= 1;
                            if (!staging[2] || staging[6:3] == 0) begin
                                work[82:79] <= staging[6:3]; work[84:83] <= 0;
                            end else begin
                                work[82:79] <= staging[46:39] == 0 && staging[54:47] != 0 ? staging[6:3] : 4'd0;
                                work[84:83] <= staging[46:39] == 0 ? (staging[54:47] == 0 ? 2'd0 : 2'd2) : 2'd1;
                            end
                        end else if (!staging[2] || staging[6:3] == 0) begin
                            work[82:79] <= staging[6:3]; work[84:83] <= 0;
                        end else if (level > staging[6:3]) work[82:79] <= staging[6:3];
                    end
                end
                state <= SAMPLE;
            end
            SAMPLE: begin
                multiplicand <= {{5{sample_value[7]}},sample_value};
                multiplier <= level; product <= 0; scale_bit <= 0;
                playing[mix_voice] <= (level != 0) || (envelope != 0);
                state <= SCALE;
            end
            SCALE: begin
                if (multiplier[0]) product <= product + multiplicand;
                multiplicand <= multiplicand <<< 1; multiplier <= multiplier >> 1;
                scale_bit <= scale_bit + 1'b1;
                if (scale_bit == 3) state <= SUM;
            end
            SUM: begin
                sum <= mixed;
                work[78:55] <= advanced_phase[23:0];
                // x^15+x^14+1, nonzero seed, period 32767 shifts.
                if (mix_voice == 3 && advanced_phase[24])
                    lfsr <= {lfsr[13:0],lfsr[14]^lfsr[13]};
                if (mix_voice == 3) begin
                    if (normalized > 127) next_duty <= 255;
                    else if (normalized < -128) next_duty <= 0;
                    else next_duty <= normalized[7:0] ^ 8'h80;
                end
                state <= STORE;
            end
            STORE: begin
                work <= {16'b0,work[111:16]};
                if (word_index == 6) begin
                    if (frame_pending[mix_voice]) pending[mix_voice] <= 0;
                    word_index <= 0;
                    if (mix_voice == 3) state <= IDLE;
                    else begin mix_voice <= mix_voice + 1'b1; state <= READ_WAIT; end
                end else word_index <= word_index + 1'b1;
            end
            default: state <= IDLE;
        endcase
        if (i_cs && i_we && o_ready) begin
            case (i_addr)
                0: master <= i_data[3:0];
                // Selection changes the target, not the common staging bank.
                1: voice <= i_data[1:0];
                2: staging[2:0] <= i_data[2:0];
                3: staging[6:3] <= i_data[3:0];
                4: staging[14:7] <= i_data;
                5: staging[22:15] <= i_data;
                6: staging[30:23] <= i_data;
                7: staging[38:31] <= i_data;
                8: staging[46:39] <= i_data;
                9: staging[54:47] <= i_data;
                10: begin
                    if (i_data[3]) begin pending <= 15; operation <= 2; end
                    else if (|i_data[2:0]) begin
                        pending[voice] <= 1;
                        operation <= i_data[2] ? 2'd2 : i_data[1] ? 2'd1 : 2'd0;
                    end
                end
                default: begin end
            endcase
        end
    end
end
`ifndef SYNTHESIS
always @(posedge i_clk) if (!i_reset && !initializing && frame && state != IDLE)
    $fatal(1,"audio: frame processing overrun");
initial if (CLK_HZ < 256000 || CLK_HZ % 1000 != 0)
    $fatal(1,"audio: CLK_HZ must be a multiple of 1000 and at least 256000");
`endif
endmodule
