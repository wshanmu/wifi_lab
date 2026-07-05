# WiFi CSI Sensing Lab

An end-to-end WiFi Channel State Information (CSI) sensing lab built on the
ESP32. Three independent ESP-IDF firmware projects generate and capture a WiFi
link, and a standalone Python tool suite visualizes the captured CSI and detects
human motion near the link.

## Data Pipeline

```text
injector  ──(spoofed 802.11 frames, channel 1)──▶  sniffer  ──(USB serial)──▶  tools/
   ▲                                                                              
   └─ softAP provides the WiFi access point / link the lab runs on
```

- The **injector** continuously transmits raw 802.11 null-function frames with a
  fixed spoofed transmitter MAC (`AA:BB:BB:BB:BB:BB`).
- The **sniffer** runs in promiscuous mode with CSI enabled, filters down to the
  injector's frames, and streams each CSI report over USB serial as a tagged
  line.
- The **tools** parse that serial stream to plot CSI amplitude and run a
  presence/motion detector (online from serial, or offline by replaying a log).

## Repository Layout

| Path | What it is |
| --- | --- |
| [`softAP/`](softAP/) | ESP-IDF firmware: ESP32 SoftAP that provides the WiFi access point for the link. |
| [`injector/`](injector/) | ESP-IDF firmware: raw 802.11 frame injector (the CSI stimulus). |
| [`sniffer/`](sniffer/) | ESP-IDF firmware: promiscuous CSI capture, streams tagged CSI over serial. |
| [`tools/`](tools/) | Standalone Python CSI visualization + presence-detection tools (no ESP-IDF needed to run). |
| [`docs/`](docs/) | Design specs and implementation plans for the tools. |

Each firmware directory is a self-contained ESP-IDF project (its own
`CMakeLists.txt`, `main/`, `sdkconfig.ci*`, and editor config). `tools/` is a
plain Python project and does not participate in the ESP-IDF build.

## Firmware Quickstart

Each module builds and flashes independently. From a module directory with the
ESP-IDF environment active:

```bash
idf.py set-target esp32        # softAP uses esp32c3; sniffer and injector use esp32
idf.py build
idf.py -p YOUR_PORT flash monitor
```

Typical bring-up order for the lab: flash **softAP**, then **injector**, then
**sniffer**, and confirm the sniffer prints tagged CSI lines like:

```text
<timestamp>123456</timestamp><rssi>-42</rssi><address>AA:BB:BB:BB:BB:BB</address>0 3 4 0 ...
```

## Tools Quickstart

See [`tools/README.md`](tools/README.md) for full instructions. In brief, from
`tools/`:

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
python plot_csi_serial.py --port YOUR_PORT                     # live CSI plot
python csi_presence_detect.py --port YOUR_PORT --log run1.txt  # motion detection + logging
```

All tools accept `--demo-signal` to run without hardware.

## Note for Instructors

`docs/` contains the tools' design spec and implementation plan, which include
**reference solutions** to the two student exercises (`MovingAverageFilter` in
`plot_csi_smoothed_TODO.py` and `MotionDetector` in `csi_presence_detect.py`).
Exclude `docs/` from anything distributed to students.
