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
| [`lab-03.md`](lab-03.md) | The student lab handout: goals, schedule, tasks, and deliverables. |
| [`environment-setup.md`](environment-setup.md) | Pre-lab setup guide (ESP-IDF, USB drivers, Python, Wireshark). |
| [`docs/`](docs/) | Design specs and implementation plans for the tools. |

Each firmware directory is a self-contained ESP-IDF project (its own
`CMakeLists.txt`, `main/`, `sdkconfig.ci*`, and editor config). `tools/` is a
plain Python project and does not participate in the ESP-IDF build.

## Lab Materials

Students should start with the two guides at the repo root:

1. [`environment-setup.md`](environment-setup.md) — complete **before lab day**:
   installs ESP-IDF, USB drivers, the course Conda environment packages (from
   [`tools/requirements.txt`](tools/requirements.txt)), and optional Wireshark.
2. [`lab-03.md`](lab-03.md) — the lab itself: flash
   the three boards, visualize CSI with the `tools/`, and implement the
   variance-threshold presence detector.

## Firmware Quickstart

Each module builds and flashes independently. From a module directory with the
ESP-IDF environment active:

```bash
idf.py set-target esp32        # softAP and sniffer
idf.py set-target esp32c3      # injector
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
conda activate cosmos-ds
python -m pip install -r requirements.txt
python plot_csi_serial.py --port YOUR_PORT
python csi_presence_detect.py --port YOUR_PORT --log run1.txt
```

All tools accept `--demo-signal` to run without hardware.
