// Four procedural voices, byte MMIO, one clock domain. See audio/registers.md.
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
// Packed configuration: decay, attack, duty, rate, volume, envelope, waveform.
localparam integer CW = 55;
reg [CW-1:0] staging [0:3];
reg [CW-1:0] active [0:3];
reg [1:0] operation [0:3]; // 0 apply, 1 trigger, 2 stop
reg [3:0] pending;
reg [3:0] master;
reg [1:0] voice;
reg [23:0] phase [0:3];
reg [14:0] lfsr;
reg [3:0] level [0:3];
reg [1:0] envelope [0:3]; // 0 stopped/constant, 1 attack, 2 decay
reg [7:0] elapsed [0:3];
localparam integer MS_DIV = CLK_HZ < 1000 ? 1 : CLK_HZ / 1000;
localparam integer MS_BITS = MS_DIV <= 1 ? 1 : $clog2(MS_DIV);
reg [MS_BITS-1:0] ms_count;
wire ms_tick = ms_count == MS_DIV-1;
reg [7:0] counter, duty, next_duty;
wire frame = counter == 0;
assign o_pwm = counter < duty;
// A command owns staging until its frame commit. Reads never wait.
assign o_ready = !i_we || !(|pending);
wire [3:0] playing;
genvar g;
generate for (g=0;g<4;g=g+1) begin: flags
    assign playing[g] = (level[g] != 0) || (envelope[g] != 0);
