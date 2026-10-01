
wire kernel_monitor_reset;
wire kernel_monitor_clock;
wire kernel_monitor_report;
assign kernel_monitor_reset = ~ap_rst_n;
assign kernel_monitor_clock = ap_clk;
assign kernel_monitor_report = 1'b0;
wire [1:0] axis_block_sigs;
wire [9:0] inst_idle_sigs;
wire [4:0] inst_block_sigs;
wire kernel_block;

assign axis_block_sigs[0] = ~stream_to_gray_U0.grp_stream_to_gray_Pipeline_stream_to_gray_loop_fu_54.x_TDATA_blk_n;
assign axis_block_sigs[1] = ~gray_to_stream_U0.grp_gray_to_stream_Pipeline_gray_to_stream_loop_fu_66.y_TDATA_blk_n;

assign inst_idle_sigs[0] = Block_entry1_proc_U0.ap_idle;
assign inst_block_sigs[0] = (Block_entry1_proc_U0.ap_done & ~Block_entry1_proc_U0.ap_continue) | ~Block_entry1_proc_U0.rows_c11_blk_n | ~Block_entry1_proc_U0.cols_c12_blk_n;
assign inst_idle_sigs[1] = stream_to_gray_U0.ap_idle;
assign inst_block_sigs[1] = (stream_to_gray_U0.ap_done & ~stream_to_gray_U0.ap_continue) | ~stream_to_gray_U0.grp_stream_to_gray_Pipeline_stream_to_gray_loop_fu_54.img_in_data63_blk_n;
assign inst_idle_sigs[2] = Sobel_0_3_0_3_1080_1920_1_false_2_2_2_U0.ap_idle;
assign inst_block_sigs[2] = (Sobel_0_3_0_3_1080_1920_1_false_2_2_2_U0.ap_done & ~Sobel_0_3_0_3_1080_1920_1_false_2_2_2_U0.ap_continue) | ~Sobel_0_3_0_3_1080_1920_1_false_2_2_2_U0.grp_xFSobelFilter3x3_0_3_1080_1920_1_0_4_1_2_2_2_1_6_1920_false_s_fu_36.grp_xFSobelFilter3x3_Pipeline_Col_Loop_fu_157.img_in_data63_blk_n | ~Sobel_0_3_0_3_1080_1920_1_false_2_2_2_U0.grp_xFSobelFilter3x3_0_3_1080_1920_1_0_4_1_2_2_2_1_6_1920_false_s_fu_36.grp_xFSobelFilter3x3_Pipeline_Clear_Row_Loop_fu_148.img_in_data63_blk_n | ~Sobel_0_3_0_3_1080_1920_1_false_2_2_2_U0.grp_xFSobelFilter3x3_0_3_1080_1920_1_0_4_1_2_2_2_1_6_1920_false_s_fu_36.grp_xFSobelFilter3x3_Pipeline_Col_Loop_fu_157.grad_x_data65_blk_n | ~Sobel_0_3_0_3_1080_1920_1_false_2_2_2_U0.grp_xFSobelFilter3x3_0_3_1080_1920_1_0_4_1_2_2_2_1_6_1920_false_s_fu_36.grad_x_data65_blk_n | ~Sobel_0_3_0_3_1080_1920_1_false_2_2_2_U0.grp_xFSobelFilter3x3_0_3_1080_1920_1_0_4_1_2_2_2_1_6_1920_false_s_fu_36.grp_xFSobelFilter3x3_Pipeline_Col_Loop_fu_157.grad_y_data66_blk_n | ~Sobel_0_3_0_3_1080_1920_1_false_2_2_2_U0.grp_xFSobelFilter3x3_0_3_1080_1920_1_0_4_1_2_2_2_1_6_1920_false_s_fu_36.grad_y_data66_blk_n;
assign inst_idle_sigs[3] = sobel_mag_to_gray_U0.ap_idle;
assign inst_block_sigs[3] = (sobel_mag_to_gray_U0.ap_done & ~sobel_mag_to_gray_U0.ap_continue) | ~sobel_mag_to_gray_U0.grp_sobel_mag_to_gray_Pipeline_sobel_mag_to_gray_loop_fu_70.grad_x_data65_blk_n | ~sobel_mag_to_gray_U0.grp_sobel_mag_to_gray_Pipeline_sobel_mag_to_gray_loop_fu_70.grad_y_data66_blk_n | ~sobel_mag_to_gray_U0.grp_sobel_mag_to_gray_Pipeline_sobel_mag_to_gray_loop_fu_70.img_out_data64_blk_n | ~sobel_mag_to_gray_U0.rows_blk_n | ~sobel_mag_to_gray_U0.cols_blk_n | ~sobel_mag_to_gray_U0.rows_c_blk_n | ~sobel_mag_to_gray_U0.cols_c_blk_n;
assign inst_idle_sigs[4] = gray_to_stream_U0.ap_idle;
assign inst_block_sigs[4] = (gray_to_stream_U0.ap_done & ~gray_to_stream_U0.ap_continue) | ~gray_to_stream_U0.grp_gray_to_stream_Pipeline_gray_to_stream_loop_fu_66.img_out_data64_blk_n | ~gray_to_stream_U0.rows_blk_n | ~gray_to_stream_U0.cols_blk_n;

assign inst_idle_sigs[5] = 1'b0;
assign inst_idle_sigs[6] = stream_to_gray_U0.ap_idle;
assign inst_idle_sigs[7] = stream_to_gray_U0.grp_stream_to_gray_Pipeline_stream_to_gray_loop_fu_54.ap_idle;
assign inst_idle_sigs[8] = gray_to_stream_U0.ap_idle;
assign inst_idle_sigs[9] = gray_to_stream_U0.grp_gray_to_stream_Pipeline_gray_to_stream_loop_fu_66.ap_idle;

sobel_mag_hls_hls_deadlock_idx0_monitor sobel_mag_hls_hls_deadlock_idx0_monitor_U (
    .clock(kernel_monitor_clock),
    .reset(kernel_monitor_reset),
    .axis_block_sigs(axis_block_sigs),
    .inst_idle_sigs(inst_idle_sigs),
    .inst_block_sigs(inst_block_sigs),
    .block(kernel_block)
);


always @ (kernel_block or kernel_monitor_reset) begin
    if (kernel_block == 1'b1 && kernel_monitor_reset == 1'b0) begin
        find_kernel_block = 1'b1;
    end
    else begin
        find_kernel_block = 1'b0;
    end
end
