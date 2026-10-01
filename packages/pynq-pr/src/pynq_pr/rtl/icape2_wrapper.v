module icape2_wrapper (
	input wire         clk,
	input wire         csib,
	input wire [31:0]  i,
	input wire         rdwrb,
	output wire [31:0] o
);

	ICAPE2 #(
		.DEVICE_ID(32'h3651093),
		.ICAP_WIDTH("X32"),
		.SIM_CFG_FILE_NAME("NONE")
	)
	icape2_inst (
		.O(o),
		.CLK(clk),
		.CSIB(csib),
		.I(i),
		.RDWRB(rdwrb)
	);

endmodule
