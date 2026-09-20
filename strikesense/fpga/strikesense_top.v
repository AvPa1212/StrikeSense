// StrikeSense sensor hub. One FPGA replaces the Arduino Uno.
//
//   MPU-6050 --I2C--> i2c_master --> mpu6050_ctrl --+
//   4 x piezo --RC--> sd_adc --> force_peak --------+--> packetizer --> uart_tx --> USB-UART --> PC
//                                                   |
//   tick_gen (500 Hz) + microsecond timestamp ------+
//
// The 27-byte packets match the Arduino firmware, so the Python server needs no changes.
module strikesense_top #(
    parameter integer CLK_HZ     = 100_000_000,
    parameter integer BAUD       = 250_000,
    parameter integer TICK_HZ    = 500,
    parameter integer MOD_HZ     = 12_500_000,   // sigma-delta modulator clock
    parameter integer FORCE_SHIFT = 5,           // lower = more sensitive force channels
    parameter integer BOOT_MS    = 100,
    parameter integer CAL_LOG2   = 8             // gyro bias averaged over 2^CAL_LOG2 samples
) (
    input  wire       clk,
    input  wire       rst,            // active high, optional (a power-on reset is built in)
    inout  wire       scl,
    inout  wire       sda,
    input  wire [3:0] cmp_in,         // sigma-delta comparator inputs, one per piezo
    output wire [3:0] fb_out,         // sigma-delta feedback outputs
    output wire       uart_txd,
    output wire [3:0] led             // 0 sensor ok, 1 streaming, 2 packet activity, 3 overrun
);
    // ---------- reset ----------
    reg [7:0] por = 8'd0;
    always @(posedge clk) if (!(&por)) por <= por + 8'd1;
    wire rst_i = rst | ~(&por);

    // ---------- 500 Hz tick and microsecond clock ----------
    localparam integer TICK_DIV = CLK_HZ / TICK_HZ;
    localparam integer US_DIV   = CLK_HZ / 1_000_000;
    reg [31:0] tick_cnt;
    reg        tick;
    reg [15:0] us_div_cnt;
    reg [31:0] us_cnt;
    reg [31:0] t_lat;
    always @(posedge clk) begin
        tick <= 1'b0;
        if (rst_i) begin
            tick_cnt <= 32'd0; us_div_cnt <= 16'd0; us_cnt <= 32'd0; t_lat <= 32'd0;
        end else begin
            if (tick_cnt == TICK_DIV - 1) begin tick_cnt <= 32'd0; tick <= 1'b1; t_lat <= us_cnt; end
            else tick_cnt <= tick_cnt + 32'd1;
            if (us_div_cnt == US_DIV - 1) begin us_div_cnt <= 16'd0; us_cnt <= us_cnt + 32'd1; end
            else us_div_cnt <= us_div_cnt + 16'd1;
        end
    end

    // ---------- IMU ----------
    wire        cmd_valid, cmd_ready, done, nack, rack;
    wire [1:0]  cmd;
    wire [7:0]  wdata, rdata;
    i2c_master #(.CLK_HZ(CLK_HZ), .I2C_HZ(400_000)) u_i2c (
        .clk(clk), .rst(rst_i), .cmd_valid(cmd_valid), .cmd(cmd), .wdata(wdata), .rack(rack),
        .cmd_ready(cmd_ready), .done(done), .rdata(rdata), .nack(nack), .scl(scl), .sda(sda));

    wire        sample_valid, sensor_ok, calibrating;
    wire signed [15:0] ax, ay, az, gx, gy, gz;
    mpu6050_ctrl #(.CLK_HZ(CLK_HZ), .BOOT_MS(BOOT_MS), .CAL_LOG2(CAL_LOG2)) u_mpu (
        .clk(clk), .rst(rst_i), .tick(tick),
        .cmd_valid(cmd_valid), .cmd(cmd), .wdata(wdata), .rack(rack),
        .cmd_ready(cmd_ready), .done(done), .rdata(rdata), .nack(nack),
        .sample_valid(sample_valid), .ax(ax), .ay(ay), .az(az), .gx(gx), .gy(gy), .gz(gz),
        .sensor_ok(sensor_ok), .calibrating(calibrating));

    // ---------- four force channels ----------
    localparam integer MOD_DIV = (CLK_HZ / MOD_HZ) < 1 ? 1 : (CLK_HZ / MOD_HZ);
    wire [3:0]  adc_valid;
    wire [15:0] adc_code [0:3];
    wire [9:0]  f [0:3];
    genvar i;
    generate
        for (i = 0; i < 4; i = i + 1) begin : force_ch
            sd_adc #(.MOD_DIV(MOD_DIV), .LOG2OSR(8)) u_adc (
                .clk(clk), .rst(rst_i), .cmp_in(cmp_in[i]), .fb_out(fb_out[i]),
                .valid(adc_valid[i]), .code(adc_code[i]));
            force_peak #(.SHIFT(FORCE_SHIFT)) u_peak (
                .clk(clk), .rst(rst_i), .code_valid(adc_valid[i]), .code(adc_code[i]),
                .tick(tick), .peak_out(f[i]));
        end
    endgenerate

    // ---------- packet out ----------
    wire       tx_ready, tx_valid, overrun;
    wire [7:0] tx_data;
    wire       stream_en = sensor_ok & ~calibrating;
    packetizer u_pkt (
        .clk(clk), .rst(rst_i), .start(sample_valid & stream_en), .t_us(t_lat),
        .ax(ax), .ay(ay), .az(az), .gx(gx), .gy(gy), .gz(gz),
        .f0(f[0]), .f1(f[1]), .f2(f[2]), .f3(f[3]),
        .tx_ready(tx_ready), .tx_valid(tx_valid), .tx_data(tx_data), .overrun(overrun));

    uart_tx #(.CLK_HZ(CLK_HZ), .BAUD(BAUD)) u_uart (
        .clk(clk), .rst(rst_i), .data(tx_data), .valid(tx_valid), .ready(tx_ready), .tx(uart_txd));

    // ---------- status LEDs ----------
    reg act;
    always @(posedge clk) begin
        if (rst_i) act <= 1'b0;
        else if (sample_valid & stream_en) act <= ~act;
    end
    assign led = {overrun, act, stream_en, sensor_ok};
endmodule
