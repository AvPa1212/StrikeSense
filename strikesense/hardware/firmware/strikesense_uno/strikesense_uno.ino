/*
  StrikeSense firmware for Arduino Uno (Elegoo UNO R3 works the same).

  Streams 500 packets per second over USB serial at 250000 baud:
    0xAA 0x55 | uint32 t_us | int16 ax ay az gx gy gz | uint16 f0 f1 f2 f3 | uint8 xor
  27 bytes each, little endian. The XOR covers the 24 bytes between the sync pair and the
  checksum. server/protocol.py decodes exactly this layout.

  Wiring (details and resistor values in hardware/WIRING.md):
    MPU-6050 (GY-521): VCC 5V, GND, SDA A4, SCL A5
    Force channel 0..3: A0..A3 (piezo disc, 100k series, 1M to GND)

  Set CSV_MODE to 1 to print readable text instead, for the Serial Monitor and Plotter.
*/
#include <Wire.h>

#define CSV_MODE 0

const uint8_t MPU_ADDR = 0x68;
const uint8_t FORCE_PINS[4] = {A0, A1, A2, A3};
const unsigned long PERIOD_US = 2000UL;  // 500 Hz

int16_t gyroBias[3] = {0, 0, 0};
unsigned long nextTick;

void mpuWrite(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  Wire.write(val);
  Wire.endTransmission();
}

bool mpuRead(int16_t *a, int16_t *g) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom((uint8_t)MPU_ADDR, (uint8_t)14, (uint8_t)true) != 14) return false;
  for (uint8_t i = 0; i < 3; i++) a[i] = (Wire.read() << 8) | Wire.read();
  Wire.read();
  Wire.read();  // skip temperature
  for (uint8_t i = 0; i < 3; i++) g[i] = (Wire.read() << 8) | Wire.read();
  return true;
}

uint16_t readForce(uint8_t pin) {
  analogRead(pin);        // throw away: the source impedance is high, so let the S/H settle
  return analogRead(pin);
}

void calibrateGyro() {
  // Keep the ball still for the first second after power up.
  long sum[3] = {0, 0, 0};
  int16_t a[3], g[3];
  const int N = 200;
  int got = 0;
  for (int i = 0; i < N; i++) {
    if (mpuRead(a, g)) {
      for (uint8_t k = 0; k < 3; k++) sum[k] += g[k];
      got++;
    }
    delay(4);
  }
  if (got > 0)
    for (uint8_t k = 0; k < 3; k++) gyroBias[k] = (int16_t)(sum[k] / got);
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  Serial.begin(250000);  // 250000 divides the 16 MHz clock exactly, so 0% baud error
  Wire.begin();
  Wire.setClock(400000);

  // Faster ADC clock: prescaler 32 gives about 26 us per conversion (default is 112 us).
  ADCSRA = (ADCSRA & 0xF8) | 0x05;

  // Confirm the IMU answers before streaming.
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x75);  // WHO_AM_I
  Wire.endTransmission(false);
  Wire.requestFrom((uint8_t)MPU_ADDR, (uint8_t)1);
  uint8_t who = Wire.available() ? Wire.read() : 0;
  if (who == 0) {
    while (true) {  // fast blink means the IMU is missing or miswired
      digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
      delay(100);
    }
  }

  mpuWrite(0x6B, 0x01);  // wake, clock from gyro X PLL
  mpuWrite(0x1A, 0x01);  // digital low-pass about 188 Hz, 1 kHz internal rate
  mpuWrite(0x19, 0x01);  // sample rate divider: 1 kHz / 2 = 500 Hz
  mpuWrite(0x1B, 0x18);  // gyro +-2000 dps  (16.4 LSB per dps)
  mpuWrite(0x1C, 0x18);  // accel +-16 g     (2048 LSB per g)
  delay(100);
  calibrateGyro();

  digitalWrite(LED_BUILTIN, HIGH);
  nextTick = micros() + PERIOD_US;
}

void loop() {
  unsigned long now = micros();
  if ((long)(now - nextTick) < 0) return;
  nextTick += PERIOD_US;
  if ((long)(now - nextTick) > (long)(4 * PERIOD_US)) nextTick = now + PERIOD_US;  // fell behind

  int16_t a[3], g[3];
  if (!mpuRead(a, g)) return;
  for (uint8_t k = 0; k < 3; k++) g[k] -= gyroBias[k];
  uint16_t f[4];
  for (uint8_t k = 0; k < 4; k++) f[k] = readForce(FORCE_PINS[k]);

#if CSV_MODE
  static uint8_t divider = 0;
  if (++divider >= 10) {  // 50 lines per second
    divider = 0;
    Serial.print(a[0]); Serial.print(',');
    Serial.print(a[1]); Serial.print(',');
    Serial.print(a[2]); Serial.print(',');
    Serial.print(g[0]); Serial.print(',');
    Serial.print(g[1]); Serial.print(',');
    Serial.print(g[2]); Serial.print(',');
    Serial.print(f[0]); Serial.print(',');
    Serial.print(f[1]); Serial.print(',');
    Serial.print(f[2]); Serial.print(',');
    Serial.println(f[3]);
  }
#else
  uint8_t pkt[27];
  pkt[0] = 0xAA;
  pkt[1] = 0x55;
  uint32_t t = now;
  memcpy(&pkt[2], &t, 4);
  memcpy(&pkt[6], a, 6);
  memcpy(&pkt[12], g, 6);
  memcpy(&pkt[18], f, 8);
  uint8_t x = 0;
  for (uint8_t i = 2; i < 26; i++) x ^= pkt[i];
  pkt[26] = x;
  Serial.write(pkt, sizeof(pkt));
#endif
}
