`timescale 1ns/1ps
module tb_ps2_fifo;
parameter DEPTH=16;
reg clk=0, reset=1, valid=0, error=0, pop=0, csr_write=0;
reg [7:0] data=0, csr_data=0;
always #5 clk=~clk;
wire [7:0] result, csr;
wire event_irq;
ps2_fifo #(.DEPTH(DEPTH)) dut(.i_clk(clk), .i_reset(reset),
    .i_data(data), .i_valid(valid), .i_error(error), .i_pop(pop),
    .i_csr_write(csr_write), .i_csr_data(csr_data),
    .o_data(result), .o_csr(csr), .o_event(event_irq));
// Independent ordered-list model, shifted on dequeue (not hardware pointers).
reg [7:0] model[0:1023];
integer length=0;
bit rxie=0, frame_error=0, overflow=0, expected_event, take, put;
reg [7:0] expected_csr;
task cycle(input bit v, input bit p, input bit e, input bit wr,
           input [7:0] byte_in, input [7:0] control);
    @(negedge clk); valid=v; pop=p; error=e; csr_write=wr; data=byte_in; csr_data=control;
    #1;
    expected_csr={3'b0,overflow,frame_error,rxie,length==DEPTH,length!=0};
    expected_event=rxie&&(v||e);
    if(csr!==expected_csr || result!==(length==0 ? 8'b0 : model[0]) || event_irq!==expected_event)
        $fatal(1,"FIFO state/result/event len=%0d csr=%h expected=%h",length,csr,expected_csr);
    take=p && length!=0; put=v && (length<DEPTH || take);
    @(posedge clk);
    if(wr) begin
        rxie=control[2]; if(control[3]) frame_error=0; if(control[4]) overflow=0;
    end
    if(e) frame_error=1;
    if(v&&!put) overflow=1;
    if(take) begin
        for(integer j=1;j<length;j=j+1) model[j-1]=model[j];
        length=length-1;
    end
    if(put) begin model[length]=byte_in; length=length+1; end
    #1;
    expected_csr={3'b0,overflow,frame_error,rxie,length==DEPTH,length!=0};
    if(csr!==expected_csr || result!==(length==0 ? 8'b0 : model[0]))
        $fatal(1,"FIFO post-edge state len=%0d",length);
endtask
integer seed=12345;
initial begin
    repeat(4) @(negedge clk); reset=0;
    cycle(1,1,0,0,8'h00,0); // Empty read + arrival retains new byte.
    cycle(0,0,0,1,0,4); // Enable with queued data.
    for(integer j=0;j<DEPTH+3;j=j+1) cycle(1,0,0,0,j,0);
    cycle(1,1,0,1,8'hff,8'h1c); // Full pop+push, W1C.
    cycle(1,0,1,1,8'h5a,8'h1c); // Errors win W1C.
    for(integer j=0;j<DEPTH+3;j=j+1) cycle(0,1,0,0,0,0);
    for(integer j=0;j<3000;j=j+1)
        cycle($random(seed)&1,$random(seed)&1,($random(seed)&31)==0,
              ($random(seed)&7)==0,$random(seed),$random(seed));
    @(negedge clk); reset=1;
    @(posedge clk); #1;
    if(csr!==0 || result!==0 || event_irq!==0) $fatal(1,"FIFO reset");
    $display("PASS PS/2 FIFO DEPTH=%0d",DEPTH); $finish;
end
endmodule
