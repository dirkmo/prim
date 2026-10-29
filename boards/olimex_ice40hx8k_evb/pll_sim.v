`timescale 1ns/1ps
// Simulation-only model for the fixed 100 -> 25 MHz configuration in top.v.
// It models output frequency and delayed LOCK, not analog acquisition/jitter.
// The production synthesis uses the real SB_PLL40_CORE primitive, never this file.
module SB_PLL40_CORE #(
    parameter FEEDBACK_PATH="SIMPLE",
    parameter [3:0] DIVR=0,
    parameter [6:0] DIVF=7,
    parameter [2:0] DIVQ=5,
    parameter [2:0] FILTER_RANGE=5
)(
    input REFERENCECLK, RESETB, BYPASS,
    output PLLOUTGLOBAL,
    output reg LOCK=0
);
reg [1:0] divide=0;
reg [4:0] acquisition=0;
assign PLLOUTGLOBAL = BYPASS ? REFERENCECLK : divide[1];
always @(posedge REFERENCECLK) begin
    if (!RESETB) begin divide<=0; acquisition<=0; LOCK<=0; end
    else begin
        divide<=divide+1'b1;
        if(acquisition!=16) acquisition<=acquisition+1'b1;
        else LOCK<=1;
    end
end
initial begin
    if(FEEDBACK_PATH!="SIMPLE" || DIVR!=0 || DIVF!=7 || DIVQ!=5 || FILTER_RANGE!=5)
        $fatal(1,"PLL simulation model requires 100 -> 25 MHz configuration");
end
endmodule
