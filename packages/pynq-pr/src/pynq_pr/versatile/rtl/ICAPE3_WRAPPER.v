module ICAPE3_WRAPPER (
	input wire 		  clk,
	input wire 		  rstn,
	input wire        ICAP_CSIB,
	input wire [31:0] ICAP_DATA,
	input wire        ICAP_RDWRB,
	output wire       ICAP_AVAIL,
	output wire       ICAP_PRDONE,
	output wire       ICAP_PRERROR
);
	// ICAPE data needs to be word reversed when generated using vivado write_bitstream
	// Original VERSATILE wrapper did it in firmware but we can do it in hardware for free!
	reg [31:0] DATA_Reversed;
	reg rdwrb_reg;
	reg csib_reg;
	
	always @(posedge clk) begin
		if (rstn == 0) begin
			DATA_Reversed <= 0;
			rdwrb_reg <= 0;
			csib_reg <= 1;
			
		end else begin
			DATA_Reversed <= {ICAP_DATA[0],  ICAP_DATA[1],  ICAP_DATA[2],  ICAP_DATA[3],
			                  ICAP_DATA[4],  ICAP_DATA[5],  ICAP_DATA[6],  ICAP_DATA[7],
			                  ICAP_DATA[8],  ICAP_DATA[9],  ICAP_DATA[10], ICAP_DATA[11],
			                  ICAP_DATA[12], ICAP_DATA[13], ICAP_DATA[14], ICAP_DATA[15],
			                  ICAP_DATA[16], ICAP_DATA[17], ICAP_DATA[18], ICAP_DATA[19],
			                  ICAP_DATA[20], ICAP_DATA[21], ICAP_DATA[22], ICAP_DATA[23],
			                  ICAP_DATA[24], ICAP_DATA[25], ICAP_DATA[26], ICAP_DATA[27],
			                  ICAP_DATA[28], ICAP_DATA[29], ICAP_DATA[30], ICAP_DATA[31]};
		rdwrb_reg <= ICAP_RDWRB;
		csib_reg  <= ICAP_CSIB;
		end
	end

	wire [31:0] ICAP_O;
	ICAPE3 #(
	.DEVICE_ID(32'h03628093),     // Specifies the pre-programmed Device ID value to be used for simulation purposes.
	.ICAP_AUTO_SWITCH("DISABLE"), // Enable switch ICAP using sync word.
	.SIM_CFG_FILE_NAME("NONE")    // Specifies the Raw Bitstream (RBT) file to be parsed by the simulation model.
	)
	ICAPE3_inst (
	.AVAIL(ICAP_AVAIL),     // 1-bit output: Availability status of ICAP.
	.O(ICAP_O),             // 32-bit output: Configuration data output bus.
	.PRDONE(ICAP_PRDONE),   // 1-bit output: Indicates completion of Partial Reconfiguration.
	.PRERROR(ICAP_PRERROR), // 1-bit output: Indicates error during Partial Reconfiguration.
	.CLK(clk),         // 1-bit input: Clock input.
	.CSIB(csib_reg),   // 1-bit input: Active-Low ICAP enable.
	.I(DATA_Reversed), // 32-bit input: Configuration data input bus.
	.RDWRB(rdwrb_reg)  // 1-bit input: Read/Write Select input.
	);


endmodule