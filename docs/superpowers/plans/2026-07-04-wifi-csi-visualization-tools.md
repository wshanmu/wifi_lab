# WiFi CSI Sensing Lab Visualization Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the WiFi CSI sensing lab's Python visualization/exercise tools in `sniffer/tools/`, porting the IMU lab's pyqtgraph tooling pattern (live plot, smoothed-TODO exercise, presence-detection classifier exercise) to the ESP32 CSI sniffer's tagged, variable-length serial format.

**Architecture:** One shared parsing/IO module (`csi_common.py`) provides a `CsiSample` parser, an amplitude converter, and three interchangeable data sources (`SerialCsiReader`, `ReplayCsiReader`, `DemoCsiReader`) that all expose the same `(queue, start(), stop())` interface. Three standalone `pyqtgraph`/Qt tools consume that interface: a reference live heatmap+trace plot, a smoothed-TODO variant of it, and a presence/motion-detection tool whose `MotionDetector` class is shared verbatim between its online (`--port`) and offline (`--replay`) modes.

**Tech Stack:** Python 3.11, `numpy`, `pyserial`, `pyqtgraph`, `PyQt6`.

## Global Constraints

- Spec: `sniffer/docs/superpowers/specs/2026-07-04-wifi-csi-visualization-tools-design.md` (approved, committed as `f8a391f`).
- Tools live in `C:\Users\haofa\esp32\sniffer\tools\` — a plain Python directory, not wired into `CMakeLists.txt` (matches `IMU_lab/tools/`, which ESP-IDF's build never touches).
- Serial line format (from `sniffer/main/sniffer.c`): `<timestamp>%lu</timestamp><rssi>%d</rssi><address>%s</address>%d %d %d ...`. Trailing integers are `int8_t` (imag, real) pairs per subcarrier.
- `EXPECTED_SUBCARRIERS = 64` (128 raw values) — used only for a one-time mismatch warning; subcarrier count is always derived from the actual parsed length.
- Amplitude formula: for flat list `iq_values`, `amplitude[k] = sqrt(iq_values[2k]**2 + iq_values[2k+1]**2)` (even index = imaginary, odd index = real).
- Default baud: `115200` (matches `IMU_lab` and ESP-IDF console default).
- Replay log line format: `t=<elapsed_seconds:.6f> <raw serial line>`.
- Dependencies: `numpy`, `PyQt6`, `pyqtgraph`, `pyserial` only — no `scikit-learn`/`joblib` (this lab's classifier is a hand-implemented threshold rule, not trained ML).
- Per the spec's Testing section: **no automated test framework or test files are added to the repo** (matches `IMU_lab/tools/`, which has none). Verification below uses scratch, uncommitted Python snippets run from the terminal, plus manual GUI runs with `--demo-signal` — never a committed `tests/` directory or `pytest` file.
- `capture_trajectory.py` / `capture_trajectory_smoothed_TODO.py` have no port — not part of this plan.
- Student-facing TODO stubs (`MovingAverageFilter.update`, `MotionDetector.update`) must be verified by temporarily filling in a reference implementation, confirming behavior, then reverting to the stub **before** committing that file — the committed code must always contain the incomplete stub, not the reference solution.

---

### Task 1: Scaffold `tools/` directory and Python environment

**Files:**
- Create: `C:\Users\haofa\esp32\sniffer\tools\requirements.txt`

**Interfaces:**
- Produces: a working virtualenv at `sniffer/tools/.venv` with `numpy`, `PyQt6`, `pyqtgraph`, `pyserial` installed, used by every later task's verification commands as `tools/.venv/Scripts/python.exe`.

- [ ] **Step 1: Create the tools directory and requirements file**

Create `C:\Users\haofa\esp32\sniffer\tools\requirements.txt`:

```
numpy
PyQt6
pyqtgraph
pyserial
```

- [ ] **Step 2: Create a virtualenv and install dependencies**

Run (from `C:\Users\haofa\esp32\sniffer\tools`):

```bash
cd "/c/Users/haofa/esp32/sniffer/tools"
python -m venv .venv
.venv/Scripts/python.exe -m pip install --upgrade pip
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Expected: pip reports successful installation of `numpy`, `PyQt6` (and its `PyQt6-Qt6`/`PyQt6-sip` dependencies), `pyqtgraph`, `pyserial` with no errors.

- [ ] **Step 3: Verify the environment can import every dependency**

Run:

```bash
.venv/Scripts/python.exe -c "import numpy, serial, pyqtgraph; from PyQt6 import QtWidgets; print('deps ok')"
```

Expected: `deps ok` printed, no traceback.

- [ ] **Step 4: Commit**

```bash
cd "/c/Users/haofa/esp32/sniffer"
git add tools/requirements.txt
git commit -m "Add tools/ scaffold with Python dependency list for WiFi CSI lab"
```

(`.venv/` is not added — it's already covered by the root `.gitignore`'s `.venv/` pattern.)

---

### Task 2: `csi_common.py` — CSI line parsing and amplitude conversion

**Files:**
- Create: `C:\Users\haofa\esp32\sniffer\tools\csi_common.py`

**Interfaces:**
- Produces:
  - `CsiSample` dataclass with fields `timestamp_cycles: int`, `rssi: int`, `address: str`, `iq_values: list[int]`.
  - `parse_csi_line(line: str) -> Optional[CsiSample]`
  - `iq_to_amplitude(iq_values: list[int]) -> np.ndarray`
  - `EXPECTED_SUBCARRIERS: int = 64`

- [ ] **Step 1: Write the scratch verification (run before implementing, confirm it fails)**

Run:

```bash
cd "/c/Users/haofa/esp32/sniffer/tools"
.venv/Scripts/python.exe -c "
import csi_common
"
```

