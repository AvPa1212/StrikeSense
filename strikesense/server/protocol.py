"""Binary packet format shared by the Arduino firmware, the parser and the simulator.

Packet (27 bytes, little endian):
    0xAA 0x55 | uint32 t_us | int16 ax ay az gx gy gz | uint16 f0 f1 f2 f3 | uint8 xor
The XOR checksum covers every byte after the two sync bytes and before the checksum.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from config import ACCEL_LSB_PER_G, GYRO_LSB_PER_DPS

SYNC = b"\xaa\x55"
_BODY = struct.Struct("<IhhhhhhHHHH")  # 4 + 12 + 8 = 24 bytes
PACKET_LEN = 2 + _BODY.size + 1  # 27


@dataclass
class Sample:
    t: float                       # seconds since the device booted
    a: tuple[float, float, float]  # g
    g: tuple[float, float, float]  # deg/s
    f: tuple[int, int, int, int]   # raw ADC counts 0..1023
    a_raw: tuple[int, int, int] = field(default=(0, 0, 0), repr=False)
    g_raw: tuple[int, int, int] = field(default=(0, 0, 0), repr=False)


def encode(t_us: int, a_raw, g_raw, f) -> bytes:
    body = _BODY.pack(t_us & 0xFFFFFFFF, *a_raw, *g_raw, *f)
    chk = 0
    for b in body:
        chk ^= b
    return SYNC + body + bytes([chk])


class PacketParser:
    """Incremental parser. Tolerates dropped bytes and resyncs on the header."""

    def __init__(self) -> None:
        self.buf = bytearray()
        self.bad = 0
        self._wrap = 0
        self._last_us = None

    def feed(self, data: bytes) -> list[Sample]:
        self.buf.extend(data)
        out: list[Sample] = []
        while True:
            i = self.buf.find(SYNC)
            if i < 0:
                # keep a trailing 0xAA in case the sync pair is split across reads
                self.buf = bytearray(b"\xaa") if self.buf[-1:] == b"\xaa" else bytearray()
                break
            if i > 0:
                del self.buf[:i]
            if len(self.buf) < PACKET_LEN:
                break
            body = bytes(self.buf[2:2 + _BODY.size])
            chk = self.buf[2 + _BODY.size]
            calc = 0
            for b in body:
                calc ^= b
            if calc != chk:
                self.bad += 1
                del self.buf[:1]
                continue
            del self.buf[:PACKET_LEN]
            t_us, ax, ay, az, gx, gy, gz, f0, f1, f2, f3 = _BODY.unpack(body)
            if self._last_us is not None and t_us < self._last_us:
                self._wrap += 1  # micros() rolls over every ~71 minutes
            self._last_us = t_us
            t = (t_us + self._wrap * 2**32) / 1e6
            out.append(Sample(
                t=t,
                a=(ax / ACCEL_LSB_PER_G, ay / ACCEL_LSB_PER_G, az / ACCEL_LSB_PER_G),
                g=(gx / GYRO_LSB_PER_DPS, gy / GYRO_LSB_PER_DPS, gz / GYRO_LSB_PER_DPS),
                f=(f0, f1, f2, f3),
                a_raw=(ax, ay, az),
                g_raw=(gx, gy, gz),
            ))
        return out
