----------------------------------------------------------------------------------
-- Company: 
-- Engineer: 
-- 
-- Create Date: 10/31/2023 11:12:38 AM
-- Design Name: 
-- Module Name: CDC_BRIDGE - Behavioral
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

-- Uncomment the following library declaration if using
-- arithmetic functions with Signed or Unsigned values
USE IEEE.NUMERIC_STD.ALL;

-- Uncomment the following library declaration if instantiating
-- any Xilinx leaf cells in this code.
LIBRARY UNISIM;
USE UNISIM.VComponents.ALL;

-- XPM_FIFO instantiation template for Asynchronous FIFO configurations
-- Refer to the targeted device family architecture libraries guide for XPM_FIFO documentation
-- =======================================================================================================================

-- Parameter usage table, organized as follows:
-- +---------------------------------------------------------------------------------------------------------------------+
-- | Parameter name       | Data type          | Restrictions, if applicable                                             |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Description                                                                                                         |
-- +---------------------------------------------------------------------------------------------------------------------+
-- +---------------------------------------------------------------------------------------------------------------------+
-- | CDC_SYNC_STAGES      | Integer            | Range: 2 - 8. Default value = 2.                                        |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Specifies the number of synchronization stages on the CDC path                                                      |
-- |                                                                                                                     |
-- |  Must be < 5 if FIFO_WRITE_DEPTH = 16                                                                               |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | DOUT_RESET_VALUE     | String             | Default value = 0.                                                      |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Reset value of read data path.                                                                                      |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | ECC_MODE             | String             | Allowed values: no_ecc, en_ecc. Default value = no_ecc.                 |
-- |---------------------------------------------------------------------------------------------------------------------|
-- |                                                                                                                     |
-- |  "no_ecc" - Disables ECC                                                                                            |
-- |   "en_ecc" - Enables both ECC Encoder and Decoder                                                                   |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | FIFO_MEMORY_TYPE     | String             | Allowed values: auto, block, distributed. Default value = auto.         |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Designate the fifo memory primitive (resource type) to use-                                                         |
-- |                                                                                                                     |
-- |  "auto"- Allow Vivado Synthesis to choose                                                                           |
-- |   "block"- Block RAM FIFO                                                                                           |
-- |   "distributed"- Distributed RAM FIFO                                                                               |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | FIFO_READ_LATENCY    | Integer            | Range: 0 - 10. Default value = 1.                                       |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Number of output register stages in the read data path.                                                             |
-- |                                                                                                                     |
-- |  If READ_MODE = "fwft", then the only applicable value is 0.                                                        |
-- | .                                                                                                                   |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | FIFO_WRITE_DEPTH     | Integer            | Range: 16 - 4194304. Default value = 2048.                              |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Defines the FIFO Write Depth, must be power of two                                                                  |
-- |                                                                                                                     |
-- |  In standard READ_MODE, the effective depth = FIFO_WRITE_DEPTH-1                                                    |
-- |   In First-Word-Fall-Through READ_MODE, the effective depth = FIFO_WRITE_DEPTH+1                                    |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | FULL_RESET_VALUE     | Integer            | Range: 0 - 1. Default value = 0.                                        |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Sets full, almost_full and prog_full to FULL_RESET_VALUE during reset                                               |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | PROG_EMPTY_THRESH    | Integer            | Range: 3 - 4194301. Default value = 10.                                 |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Specifies the minimum number of read words in the FIFO at or below which prog_empty is asserted.                    |
-- |                                                                                                                     |
-- |   Min_Value = 3 + (READ_MODE_VAL*2)                                                                                 |
-- |   Max_Value = (FIFO_WRITE_DEPTH-3) - (READ_MODE_VAL*2)                                                              |
-- |                                                                                                                     |
-- | If READ_MODE = "std", then READ_MODE_VAL = 0; Otherwise READ_MODE_VAL = 1                                           |
-- | NOTE: The default threshold value is dependent on default FIFO_WRITE_DEPTH value. If FIFO_WRITE_DEPTH value is      |
-- | changed, ensure the threshold value is within the valid range though the programmable flags are not used.           |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | PROG_FULL_THRESH     | Integer            | Range: 5 - 4194301. Default value = 10.                                 |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Specifies the maximum number of write words in the FIFO at or above which prog_full is asserted.                    |
-- |                                                                                                                     |
-- |  Min_Value = 3 + (READ_MODE_VAL*2*(FIFO_WRITE_DEPTH/FIFO_READ_DEPTH))+CDC_SYNC_STAGES                               |
-- |   Max_Value = (FIFO_WRITE_DEPTH-3) - (READ_MODE_VAL*2*(FIFO_WRITE_DEPTH/FIFO_READ_DEPTH))                           |
-- |                                                                                                                     |
-- | If READ_MODE = "std", then READ_MODE_VAL = 0; Otherwise READ_MODE_VAL = 1                                           |
-- | NOTE: The default threshold value is dependent on default FIFO_WRITE_DEPTH value. If FIFO_WRITE_DEPTH value is      |
-- | changed, ensure the threshold value is within the valid range though the programmable flags are not used.           |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | RD_DATA_COUNT_WIDTH  | Integer            | Range: 1 - 23. Default value = 1.                                       |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Specifies the width of rd_data_count                                                                                |
-- |                                                                                                                     |
-- |  FIFO_READ_DEPTH = FIFO_WRITE_DEPTH*WRITE_DATA_WIDTH/READ_DATA_WIDTH                                                |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | READ_DATA_WIDTH      | Integer            | Range: 1 - 4096. Default value = 32.                                    |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Defines the width of the read data port, dout                                                                       |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | READ_MODE            | String             | Allowed values: std, fwft. Default value = std.                         |
-- |---------------------------------------------------------------------------------------------------------------------|
-- |                                                                                                                     |
-- |  "std"- standard read mode                                                                                          |
-- |   "fwft"- First-Word-Fall-Through read mode                                                                         |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | RELATED_CLOCKS       | Integer            | Range: 0 - 1. Default value = 0.                                        |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Specifies if the wr_clk and rd_clk are related having the same source but different clock ratios                    |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | USE_ADV_FEATURES     | String             | Default value = 0707.                                                   |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Enables data_valid, almost_empty, rd_data_count, prog_empty, underflow, wr_ack, almost_full, wr_data_count,         |
-- | prog_full, overflow features.                                                                                       |
-- |                                                                                                                     |
-- |  Setting USE_ADV_FEATURES[0]  to 1 enables overflow flag;     Default value of this bit is 1                        |
-- |   Setting USE_ADV_FEATURES[1]  to 1 enables prog_full flag;    Default value of this bit is 1                       |
-- |   Setting USE_ADV_FEATURES[2]  to 1 enables wr_data_count;     Default value of this bit is 1                       |
-- |   Setting USE_ADV_FEATURES[3]  to 1 enables almost_full flag;  Default value of this bit is 0                       |
-- |   Setting USE_ADV_FEATURES[4]  to 1 enables wr_ack flag;       Default value of this bit is 0                       |
-- |   Setting USE_ADV_FEATURES[8]  to 1 enables underflow flag;    Default value of this bit is 1                       |
-- |   Setting USE_ADV_FEATURES[9]  to 1 enables prog_empty flag;   Default value of this bit is 1                       |
-- |   Setting USE_ADV_FEATURES[10] to 1 enables rd_data_count;     Default value of this bit is 1                       |
-- |   Setting USE_ADV_FEATURES[11] to 1 enables almost_empty flag; Default value of this bit is 0                       |
-- |   Setting USE_ADV_FEATURES[12] to 1 enables data_valid flag;   Default value of this bit is 0                       |
-- | .                                                                                                                   |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | WAKEUP_TIME          | Integer            | Range: 0 - 2. Default value = 0.                                        |
-- |---------------------------------------------------------------------------------------------------------------------|
-- |                                                                                                                     |
-- |  0 - Disable sleep                                                                                                  |
-- |   2 - Use Sleep Pin                                                                                                 |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | WRITE_DATA_WIDTH     | Integer            | Range: 1 - 4096. Default value = 32.                                    |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Defines the width of the write data port, din                                                                       |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | WR_DATA_COUNT_WIDTH  | Integer            | Range: 1 - 23. Default value = 1.                                       |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Specifies the width of wr_data_count                                                                                |
-- +---------------------------------------------------------------------------------------------------------------------+

