# FPGA sensor hub (Verilog)

One FPGA replaces the Arduino Uno. It reads the MPU-6050 over I2C and four piezo force channels through chip-free sigma-delta ADCs, then streams the exact 27-byte packets the Python server already understands. No server changes: `SOURCE=serial`.

## Architecture

```
                          +----------------------- strikesense_top -----------------------+
                          |                                                               |
 MPU-6050 --SCL/SDA-----> | i2c_master -> mpu6050_ctrl --(ax ay az gx gy gz, bias-free)--+|
 (GY-521, 3.3 V)          |  400 kHz       init, WHO_AM_I, gyro calibration, 500 Hz burst ||
                          |                                                              ||
 piezo 0..3 --RC net----> | sd_adc x4 --> force_peak x4 --(f0..f3, 0..1023)--------------+|--> packetizer --> uart_tx --> USB-UART --> PC
   cmp_in[3:0]/fb_out[3:0]|  1-bit SD +     DC removal, rectify, peak hold                ||     27 bytes        250000 baud     server
                          |  sinc2 (49 kHz)                                              ||
                          |                                                              ||
                          | tick_gen (500 Hz) + microsecond clock ------------------------+|
                          | power-on reset, 4 status LEDs                                 |
                          +---------------------------------------------------------------+
```

Everything is one clock domain, Verilog-2001, no vendor primitives, no block RAM, no DSP slices. A Yosys synthesis for a Xilinx-style target came out around 1.3k LUTs and 1.5k flip-flops, so it fits any board with a few thousand LUTs.

## Modules (`rtl/`)

| File | Job |
|---|---|
| `strikesense_top.v` | Wires everything together. Parameters: `CLK_HZ`, `BAUD`, `FORCE_SHIFT`, `CAL_LOG2`, `BOOT_MS` |
| `i2c_master.v` | Byte-level I2C master, 400 kHz, clock stretching, open-drain |
| `mpu6050_ctrl.v` | Writes the same 5 config registers as the Arduino sketch, checks WHO_AM_I, averages the gyro for 2^8 samples, then does one 14-byte burst per tick. Retries if the IMU disappears |
| `sd_adc.v` | First-order sigma-delta modulator at 12.5 MHz plus a sinc2 decimator. Gives a 16-bit code at about 49 kHz |
| `force_peak.v` | Removes the slow DC level, rectifies, scales to 0..1023, holds the peak for each 2 ms packet |
| `packetizer.v` | Builds the 27-byte packet, XOR checksum, feeds the UART |
| `uart_tx.v` | 8N1 transmitter |

Packet layout (little endian): `0xAA 0x55 | uint32 t_us | int16 ax ay az gx gy gz | uint16 f0 f1 f2 f3 | uint8 xor`. Accel is +-16 g at 2048 LSB/g, gyro +-2000 dps at 16.4 LSB/dps, same as the Arduino build.

Why it beats the Uno on the force channels: the Uno samples each piezo once per 2 ms packet and can miss a millisecond-long peak. Here the ADC runs at about 49 kHz and the peak is held, so each packet carries the true impact strength.

## Analog front end (per force channel)

```
                 3V3
                  |
                [2M]        +-- clamp: 1N4148 Vin->3V3 (anode at Vin), 1N4148 GND->Vin
                  |         |
piezo (+) --------+---------+--[100k]--+--------------- cmp_in[i]  (FPGA input)
                  |                    |
                [2M]                 [1 nF]
                  |                    |
piezo (-) -------GND                  GND
                                       |
                        fb_out[i] --[100k]-- (same node as cmp_in)
```

The two 2 MOhm resistors bias the piezo at mid-supply so both polarities register. The loop keeps the RC node at the FPGA input threshold, so the fraction of ones on `cmp_in` equals Vin / 3.3 V. The DC tracker in `force_peak.v` removes any threshold offset, which is why you do not need a precise reference.

These are starting values from an idealized simulation, not from a bench. Expect to tune: raise the capacitor for less noise (slower response), lower `FORCE_SHIFT` for more sensitivity, and equalize the four channels with `FORCE_GAINS` on the server. The clamp diodes matter, because a hard hit can put tens of volts on a piezo and FPGA pins are not 5 V tolerant.

## Pins

See `constraints_template.xdc`. Signals: `clk`, `rst`, `scl`, `sda`, `cmp_in[3:0]`, `fb_out[3:0]`, `uart_txd`, `led[3:0]`. Everything is 3.3 V LVCMOS.

- Power the GY-521 from the board's 3.3 V, not 5 V. Its I2C pull-ups follow its supply, and 5 V on an FPGA pin can damage it.
- `uart_txd` goes to your board's USB-UART receive input. Most dev boards already wire this to the USB port.
- Set `CLK_HZ` to your oscillator (100 MHz, 50 MHz, 12 MHz all work; the dividers scale).
- The default 250000 baud is what the server expects. If your USB-UART chip does not support it, set `BAUD` to 921600 in the top module and `BAUD=921600` for the server. Do not drop to 115200: 27 bytes then take longer than the 2 ms packet period and the `overrun` LED lights.

## Run it with the server

```bash
cd server
SOURCE=serial SERIAL_PORT=COM5 BAUD=250000 uvicorn app:app --port 8000
```

LEDs: 0 = IMU found, 1 = streaming (calibration done), 2 = toggles per packet, 3 = overrun. Keep the ball still for the first second while the gyro calibrates. Force channels need about 85 ms after power-up to settle their DC tracking.

## Simulation (`sim/`)

`sim/run_sim.sh` needs Icarus Verilog and Python. It simulates the real top level with:

- a behavioral MPU-6050 whose readings change on every burst,
- an RC model of four sigma-delta nodes with injected piezo impulses of 1.0 V, 0.5 V, 0.1 V and none,
- a UART receiver whose bytes are decoded by the server's own `protocol.py`.

Checked in that run: all five IMU config registers written correctly; 0 bad checksums; exactly 2000 us between packets; no IMU read lost or repeated; gyro bias removal leaves exactly the injected step; force peaks came out 617, 308, 61 and 0 counts for those four impulses (the ideal is about 620, 310, 62, 0, and they rank in the right order); the hub stays silent when the IMU is absent. It also ran at both 25 MHz and 100 MHz clocks. Yosys synthesis reports no latches and no structural problems.

## Not verified

- No run on a physical FPGA or a physical MPU-6050.
- I2C clock stretching is implemented but not exercised by the testbench.
- The analog front end is only simulated as an ideal RC loop. Real input thresholds, pin capacitance, supply noise and piezo behavior will differ.
- Your board's pin names, clock and USB-UART limits are unknown to me, hence the constraint template.

## Stretch ideas

- Time-difference-of-arrival strike location: timestamp each piezo's first edge with the 100 MHz clock (10 ns) instead of comparing amplitudes.
- A sinc3 filter and longer oversampling for lower noise.
- Run the small classifier on the FPGA itself (fixed-point 8-24-16-5 MLP).
