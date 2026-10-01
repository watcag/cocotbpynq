`timescale 1ps / 1ps

module softmax
#(
    parameter integer D_W      = 8,
    parameter integer D_W_ACC  = 32,
    parameter integer N        = 32,
    parameter integer FP_BITS  = 30,
    parameter integer MAX_BITS = 30,
    parameter integer OUT_BITS = 6
)
(
    input  wire                      clk,
    input  wire                      rst,
    input  wire                      enable,
    input  wire                      in_valid,
    input  wire signed [D_W_ACC-1:0] qin,           // softmax input
    input  wire signed [D_W_ACC-1:0] qb,            // exp coefficient
    input  wire signed [D_W_ACC-1:0] qc,            // exp coefficient
    input  wire signed [D_W_ACC-1:0] qln2,          // exp coefficient
    input  wire signed [D_W_ACC-1:0] qln2_inv,      // exp coefficient
    input  wire        [D_W_ACC-1:0] Sreq,
    output wire                      out_valid,
    output wire signed [D_W-1:0]     qout           // softmax output
);

localparam [D_W_ACC-1:0] DIVIDENT = 1 << MAX_BITS;
localparam integer          SHIFT = MAX_BITS - OUT_BITS;
/* verilator lint_off WIDTHEXPAND */

reg                         in_v_r;
reg  signed   [D_W_ACC-1:0] qin_r;
reg           [D_W_ACC-1:0] Sreq_r;

wire signed   [D_W_ACC-1:0] qmax_out;
reg  signed   [D_W_ACC-1:0] qmax_out_r;
wire                        qmax_init;
reg           [$clog2(N):0] qmax_cntr;
reg                         qmax_out_v;

reg                         qexp_in_v_r, qexp_in_v_r1;
reg  signed   [D_W_ACC-1:0] qexp_in_r;
reg           [$clog2(N):0] qexp_cntr;
wire                        qexp_out_v;
reg                         qexp_out_v_r;
wire signed   [D_W_ACC-1:0] qexp_out;
reg  signed [2*D_W_ACC-1:0] qreq_mul;
reg                         qreq_round;

reg                         qacc_in_v_r;
reg  signed   [D_W_ACC-1:0] qacc_in_r;
wire                        qacc_init;
reg           [$clog2(N):0] qacc_cntr;
reg                         qacc_out_v;
wire signed   [D_W_ACC-1:0] qacc_out;

wire                        qdiv_out_v;
reg                         qdiv_out_v_r;
reg           [$clog2(N):0] qdiv_cntr;
wire signed   [D_W_ACC-1:0] qdiv_out;
reg  signed   [D_W_ACC-1:0] qdiv_out_r, qdiv_out_r1;

reg           [$clog2(N):0] qout_cntr;
reg                         qout_v_r, qout_v_r1, qout_v_r2;
reg  signed       [D_W-1:0] qout_r;
reg  signed [2*D_W_ACC-1:0] qout_mul;

reg                         max_buf_write;
reg                         max_buf_read;
reg  signed   [D_W_ACC-1:0] max_buf_wrdata;
wire signed   [D_W_ACC-1:0] max_buf_rddata;

reg                         acc_buf_write;
reg                         acc_buf_read;
reg  signed   [D_W_ACC-1:0] acc_buf_wrdata;
wire signed   [D_W_ACC-1:0] acc_buf_rddata;

reg                         div_buf_write;
reg                         div_buf_read;
reg  signed   [D_W_ACC-1:0] div_buf_wrdata;
wire signed   [D_W_ACC-1:0] div_buf_rddata;

assign qmax_init = in_v_r & (qmax_cntr == 0);
assign qacc_init = qacc_in_v_r & (qacc_cntr == 0);
assign out_valid = qout_v_r2;
assign qout      = qout_r;

// Writing to MAX Buffer
always @(posedge clk) begin
    if (rst) begin
        qin_r  <= 0;
        in_v_r <= 0;
        Sreq_r <= 0;

        max_buf_write  <= 0;
        max_buf_wrdata <= 0;

        qmax_cntr  <= 0;
        qmax_out_v <= 0;
        qmax_out_r <= 0;
    end else if (enable) begin
        qin_r <= qin;
        in_v_r <= in_valid;
        Sreq_r <= Sreq;
        
        qmax_out_v <= 0;
        
        if (in_v_r) begin
            qmax_cntr <= qmax_cntr + 1;
            if (qmax_cntr == N-1) begin
                qmax_cntr <= 0;
                qmax_out_v <= 1;
            end
        end

        max_buf_wrdata <= qin_r;
        max_buf_write  <= in_v_r;
        
        if (qmax_out_v) begin
            qmax_out_r <= qmax_out;
            // $display("qmax=%0d",qmax_out);
        end
    end
end

// Reading from MAX Buffer
always @(posedge clk) begin
    if (rst) begin
        max_buf_read <= 0;
        qexp_cntr    <= 0;
        qexp_in_r    <= 0;
        qexp_in_v_r  <= 0;
        qexp_in_v_r1 <= 0;
    end else if (enable) begin
        if (qmax_out_v) begin
            qexp_in_v_r <= 1;
            max_buf_read <= 1;
        end else if (qexp_in_v_r && qexp_cntr == N-1) begin
            qexp_in_v_r <= 0;
            max_buf_read <= 0;
        end

        if (qexp_in_v_r) begin
            qexp_cntr <= qexp_cntr + 1;
            if (qexp_cntr == N-1) begin
                qexp_cntr <= 0;
            end
        end

        qexp_in_v_r1 <= qexp_in_v_r;
        qexp_in_r <= max_buf_rddata - qmax_out_r;

        // if (qexp_in_v_r1)
        //     $display("qexp_in=%0d",qexp_in_r);
    end
end

// Writing to ACC Buffer
always @(posedge clk) begin
    if (rst) begin
        qacc_in_r   <= 0;
        qacc_in_v_r <= 0;
        qacc_cntr   <= 0;

        qexp_out_v_r <= 0;

        acc_buf_write  <= 0;
        acc_buf_wrdata <= 0;

        qacc_out_v <= 0;
        qreq_round <= 0;
    end else if (enable) begin
        qreq_mul    <= qexp_out * Sreq_r;
        qacc_in_r   <= qreq_mul[FP_BITS-1] ? qreq_mul[2*D_W_ACC-1:FP_BITS] + 1 : qreq_mul[2*D_W_ACC-1:FP_BITS];     // rounding
        qexp_out_v_r <= qexp_out_v;
        qacc_in_v_r  <= qexp_out_v_r;
        
        qacc_out_v <= 0;

        // if (qexp_out_v)
        //     $display("qexp_out=%0d",qexp_out);
        
        // if (qacc_in_v_r)
        //     $display("qreq=%0d",qacc_in_r);

        if (qacc_in_v_r) begin
            qacc_cntr <= qacc_cntr + 1;
            if (qacc_cntr == N-1) begin
                qacc_cntr <= 0;
                qacc_out_v <= 1;
            end
        end

        acc_buf_wrdata <= qacc_in_r;
        acc_buf_write  <= qacc_in_v_r;

        // if (qacc_out_v)
        //     $display("qacc=%0d",qacc_out);
    end
end

// Reading from ACC Buffer
// Writing to DIV Buffer
always @(posedge clk) begin
    if (rst) begin
        div_buf_write <= 0;
        div_buf_wrdata <= 0;
        qdiv_out_r    <= 0;
        acc_buf_read  <= 0;
        qdiv_out_v_r <= 0;
        qdiv_cntr     <= 0;
    end else if (enable) begin
        qdiv_out_v_r <= 0;

        if (qacc_out_v) begin
            acc_buf_read <= 1;
        end else if (acc_buf_read && qdiv_cntr == N-1) begin
            acc_buf_read <= 0;
        end

        if (acc_buf_read) begin
            qdiv_cntr <= qdiv_cntr + 1;
            if (qdiv_cntr == N-1) begin
                qdiv_cntr <= 0;
            end
            if (qdiv_cntr == 31) begin
                qdiv_out_v_r <= 1;
            end
        end

        div_buf_write <= acc_buf_read;
        div_buf_wrdata <= acc_buf_rddata;

        if (qdiv_out_v) begin
            qdiv_out_r <= qdiv_out;
        end
    end
end

// Reading from DIV Buffer
always @(posedge clk) begin
    if (rst) begin
        qout_cntr <= 0;
        qout_r    <= 0;
        qout_v_r  <= 0;
        qout_v_r2 <= 0;
        div_buf_read <= 0;
        qdiv_out_r1 <= 0;
        qout_v_r1 <= 0;
        qout_mul <= 0;
    end else if (enable) begin
        if (qdiv_out_v_r) begin
            qout_v_r <= 1;
            div_buf_read <= 1;
            qdiv_out_r1 <= qdiv_out_r;
        end else if (qout_v_r && qout_cntr == N-1) begin
            qout_v_r <= 0;
            div_buf_read <= 0;
        end

        if (qout_v_r) begin
            qout_cntr <= qout_cntr + 1;
            if (qout_cntr == N-1) begin
                qout_cntr <= 0;
            end
        end

        qout_v_r1 <= qout_v_r;

        qout_mul  <= div_buf_rddata * qdiv_out_r1;
        qout_r    <= qout_mul >> SHIFT;
        qout_v_r2 <= qout_v_r1;

        // if (qout_v_r1)
        //     $display("#time=%0d, qreq=%0d,qdiv=%0d,res=%0d",$time,div_buf_rddata,qdiv_out_r1,qout_mul >> SHIFT);
    end
end

sreg #(.D_W(D_W_ACC), .DEPTH(N))
max_sreg (
    .clk      ( clk            ),
    .rst      ( rst            ),
    .shift_en ( enable & (max_buf_write | max_buf_read) ),
    .data_in  ( max_buf_wrdata ),
    .data_out ( max_buf_rddata )
);

sreg #(.D_W(D_W_ACC), .DEPTH(N))
acc_sreg (
    .clk      ( clk            ),
    .rst      ( rst            ),
    .shift_en ( enable & (acc_buf_write | acc_buf_read) ),
    .data_in  ( acc_buf_wrdata ),
    .data_out ( acc_buf_rddata )
);

sreg #(.D_W(D_W_ACC), .DEPTH(32))
div_sreg (
    .clk      ( clk            ),
    .rst      ( rst            ),
    .shift_en ( enable & (div_buf_write | div_buf_read) ),
    .data_in  ( div_buf_wrdata ),
    .data_out ( div_buf_rddata )
);

max #(.D_W(D_W_ACC))
qmax (
    .clk        ( clk        ),
    .rst        ( rst        ),
    .enable     ( enable     ),
    .initialize ( qmax_init  ),
    .in_data    ( qin_r      ),
    .result     ( qmax_out   )
);

acc #(.D_W(D_W_ACC))
qacc (
    .clk        ( clk         ),
    .rst        ( rst         ),
    .enable     ( enable      ),
    .initialize ( qacc_init   ),
    .in_data    ( qacc_in_r   ),
    .result     ( qacc_out    )
);

exp #(
    .D_W     ( D_W_ACC ),
    .FP_BITS ( FP_BITS )
)
qexp (
    .clk       ( clk           ),
    .rst       ( rst           ),
    .enable    ( enable        ),
    .in_valid  ( qexp_in_v_r1  ),
    .qin       ( qexp_in_r     ),
    .qb        ( qb            ),
    .qc        ( qc            ),
    .qln2      ( qln2          ),
    .qln2_inv  ( qln2_inv      ),
    .out_valid ( qexp_out_v    ),
    .qout      ( qexp_out      )
);

div #(.D_W(D_W_ACC))
qdiv (
    .clk       ( clk         ),
    .rst       ( rst         ),
    .enable    ( enable      ),
    .in_valid  ( qacc_out_v  ),
    .divisor   ( qacc_out    ),
    .divident  ( DIVIDENT    ),
    .out_valid ( qdiv_out_v  ),
    .quotient  ( qdiv_out    )
);

/* verilator lint_on WIDTHEXPAND */

endmodule
