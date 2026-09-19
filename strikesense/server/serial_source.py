"""Reads the Arduino Uno over USB serial on a background thread."""
from __future__ import annotations

import queue
import threading
import time

from protocol import PacketParser, Sample


def find_port() -> str:
    from serial.tools import list_ports
    for p in list_ports.comports():
        desc = f"{p.description} {p.manufacturer or ''}".lower()
        if any(k in desc for k in ("arduino", "ch340", "usb serial", "usbmodem", "usbserial")):
            return p.device
    raise RuntimeError("No Arduino found. Plug it in or set SERIAL_PORT (for example COM5 or /dev/ttyACM0).")


class SerialSource:
    def __init__(self, port: str, baud: int) -> None:
        import serial
        self.name = "serial"
        self.port = port or find_port()
        self.ser = serial.Serial(self.port, baud, timeout=0.05)
        time.sleep(2.0)  # the Uno resets when the port opens
        self.ser.reset_input_buffer()
        self.parser = PacketParser()
        self.q: queue.Queue[Sample] = queue.Queue(maxsize=20000)
        self.alive = True
        threading.Thread(target=self._run, daemon=True).start()

    @property
    def bad_packets(self) -> int:
        return self.parser.bad

    def _run(self) -> None:
        while self.alive:
            try:
                data = self.ser.read(self.ser.in_waiting or 1)
            except Exception:
                time.sleep(0.2)
                continue
            for s in self.parser.feed(data):
                try:
                    self.q.put_nowait(s)
                except queue.Full:
                    pass

    def drain(self) -> list[Sample]:
        out = []
        while True:
            try:
                out.append(self.q.get_nowait())
            except queue.Empty:
                return out

    def close(self) -> None:
        self.alive = False
        try:
            self.ser.close()
        except Exception:
            pass
