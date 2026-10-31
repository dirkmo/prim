// 25 MHz, 640x480, 80x30 monochrome text. One EBR read port and one
// independent write port: video reserves one read slot per eight pixels.
module vga_text(
    input i_clk, i_reset,
    input i_cs, i_we,
    input [11:0] i_addr,
    input [7:0] i_data,
    output [7:0] o_data,
    output o_ack,
    input i_reg_cs,
    input [2:0] i_reg_addr,
    output reg [7:0] o_reg_data,
    output o_bank,
    output o_hsync, o_vsync, o_pixel, o_active
);
reg [4:0] control;
reg [4:0] row_offset, cursor_y;
reg [6:0] cursor_x;
reg [9:0] h;
reg [9:0] v;
reg [4:0] blink_frames;
wire active = h < 640 && v < 480;
wire video_fetch = active && h[2:0] == 0;
wire [4:0] physical_row = v[8:4] + row_offset;
wire [11:0] video_addr = {physical_row,6'b0} + {physical_row,4'b0} + {5'b0,h[9:3]};

reg [7:0] ram [0:4095];
reg [7:0] ram_data;
reg [7:0] cpu_data;
integer n;
initial for (n=0; n<4096; n=n+1) ram[n] = 8'h20;
localparam IDLE=0, READ_WAIT=1, DONE=2;
reg [1:0] state;
wire cpu_read = !i_reset && i_cs && !i_we && state == IDLE && !video_fetch;
wire cpu_write = !i_reset && i_cs && i_we && state == IDLE;
// No RAM reset or write-through bypass: infer exactly one read/write port.
always @(posedge i_clk) begin
    if (cpu_write) ram[i_addr] <= i_data;
    if (video_fetch || cpu_read) ram_data <= ram[video_fetch ? video_addr : i_addr];
end
assign o_data = cpu_data;
assign o_ack = !i_reset && state == DONE;
assign o_bank = control[0];

reg fetch_d;
reg [3:0] scan_d;
reg [2:0] bit_d, bit_dd;
reg [1:0] hs_pipe, vs_pipe, active_pipe, cursor_pipe;
wire [7:0] glyph;
vga_font font(.i_clk(i_clk), .i_en(fetch_d),
    .i_addr({ram_data,scan_d}), .o_data(glyph));
wire cursor = control[2] && h[9:3] == cursor_x && v[8:4] == cursor_y &&
    (!control[3] || !blink_frames[4]) && (!control[4] || v[3:0] == 15);
assign o_hsync = i_reset ? 1'b1 : hs_pipe[1];
assign o_vsync = i_reset ? 1'b1 : vs_pipe[1];
assign o_active = !i_reset && active_pipe[1];
assign o_pixel = o_active && control[1] && (glyph[7-bit_dd] || cursor_pipe[1]);

always @* begin
    case (i_reg_addr)
        0: o_reg_data = {3'b0,control};
        1: o_reg_data = {3'b0,row_offset};
        2: o_reg_data = {1'b0,cursor_x};
        3: o_reg_data = {3'b0,cursor_y};
        4: o_reg_data = {6'b0,v >= 480,!active};
        default: o_reg_data = 0;
    endcase
end
always @(posedge i_clk) begin
    if (i_reset) begin
        control <= 0; row_offset <= 0; cursor_x <= 0; cursor_y <= 0;
        h <= 0; v <= 0; blink_frames <= 0;
        state <= IDLE; fetch_d <= 0; scan_d <= 0;
        bit_d <= 0; bit_dd <= 0;
        hs_pipe <= 3; vs_pipe <= 3; active_pipe <= 0; cursor_pipe <= 0;
    end else begin
        case (state)
            IDLE: if (cpu_write) state <= DONE;
                  else if (cpu_read) state <= READ_WAIT;
            READ_WAIT: begin cpu_data <= ram_data; state <= DONE; end
            DONE: state <= IDLE;
            default: state <= IDLE;
        endcase
        if (i_reg_cs && i_we) begin
            case (i_reg_addr)
                0: control <= i_data[4:0];
                1: row_offset <= i_data[4:0];
                2: cursor_x <= i_data[6:0];
                3: cursor_y <= i_data[4:0];
            endcase
        end
        if (h == 799) begin
            h <= 0;
            if (v == 524) begin v <= 0; blink_frames <= blink_frames + 1'b1; end
            else v <= v + 1'b1;
        end else h <= h + 1'b1;
        fetch_d <= video_fetch;
        scan_d <= v[3:0];
        bit_d <= h[2:0]; bit_dd <= bit_d;
        hs_pipe <= {hs_pipe[0],!(h >= 656 && h < 752)};
        vs_pipe <= {vs_pipe[0],!(v >= 490 && v < 492)};
        active_pipe <= {active_pipe[0],active};
        cursor_pipe <= {cursor_pipe[0],cursor};
    end
end
endmodule