Expected: `ModuleNotFoundError: No module named 'csi_common'` (the file doesn't exist yet).

- [ ] **Step 2: Create `csi_common.py` with the parsing core**

```python
#!/usr/bin/env python3
"""Shared CSI line parsing, serial reading, replay, and demo-signal helpers.

Used by plot_csi_serial.py, plot_csi_smoothed_TODO.py, and
csi_presence_detect.py so the tagged, variable-length CSI serial format
is only parsed in one place.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Optional

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
```

- [ ] **Step 3: Run the scratch verification again**

Run:

```bash
.venv/Scripts/python.exe -c "
import numpy as np
from csi_common import parse_csi_line, iq_to_amplitude, EXPECTED_SUBCARRIERS

# A 4-subcarrier line (8 ints) so we don't need to type 128 numbers.
line = '<timestamp>12345</timestamp><rssi>-42</rssi><address>AA:BB:BB:BB:BB:BB</address>0 3 4 0 -1 1 2 2'
sample = parse_csi_line(line)
assert sample is not None
assert sample.timestamp_cycles == 12345
assert sample.rssi == -42
assert sample.address == 'AA:BB:BB:BB:BB:BB'
assert sample.iq_values == [0, 3, 4, 0, -1, 1, 2, 2]

amplitude = iq_to_amplitude(sample.iq_values)
expected = np.array([3.0, 4.0, np.sqrt(2), np.sqrt(8)], dtype=np.float32)
assert np.allclose(amplitude, expected), amplitude

assert parse_csi_line('garbage line') is None
assert EXPECTED_SUBCARRIERS == 64
print('csi_common core: OK')
"
```

Expected: `csi_common core: OK` printed, no `AssertionError` or traceback. (A one-line `Warning: expected 64 subcarriers...` is expected and fine — this 8-value test line only has 4 subcarriers.)

- [ ] **Step 4: Commit**

```bash
cd "/c/Users/haofa/esp32/sniffer"
git add tools/csi_common.py
git commit -m "Add CSI line parsing and amplitude conversion to csi_common"
```

---

### Task 3: `csi_common.py` — replay log format + `SerialCsiReader`

**Files:**
- Modify: `C:\Users\haofa\esp32\sniffer\tools\csi_common.py` (append to end of file)

**Interfaces:**
- Consumes: `parse_csi_line` (Task 2).
- Produces:
  - `format_log_line(elapsed_seconds: float, raw_line: str) -> str`
  - `parse_log_line(line: str) -> Optional[tuple[float, str]]`
  - `SerialCsiReader(port: str, baud: int, log_path: Optional[str] = None, on_unparsed: Optional[Callable[[str], None]] = None)` with `.queue`, `.start()`, `.stop()`. Emits `("sample", (elapsed: float, sample: CsiSample))` or `("error", message: str)` onto `.queue`.

- [ ] **Step 1: Write the scratch verification for the pure log-format helpers (confirm it fails first)**

Run:

```bash
cd "/c/Users/haofa/esp32/sniffer/tools"
.venv/Scripts/python.exe -c "
from csi_common import format_log_line, parse_log_line
"
```

Expected: `ImportError: cannot import name 'format_log_line'` (not written yet).

- [ ] **Step 2: Append the log-format helpers and `SerialCsiReader` to `csi_common.py`**

Add these imports to the top of `csi_common.py` (extend the existing `import` block, keep `dataclasses`, `re`, `Optional`, `np` already there):

```python
import queue
import threading
import time
from pathlib import Path
from typing import Callable, Optional
```

(Replace the existing `from typing import Optional` line with the `Callable, Optional` version above.)

Append to the end of the file:

```python
def format_log_line(elapsed_seconds: float, raw_line: str) -> str:
    """Format a raw serial line for the replay log, prefixed with its arrival time."""
    return f"t={elapsed_seconds:.6f} {raw_line}"


LOG_LINE_RE = re.compile(r"t=([0-9.]+) (.*)")


def parse_log_line(line: str) -> Optional[tuple[float, str]]:
    """Parse a replay log line back into (elapsed_seconds, raw_line)."""
    match = LOG_LINE_RE.match(line)
    if not match:
        return None
    return float(match.group(1)), match.group(2)


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
    ):
        self.port = port
        self.baud = baud
        self.log_path = Path(log_path) if log_path else None
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
        import serial  # imported here so importing csi_common never requires a serial port

        start_time = time.monotonic()
        log_file = self.log_path.open("a", encoding="utf-8") if self.log_path else None
        try:
            with serial.Serial(self.port, baudrate=self.baud, timeout=0.1) as ser:
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
        except serial.SerialException as exc:
            self.queue.put(("error", str(exc)))
        finally:
            if log_file is not None:
                log_file.close()
```

Note: `import serial` is deliberately done inside `SerialCsiReader._run` (not at module top) so that importing `csi_common` for the pure-function checks in Tasks 2, 4, and 5 never requires `pyserial` to be importable in whatever environment runs them — only code paths that actually open a serial port need it. `pyserial` is still a hard requirement for the tools themselves (declared in `requirements.txt`, installed in Task 1) since `SerialCsiReader` is exercised at real runtime.

- [ ] **Step 3: Run the scratch verification for the pure helpers**

Run:

```bash
.venv/Scripts/python.exe -c "
from csi_common import format_log_line, parse_log_line

line = format_log_line(1.5, '<timestamp>1</timestamp><rssi>-10</rssi><address>AA:BB:BB:BB:BB:BB</address>1 2')
assert line == 't=1.500000 <timestamp>1</timestamp><rssi>-10</rssi><address>AA:BB:BB:BB:BB:BB</address>1 2'

parsed = parse_log_line(line)
assert parsed == (1.5, '<timestamp>1</timestamp><rssi>-10</rssi><address>AA:BB:BB:BB:BB:BB</address>1 2')

assert parse_log_line('not a log line') is None
print('log line helpers: OK')
"
```

Expected: `log line helpers: OK`, no traceback.

- [ ] **Step 4: Verify `SerialCsiReader` at least constructs and imports cleanly (no real port needed for this check)**

Run:

```bash
.venv/Scripts/python.exe -c "
from csi_common import SerialCsiReader

reader = SerialCsiReader(port='COM_DOES_NOT_EXIST', baud=115200)
reader.start()
import time
time.sleep(0.3)
kind, payload = reader.queue.get(timeout=2)
assert kind == 'error', (kind, payload)
print('SerialCsiReader error path: OK ->', payload)
reader.stop()
"
```

Expected: `SerialCsiReader error path: OK -> ...` printed, where `...` is a pyserial error message about the port not existing (exact wording varies by platform — any `SerialException` message is acceptable). This confirms the reader's error-reporting path works without needing real hardware; the happy path (real CSI lines arriving) is confirmed manually in Task 10 with the actual board.

- [ ] **Step 5: Commit**

```bash
cd "/c/Users/haofa/esp32/sniffer"
git add tools/csi_common.py
git commit -m "Add replay log format and SerialCsiReader to csi_common"
```

---

### Task 4: `csi_common.py` — `ReplayCsiReader`

**Files:**
- Modify: `C:\Users\haofa\esp32\sniffer\tools\csi_common.py` (append to end of file)

**Interfaces:**
- Consumes: `parse_csi_line`, `parse_log_line` (Tasks 2–3).
- Produces: `ReplayCsiReader(log_path: str, speed: float = 1.0, on_unparsed: Optional[Callable[[str], None]] = None)` with the same `.queue` / `.start()` / `.stop()` interface, emitting the same `("sample", (elapsed, CsiSample))` / `("error", message)` tuples.

- [ ] **Step 1: Write the scratch verification (confirm it fails first)**

Run:

```bash
cd "/c/Users/haofa/esp32/sniffer/tools"
.venv/Scripts/python.exe -c "
from csi_common import ReplayCsiReader
"
```

Expected: `ImportError: cannot import name 'ReplayCsiReader'`.

- [ ] **Step 2: Append `ReplayCsiReader` to `csi_common.py`**

```python
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
```

- [ ] **Step 3: Run the scratch verification, exercising a real temp log file end-to-end**

Run:

```bash
.venv/Scripts/python.exe -c "
import tempfile, os, time
from csi_common import ReplayCsiReader, format_log_line

lines = [
    format_log_line(0.0, '<timestamp>1</timestamp><rssi>-40</rssi><address>AA:BB:BB:BB:BB:BB</address>0 3 4 0'),
    format_log_line(0.05, '<timestamp>2</timestamp><rssi>-41</rssi><address>AA:BB:BB:BB:BB:BB</address>-1 1 2 2'),
    format_log_line(0.10, '<timestamp>3</timestamp><rssi>-42</rssi><address>AA:BB:BB:BB:BB:BB</address>1 1 1 1'),
]

fd, path = tempfile.mkstemp(suffix='.txt')
os.close(fd)
with open(path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines) + '\n')

try:
    reader = ReplayCsiReader(path, speed=0)  # speed=0 -> as fast as possible
    reader.start()

    received = []
    deadline = time.monotonic() + 2.0
    while len(received) < 3 and time.monotonic() < deadline:
        try:
            kind, payload = reader.queue.get(timeout=0.5)
        except Exception:
            continue
        assert kind == 'sample', (kind, payload)
        received.append(payload)

    assert len(received) == 3, received
    assert received[0][1].rssi == -40
    assert received[1][1].rssi == -41
    assert received[2][1].rssi == -42
    assert [round(elapsed, 2) for elapsed, _ in received] == [0.0, 0.05, 0.1]
    reader.stop()
    print('ReplayCsiReader: OK')
finally:
    os.remove(path)
"
```

Expected: `ReplayCsiReader: OK`, no traceback. (The temp file is created and removed by the script itself — nothing is left in the repo.)

- [ ] **Step 4: Verify the missing-file and empty-file error paths**

Run:

```bash
.venv/Scripts/python.exe -c "
from csi_common import ReplayCsiReader

reader = ReplayCsiReader('this_file_does_not_exist.txt')
reader.start()
kind, payload = reader.queue.get(timeout=2)
assert kind == 'error' and 'not found' in payload, (kind, payload)
reader.stop()
print('ReplayCsiReader missing-file error: OK')
"
```

Expected: `ReplayCsiReader missing-file error: OK`.

- [ ] **Step 5: Commit**

```bash
cd "/c/Users/haofa/esp32/sniffer"
git add tools/csi_common.py
git commit -m "Add ReplayCsiReader to csi_common"
```

---

### Task 5: `csi_common.py` — demo signal generator (`DemoCsiReader`)

**Files:**
- Modify: `C:\Users\haofa\esp32\sniffer\tools\csi_common.py` (append to end of file)

**Interfaces:**
- Consumes: `CsiSample` (Task 2).
- Produces:
  - `generate_demo_amplitude(num_subcarriers: int, t: float, rng: np.random.Generator) -> np.ndarray`
  - `DemoCsiReader(num_subcarriers: int = EXPECTED_SUBCARRIERS, sample_rate: float = 100.0, seed: int = 0)` with the same `.queue` / `.start()` / `.stop()` interface as the other two readers, emitting only `("sample", (elapsed, CsiSample))` (it never errors).

- [ ] **Step 1: Write the scratch verification (confirm it fails first)**

Run:

```bash
cd "/c/Users/haofa/esp32/sniffer/tools"
.venv/Scripts/python.exe -c "
from csi_common import generate_demo_amplitude
"
```

Expected: `ImportError: cannot import name 'generate_demo_amplitude'`.

- [ ] **Step 2: Append the demo generator and `DemoCsiReader` to `csi_common.py`**

```python
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
```

- [ ] **Step 3: Run the scratch verification for `generate_demo_amplitude`'s idle-vs-motion behavior**

Run:

```bash
.venv/Scripts/python.exe -c "
import numpy as np
from csi_common import generate_demo_amplitude

rng = np.random.default_rng(0)
idle_samples = np.stack([generate_demo_amplitude(64, t, rng) for t in np.arange(0.0, 3.5, 0.1)])
motion_samples = np.stack([generate_demo_amplitude(64, t, rng) for t in np.arange(4.0, 7.5, 0.1)])

idle_variance = float(np.mean(np.var(idle_samples, axis=0)))
motion_variance = float(np.mean(np.var(motion_samples, axis=0)))

assert motion_variance > idle_variance * 3, (idle_variance, motion_variance)
print(f'generate_demo_amplitude: OK (idle={idle_variance:.3f}, motion={motion_variance:.3f})')
"
```

Expected: `generate_demo_amplitude: OK (idle=..., motion=...)` with the motion value clearly larger, no `AssertionError`.

- [ ] **Step 4: Run the scratch verification for `DemoCsiReader`**

Run:

```bash
.venv/Scripts/python.exe -c "
import time
from csi_common import DemoCsiReader, iq_to_amplitude

reader = DemoCsiReader(sample_rate=50.0)
reader.start()
time.sleep(0.5)

samples = []
while not reader.queue.empty():
    kind, payload = reader.queue.get_nowait()
    assert kind == 'sample', (kind, payload)
    samples.append(payload)

reader.stop()

assert len(samples) >= 10, len(samples)
elapsed, sample = samples[0]
amplitude = iq_to_amplitude(sample.iq_values)
assert amplitude.shape == (64,), amplitude.shape
assert sample.address == 'AA:BB:BB:BB:BB:BB'
print(f'DemoCsiReader: OK ({len(samples)} samples in 0.5s)')
"
```

Expected: `DemoCsiReader: OK (N samples in 0.5s)` with `N` roughly 20–30 (50 Hz for 0.5 s), no traceback.

- [ ] **Step 5: Commit**

```bash
cd "/c/Users/haofa/esp32/sniffer"
git add tools/csi_common.py
git commit -m "Add demo-signal generator and DemoCsiReader to csi_common"
```

---

### Task 6: `plot_csi_serial.py` — reference live heatmap + subcarrier trace

**Files:**
- Create: `C:\Users\haofa\esp32\sniffer\tools\plot_csi_serial.py`

**Interfaces:**
- Consumes: `csi_common.{CsiSample, iq_to_amplitude, SerialCsiReader, DemoCsiReader}` (Tasks 2, 3, 5).
- Produces: a runnable script; no other task imports from this file.

- [ ] **Step 1: Create `plot_csi_serial.py`**

```python
#!/usr/bin/env python3
"""Reference tool: live CSI amplitude heatmap + selectable-subcarrier trace."""

from __future__ import annotations

import argparse
import queue
import sys
from collections import deque

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtWidgets

from csi_common import DemoCsiReader, SerialCsiReader, iq_to_amplitude


class LiveCsiPlot(QtWidgets.QWidget):
    def __init__(self, args, data_queue):
        super().__init__()
        self.args = args
        self.data_queue = data_queue
        self.start_time = None
        self.sample_count = 0
        self.num_subcarriers = None
        self.selected_subcarrier = 0

        self.times = deque(maxlen=args.max_samples)
        self.amplitude_history = deque(maxlen=args.max_samples)

        self.setWindowTitle("ESP32 CSI Live Amplitude")
        self.resize(1180, 820)

        layout = QtWidgets.QVBoxLayout(self)

        control_row = QtWidgets.QHBoxLayout()
        control_row.addWidget(QtWidgets.QLabel("Subcarrier index:"))
        self.subcarrier_select = QtWidgets.QComboBox()
        self.subcarrier_select.currentIndexChanged.connect(self._on_subcarrier_changed)
        control_row.addWidget(self.subcarrier_select)
        control_row.addStretch(1)
        layout.addLayout(control_row)

        pg.setConfigOptions(antialias=True, background="#F5F7FB", foreground="#273142")
        self.graphics = pg.GraphicsLayoutWidget()
        layout.addWidget(self.graphics)

        self.heatmap_plot = self.graphics.addPlot(row=0, col=0, title="CSI Amplitude Heatmap")
        self.heatmap_plot.setLabel("left", "Subcarrier index")
        self.heatmap_plot.setLabel("bottom", "Time", units="s")
        self.image_item = pg.ImageItem()
        self.heatmap_plot.addItem(self.image_item)
        colormap = pg.colormap.get("viridis")
        self.image_item.setLookupTable(colormap.getLookupTable())

        self.graphics.nextRow()
        self.trace_plot = self.graphics.addPlot(row=1, col=0, title="Selected Subcarrier Amplitude")
        self.trace_plot.setLabel("left", "Amplitude")
        self.trace_plot.setLabel("bottom", "Time", units="s")
        self.trace_curve = self.trace_plot.plot(pen=pg.mkPen("#4C72B0", width=2.2))
        self.trace_plot.setXLink(self.heatmap_plot)

        self.status_label = QtWidgets.QLabel("Waiting for CSI samples...")
        layout.addWidget(self.status_label)

    def _on_subcarrier_changed(self, index: int) -> None:
        if index < 0:
            return
        self.selected_subcarrier = index

    def update(self) -> None:
        got_sample = False

        while True:
            try:
                kind, payload = self.data_queue.get_nowait()
            except queue.Empty:
                break

            if kind == "error":
                self.status_label.setText(f"Serial error: {payload}")
                print(f"Serial error: {payload}", file=sys.stderr)
                continue

            elapsed, sample = payload
            amplitude = iq_to_amplitude(sample.iq_values)

            if self.num_subcarriers is None:
                self.num_subcarriers = len(amplitude)
                self.subcarrier_select.addItems([str(i) for i in range(self.num_subcarriers)])

            if len(amplitude) != self.num_subcarriers:
                continue

            if self.start_time is None:
                self.start_time = elapsed

            self.times.append(elapsed - self.start_time)
            self.amplitude_history.append(amplitude)
            self.sample_count += 1
            got_sample = True

        if not got_sample or not self.times:
            return

        times_array = np.fromiter(self.times, dtype=np.float32, count=len(self.times))
        amplitude_matrix = np.stack(self.amplitude_history, axis=0)

        self.image_item.setImage(amplitude_matrix, autoLevels=True)
        x0, x1 = float(times_array[0]), float(times_array[-1])
        self.image_item.setRect(QtCore.QRectF(x0, 0, max(x1 - x0, 1e-6), self.num_subcarriers))

        selected_index = min(self.selected_subcarrier, self.num_subcarriers - 1)
        selected_trace = amplitude_matrix[:, selected_index]
        self.trace_curve.setData(times_array, selected_trace)

        right = max(self.args.window, x1)
        self.heatmap_plot.setXRange(max(0.0, right - self.args.window), right, padding=0)

        _, latest_sample = payload
        self.status_label.setText(
            f"samples {self.sample_count} | subcarriers {self.num_subcarriers} | "
            f"selected sc{selected_index} amplitude {selected_trace[-1]:.2f} | "
            f"rssi {latest_sample.rssi} dBm"
        )


def build_reader(args):
    if args.demo_signal:
        return DemoCsiReader()
    return SerialCsiReader(args.port, args.baud)


def main():
    parser = argparse.ArgumentParser(description="Live plot ESP32 CSI amplitude (heatmap + selected subcarrier).")
    parser.add_argument("--port", default=None, help="Serial port, e.g. COM5")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate")
    parser.add_argument("--window", type=float, default=10.0, help="Seconds of data to keep visible")
    parser.add_argument("--max-samples", type=int, default=2000, help="Maximum samples kept in memory")
    parser.add_argument("--fps", type=float, default=20.0, help="Plot refresh rate")
    parser.add_argument("--demo-signal", action="store_true", help="Use generated CSI-like data instead of serial input")
    args = parser.parse_args()

    if args.window <= 0.0:
        parser.error("--window must be positive")
    if args.fps <= 0.0:
        parser.error("--fps must be positive")
    if not args.demo_signal and not args.port:
        parser.error("--port is required unless --demo-signal is used")

    reader = build_reader(args)
    reader.start()

    app = QtWidgets.QApplication(sys.argv)
    window = LiveCsiPlot(args, reader.queue)
    window.show()

    timer = QtCore.QTimer()
    timer.timeout.connect(window.update)
    timer.start(max(1, int(1000 / args.fps)))

    def cleanup():
        timer.stop()
        reader.stop()

    app.aboutToQuit.connect(cleanup)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Automated startup smoke check (no display interaction required)**

This confirms the process imports, parses args, and starts generating demo data without raising — it does not confirm the window renders correctly (that needs a human, see Step 3).

Run:

```bash
cd "/c/Users/haofa/esp32/sniffer/tools"
.venv/Scripts/python.exe plot_csi_serial.py --demo-signal &
PID=$!
sleep 3
if kill -0 $PID 2>/dev/null; then
  echo "plot_csi_serial.py: still running after 3s (OK)"
  kill $PID
else
  echo "plot_csi_serial.py: exited early (FAIL)"
  wait $PID
fi
```

Expected: `plot_csi_serial.py: still running after 3s (OK)`. If it printed `FAIL`, re-run without backgrounding (`.venv/Scripts/python.exe plot_csi_serial.py --demo-signal`) to see the traceback and fix it before proceeding.

- [ ] **Step 3: Manual visual verification**

Ask a human with access to the desktop session to run:

```bash
.venv/Scripts/python.exe plot_csi_serial.py --demo-signal
```

Confirm: a window titled "ESP32 CSI Live Amplitude" opens; the top heatmap panel scrolls and shows a color gradient across ~64 subcarrier rows that visibly changes character every ~4 seconds (calm vs. noisy, per the demo generator's idle/motion phases); the subcarrier dropdown lists indices `0`..`63`; changing the dropdown updates which row's trace the bottom panel plots; the status line updates with sample count, rssi, and the selected subcarrier's amplitude.

- [ ] **Step 4: Commit**

```bash
cd "/c/Users/haofa/esp32/sniffer"
git add tools/plot_csi_serial.py
git commit -m "Add reference live CSI heatmap + subcarrier trace tool"
```

---

### Task 7: `plot_csi_smoothed_TODO.py` — moving-average student exercise

**Files:**
- Create: `C:\Users\haofa\esp32\sniffer\tools\plot_csi_smoothed_TODO.py`

**Interfaces:**
- Consumes: `csi_common.{iq_to_amplitude, SerialCsiReader, DemoCsiReader}` (Tasks 2, 3, 5).
- Produces: a runnable script containing `MovingAverageFilter` (shipped as an incomplete `pass` stub); no other task imports from this file.

- [ ] **Step 1: Create `plot_csi_smoothed_TODO.py` with a temporary reference `MovingAverageFilter` (for verification only — will be reverted to the stub in Step 3)**

```python
#!/usr/bin/env python3
"""Student exercise: live CSI amplitude view with raw-vs-smoothed subcarrier trace.

Complete MovingAverageFilter.update() below (same exercise as the IMU lab's
plot_imu_smoothed_TODO.py, applied to a CSI subcarrier's amplitude instead
of an IMU axis).
"""

from __future__ import annotations

import argparse
import queue
import sys
from collections import deque

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtWidgets

from csi_common import DemoCsiReader, SerialCsiReader, iq_to_amplitude


class MovingAverageFilter:
    """Streaming moving average.

    TODO SECTION:
    The task is to implement update(new_value) so it returns the average of
    the most recent N samples, where N is self.window_size.

    Notes:
    - Do not recompute sum(self.window) every time.
    - Keep a running_sum.
    - When the window is full, subtract the oldest sample before appending.
    - Return running_sum / number_of_samples_currently_in_window.
    """

    def __init__(self, window_size):
        self.window_size = window_size
        self.window = deque()
        self.running_sum = 0.0

    def update(self, new_value):
        if len(self.window) == self.window_size:
            self.running_sum -= self.window.popleft()
        self.window.append(new_value)
        self.running_sum += new_value
        return self.running_sum / len(self.window)


class LiveCsiSmoothedPlot(QtWidgets.QWidget):
    def __init__(self, args, data_queue):
        super().__init__()
        self.args = args
        self.data_queue = data_queue
        self.start_time = None
        self.sample_count = 0
        self.num_subcarriers = None
        self.selected_subcarrier = 0

        self.times = deque(maxlen=args.max_samples)
        self.amplitude_history = deque(maxlen=args.max_samples)
        self.smoothed_values = deque(maxlen=args.max_samples)
        self.filter = MovingAverageFilter(args.average_window)

        self.setWindowTitle("ESP32 CSI Raw + Smoothed Amplitude")
        self.resize(1180, 820)

        layout = QtWidgets.QVBoxLayout(self)

        control_row = QtWidgets.QHBoxLayout()
        control_row.addWidget(QtWidgets.QLabel("Subcarrier index:"))
        self.subcarrier_select = QtWidgets.QComboBox()
        self.subcarrier_select.currentIndexChanged.connect(self._on_subcarrier_changed)
        control_row.addWidget(self.subcarrier_select)
        control_row.addStretch(1)
        layout.addLayout(control_row)

        pg.setConfigOptions(antialias=True, background="#F5F7FB", foreground="#273142")
        self.graphics = pg.GraphicsLayoutWidget()
        layout.addWidget(self.graphics)

        self.heatmap_plot = self.graphics.addPlot(row=0, col=0, title="CSI Amplitude Heatmap (raw)")
        self.heatmap_plot.setLabel("left", "Subcarrier index")
        self.heatmap_plot.setLabel("bottom", "Time", units="s")
        self.image_item = pg.ImageItem()
        self.heatmap_plot.addItem(self.image_item)
        colormap = pg.colormap.get("viridis")
        self.image_item.setLookupTable(colormap.getLookupTable())

        self.graphics.nextRow()
        self.trace_plot = self.graphics.addPlot(row=1, col=0, title="Selected Subcarrier: Raw vs Smoothed")
        self.trace_plot.setLabel("left", "Amplitude")
        self.trace_plot.setLabel("bottom", "Time", units="s")
        self.raw_curve = self.trace_plot.plot(
            pen=pg.mkPen("#4C72B0", width=1.4, style=QtCore.Qt.PenStyle.DashLine), name="raw"
        )
        self.smooth_curve = self.trace_plot.plot(pen=pg.mkPen("#55A868", width=2.6), name="smoothed")
        self.trace_plot.addLegend(offset=(-12, 12))
        self.trace_plot.setXLink(self.heatmap_plot)

        self.status_label = QtWidgets.QLabel("Waiting for CSI samples...")
        layout.addWidget(self.status_label)

    def _on_subcarrier_changed(self, index: int) -> None:
        if index < 0:
            return
        self.selected_subcarrier = index
        self._recompute_smoothed()

    def _recompute_smoothed(self) -> None:
        self.filter = MovingAverageFilter(self.args.average_window)
        self.smoothed_values.clear()
        for amplitude in self.amplitude_history:
            index = min(self.selected_subcarrier, len(amplitude) - 1)
            self.smoothed_values.append(self.filter.update(amplitude[index]))

    def update(self) -> None:
        got_sample = False

        while True:
            try:
                kind, payload = self.data_queue.get_nowait()
            except queue.Empty:
                break

            if kind == "error":
                self.status_label.setText(f"Serial error: {payload}")
                print(f"Serial error: {payload}", file=sys.stderr)
                continue

            elapsed, sample = payload
            amplitude = iq_to_amplitude(sample.iq_values)

            if self.num_subcarriers is None:
                self.num_subcarriers = len(amplitude)
                self.subcarrier_select.addItems([str(i) for i in range(self.num_subcarriers)])

            if len(amplitude) != self.num_subcarriers:
                continue

            if self.start_time is None:
                self.start_time = elapsed

            self.times.append(elapsed - self.start_time)
            self.amplitude_history.append(amplitude)
            selected_index = min(self.selected_subcarrier, self.num_subcarriers - 1)
            self.smoothed_values.append(self.filter.update(amplitude[selected_index]))
            self.sample_count += 1
            got_sample = True

        if not got_sample or not self.times:
            return

        times_array = np.fromiter(self.times, dtype=np.float32, count=len(self.times))
        amplitude_matrix = np.stack(self.amplitude_history, axis=0)

        self.image_item.setImage(amplitude_matrix, autoLevels=True)
        x0, x1 = float(times_array[0]), float(times_array[-1])
        self.image_item.setRect(QtCore.QRectF(x0, 0, max(x1 - x0, 1e-6), self.num_subcarriers))

        selected_index = min(self.selected_subcarrier, self.num_subcarriers - 1)
        raw_trace = amplitude_matrix[:, selected_index]
        smooth_trace = np.fromiter(
            (v if v is not None else float("nan") for v in self.smoothed_values),
            dtype=np.float32,
            count=len(self.smoothed_values),
        )

        self.raw_curve.setData(times_array, raw_trace)
        self.smooth_curve.setData(times_array, smooth_trace)

        right = max(self.args.window, x1)
        self.heatmap_plot.setXRange(max(0.0, right - self.args.window), right, padding=0)

        self.status_label.setText(
            f"samples {self.sample_count} | subcarriers {self.num_subcarriers} | "
            f"moving average window {self.args.average_window} samples | "
            f"selected sc{selected_index} raw {raw_trace[-1]:.2f}"
        )


def build_reader(args):
    if args.demo_signal:
        return DemoCsiReader()
    return SerialCsiReader(args.port, args.baud)


def main():
    parser = argparse.ArgumentParser(description="Live plot ESP32 CSI amplitude with raw-vs-smoothed subcarrier trace.")
    parser.add_argument("--port", default=None, help="Serial port, e.g. COM5")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate")
    parser.add_argument("--window", type=float, default=10.0, help="Seconds of data to keep visible")
    parser.add_argument("--max-samples", type=int, default=2000, help="Maximum samples kept in memory")
    parser.add_argument("--fps", type=float, default=20.0, help="Plot refresh rate")
    parser.add_argument("--average-window", type=int, default=5, help="Moving average length in samples")
    parser.add_argument("--demo-signal", action="store_true", help="Use generated CSI-like data instead of serial input")
    args = parser.parse_args()

    if args.window <= 0.0:
        parser.error("--window must be positive")
    if args.fps <= 0.0:
        parser.error("--fps must be positive")
    if args.average_window < 1:
        parser.error("--average-window must be at least 1")
    if not args.demo_signal and not args.port:
        parser.error("--port is required unless --demo-signal is used")

    reader = build_reader(args)
    reader.start()

    app = QtWidgets.QApplication(sys.argv)
    window = LiveCsiSmoothedPlot(args, reader.queue)
    window.show()

    timer = QtCore.QTimer()
    timer.timeout.connect(window.update)
    timer.start(max(1, int(1000 / args.fps)))

    def cleanup():
        timer.stop()
        reader.stop()

    app.aboutToQuit.connect(cleanup)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the reference `MovingAverageFilter` behaves correctly (headless, no GUI)**

Run:

```bash
cd "/c/Users/haofa/esp32/sniffer/tools"
.venv/Scripts/python.exe -c "
import importlib.util
spec = importlib.util.spec_from_file_location('smoothed_todo', 'plot_csi_smoothed_TODO.py')
module = importlib.util.module_from_spec(spec)
import sys
sys.argv = ['plot_csi_smoothed_TODO.py']  # avoid argparse seeing pytest/host args
spec.loader.exec_module(module)

f = module.MovingAverageFilter(window_size=3)
results = [f.update(v) for v in [10, 20, 30, 40]]
assert results[0] == 10.0
assert results[1] == 15.0
assert abs(results[2] - 20.0) < 1e-9
assert abs(results[3] - 30.0) < 1e-9  # window is now [20,30,40]
print('MovingAverageFilter reference implementation: OK')
"
```

Expected: `MovingAverageFilter reference implementation: OK`. (Loading the module this way runs only its definitions, not `main()`, since it's guarded by `if __name__ == "__main__":`.)

- [ ] **Step 3: Manual visual verification of the reference implementation, then revert to the student stub**

Ask a human to run:

```bash
.venv/Scripts/python.exe plot_csi_smoothed_TODO.py --demo-signal --average-window 8
```

Confirm: same layout as `plot_csi_serial.py`, plus the bottom panel now shows a dashed raw line and a solid green smoothed line that visibly lags/flattens the raw line's fluctuations.

Once confirmed, **replace** the `MovingAverageFilter.update` method body (the reference implementation from Step 1) with the student TODO stub — this is the version that gets committed:

```python
    def update(self, new_value):
        # TODO: Implement the moving average update logic here
        pass
```

- [ ] **Step 4: Confirm the harness still runs (without crashing) with the stub in place**

Run the same startup smoke check as Task 6 Step 2, pointed at this file:

```bash
.venv/Scripts/python.exe plot_csi_smoothed_TODO.py --demo-signal &
PID=$!
sleep 3
if kill -0 $PID 2>/dev/null; then
  echo "plot_csi_smoothed_TODO.py: still running after 3s (OK)"
  kill $PID
else
  echo "plot_csi_smoothed_TODO.py: exited early (FAIL)"
  wait $PID
fi
```

Expected: `plot_csi_smoothed_TODO.py: still running after 3s (OK)`. The smoothed curve will not appear (the stub returns `None`, plotted as `NaN`) — that's the correct pre-implementation state; the raw dashed curve and heatmap still render.

- [ ] **Step 5: Commit**

```bash
cd "/c/Users/haofa/esp32/sniffer"
git add tools/plot_csi_smoothed_TODO.py
git commit -m "Add moving-average smoothing TODO exercise for CSI subcarrier trace"
```

---

### Task 8: `csi_presence_detect.py` — shared `MotionDetector`, online + offline

**Files:**
- Create: `C:\Users\haofa\esp32\sniffer\tools\csi_presence_detect.py`

**Interfaces:**
- Consumes: `csi_common.{DemoCsiReader, ReplayCsiReader, SerialCsiReader, iq_to_amplitude, format_log_line}` (Tasks 2–5).
- Produces: a runnable script containing `MotionDetector` (shipped as an incomplete-but-safe stub); no other task imports from this file.

- [ ] **Step 1: Create `csi_presence_detect.py` with a temporary reference `MotionDetector` (for verification only — will be reverted to the stub in Step 3)**

```python
#!/usr/bin/env python3
"""Student exercise: WiFi CSI presence/motion detector.

Runs identically online (--port, live serial) and offline (--replay, a log
file recorded by a previous --log run), by feeding both through the same
MotionDetector instance and GUI update loop.

Complete MotionDetector.update() below.
"""

from __future__ import annotations

import argparse
import collections
import queue
import sys
from collections import deque

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtWidgets

from csi_common import DemoCsiReader, ReplayCsiReader, SerialCsiReader, iq_to_amplitude


class MotionDetector:
    """Sliding-window variance-based motion detector.

    TODO SECTION:
    Implement update(amplitude_vector) so it:
    1. Appends amplitude_vector to self.history (already done below; a
       deque with maxlen=self.window_size, so it automatically drops the
       oldest vector once full).
    2. Once self.history has at least 2 vectors, computes the variance of
       each subcarrier's amplitude across the vectors currently in
       self.history. np.var(np.stack(self.history), axis=0) is the natural
       tool here -- it gives one variance value per subcarrier.
    3. Aggregates that per-subcarrier variance array into a single score,
       e.g. its mean: float(np.mean(per_subcarrier_variance)).
    4. Returns {"score": score, "motion": score > self.threshold}.

    Before there are at least 2 samples in the window, return
    {"score": 0.0, "motion": False} -- this is also the fallback behavior
    of the stub below, so the surrounding GUI always has a valid result to
    render even before the TODO is implemented.
    """

    def __init__(self, window_size: int, threshold: float):
        self.window_size = window_size
        self.threshold = threshold
        self.history: "collections.deque[np.ndarray]" = collections.deque(maxlen=window_size)

    def update(self, amplitude_vector: np.ndarray) -> dict:
        self.history.append(amplitude_vector)
        if len(self.history) < 2:
            return {"score": 0.0, "motion": False}
        per_subcarrier_variance = np.var(np.stack(self.history), axis=0)
        score = float(np.mean(per_subcarrier_variance))
        return {"score": score, "motion": score > self.threshold}


class PresenceDetectorWindow(QtWidgets.QWidget):
    def __init__(self, args, data_queue, detector):
        super().__init__()
        self.args = args
        self.data_queue = data_queue
        self.detector = detector
        self.start_time = None
        self.sample_count = 0

        self.times = deque(maxlen=args.max_samples)
        self.scores = deque(maxlen=args.max_samples)

        self.setWindowTitle("ESP32 CSI Presence Detector")
        self.resize(900, 620)

        layout = QtWidgets.QVBoxLayout(self)

        self.status_label = QtWidgets.QLabel("Waiting for CSI samples...")
        self.status_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        font = self.status_label.font()
        font.setPointSize(28)
        font.setBold(True)
        self.status_label.setFont(font)
        layout.addWidget(self.status_label)

        pg.setConfigOptions(antialias=True, background="#F5F7FB", foreground="#273142")
        self.graphics = pg.GraphicsLayoutWidget()
        layout.addWidget(self.graphics)

        self.score_plot = self.graphics.addPlot(title="Motion Score")
        self.score_plot.setLabel("left", "Score")
        self.score_plot.setLabel("bottom", "Time", units="s")
        self.score_curve = self.score_plot.plot(pen=pg.mkPen("#4C72B0", width=2.2))
        self.threshold_line = pg.InfiniteLine(
            pos=args.threshold, angle=0,
            pen=pg.mkPen("#C44E52", width=1.6, style=QtCore.Qt.PenStyle.DashLine),
        )
        self.score_plot.addItem(self.threshold_line)

        self.detail_label = QtWidgets.QLabel("")
        layout.addWidget(self.detail_label)

    def update(self) -> None:
        got_sample = False
        latest_result = None
        latest_sample = None

        while True:
            try:
                kind, payload = self.data_queue.get_nowait()
            except queue.Empty:
                break

            if kind == "error":
                self.status_label.setText(f"Error: {payload}")
                print(f"Error: {payload}", file=sys.stderr)
                continue

            elapsed, sample = payload
            amplitude = iq_to_amplitude(sample.iq_values)
            result = self.detector.update(amplitude)

            if self.start_time is None:
                self.start_time = elapsed

            self.times.append(elapsed - self.start_time)
            self.scores.append(result["score"])
            self.sample_count += 1
            got_sample = True
            latest_result = result
            latest_sample = sample

        if not got_sample or not self.times:
            return

        if latest_result["motion"]:
            self.status_label.setText("MOTION DETECTED")
            self.status_label.setStyleSheet("color: #B42318;")
        else:
            self.status_label.setText("NO MOTION")
            self.status_label.setStyleSheet("color: #166534;")

        self.detail_label.setText(
            f"samples {self.sample_count} | score {latest_result['score']:.3f} | "
            f"threshold {self.args.threshold:.3f} | rssi {latest_sample.rssi} dBm"
        )

        times_array = np.fromiter(self.times, dtype=np.float32, count=len(self.times))
        scores_array = np.fromiter(self.scores, dtype=np.float32, count=len(self.scores))
        self.score_curve.setData(times_array, scores_array)


def build_reader(args):
    if args.demo_signal:
        return DemoCsiReader()
    if args.replay:
        return ReplayCsiReader(args.replay, speed=args.replay_speed)
    return SerialCsiReader(args.port, args.baud, log_path=args.log)


def main():
    parser = argparse.ArgumentParser(description="WiFi CSI presence/motion detector (online + offline).")
    parser.add_argument("--port", default=None, help="Serial port for live detection, e.g. COM5")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate")
    parser.add_argument("--log", default=None, help="Path to record raw CSI lines for later --replay")
    parser.add_argument("--replay", default=None, help="Replay a log file recorded with --log instead of live serial")
    parser.add_argument("--replay-speed", type=float, default=1.0, help="Replay pacing multiplier; 0 = as fast as possible")
    parser.add_argument("--demo-signal", action="store_true", help="Use generated CSI-like data instead of serial/replay input")
    parser.add_argument("--window-size", type=int, default=20, help="Number of packets in the motion detector's sliding window")
    parser.add_argument("--threshold", type=float, default=2.0, help="Motion score threshold")
    parser.add_argument("--max-samples", type=int, default=500, help="Maximum samples kept in memory for the score plot")
    parser.add_argument("--fps", type=float, default=20.0, help="Plot refresh rate")
    args = parser.parse_args()

    modes_selected = sum(bool(x) for x in (args.port, args.replay, args.demo_signal))
    if modes_selected != 1:
        parser.error("Provide exactly one of --port, --replay, or --demo-signal")
    if args.window_size < 2:
        parser.error("--window-size must be at least 2")
    if args.fps <= 0.0:
        parser.error("--fps must be positive")

    reader = build_reader(args)
    reader.start()

    detector = MotionDetector(window_size=args.window_size, threshold=args.threshold)

    app = QtWidgets.QApplication(sys.argv)
    window = PresenceDetectorWindow(args, reader.queue, detector)
    window.show()

    timer = QtCore.QTimer()
    timer.timeout.connect(window.update)
    timer.start(max(1, int(1000 / args.fps)))

    def cleanup():
        timer.stop()
        reader.stop()

    app.aboutToQuit.connect(cleanup)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the reference `MotionDetector` headlessly against the demo-signal generator (no GUI, no hardware)**

Run:

```bash
cd "/c/Users/haofa/esp32/sniffer/tools"
.venv/Scripts/python.exe -c "
import importlib.util, sys
spec = importlib.util.spec_from_file_location('presence_detect', 'csi_presence_detect.py')
module = importlib.util.module_from_spec(spec)
sys.argv = ['csi_presence_detect.py']
spec.loader.exec_module(module)

import numpy as np
from csi_common import generate_demo_amplitude

detector = module.MotionDetector(window_size=20, threshold=2.0)
rng = np.random.default_rng(0)

idle_motion_flags = [detector.update(generate_demo_amplitude(64, t, rng))['motion'] for t in np.arange(0.0, 3.5, 0.05)]
motion_motion_flags = [detector.update(generate_demo_amplitude(64, t, rng))['motion'] for t in np.arange(4.0, 7.5, 0.05)]

assert sum(idle_motion_flags) == 0, f'expected no motion flags during idle phase, got {sum(idle_motion_flags)}'
assert sum(motion_motion_flags) > len(motion_motion_flags) // 2, (
    f'expected most of the motion phase to be flagged as motion, got {sum(motion_motion_flags)}/{len(motion_motion_flags)}'
)
print('MotionDetector reference implementation: OK')
"
```

Expected: `MotionDetector reference implementation: OK`. If the idle phase produces false positives or the motion phase isn't reliably detected, adjust `--threshold`'s default (currently `2.0`) against the demo generator's actual idle/motion variance levels (printed by Task 5 Step 3's check) before proceeding — the default must comfortably separate the two demo phases.

- [ ] **Step 3: Verify online-vs-offline parity (`--log` then `--replay` produce the same classifications) — headless, using `DemoCsiReader` as the "live" source**

Run:

```bash
.venv/Scripts/python.exe -c "
import importlib.util, sys, tempfile, os, time
spec = importlib.util.spec_from_file_location('presence_detect', 'csi_presence_detect.py')
module = importlib.util.module_from_spec(spec)
sys.argv = ['csi_presence_detect.py']
spec.loader.exec_module(module)

from csi_common import DemoCsiReader, ReplayCsiReader, format_log_line, iq_to_amplitude

fd, log_path = tempfile.mkstemp(suffix='.txt')
os.close(fd)

try:
    # 'Online' pass: drive DemoCsiReader directly and tee to a log file by hand
    # (equivalent to SerialCsiReader's log_path behavior, without needing a port).
    live_reader = DemoCsiReader(sample_rate=50.0)
    live_reader.start()
    time.sleep(3.0)
    live_reader.stop()

    online_detector = module.MotionDetector(window_size=20, threshold=2.0)
    online_results = []
    with open(log_path, 'w', encoding='utf-8') as f:
        while not live_reader.queue.empty():
            kind, (elapsed, sample) = live_reader.queue.get_nowait()
            assert kind == 'sample'
            raw_line = (
                f'<timestamp>{sample.timestamp_cycles}</timestamp>'
                f'<rssi>{sample.rssi}</rssi><address>{sample.address}</address>'
                + ' '.join(str(v) for v in sample.iq_values)
            )
            f.write(format_log_line(elapsed, raw_line) + '\n')
            online_results.append(online_detector.update(iq_to_amplitude(sample.iq_values))['motion'])

    # Offline pass: replay the log file just written, as fast as possible.
    replay_reader = ReplayCsiReader(log_path, speed=0)
    replay_reader.start()
    offline_detector = module.MotionDetector(window_size=20, threshold=2.0)
    offline_results = []
    deadline = time.monotonic() + 5.0
    while len(offline_results) < len(online_results) and time.monotonic() < deadline:
        try:
            kind, (elapsed, sample) = replay_reader.queue.get(timeout=0.5)
        except Exception:
            continue
        assert kind == 'sample'
        offline_results.append(offline_detector.update(iq_to_amplitude(sample.iq_values))['motion'])
    replay_reader.stop()

    assert online_results == offline_results, (online_results, offline_results)
    print(f'Online/offline parity: OK ({len(online_results)} samples, identical classifications)')
finally:
    os.remove(log_path)
"
```

Expected: `Online/offline parity: OK (N samples, identical classifications)`, no `AssertionError`. This confirms the same `MotionDetector` class produces identical results whether fed live or replayed.

- [ ] **Step 4: Manual visual verification, then revert to the student stub**

Ask a human to run:

```bash
.venv/Scripts/python.exe csi_presence_detect.py --demo-signal
```

Confirm: the status label alternates between "NO MOTION" (green) and "MOTION DETECTED" (red) roughly every 4 seconds, matching the demo generator's idle/motion phases; the score plot scrolls with a visible dashed threshold line; the score visibly rises above the threshold during motion phases.

Once confirmed, **replace** the `MotionDetector.update` method body with the student-safe stub — this is the version that gets committed. It must remain safe to call every frame (never raise, always return a valid dict) while leaving the actual variance/threshold logic for the student:

```python
    def update(self, amplitude_vector: np.ndarray) -> dict:
        self.history.append(amplitude_vector)
        # TODO: Once self.history has at least 2 vectors, compute the
        # variance of each subcarrier's amplitude across self.history
        # (np.var(np.stack(self.history), axis=0)), aggregate it to a
        # single score (e.g. float(np.mean(...))), and return
        # {"score": score, "motion": score > self.threshold}.
        return {"score": 0.0, "motion": False}
```

- [ ] **Step 5: Confirm the harness still runs (without crashing) with the stub in place**

Run:

```bash
.venv/Scripts/python.exe csi_presence_detect.py --demo-signal &
PID=$!
sleep 3
if kill -0 $PID 2>/dev/null; then
  echo "csi_presence_detect.py: still running after 3s (OK)"
  kill $PID
else
  echo "csi_presence_detect.py: exited early (FAIL)"
  wait $PID
fi
```

Expected: `csi_presence_detect.py: still running after 3s (OK)`. With the stub in place, the status label will always read "NO MOTION" — that's the correct pre-implementation state.

- [ ] **Step 6: Commit**

```bash
cd "/c/Users/haofa/esp32/sniffer"
git add tools/csi_presence_detect.py
git commit -m "Add presence/motion detection TODO exercise with online+offline harness"
```

---

### Task 9: `README.md`

**Files:**
- Create: `C:\Users\haofa\esp32\sniffer\tools\README.md`

**Interfaces:**
- None (documentation only).

- [ ] **Step 1: Create `tools/README.md`**

```markdown
# WiFi CSI Sensing Lab Tools

This folder contains the Python visualization and exercise tools for the WiFi
CSI sensing lab. They read tagged CSI reports from the ESP32 sniffer firmware
(`main/sniffer.c`) over USB serial, then visualize amplitude and (for the
presence-detection exercise) classify whether motion is happening near the
link.

## What You Will Use

| Path | Purpose |
| --- | --- |
| `csi_common.py` | Shared CSI line parser, serial/replay/demo data sources. Not run directly. |
| `plot_csi_serial.py` | Live amplitude heatmap + selectable-subcarrier trace (reference). |
| `plot_csi_smoothed_TODO.py` | Student TODO: moving-average smoothing of the selected subcarrier's amplitude. |
| `csi_presence_detect.py` | Student TODO: variance-threshold motion detector, runnable online (live serial) or offline (replayed log). |

## Hardware Overview

```text
WiFi injector --> 802.11 Data frames --> ESP32 (sniffer.c, promiscuous + CSI) --> USB serial --> Python tools
```

The firmware only logs CSI for the injector's spoofed sender MAC
(`AA:BB:BB:BB:BB:BB`), filtered by frame-control byte, on WiFi channel 1 with
HT-LLTF CSI enabled (128 raw `int8` values -> 64 subcarriers per packet).

Expected raw serial line (what these tools parse):

```text
<timestamp>123456</timestamp><rssi>-42</rssi><address>AA:BB:BB:BB:BB:BB</address>0 3 4 0 -1 1 ...
```

## Python Setup

Windows PowerShell, from `tools/`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Find the ESP32 serial port in Device Manager -> Ports (COM & LPT).

## Run the Tools

All three tools accept `--demo-signal` to run without any ESP32 attached,
using a synthetic amplitude signal that alternates every 4 seconds between a
calm ("idle") phase and a noisy ("motion") phase -- useful for testing your
TODO implementations before you have hardware in hand.

Live heatmap + subcarrier trace:

```powershell
python plot_csi_serial.py --port COM5 --baud 115200
python plot_csi_serial.py --demo-signal
```

Smoothed subcarrier trace (TODO):

```powershell
python plot_csi_smoothed_TODO.py --port COM5 --average-window 8
python plot_csi_smoothed_TODO.py --demo-signal --average-window 8
```

Presence/motion detector (TODO), live:

```powershell
python csi_presence_detect.py --port COM5 --log capture1.txt
```

Presence/motion detector (TODO), replayed from a log recorded above:

```powershell
python csi_presence_detect.py --replay capture1.txt
```

Presence/motion detector (TODO), no hardware:

```powershell
python csi_presence_detect.py --demo-signal
```

## Student TODOs

### `plot_csi_smoothed_TODO.py`: `MovingAverageFilter.update`

Same exercise as the IMU lab's `plot_imu_smoothed_TODO.py`: implement a
streaming moving average over the most recent `self.window_size` samples,
using `self.running_sum` and the `self.window` deque (do not recompute the
sum from scratch on every call).

### `csi_presence_detect.py`: `MotionDetector.update`

Implement a sliding-window variance-based motion score:

1. `self.history` already keeps the most recent `self.window_size` amplitude
   vectors (one per CSI packet) -- it's a `deque(maxlen=self.window_size)`.
2. Once there are at least 2 vectors in `self.history`, compute the variance
   of each subcarrier's amplitude across the window:
   `np.var(np.stack(self.history), axis=0)`.
3. Aggregate that per-subcarrier variance array into one score, e.g.
   `float(np.mean(per_subcarrier_variance))`.
4. Return `{"score": score, "motion": score > self.threshold}`.

Before there are 2 samples yet, return `{"score": 0.0, "motion": False}`.

Tune `--threshold` and `--window-size` against your own data (or
`--demo-signal`, which has a clear idle/motion distinction) once implemented.

## Notes

- Subcarrier count is derived from the actual parsed CSI length each packet
  (expected: 64 subcarriers / 128 raw values); a one-time warning prints if
  it differs, but the tools keep running.
- `--log` in `csi_presence_detect.py` records raw serial lines (prefixed with
  arrival time) so you can `--replay` the exact same session later and get
  identical classifier behavior.
```

- [ ] **Step 2: Confirm every command in the README matches an actual argparse flag**

Run:

```bash
cd "/c/Users/haofa/esp32/sniffer/tools"
.venv/Scripts/python.exe plot_csi_serial.py --help
.venv/Scripts/python.exe plot_csi_smoothed_TODO.py --help
.venv/Scripts/python.exe csi_presence_detect.py --help
```

Expected: each prints its argparse help text with no traceback, and manually cross-check that `--port`, `--baud`, `--average-window`, `--log`, `--replay`, `--demo-signal` (as used in the README) all appear.

- [ ] **Step 3: Commit**

```bash
cd "/c/Users/haofa/esp32/sniffer"
git add tools/README.md
git commit -m "Add WiFi CSI tools README"
```

---

### Task 10: End-to-end manual verification

**Files:** none (verification only).

**Interfaces:** none.

- [ ] **Step 1: Demo-signal pass on all three tools**

Ask a human with desktop access to run each of the following for ~15 seconds and confirm the behaviors described in Tasks 6/7/8's manual-verification steps:

```bash
cd "/c/Users/haofa/esp32/sniffer/tools"
.venv/Scripts/python.exe plot_csi_serial.py --demo-signal
.venv/Scripts/python.exe plot_csi_smoothed_TODO.py --demo-signal --average-window 8
.venv/Scripts/python.exe csi_presence_detect.py --demo-signal
```

- [ ] **Step 2: Real-hardware pass (once the sniffer firmware is flashed and an injector is transmitting)**

```bash
.venv/Scripts/python.exe plot_csi_serial.py --port COMx
.venv/Scripts/python.exe csi_presence_detect.py --port COMx --log capture1.txt
.venv/Scripts/python.exe csi_presence_detect.py --replay capture1.txt
```

Confirm: real CSI data renders in the heatmap (not just noise), and the `--log` / `--replay` pair produce visually consistent MOTION/NO MOTION behavior for the same recorded session (exact score values may differ slightly in timing since replay pacing isn't the same as the original wall-clock trace beyond what's stored in the log, but the motion/no-motion pattern should match).

No commit for this task (verification only, no files changed).

---

## Self-Review Notes

- **Spec coverage:** All six spec sections (Components 1–4, requirements.txt, README) map to Tasks 1–9. The spec's "Testing" section maps to the scratch-verification steps embedded in every task plus Task 10. The spec's "Open Items" note (sniffer wasn't a git repo) was already resolved by the user (`git init` done in the prior session, spec commit `f8a391f` already exists).
- **Placeholder scan:** no `TBD`/`TODO` left unresolved in this plan's own instructions — every `TODO` string that appears is intentionally inside a student-facing source file, not a gap in the plan.
- **Type consistency:** `CsiSample`, `iq_to_amplitude`, and all three readers' `(queue, start, stop)` interface are defined once in Task 2/3/4/5 and used with identical signatures in Tasks 6–8; `MotionDetector.update`'s return shape (`{"score": float, "motion": bool}`) is identical between its Task 8 Step 1 reference version and Step 4's committed stub.
- **Scope check:** single cohesive deliverable (one `tools/` directory, four source files + docs); no unrelated subsystems bundled in.
