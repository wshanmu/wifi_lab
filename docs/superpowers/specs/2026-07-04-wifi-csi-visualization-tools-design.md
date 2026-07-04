# WiFi CSI Sensing Lab — Visualization Tools Design

Date: 2026-07-04
Status: Approved by user, pending implementation plan

## Background

The UCLA COSMOS Cluster 10 course has an existing IMU lab (`IMU_lab` repo) with a set of
Python visualization/exercise tools built on `pyqtgraph` + `pyserial`, reading fixed-format
serial lines from an ESP32 (`accel[g] x=... | gyro[dps] x=...`). We are building a parallel
WiFi CSI sensing lab, reusing the same firmware/tools architecture and lab pedagogy
(reference scripts + `_TODO` student exercises), but adapted to CSI data.

The firmware lives at `C:\Users\haofa\esp32\sniffer\main\sniffer.c`. Its CSI callback
(`receive_csi_cb`) prints one line per received CSI report:

```
<timestamp>%lu</timestamp><rssi>%d</rssi><address>%s</address>%d %d %d ...\n
```

- `timestamp` is the ESP32 CPU cycle counter (`CCOUNT`) at capture time — a free-running
  counter, not wall-clock time, and not directly convertible to seconds without knowing
  clock frequency and handling wraparound.