end endgenerate
always @* begin
    o_data = 0;
    case (i_addr)
        0: o_data = {4'b0,master};
        1: o_data = {6'b0,voice};
        2: o_data = {5'b0,staging[voice][2:0]};
        3: o_data = {4'b0,staging[voice][6:3]};
        4: o_data = staging[voice][14:7];
        5: o_data = staging[voice][22:15];
        6: o_data = staging[voice][30:23];
        7: o_data = staging[voice][38:31];
        8: o_data = staging[voice][46:39];
        9: o_data = staging[voice][54:47];
        11: o_data = {pending,playing};
        default: o_data = 0;
    endcase
end
// Shared signed 8x4 shift/add scaler and mixer; 6 clocks per voice.
reg [1:0] mix_voice;
reg [2:0] mix_step;
reg busy;
reg signed [12:0] multiplicand, product;
reg [3:0] multiplier;
reg signed [14:0] sum;
reg signed [7:0] sample_value;
wire [7:0] position = phase[mix_voice][23:16];
wire [7:0] triangle = phase[mix_voice][23] ? ~phase[mix_voice][22:15] : phase[mix_voice][22:15];
always @* begin
    if (mix_voice == 3) sample_value = lfsr[0] ? 8'sd127 : -8'sd127;
    else case (active[mix_voice][1:0])
        0: sample_value = position < active[mix_voice][38:31] ? 8'sd127 : -8'sd127;
        1: sample_value = $signed(triangle ^ 8'h80);
        2: sample_value = $signed(position ^ 8'h80);
        default: sample_value = 0;
    endcase
end
wire signed [14:0] mixed = sum + {{2{product[12]}},product};
wire signed [14:0] normalized = (mixed >>> 6) >>> master[3:2];
wire [24:0] advanced_phase = {1'b0,phase[mix_voice]} + {1'b0,active[mix_voice][30:7]};
reg [1:0] env_voice;
reg env_busy;
integer n;
always @(posedge i_clk) begin
    if (i_reset) begin
        master <= 0; voice <= 0; pending <= 0;
        counter <= 0; duty <= 128; next_duty <= 128; ms_count <= 0;
        lfsr <= 15'h1; busy <= 0; mix_voice <= 0; mix_step <= 0;
        env_voice <= 0; env_busy <= 0;
        sum <= 0; product <= 0; multiplicand <= 0; multiplier <= 0;
        for(n=0;n<4;n=n+1) begin
            staging[n] <= 0; active[n] <= 0;
            operation[n] <= 0; phase[n] <= 0; level[n] <= 0;
            envelope[n] <= 0; elapsed[n] <= 0;
        end
    end else begin
        counter <= counter + 1'b1;
        if (ms_tick) ms_count <= 0; else ms_count <= ms_count + 1'b1;
        if (env_busy) begin
            env_voice <= env_voice + 1'b1;
            if (env_voice == 3) env_busy <= 0;
            if (envelope[env_voice] != 0) begin
                if (envelope[env_voice] == 1) begin
                    if (active[env_voice][46:39] == 0 || elapsed[env_voice] >= active[env_voice][46:39]-1'b1) begin
                        elapsed[env_voice] <= 0;
                        if (active[env_voice][46:39] == 0 || level[env_voice] >= active[env_voice][6:3]-1'b1) begin
                            level[env_voice] <= active[env_voice][54:47] == 0 ? 4'd0 : active[env_voice][6:3];
                            envelope[env_voice] <= active[env_voice][54:47] == 0 ? 2'd0 : 2'd2;
                        end else level[env_voice] <= level[env_voice] + 1'b1;
                    end else elapsed[env_voice] <= elapsed[env_voice] + 1'b1;
                end else begin
                    if (active[env_voice][54:47] == 0 || elapsed[env_voice] >= active[env_voice][54:47]-1'b1) begin
                        elapsed[env_voice] <= 0;
                        if (active[env_voice][54:47] == 0 || level[env_voice] <= 1) begin
                            level[env_voice] <= 0; envelope[env_voice] <= 0;
                        end else level[env_voice] <= level[env_voice] - 1'b1;
                    end else elapsed[env_voice] <= elapsed[env_voice] + 1'b1;
                end
            end
        end
        if (ms_tick) begin env_busy <= 1; env_voice <= 0; end
        if (frame) begin
            duty <= (!master[0] || master[1]) ? 8'd128 : next_duty;
            busy <= 1; mix_voice <= 0; mix_step <= 0; sum <= 0;
            for(n=0;n<4;n=n+1) begin
                if (pending[n]) begin
                    pending[n] <= 0;
                    if (operation[n] == 2) begin
                        level[n] <= 0; envelope[n] <= 0; elapsed[n] <= 0;
                    end else begin
                        active[n] <= staging[n];
                        if (operation[n] == 1) begin
                            phase[n] <= 0; elapsed[n] <= 0;
                            if (n == 3) lfsr <= 15'h1;
                            if (!staging[n][2]) begin
                                level[n] <= staging[n][6:3]; envelope[n] <= 0;
                            end else if (staging[n][6:3] == 0) begin
                                level[n] <= 0; envelope[n] <= 0;
                            end else begin
                                level[n] <= staging[n][46:39] == 0 && staging[n][54:47] != 0 ? staging[n][6:3] : 4'd0;
                                envelope[n] <= staging[n][46:39] == 0 ? (staging[n][54:47] == 0 ? 2'd0 : 2'd2) : 2'd1;
                            end
                        end else if (!staging[n][2] || staging[n][6:3] == 0) begin
                            level[n] <= staging[n][6:3]; envelope[n] <= 0;
                        end else if (level[n] > staging[n][6:3]) level[n] <= staging[n][6:3];
                    end
                end
            end
        end else if (busy) begin
            if (mix_step == 0) begin
                multiplicand <= {{5{sample_value[7]}},sample_value};
                multiplier <= level[mix_voice]; product <= 0; mix_step <= 1;
            end else if (mix_step <= 4) begin
                if (multiplier[0]) product <= product + multiplicand;
                multiplicand <= multiplicand <<< 1; multiplier <= multiplier >> 1;
                mix_step <= mix_step + 1'b1;
            end else begin
                sum <= mixed;
                phase[mix_voice] <= advanced_phase[23:0];
                // x^15+x^14+1, left shift, nonzero seed, period 32767.
                if (mix_voice == 3 && advanced_phase[24])
                    lfsr <= {lfsr[13:0],lfsr[14]^lfsr[13]};
                if (mix_voice == 3) begin
                    busy <= 0;
                    if (normalized > 127) next_duty <= 255;
                    else if (normalized < -128) next_duty <= 0;
                    else next_duty <= normalized[7:0] ^ 8'h80;
                end else begin mix_voice <= mix_voice + 1'b1; mix_step <= 0; end
            end
        end
        // Configuration writes wait until pending frame commits finish.
        if (i_cs && i_we && o_ready) begin
            case (i_addr)
                0: master <= i_data[3:0];
                1: voice <= i_data[1:0];
                2: staging[voice][2:0] <= i_data[2:0];
                3: staging[voice][6:3] <= i_data[3:0];
                4: staging[voice][14:7] <= i_data;
                5: staging[voice][22:15] <= i_data;
                6: staging[voice][30:23] <= i_data;
                7: staging[voice][38:31] <= i_data;
                8: staging[voice][46:39] <= i_data;
                9: staging[voice][54:47] <= i_data;
                10: begin
                    if (i_data[3]) begin
                        pending <= 4'b1111;
                        for(n=0;n<4;n=n+1) operation[n] <= 2;
                    end else if (|i_data[2:0]) begin
                        pending[voice] <= 1;
                        operation[voice] <= i_data[2] ? 2'd2 : i_data[1] ? 2'd1 : 2'd0;
                    end
                end
                default: begin end
            endcase
        end
    end
end
endmodule
