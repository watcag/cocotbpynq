module icape3_wrapper (
	input wire         clk,
	input wire         csib,
	input wire [31:0]  i,
	input wire         rdwrb,
	output wire [31:0] o,
	output wire        avail,
	output wire        prdone,
	output wire        prerror
);

	ICAPE3 #(
		.DEVICE_ID(32'h03628093),
		.ICAP_AUTO_SWITCH("DISABLE"),
		.SIM_CFG_FILE_NAME("NONE")
	)
	icape3_inst (
		.AVAIL(avail),
		.O(o),
		.PRDONE(prdone),
		.PRERROR(prerror),
		.CLK(clk),
		.CSIB(csib),
		.I(i),
		.RDWRB(rdwrb)
	);

endmodule
