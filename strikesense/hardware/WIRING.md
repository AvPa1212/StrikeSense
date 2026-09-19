# Wiring and hardware

## Parts

Must have:
- Arduino Uno (Elegoo UNO R3), USB cable, breadboard, jumper wires
- MPU-6050 on a GY-521 board (about $3). Check your Elegoo kit and the MLH hardware lab first. Without an IMU, run the simulator and present the hardware as the design.

For the strike map (optional, the stack degrades gracefully without them):
- 4 piezo discs (the flat brass buzzer discs, from dead buzzers or greeting cards)
- 4 resistors of 100 kOhm and 4 of 1 MOhm

I have not checked what your specific kit contains, so verify the resistor values before buying anything.

## Pinout

| Part | Pin | Uno |
|---|---|---|
| GY-521 | VCC | 5V |
| GY-521 | GND | GND |
| GY-521 | SDA | A4 |
| GY-521 | SCL | A5 |
| GY-521 | AD0 | GND (address 0x68) |
| Force 0 to 3 | see below | A0, A1, A2, A3 |

A4 and A5 are the I2C lines on the Uno, so only A0 to A3 remain free. That is why there are four force channels, not six.

Each force channel:

```
piezo (+) ---[100k]---+---- A0 (A1, A2, A3)
                      |
                    [1M]
                      |
piezo (-) ------------+---- GND
```

Why these values: the 1 MOhm to ground gives a decay of roughly 20 ms, slow enough for a 500 Hz loop to catch the peak. The 100 kOhm in series limits current into the Uno pin when a hard hit spikes the disc above 5 V. A 5.1 V zener from the pin to ground adds protection if you have one.

## Bring-up in 10 minutes

1. Open `firmware/strikesense_uno/strikesense_uno.ino`, set `CSV_MODE` to 1, upload.
2. Serial Monitor at 250000 baud. Tilt the board: az should swing between about +2048 and -2048 counts per g. Tap a piezo: the matching column jumps.
3. Fast LED blink means the IMU is missing or miswired (SDA/SCL swapped is the usual cause).
4. Set `CSV_MODE` back to 0, upload, close the Serial Monitor (it holds the port).
5. `SOURCE=serial SERIAL_PORT=COM5 uvicorn app:app --port 8000` (Linux/Mac: `/dev/ttyACM0`).

The firmware is checked against the Python parser on a desktop with mocked Arduino headers (8000 packets, 0 bad, correct timing). It has not been run on a physical Uno by me, so expect to debug wiring.

## Ball frame and orientation

The pipeline assumes the ball sits at rest before each kick like this:

- +X points at the target, +Y to the kicker's left, +Z up.
- Put tape on the face toward the kicker (the -X face). The dashboard says "marked side facing you".

Force sensor directions (from the ball center, before normalizing):

| Channel | Direction (x, y, z) | Hemisphere |
|---|---|---|
| A0 | (+1, +1, +1) | behind the ball |
| A1 | (+1, -1, -1) | behind the ball |
| A2 | (-1, +1, -1) | kicker side |
| A3 | (-1, -1, +1) | kicker side |

Glue each disc to the inside of the shell at those points. The four positions form a tetrahedron, which is what lets four sensors locate a contact point in two directions.

Calibrate gains: tap the ball with the same force at each sensor's location and set `FORCE_GAINS` (comma list, for example `1,1.4,0.8,1.1`) so the four peaks match.

## Where the IMU goes

Mount it at the exact center of the ball. In flight the accelerometer should read about 0 g, and that is how hang time is detected. Off-center mounting adds centripetal readings of omega squared times the offset. At 2000 deg/s that is about 2.5 g for a 2 cm offset, which breaks flight detection. Stay within about 5 mm.

## What the sensors can and cannot do

- Gyro range is +-2000 deg/s. Hard curls can saturate it. The dashboard flags `spin_saturated`.
- The MPU-6050 tops out at +-16 g. A real kick puts hundreds of g on the ball for about 10 ms, so contact acceleration always clips. Launch speed and launch angle show as locked until you add a high-g accelerometer. A +-200 g part such as the ADXL375 helps but may still clip on hard kicks. A +-400 g part such as the H3LIS331DL is safer. Set `ACCEL_RANGE_G` and `ACCEL_LSB_PER_G` to match, and the locked stats unlock.
- Hang time, apex height, contact time, spin and strike point all work on the plain MPU-6050.

## Path to the in-ball version

The Uno is too big and needs a cable. For the real ball, keep the same packet format and swap the board:

1. ESP32 or Nano-class board, LiPo cell, USB-C charging module. The MLH hardware lab may lend an ESP32.
2. Stream the same 27-byte packets over WiFi (TCP or WebSocket) instead of serial, then add a network source next to `serial_source.py`.
3. Print a hub with four spokes for the discs and a central IMU cradle. Foam fills the rest, and mass must be symmetric about the center. Weigh the finished ball against a standard one (a size 5 ball is roughly 410 to 450 g).
4. Print the frame in a flexible material. TPU is the usual choice for airless-style lattices.

Prices: I have not looked up current prices, so cost the ball and parts yourself before quoting numbers.