-- Port usage table, organized as follows:
-- +---------------------------------------------------------------------------------------------------------------------+
-- | Port name      | Direction | Size, in bits                         | Domain  | Sense       | Handling if unused     |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Description                                                                                                         |
-- +---------------------------------------------------------------------------------------------------------------------+
-- +---------------------------------------------------------------------------------------------------------------------+
-- | almost_empty   | Output    | 1                                     | rd_clk  | Active-high | DoNotCare              |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Almost Empty : When asserted, this signal indicates that only one more read can be performed before the FIFO goes to|
-- | empty.                                                                                                              |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | almost_full    | Output    | 1                                     | wr_clk  | Active-high | DoNotCare              |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Almost Full: When asserted, this signal indicates that only one more write can be performed before the FIFO is full.|
-- +---------------------------------------------------------------------------------------------------------------------+
-- | data_valid     | Output    | 1                                     | rd_clk  | Active-high | DoNotCare              |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Read Data Valid: When asserted, this signal indicates that valid data is available on the output bus (dout).        |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | dbiterr        | Output    | 1                                     | rd_clk  | Active-high | DoNotCare              |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Double Bit Error: Indicates that the ECC decoder detected a double-bit error and data in the FIFO core is corrupted.|
-- +---------------------------------------------------------------------------------------------------------------------+
-- | din            | Input     | WRITE_DATA_WIDTH                      | wr_clk  | NA          | Required               |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Write Data: The input data bus used when writing the FIFO.                                                          |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | dout           | Output    | READ_DATA_WIDTH                       | rd_clk  | NA          | Required               |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Read Data: The output data bus is driven when reading the FIFO.                                                     |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | empty          | Output    | 1                                     | rd_clk  | Active-high | Required               |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Empty Flag: When asserted, this signal indicates that the FIFO is empty.                                            |
-- | Read requests are ignored when the FIFO is empty, initiating a read while empty is not destructive to the FIFO.     |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | full           | Output    | 1                                     | wr_clk  | Active-high | Required               |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Full Flag: When asserted, this signal indicates that the FIFO is full.                                              |
-- | Write requests are ignored when the FIFO is full, initiating a write when the FIFO is full is not destructive       |
-- | to the contents of the FIFO.                                                                                        |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | injectdbiterr  | Input     | 1                                     | wr_clk  | Active-high | Tie to 1'b0            |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Double Bit Error Injection: Injects a double bit error if the ECC feature is used on block RAMs or                  |
-- | UltraRAM macros.                                                                                                    |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | injectsbiterr  | Input     | 1                                     | wr_clk  | Active-high | Tie to 1'b0            |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Single Bit Error Injection: Injects a single bit error if the ECC feature is used on block RAMs or                  |
-- | UltraRAM macros.                                                                                                    |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | overflow       | Output    | 1                                     | wr_clk  | Active-high | DoNotCare              |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Overflow: This signal indicates that a write request (wren) during the prior clock cycle was rejected,              |
-- | because the FIFO is full. Overflowing the FIFO is not destructive to the contents of the FIFO.                      |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | prog_empty     | Output    | 1                                     | rd_clk  | Active-high | DoNotCare              |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Programmable Empty: This signal is asserted when the number of words in the FIFO is less than or equal              |
-- | to the programmable empty threshold value.                                                                          |
-- | It is de-asserted when the number of words in the FIFO exceeds the programmable empty threshold value.              |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | prog_full      | Output    | 1                                     | wr_clk  | Active-high | DoNotCare              |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Programmable Full: This signal is asserted when the number of words in the FIFO is greater than or equal            |
-- | to the programmable full threshold value.                                                                           |
-- | It is de-asserted when the number of words in the FIFO is less than the programmable full threshold value.          |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | rd_clk         | Input     | 1                                     | NA      | Rising edge | Required               |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Read clock: Used for read operation. rd_clk must be a free running clock.                                           |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | rd_data_count  | Output    | RD_DATA_COUNT_WIDTH                   | rd_clk  | NA          | DoNotCare              |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Read Data Count: This bus indicates the number of words read from the FIFO.                                         |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | rd_en          | Input     | 1                                     | rd_clk  | Active-high | Required               |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Read Enable: If the FIFO is not empty, asserting this signal causes data (on dout) to be read from the FIFO.        |
-- |                                                                                                                     |
-- |  Must be held active-low when rd_rst_busy is active high.                                                           |
-- | .                                                                                                                   |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | rd_rst_busy    | Output    | 1                                     | rd_clk  | Active-high | Required               |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Read Reset Busy: Active-High indicator that the FIFO read domain is currently in a reset state.                     |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | rst            | Input     | 1                                     | wr_clk  | Active-high | Required               |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Reset: Must be synchronous to wr_clk. Must be applied only when wr_clk is stable and free-running.                  |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | sbiterr        | Output    | 1                                     | rd_clk  | Active-high | DoNotCare              |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Single Bit Error: Indicates that the ECC decoder detected and fixed a single-bit error.                             |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | sleep          | Input     | 1                                     | NA      | Active-high | Tie to 1'b0            |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Dynamic power saving: If sleep is High, the memory/fifo block is in power saving mode.                              |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | underflow      | Output    | 1                                     | rd_clk  | Active-high | DoNotCare              |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Underflow: Indicates that the read request (rd_en) during the previous clock cycle was rejected                     |
-- | because the FIFO is empty. Under flowing the FIFO is not destructive to the FIFO.                                   |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | wr_ack         | Output    | 1                                     | wr_clk  | Active-high | DoNotCare              |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Write Acknowledge: This signal indicates that a write request (wr_en) during the prior clock cycle is succeeded.    |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | wr_clk         | Input     | 1                                     | NA      | Rising edge | Required               |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Write clock: Used for write operation. wr_clk must be a free running clock.                                         |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | wr_data_count  | Output    | WR_DATA_COUNT_WIDTH                   | wr_clk  | NA          | DoNotCare              |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Write Data Count: This bus indicates the number of words written into the FIFO.                                     |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | wr_en          | Input     | 1                                     | wr_clk  | Active-high | Required               |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Write Enable: If the FIFO is not full, asserting this signal causes data (on din) to be written to the FIFO.        |
-- |                                                                                                                     |
-- |  Must be held active-low when rst or wr_rst_busy is active high.                                                    |
-- | .                                                                                                                   |
-- +---------------------------------------------------------------------------------------------------------------------+
-- | wr_rst_busy    | Output    | 1                                     | wr_clk  | Active-high | Required               |
-- |---------------------------------------------------------------------------------------------------------------------|
-- | Write Reset Busy: Active-High indicator that the FIFO write domain is currently in a reset state.                   |
-- +---------------------------------------------------------------------------------------------------------------------+
-- xpm_fifo_async : In order to incorporate this function into the design,
--      VHDL      : the following instance declaration needs to be placed
--    instance    : in the body of the design code.  The instance name
--  declaration   : (xpm_fifo_async_inst) and/or the port declarations after the
--      code      : "=>" declaration maybe changed to properly reference and
--                : connect this function to the design.  All inputs and outputs
--                : must be connected.

