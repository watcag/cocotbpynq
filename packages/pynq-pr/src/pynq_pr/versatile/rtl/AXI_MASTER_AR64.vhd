----------------------------------------------------------------------------------
-- Company: 
-- Engineer: 
-- 
-- Create Date: 10/16/2023 01:13:39 PM
-- Design Name: 
-- Module Name: AXI_MASTER_AR - Behavioral
-- Project Name: 
-- Target Devices: 
-- Tool Versions: 
-- Description: 
-- 
-- Dependencies: 
-- 
-- Revision:
-- Revision 0.01 - File Created
-- Additional Comments:
-- 
----------------------------------------------------------------------------------

LIBRARY IEEE;
USE IEEE.STD_LOGIC_1164.ALL;
USE IEEE.STD_LOGIC_UNSIGNED.ALL;

-- Uncomment the following library declaration if using
-- arithmetic functions with Signed or Unsigned values
--use IEEE.NUMERIC_STD.ALL;

-- Uncomment the following library declaration if instantiating
-- any Xilinx leaf cells in this code.
--library UNISIM;
--use UNISIM.VComponents.all;

ENTITY Bitstream_Reader IS
    PORT (
        clk : IN STD_LOGIC;
        rstn : IN STD_LOGIC;
        -- AR CHANNEL
        arvalid : OUT STD_LOGIC;
        arready : IN STD_LOGIC;
        araddr : OUT STD_LOGIC_VECTOR(31 DOWNTO 0);
        arsize : OUT STD_LOGIC_VECTOR(2 DOWNTO 0);
        arburst : OUT STD_LOGIC_VECTOR(1 DOWNTO 0);
        arcache : OUT STD_LOGIC_VECTOR(3 DOWNTO 0);
        arprot : OUT STD_LOGIC_VECTOR(2 DOWNTO 0);
        arid : OUT STD_LOGIC_VECTOR(5 DOWNTO 0);
        arlen : OUT STD_LOGIC_VECTOR(3 DOWNTO 0);
        arlock : OUT STD_LOGIC_VECTOR(1 DOWNTO 0);
        arqos : OUT STD_LOGIC_VECTOR(3 DOWNTO 0);
        -- R CHANNEL
        rid : IN STD_LOGIC_VECTOR(5 DOWNTO 0);
        rdata : IN STD_LOGIC_VECTOR(63 DOWNTO 0);
        rresp : IN STD_LOGIC_VECTOR(1 DOWNTO 0);
        rlast : IN STD_LOGIC;
        rvalid : IN STD_LOGIC;
        rready : OUT STD_LOGIC;
        --ICAPE2 CHANNEL
        icap_data : OUT STD_LOGIC_VECTOR(63 DOWNTO 0);
        icap_data_valid : OUT STD_LOGIC;
        -- CTRL signals
        start : IN STD_LOGIC;
        prg : IN STD_LOGIC;
        ready : OUT STD_LOGIC;
        first_addr : IN STD_LOGIC_VECTOR(31 DOWNTO 0);
        last_addr : IN STD_LOGIC_VECTOR(31 DOWNTO 0);
        final_burst : IN STD_LOGIC_VECTOR(3 DOWNTO 0);
        icap_error : IN STD_LOGIC;
        hp_ar_fifocount : IN STD_LOGIC_VECTOR(2 DOWNTO 0)
    );
END Bitstream_Reader;

ARCHITECTURE Behavioral OF Bitstream_Reader IS

    TYPE fsm_state IS (IDLE, SEND_ADDR, WAITT, PROG);
    SIGNAL current_state : fsm_state;
    SIGNAL next_state : fsm_state;

    SIGNAL araddr_reg : STD_LOGIC_VECTOR(31 DOWNTO 0);
    SIGNAL first_addr_reg : STD_LOGIC_VECTOR(31 DOWNTO 0);
    SIGNAL last_addr_reg : STD_LOGIC_VECTOR(31 DOWNTO 0);
    SIGNAL final_burst_reg : STD_LOGIC_VECTOR(3 DOWNTO 0);

BEGIN
    araddr <= araddr_reg;
    icap_data <= rdata;
    icap_data_valid <= rvalid;

    CLK_PROC : PROCESS (clk)
    BEGIN
        IF (rising_edge(clk)) THEN
            IF rstn = '0' THEN
                current_state <= IDLE;
                araddr_reg <= (OTHERS => '0');
                first_addr_reg <= (OTHERS => '0');
                last_addr_reg <= (OTHERS => '0');
                final_burst_reg <= (OTHERS => '0');
            ELSE
                current_state <= next_state;
                CASE(current_state) IS
                    WHEN IDLE =>
                    araddr_reg <= first_addr_reg;
                    WHEN PROG =>
                    first_addr_reg <= first_addr;
                    last_addr_reg <= last_addr;
                    final_burst_reg <= final_burst;
                    WHEN SEND_ADDR =>
                    IF arready = '1' THEN
                        IF araddr_reg /= last_addr_reg THEN
                            araddr_reg <= araddr_reg + 128;
                        END IF;
                    END IF;
                    WHEN WAITT =>
                END CASE;
            END IF;
        END IF;
    END PROCESS; -- CLK_PROC

    FSM_PROC : PROCESS (current_state, start, arready, hp_ar_fifocount, araddr_reg, last_addr_reg)
    BEGIN
        CASE(current_state) IS
            WHEN IDLE =>
            next_state <= IDLE;
            IF start = '1' THEN
                next_state <= SEND_ADDR;
            ELSIF prg = '1' THEN
                next_state <= PROG;
            END IF;
            WHEN SEND_ADDR =>
            next_state <= SEND_ADDR;
            IF arready = '0' OR araddr_reg = last_addr_reg THEN
                next_state <= WAITT;
            END IF;
            WHEN WAITT =>
            next_state <= WAITT;
            IF arready = '1' THEN
                next_state <= SEND_ADDR;
                IF araddr_reg = last_addr_reg THEN
                    next_state <= IDLE;
                END IF;
            END IF;
            WHEN PROG =>
            next_state <= IDLE;
        END CASE;
    END PROCESS; -- FSM_PROC

    OUT_PROC : PROCESS (current_state, arready, araddr_reg, last_addr_reg, final_burst_reg)
    BEGIN
        arvalid <= '0';
        ready <= '0';
        rready <= '1';
        arlen <= "1111";

        arsize <= "011";
        arburst <= "01";
        arcache <= "0000";
        arprot <= "000";
        arid <= "000000";
        arlock <= "00";
        arqos <= "1111";
        CASE(current_state) IS
            WHEN IDLE =>
            ready <= '1';
            WHEN SEND_ADDR =>
            arvalid <= arready;
            IF araddr_reg = last_addr_reg THEN
                arlen <= final_burst_reg;
            END IF;
            WHEN WAITT =>
            WHEN PROG =>
        END CASE;
    END PROCESS; -- OUT_PROC
END Behavioral;