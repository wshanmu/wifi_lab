---
layout: page
title: "Environment Setup: ESP-IDF and Python"
description: Step-by-step environment setup guide for the WiFi CSI sensing lab on Windows, macOS, and Linux.
parent: Labs
nav_order: X
---

# Environment Setup: ESP-IDF and Python

Complete this guide **before lab day** on your own laptop. It covers two independent setups:

- **Part 1 — ESP-IDF:** the toolchain for flashing firmware onto ESP32 boards.
- **Part 2 — Python environment:** the packages used for CSI data analysis and visualization.

Estimated time: 30–60 minutes depending on your internet speed and whether you run into driver issues. Do not leave this until the morning of the lab.

This guide covers **Windows**, **macOS**, and **Linux**. Follow only the section that matches your operating system.

If you get stuck, contact your TA before lab day.

---

## Part 1: ESP-IDF Setup

ESP-IDF (Espressif IoT Development Framework) is the official toolchain for building and flashing firmware onto ESP32 boards. In this lab you will use it to flash pre-built firmware images — you do not need to write or compile any C code yourself.

Follow the official Espressif installation guide for your operating system. The guide covers both a graphical installer (recommended for most users) and a command-line option:

- **Windows:** [Installation of ESP-IDF and Tools on Windows](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/windows-setup.html)
- **Linux:** [Installation of ESP-IDF and Tools on Linux](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/linux-setup.html)
- **macOS:** [Installation of ESP-IDF and Tools on macOS](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/macos-setup.html)

