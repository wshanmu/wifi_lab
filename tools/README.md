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