- `address` is the sender MAC (already filtered by firmware to the injector's spoofed MAC).
- The trailing space-separated integers are the raw CSI buffer: `int8_t` (imaginary, real)
  pairs per subcarrier. With HT-LLTF CSI enabled at 20MHz (the configured mode), this is
  128 values → 64 subcarriers. Tools should size themselves from the actual parsed length
  at runtime rather than hardcoding 128, and warn once if it differs from the expected 64
  subcarriers, so the tools degrade gracefully if the firmware config changes.

This differs structurally from the IMU serial format (fixed 6 floats): CSI lines carry a
variable-length vector, so parsing is regex-for-tags-then-split rather than a single fixed
float regex.

## Scope

New directory: `C:\Users\haofa\esp32\sniffer\tools\`, mirroring `IMU_lab/tools/`:

```
sniffer/tools/
  csi_common.py             # shared parser + serial reader + replay reader + demo signal
  plot_csi_serial.py        # reference: live heatmap + selectable-subcarrier trace
  plot_csi_smoothed_TODO.py # same view + moving-average TODO
  csi_presence_detect.py    # shared MotionDetector class; online (--port) + offline (--replay)
  requirements.txt
  README.md
```

Unlike the IMU repo (which duplicates parsing/serial-reader boilerplate in every script),
CSI line parsing is nontrivial enough (tagged, variable-length) that a shared
`csi_common.py` module is used by all three tools, per explicit user preference.

`capture_trajectory.py` / `capture_trajectory_smoothed_TODO.py` have no CSI analog (their
core logic is IMU-specific quaternion dead-reckoning) and are not ported. Their "capture on
keypress, compare against a baseline" spirit is replaced by the presence-detection tool's
online/offline workflow instead.

## Components

### `csi_common.py`

- `CsiSample` — dataclass: `timestamp_cycles: int`, `rssi: int`, `address: str`,
  `iq_values: list[int]`.
- `parse_csi_line(line: str) -> CsiSample | None` — regex:
  `r"<timestamp>(\d+)</timestamp><rssi>(-?\d+)</rssi><address>([0-9A-Fa-f:]+)</address>(.+)"`,
  with the trailing group split on whitespace and parsed as ints. Returns `None` on no match
  (mirrors `parse_sample` returning `None` in the IMU tools).
- `iq_to_amplitude(iq_values) -> np.ndarray` — `amplitude[k] = sqrt(iq[2k]**2 + iq[2k+1]**2)`
  for `k` in `range(len(iq_values) // 2)`. If `len(iq_values)` is odd, the trailing value is
  dropped (logged once).
- `EXPECTED_SUBCARRIERS = 64` — used only for a one-time mismatch warning, never to reject
  data.
- `SerialCsiReader` — background thread (daemon), same queue-based interface as the IMU
  `serial_worker`: pushes `("sample", (arrival_monotonic, CsiSample))` or `("error", message)`
  onto a `queue.Queue`. Optional `log_path` constructor arg: when set, every raw line is
  appended to that file prefixed with the arrival time relative to reader start, formatted as
  `t=<seconds_since_start> <raw line>`, so replay can reconstruct real inter-packet spacing.
- `ReplayCsiReader` — same queue-based interface, sourced from a log file written by
  `SerialCsiReader`. Reads `t=<seconds> <raw line>` records, parses the raw line the same way,
  and paces delivery using the recorded deltas, scaled by a `speed` multiplier
  (`speed=0` or a dedicated flag means "as fast as possible", no pacing). Downstream
  consumers (the plot/classifier update loops) read from the same queue interface regardless
  of which reader is in use, so live vs. replay is invisible past this point.
- `generate_demo_samples(...)` — synthetic CSI-like amplitude generator (idle low-variance
  baseline with periodic injected "motion" bursts of higher variance), used by
  `--demo-signal` in tools that support it, mirroring `IMU_Classifier`'s `--demo-signal` flag.
  This lets all three tools and their TODOs be exercised without hardware.

### `plot_csi_serial.py` (complete reference)

- Qt window: `QComboBox` subcarrier-index selector (0..N-1, populated from the first parsed
  packet's actual subcarrier count) above a `pg.GraphicsLayoutWidget` with two stacked
  panels:
  - Top: amplitude heatmap — `pg.ImageItem`, x-axis = time (scrolling window, same
    `--window` semantics as the IMU plots), y-axis = subcarrier index, color = amplitude.
  - Bottom: line plot of amplitude vs. time for only the currently-selected subcarrier;
    updates live and redraws from history when the selection changes.
- Same visual styling conventions as the IMU pyqtgraph tools (color palette, fonts, status
  label showing sample count / rssi / selected subcarrier amplitude).
- Uses `csi_common.SerialCsiReader`; supports `--demo-signal` for hardware-free testing.

### `plot_csi_smoothed_TODO.py` (student exercise)

- Identical GUI/layout to `plot_csi_serial.py`.
- Bottom panel overlays raw (dashed) vs. moving-average-smoothed (solid) amplitude for the
  selected subcarrier — same visual pattern as `plot_imu_smoothed_TODO.py`'s raw/smooth
  overlay.
- Contains the **same `MovingAverageFilter` class and `update()` `pass` stub** as
  `plot_imu_smoothed_TODO.py` / `capture_trajectory_smoothed_TODO.py` (streaming running-sum
  moving average over a `deque(maxlen=window_size)`). Same exercise, new context — students
  who did the IMU lab already understand the shape of this TODO.
- The filter instance resets when the student changes the selected subcarrier (switching
  mid-window would otherwise mix two unrelated series into one running average).

### `csi_presence_detect.py` (harness provided; `MotionDetector` is the student TODO)

- `MotionDetector` class — constructed with `window_size` (packets) and `threshold`:
  - `update(amplitude_vector: np.ndarray) -> dict` — **STUDENT TODO**: maintain a sliding
    window of recent amplitude vectors, compute a variance-based motion score (e.g., mean
    across subcarriers of each subcarrier's variance over the window), and threshold it.
    Returns `{"score": float, "motion": bool}`. Same class/instance is used for both online
    and offline runs — no code path branches by data source.
- CLI, one script, two mutually exclusive source modes:
  - Live: `--port COM5 [--log capture.txt]` (log optional; when given, tees raw serial lines
    for later replay).
  - Offline: `--replay capture.txt [--replay-speed X]`.
  - `--demo-signal` also supported for source-free testing.
- Live pyqtgraph GUI: large MOTION / NO MOTION status text (color-coded) + a scrolling line
  plot of the motion score over time with a horizontal `pg.InfiniteLine` at the threshold.
  Same GUI code runs for both modes since both feed the same `MotionDetector` through the
  same queue interface.

### `requirements.txt`

```
numpy
PyQt6
pyqtgraph
pyserial
```

(No `scikit-learn`/`joblib` — this lab's classifier is a hand-implemented threshold rule, not
a trained ML model.)

### `README.md`

Same structure as `IMU_lab/README.md` / `IMU_Classifier/README.md`: a tool table, hardware
overview (reusing the WiFi CSI firmware's channel/config values), Python setup, per-tool run
commands (including `--demo-signal` for no-hardware testing), and a "Student TODO" section
for each of the two exercises (`plot_csi_smoothed_TODO.py`'s `MovingAverageFilter`,
`csi_presence_detect.py`'s `MotionDetector.update`).

## Data Flow

```
ESP32 sniffer.c --serial--> raw tagged line
   --> SerialCsiReader / ReplayCsiReader (csi_common.py)
   --> queue of (arrival_time, CsiSample)
   --> per-tool consumer:
         plot_csi_serial.py / plot_csi_smoothed_TODO.py: iq_to_amplitude -> GUI update
         csi_presence_detect.py: iq_to_amplitude -> MotionDetector.update -> GUI update
```

## Error Handling

Consistent with the IMU tools' conventions:

- Lines that don't match `parse_csi_line`'s regex are silently skipped (optionally printed
  with `--print-unparsed`, matching the IMU scripts' flag).
- Serial exceptions are pushed onto the queue as `("error", message)` and surfaced in the
  status label / stderr, not raised into the GUI thread.
- A missing or empty `--replay` file is a clear startup error (`parser.error(...)`), not a
  silent no-op.
- CSI length mismatches (not 128 / not even) never crash the tool: subcarrier count is
  derived from the actual parsed length each packet, with a one-time warning if it doesn't
  match `EXPECTED_SUBCARRIERS`.
- Subcarrier selector index is clamped to the currently known subcarrier count.

## Testing

No CI/unit-test framework is introduced (matching the IMU repo, which has none for its
`tools/`). Verification is manual, via:

1. `--demo-signal` on all three tools, confirming the GUIs render and update without
   hardware.
2. Completing both TODOs (`MovingAverageFilter.update`, `MotionDetector.update`) against the
   demo signal and confirming expected behavior (smoothed curve visibly lags/smooths the raw
   curve; motion score rises during injected demo "motion" bursts and crosses the threshold).
3. `csi_presence_detect.py --port ... --log capture.txt` followed by
   `csi_presence_detect.py --replay capture.txt` to confirm identical classifier behavior
   live vs. replayed.

## Open Items / Notes for Implementation

- `docs/superpowers/specs/` was created directly under `sniffer/`, which is **not currently
  a git repository** (confirmed: no `.git` at or above that path). This spec is saved to disk
  but not committed. If the user wants version history for this project, `git init` should be
  run there first — not done automatically here.