The top-level get-started page is at: [https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/index.html#installation](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/index.html#installation)

Once done, verify the installation by opening your ESP-IDF terminal and running:

```bash
idf.py --version
```

You should see output like `ESP-IDF v5.x.x` or `ESP-IDF v6.x.x`.

---

### Lab-specific notes (read these after completing the official guide)

The official guide focuses on building and running a sample project. For this lab you only need to flash pre-built firmware images, so you can stop after the installation step — you do not need to complete the "Build Your First Project" section.

#### Identifying your USB-to-UART driver

Most ESP32 boards use one of two USB chips. You need the correct driver installed to communicate with the board over USB.

- Flip your board over and look for a small IC near the USB port.
- **CP2102 / CP2104** (Silicon Labs): driver included in the Windows ESP-IDF installer; built into macOS 12.3+; no extra install needed on Linux.
- **CH340 / CH341** (WCH): requires a manual driver install on Windows ([CH341SER.EXE](https://www.wch-ic.com/downloads/CH341SER_EXE.html)) and macOS ([CH341SER_MAC.ZIP](https://www.wch-ic.com/downloads/CH341SER_MAC_ZIP.html)); no extra install on Linux.
- If you cannot identify the chip visually, install both drivers — they do not conflict.

#### Confirming the board is recognized

After installing the driver, plug in your ESP32 board and check:

- **Windows:** open Device Manager → Ports (COM & LPT) — look for an entry like `Silicon Labs CP210x USB to UART Bridge (COM5)` or `USB-SERIAL CH340 (COM3)`. Note the COM number.
- **Linux:** run `ls /dev/ttyUSB* /dev/ttyACM*` — you should see `/dev/ttyUSB0` or similar. If you get `Permission denied` when using the port, run `sudo usermod -aG dialout $USER` and log out and back in.
- **macOS:** run `ls /dev/cu.*` — you should see `/dev/cu.usbserial-*` (CP210x) or `/dev/cu.wchusbserial*` (CH340). If macOS blocks the CH340 driver, go to System Settings → Privacy & Security → Allow Anyway.

If no entry appears on any platform, try a different USB cable — many cables are charge-only and carry no data.

#### Testing the connection with esptool

Once the board is recognized, confirm `esptool.py` can communicate with it. Replace `<PORT>` with your actual port (`COM5`, `/dev/ttyUSB0`, `/dev/cu.usbserial-0001`, etc.):

```bash
esptool.py --port <PORT> chip_id
```

Expected output:

```
Chip is ESP32-D0WDQ6 (revision 1)
Features: WiFi, BT, Dual Core, ...
```

If you see `Failed to connect`, hold the **BOOT** button on the board while running the command and release it once the connection attempt starts. Some boards require this to enter the flashing bootloader.

---

## Part 2: Python Environment Setup

Use the `cosmos-ds` Conda environment from Lab 1. Keeping the same environment across the data science and IoT labs avoids duplicate package installs and makes VS Code/Jupyter kernel selection simpler.

#### Step 1 — Activate the course environment

```bash
conda activate cosmos-ds
```

If this fails, create the environment:

```bash
conda create -n cosmos-ds python=3.11
conda activate cosmos-ds
```

#### Step 2 — Confirm Python version

```bash
python --version
```

or, on some systems:

```bash
python3 --version
```

You need Python **3.10 or newer**. Python 3.11 is recommended for this course.

#### Step 3 — Upgrade pip

```bash
python -m pip install --upgrade pip
```

#### Step 4 — Install the lab's Python packages

The analysis tools live in the course repository under `tools/`, and their exact
versions are pinned in `tools/requirements.txt`. From inside your cloned copy of
the lab repo, with `cosmos-ds` active, install them:

```bash
python -m pip install -r tools/requirements.txt
```

This installs:

| Package | Purpose |
| --- | --- |
| `numpy` | array operations on CSI data |
| `pyserial` | reading raw CSI output from the ESP32 serial port |
| `pyqtgraph` | live plotting of CSI amplitude (heatmap + per-subcarrier traces) |
| `PyQt6` | GUI backend for the plotting tools (pinned `<6.11` for Windows compatibility) |

If you do not have the repo yet, ask your TA for the clone URL, or install the
same packages directly:

```bash
python -m pip install "numpy" "pyserial" "pyqtgraph" "PyQt6<6.11"
```

**Optional — breathing-rate extension:** the after-class breathing extension
also uses `scipy` (bandpass filter + FFT). Install it only if you attempt that
section:

```bash
python -m pip install scipy
```

**Optional — Jupyter notebooks:** if your TA provides analysis notebooks, also
install:

```bash
python -m pip install jupyter matplotlib
```

Installation typically takes 2–5 minutes.

#### Step 5 — Verify the packages

```bash
python -c "import numpy, serial, pyqtgraph; from PyQt6 import QtWidgets; print('All packages OK')"
```

Expected output:

```
All packages OK
```

#### Step 6 — Confirm the tools run (no hardware needed)

The plotting tools include a built-in synthetic signal, so you can verify your
setup before lab day without any board attached. From the repo root:

```bash
python tools/plot_csi_serial.py --demo-signal
```

A window titled "ESP32 CSI Live Amplitude" should open showing a scrolling
heatmap that alternates between calm and noisy every few seconds. Close the
window to exit.

> **Optional (Jupyter):** if you installed Jupyter for the notebook path, confirm
> it launches with `jupyter notebook` — a browser tab should open showing the
> file browser. Press `Ctrl+C` in the terminal to stop the server.

---

## Part 3: Wireshark

Wireshark is optional for students. The TA may show the packet demo on the instructor laptop, and you can still inspect the provided `wireshark_example.pcap` if you install Wireshark locally. No live capture or monitor-mode setup is required for the main lab.

#### Windows

1. Go to [https://www.wireshark.org/download.html](https://www.wireshark.org/download.html).
2. Download the Windows installer (64-bit).
3. Run the installer with default options. When asked about installing **Npcap**, leave it checked — it is required for Wireshark to open live captures on Windows (even though you will only be opening a file).
4. Open Wireshark from the Start Menu and confirm it launches.

#### macOS

1. Go to [https://www.wireshark.org/download.html](https://www.wireshark.org/download.html).
2. Download the **macOS Arm 64-bit .dmg** (Apple Silicon) or **macOS Intel 64-bit .dmg** depending on your Mac.
   - To check: go to **Apple menu → About This Mac**. "Apple M1/M2/M3" = Arm; "Intel Core" = Intel.
3. Open the `.dmg` and drag **Wireshark** into your Applications folder.
4. Open Wireshark from Applications and confirm it launches.

> No additional driver or group setup is needed on macOS for opening `.pcap` files.

#### Linux

```bash
sudo apt-get install -y wireshark
```

During installation you will be asked: *"Should non-superusers be able to capture packets?"* Select **Yes**.

Then add yourself to the `wireshark` group:

```bash
sudo usermod -aG wireshark $USER
```

Log out and back in, then verify:

```bash
groups | grep wireshark
```

Open Wireshark to confirm it launches:

```bash
wireshark &
```

---

## Final Verification Checklist

Run through this checklist **before lab day** and confirm every item works. If anything fails, contact your TA.

**ESP-IDF**
- [ ] `idf.py --version` prints a version number without error
- [ ] `esptool.py --port <PORT> chip_id` successfully reads the chip ID from an ESP32 board
- [ ] The board appears as a COM port (Windows), `/dev/ttyUSB*` or `/dev/ttyACM*` (Linux), or `/dev/cu.usbserial-*` or `/dev/cu.wchusbserial*` (macOS) when plugged in

**Python environment**
- [ ] `python -c "import numpy, serial, pyqtgraph; from PyQt6 import QtWidgets; print('All packages OK')"` prints `All packages OK`
- [ ] `python tools/plot_csi_serial.py --demo-signal` opens a live plot window
- [ ] *(optional)* `jupyter notebook` opens a browser tab, if you installed the notebook path

**Wireshark**
- [ ] Wireshark opens and can load a `.pcap` file (File → Open any `.pcap` file)

---

## Common Issues

## Installing ESP-IDF and Tools via EIM:
```
Failed to Start Installation
Downloaded archive size mismatch for archive_v6.0.2_windows-x64.zst: expected 3307300246, got 3306918911
```

This is likely due to the interruption during downloading, simply delete the partially downloaded package and try again. If still failing, use custom installation, and select all default configurations.

Install the IDE, use VS Code ESP-IDF Extension. Walkthrough the get started ESP-IDF Basic Usage Guide to create a new sample project and get yourself familiar with the environment. You don't need the actual hardware board to complete this, just compile the sample project on your compute and observe it succeed. No need to flash.

# ESP32 Build, Flash and Monitor
In VSCode, you can press `Ctrl+Shift+P` to invoke the command palette, where you can find all ESP-IDF commands you need:
![alt text](image.png)

You can also configure your ESP32 device using the toolbar at the bottom:
![alt text](image-1.png)

Set the target to ESP32 -> ESP32 Chip (via ESP-PROG), when flash, use URAT, remember to set your port