--    Library     : In addition to adding the instance declaration, a use
--  declaration   : statement for the UNISIM.vcomponents library needs to be
--      for       : added before the entity declaration.  This library
--     Xilinx     : contains the component declarations for all Xilinx
--   primitives   : primitives and points to the models that will be used
--                : for simulation.

--  Please reference the appropriate libraries guide for additional information on the XPM modules.

--  Copy the following two statements and paste them before the
--  Entity declaration, unless they already exist.

LIBRARY xpm;
USE xpm.vcomponents.ALL;

ENTITY CDC_BRIDGE IS
    PORT (
        clk_src : IN STD_LOGIC;
        clk_dest : IN STD_LOGIC;
        rstn : IN STD_LOGIC;

        axi3_data_valid : IN STD_LOGIC;
        axi3_data : IN STD_LOGIC_VECTOR(63 DOWNTO 0);

        icap_data : OUT STD_LOGIC_VECTOR(31 DOWNTO 0);
        icap_csib : OUT STD_LOGIC
    );
END CDC_BRIDGE;

ARCHITECTURE Behavioral OF CDC_BRIDGE IS

    TYPE WRITER_FSM_STATE IS (IDLE, PUSH64);
    TYPE READER_FSM_STATE IS (IDLE, POP32);
    SIGNAL writer_state : WRITER_FSM_STATE;
    SIGNAL reader_state : READER_FSM_STATE;

    SIGNAL xpm_fifo_empty : STD_LOGIC;
    SIGNAL xpm_fifo_full : STD_LOGIC;
    SIGNAL xpm_fifo_wr_en : STD_LOGIC;
    SIGNAL xpm_fifo_rd_en : STD_LOGIC;
    SIGNAL xpm_fifo_din : STD_LOGIC_VECTOR(63 DOWNTO 0);
    SIGNAL xpm_fifo_rst : STD_LOGIC;

    SIGNAL icap_csib_cycle_delay : STD_LOGIC;

