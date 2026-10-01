`timescale 1ps / 1ps

module ping_pong_control
(
    input  wire                    clk,
    input  wire                    rst,
    input  wire                    tlast_A_flag,
    input  wire                    done_rd,
    input  wire                    done_wr,
    input  wire                    done_wr_early,   //for stalling axi
    output reg   [1:0]             blk_0,           //{rd_en,wr_en}
    output reg   [1:0]             blk_1,           //{rd_en,wr_en}
    output reg                     stall_axi_b
);

typedef enum {A,B,C,D,F,G,H,I,C_0,C_1,F_0,F_1,I_0,I_1} states;

states curr_state, next_state;

always @(posedge clk) begin
    if (rst) curr_state <= A;
    else curr_state <= next_state;
end

always_comb begin : next_state_assignment
    case (curr_state)
    A: begin
        case ({done_wr,tlast_A_flag})
        2'b00: next_state = A;
        2'b01: next_state = A;
        2'b10: next_state = B;
        2'b11: next_state = D;
        endcase
    end
    B: begin
        // $display("Done %0b",{done_wr_early,done_wr,tlast_A_flag});
        case ({done_wr_early,done_wr,tlast_A_flag})
        3'b0_01: next_state = D;
        3'b1_00: next_state = C_0; //C_0
        3'b1_01: next_state = F_0; //F_0
        default: next_state = B;
        endcase
    end
    C: next_state = (tlast_A_flag) ? F : C;
    C_0: begin
        case ({done_wr,tlast_A_flag})
        2'b00: next_state = C_0;
        2'b01: next_state = C_1;
        2'b10: next_state = C;
        2'b11: next_state = F;
        endcase
    end
    C_1: next_state = (done_wr) ? F : C_1;
    D: begin
        case ({done_wr_early,done_wr,done_rd})
        3'b0_01: next_state = G;
        3'b1_01: next_state = G;
        3'b1_00: next_state = F_0;  //F_0
        3'b0_11: next_state = H;
        default: next_state = D;
        endcase
    end
    F: next_state = (done_rd) ? H : F;
    F_0: begin
       case ({done_wr,done_rd})
        2'b00: next_state = F_0;
        2'b01: next_state = F_1;
        2'b10: next_state = F;
        2'b11: next_state = H;
        endcase
    end
    F_1: next_state = (done_wr) ? H : F_1;
    G:   next_state = (done_wr) ? H : G;
    H: begin
        case ({done_wr_early,done_wr,done_rd})
        3'b0_01: next_state = A;
        3'b1_01: next_state = A;
        3'b1_00: next_state = I_0; //I_0
        3'b0_11: next_state = D;
        default: next_state = H;
        endcase
    end
    I: next_state = (done_rd) ? D: I;
    I_0: begin
       case ({done_wr,done_rd})
        2'b00: next_state = I_0;
        2'b01: next_state = I_1;
        2'b10: next_state = I;
        2'b11: next_state = D;
        endcase
    end
    I_1: next_state = (done_wr) ? D : I_1;
    default: next_state = A;
    endcase
end

always_comb begin : output_assignment
    case(curr_state)
    A: begin 
            stall_axi_b = 1'b0;
            blk_0 = 2'b01;
            blk_1 = 2'b00;
        end
    B: begin 
            stall_axi_b = 1'b0;
            blk_0 = 2'b00;
            blk_1 = 2'b01;
        end
    C: begin 
            stall_axi_b = 1'b1;
            blk_0 = 2'b00;
            blk_1 = 2'b00;
        end
    C_0: begin 
            stall_axi_b = 1'b1;
            blk_0 = 2'b00;
            blk_1 = 2'b01;
        end
    C_1: begin 
            stall_axi_b = 1'b1;
            blk_0 = 2'b10;
            blk_1 = 2'b01;
        end
    D: begin 
            stall_axi_b = 1'b0;
            blk_0 = 2'b10;
            blk_1 = 2'b01;
        end
    F: begin 
            stall_axi_b = 1'b1;
            blk_0 = 2'b10;
            blk_1 = 2'b00;
        end
    F_0: begin 
            stall_axi_b = 1'b1;
            blk_0 = 2'b10;
            blk_1 = 2'b01;
        end
    F_1: begin 
            stall_axi_b = 1'b1;
            blk_0 = 2'b00;
            blk_1 = 2'b01;
        end
    G: begin 
            stall_axi_b = 1'b0;
            blk_0 = 2'b00;
            blk_1 = 2'b01;
        end
    H: begin 
            stall_axi_b = 1'b0;
            blk_0 = 2'b01;
            blk_1 = 2'b10;
        end
    I: begin 
            stall_axi_b = 1'b1;
            blk_0 = 2'b00;
            blk_1 = 2'b10;
        end
    I_0: begin 
            stall_axi_b = 1'b1;
            blk_0 = 2'b01;
            blk_1 = 2'b10;
        end
    I_1: begin 
            stall_axi_b = 1'b1;
            blk_0 = 2'b01;
            blk_1 = 2'b00;
        end
    default: begin 
            stall_axi_b = 1'b0;
            blk_0 = 2'b01;
            blk_1 = 2'b00;
    end
    endcase
end
endmodule
