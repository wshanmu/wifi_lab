#!/usr/bin/env python3
"""Shared CSI line parsing, serial reading, replay, and demo-signal helpers.

Used by plot_csi_serial.py and csi_presence_detect.py so the tagged,
variable-length CSI serial format is only parsed in one place.
"""

from __future__ import annotations

import dataclasses
import queue
import re
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

import numpy as np


CSI_LINE_RE = re.compile(
    r"<timestamp>(\d+)</timestamp><rssi>(-?\d+)</rssi><address>([0-9A-Fa-f:]+)</address>(.+)"
)

EXPECTED_SUBCARRIERS = 64

_warned_length_mismatch = False


@dataclasses.dataclass
class CsiSample:
    timestamp_cycles: int
    rssi: int
    address: str
    iq_values: list[int]


def parse_csi_line(line: str) -> Optional[CsiSample]:
    """Parse one sniffer.c serial line into a CsiSample, or None if it doesn't match."""
    match = CSI_LINE_RE.search(line)
    if not match:
        return None

    timestamp_str, rssi_str, address, values_str = match.groups()
    tokens = values_str.split()
    if not tokens:
        return None

    try:
        iq_values = [int(token) for token in tokens]
    except ValueError:
        return None

    return CsiSample(
        timestamp_cycles=int(timestamp_str),
        rssi=int(rssi_str),
        address=address,
        iq_values=iq_values,
    )


def iq_to_amplitude(iq_values: list[int]) -> np.ndarray:
    """Convert a flat (imag, real) x N int list into an N-length amplitude array."""
    global _warned_length_mismatch

    values = np.asarray(iq_values, dtype=np.float32)
    if values.size % 2 != 0:
        values = values[:-1]

    num_subcarriers = values.size // 2
    if num_subcarriers != EXPECTED_SUBCARRIERS and not _warned_length_mismatch:
        print(
            f"Warning: expected {EXPECTED_SUBCARRIERS} subcarriers "
            f"({EXPECTED_SUBCARRIERS * 2} values) but got {num_subcarriers} "
            f"({values.size} values). Continuing with the actual size."
        )
        _warned_length_mismatch = True

    imag = values[0::2]
    real = values[1::2]
    return np.sqrt(imag ** 2 + real ** 2)


def format_log_line(elapsed_seconds: float, raw_line: str) -> str:
    """Format a raw serial line for the replay log, prefixed with its arrival time."""
    return f"t={elapsed_seconds:.6f} {raw_line}"


LOG_LINE_RE = re.compile(r"t=([0-9.]+) (.*)")


def parse_log_line(line: str) -> Optional[tuple[float, str]]:
    """Parse a replay log line back into (elapsed_seconds, raw_line)."""
    match = LOG_LINE_RE.match(line)
    if not match:
        return None
    try:
        elapsed_seconds = float(match.group(1))
    except ValueError:
        return None
    return elapsed_seconds, match.group(2)


class SerialCsiReader:
    """Reads CSI samples from a live serial port on a background thread.

    Exposes the same (queue, start, stop) interface as ReplayCsiReader and
    DemoCsiReader, so tools can swap sources without branching their update
    loop.
    """

    def __init__(
        self,
        port: str,
        baud: int,
        log_path: Optional[str] = None,
        on_unparsed: Optional[Callable[[str], None]] = None,
        reset_on_connect: bool = True,
    ):
        self.port = self._macos_callout_port(port)
        self.baud = baud
        self.log_path = Path(log_path) if log_path else None
        self.on_unparsed = on_unparsed
        self.reset_on_connect = reset_on_connect
        self.queue: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._serial_lock = threading.Lock()
        self._serial = None

    @staticmethod
    def _macos_callout_port(port: str) -> str:
        """Prefer /dev/cu.* over /dev/tty.* for outgoing serial on macOS."""
        if sys.platform == "darwin" and port.startswith("/dev/tty."):
            callout_port = "/dev/cu." + port.removeprefix("/dev/tty.")
            if Path(callout_port).exists():
                return callout_port
        return port

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        with self._serial_lock:
            ser = self._serial
        if ser is not None:
            try:
                ser.cancel_read()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2)
            if self._thread.is_alive():
                with self._serial_lock:
                    ser = self._serial
                self._close_serial(ser)
                self._thread.join(timeout=1)
            self._thread = None

    def _open_serial(self, serial_module):
        ser = serial_module.Serial(
            port=None,
            baudrate=self.baud,
            timeout=0.1,
            write_timeout=0.1,
            rtscts=False,
            dsrdtr=False,
        )
        ser.dtr = False
        ser.rts = False
        ser.port = self.port
        ser.open()
        self._disable_hangup_on_close(ser)
        self._set_idle_control_lines(ser)
        return ser

    def _disable_hangup_on_close(self, ser) -> None:
        try:
            import termios

            attrs = termios.tcgetattr(ser.fileno())
            attrs[2] &= ~termios.HUPCL
            termios.tcsetattr(ser.fileno(), termios.TCSANOW, attrs)
        except Exception:
            pass

    def _set_idle_control_lines(self, ser) -> None:
        try:
            # ESP32 auto-reset boards expect EN and GPIO0 to sit high while
            # the app runs. With pyserial, inactive DTR/RTS is the idle state.
            ser.dtr = False
            ser.rts = False
        except Exception:
            pass

    def _reset_esp32_into_app(self, ser) -> None:
        try:
            ser.dtr = False  # GPIO0 high: normal boot, not bootloader.
            ser.rts = True   # EN low: hold reset.
            time.sleep(0.1)
            ser.rts = False  # EN high: run app.
            time.sleep(1.5)
            self._set_idle_control_lines(ser)
        except Exception:
            pass

    def _close_serial(self, ser) -> None:
        if ser is None:
            return
        self._set_idle_control_lines(ser)
        try:
            ser.close()
        except Exception:
            pass

    def _run(self) -> None:
        import serial  # imported here so importing csi_common never requires a serial port

        start_time = time.monotonic()
        log_file = None
        ser = None
        try:
            log_file = self.log_path.open("a", encoding="utf-8") if self.log_path else None
            ser = self._open_serial(serial)
            with self._serial_lock:
                self._serial = ser

            if self.reset_on_connect:
                self._reset_esp32_into_app(ser)
            if self._stop_event.is_set():
                return

            ser.reset_input_buffer()
            while not self._stop_event.is_set():
                raw = ser.readline()
                if not raw:
                    continue

                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                sample = parse_csi_line(line)
                if sample is None:
                    if self.on_unparsed is not None:
                        self.on_unparsed(line)
                    continue

                elapsed = time.monotonic() - start_time
                if log_file is not None:
                    log_file.write(format_log_line(elapsed, line) + "\n")
                    log_file.flush()

                self.queue.put(("sample", (elapsed, sample)))
        except (serial.SerialException, OSError) as exc:
            if not self._stop_event.is_set():
                self.queue.put(("error", str(exc)))
        finally:
            with self._serial_lock:
                if self._serial is ser:
                    self._serial = None
            self._close_serial(ser)
            if log_file is not None:
                log_file.close()