BEGIN

    xpm_fifo_rst <= NOT rstn;

    WRITER_FSM : PROCESS (clk_src)
    BEGIN
        IF (rising_edge(clk_src)) THEN
            IF (rstn = '0') THEN
                writer_state <= IDLE;
                xpm_fifo_wr_en <= '0';
                xpm_fifo_din <= (OTHERS => '0');
            ELSE
                xpm_fifo_wr_en <= '0';
                xpm_fifo_din <= axi3_data;
                CASE(writer_state) IS
                    WHEN IDLE =>
                    IF axi3_data_valid = '1' AND xpm_fifo_full = '0' THEN
                        writer_state <= PUSH64;
                        xpm_fifo_wr_en <= '1';
                    END IF;
                    WHEN PUSH64 =>
                    xpm_fifo_wr_en <= '1';
                    IF axi3_data_valid = '0' OR xpm_fifo_full = '1' THEN
                        xpm_fifo_wr_en <= '0';
                        writer_state <= IDLE;
                    END IF;
                END CASE;
            END IF;
        END IF;
    END PROCESS; -- WRITER_FSM

    READER_FSM : PROCESS (clk_dest)
    BEGIN
        IF (rising_edge(clk_dest)) THEN
            IF (rstn = '0') THEN
                reader_state <= IDLE;
                xpm_fifo_rd_en <= '0';
                icap_csib <= '1';
                icap_csib_cycle_delay <= '1';
            ELSE
                icap_csib <= icap_csib_cycle_delay;
                icap_csib_cycle_delay <= '1';
                xpm_fifo_rd_en <= '0';
                CASE(reader_state) IS
                    WHEN IDLE =>
                    IF xpm_fifo_empty = '0' THEN
                        reader_state <= POP32;
                    END IF;
                    WHEN POP32 =>
                    xpm_fifo_rd_en <= '1';
                    icap_csib_cycle_delay <= '0';
                    IF xpm_fifo_empty = '1' THEN
                        icap_csib_cycle_delay <= '1';
                        reader_state <= IDLE;
                    END IF;
                END CASE;
            END IF;
        END IF;
    END PROCESS; -- READER_FSM

    -- <-----Cut code below this line and paste into the architecture body---->

    -- xpm_fifo_async: Asynchronous FIFO
    -- Xilinx Parameterized Macro, version 2018.2

    xpm_fifo_async_inst : xpm_fifo_async
    GENERIC MAP(
        CDC_SYNC_STAGES => 2, -- DECIMAL
        DOUT_RESET_VALUE => "0", -- String
        ECC_MODE => "no_ecc", -- String
        FIFO_MEMORY_TYPE => "block", -- String
        FIFO_READ_LATENCY => 2, -- DECIMAL
        FIFO_WRITE_DEPTH => 16, -- DECIMAL
        FULL_RESET_VALUE => 0, -- DECIMAL
        PROG_EMPTY_THRESH => 10, -- DECIMAL
        PROG_FULL_THRESH => 10, -- DECIMAL
        RD_DATA_COUNT_WIDTH => 1, -- DECIMAL
        READ_DATA_WIDTH => 32, -- DECIMAL
        READ_MODE => "std", -- String
        RELATED_CLOCKS => 0, -- DECIMAL
        USE_ADV_FEATURES => "0000", -- String
        WAKEUP_TIME => 0, -- DECIMAL
        WRITE_DATA_WIDTH => 64, -- DECIMAL
        WR_DATA_COUNT_WIDTH => 1 -- DECIMAL
    )
    PORT MAP(
        sleep => '0',
        injectsbiterr => '0',
        injectdbiterr => '0',
        din => xpm_fifo_din,
        rst => xpm_fifo_rst,
        wr_clk => clk_src,
        wr_en => xpm_fifo_wr_en,
        rd_clk => clk_dest,
        rd_en => xpm_fifo_rd_en,
        dout => icap_data,
        empty => xpm_fifo_empty,
        full => xpm_fifo_full
    );

    -- End of xpm_fifo_async_inst instantiation

END Behavioral;