class ReplayCsiReader:
    """Replays a log file written by SerialCsiReader through the same queue interface."""

    def __init__(
        self,
        log_path: str,
        speed: float = 1.0,
        on_unparsed: Optional[Callable[[str], None]] = None,
    ):
        self.log_path = Path(log_path)
        self.speed = speed
        self.on_unparsed = on_unparsed
        self.queue: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _run(self) -> None:
        if not self.log_path.exists():
            self.queue.put(("error", f"Replay file not found: {self.log_path}"))
            return

        with self.log_path.open("r", encoding="utf-8") as f:
            lines = [line.rstrip("\n") for line in f if line.strip()]

        if not lines:
            self.queue.put(("error", f"Replay file is empty: {self.log_path}"))
            return

        previous_elapsed: Optional[float] = None
        for line in lines:
            if self._stop_event.is_set():
                return

            parsed = parse_log_line(line)
            if parsed is None:
                continue
            elapsed, raw_line = parsed

            sample = parse_csi_line(raw_line)
            if sample is None:
                if self.on_unparsed is not None:
                    self.on_unparsed(raw_line)
                continue

            if self.speed > 0 and previous_elapsed is not None:
                gap = (elapsed - previous_elapsed) / self.speed
                if gap > 0:
                    time.sleep(gap)
            previous_elapsed = elapsed

            self.queue.put(("sample", (elapsed, sample)))


DEMO_ADDRESS = "AA:BB:BB:BB:BB:BB"


def generate_demo_amplitude(num_subcarriers: int, t: float, rng: np.random.Generator) -> np.ndarray:
    """Synthetic per-subcarrier amplitude: calm baseline, alternating 4s idle / 4s motion."""
    motion_phase = int(t // 4.0) % 2
    base = 10.0 + 2.0 * np.sin(np.linspace(0.0, 2.0 * np.pi, num_subcarriers, dtype=np.float32))

    if motion_phase == 0:
        noise = rng.normal(scale=0.2, size=num_subcarriers)
    else:
        wobble = np.sin(4.0 * t + np.arange(num_subcarriers))
        noise = rng.normal(scale=3.0, size=num_subcarriers) * wobble

    return (base + noise).astype(np.float32)


class DemoCsiReader:
    """Generates synthetic CSI-like samples so tools can be exercised without hardware."""

    def __init__(self, num_subcarriers: int = EXPECTED_SUBCARRIERS, sample_rate: float = 100.0, seed: int = 0):
        self.num_subcarriers = num_subcarriers
        self.sample_rate = sample_rate
        self.seed = seed
        self.queue: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _run(self) -> None:
        rng = np.random.default_rng(self.seed)
        start_time = time.monotonic()
        period = 1.0 / self.sample_rate
        next_tick = start_time

        while not self._stop_event.is_set():
            elapsed = time.monotonic() - start_time
            amplitude = generate_demo_amplitude(self.num_subcarriers, elapsed, rng)

            iq_values: list[int] = []
            for value in amplitude:
                iq_values.append(0)
                iq_values.append(int(round(float(value))))

            sample = CsiSample(
                timestamp_cycles=0,
                rssi=-50,
                address=DEMO_ADDRESS,
                iq_values=iq_values,
            )
            self.queue.put(("sample", (elapsed, sample)))

            next_tick += period
            sleep_time = next_tick - time.monotonic()
            if sleep_time > 0:
                time.sleep(sleep_time)
