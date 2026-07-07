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
import signal
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
        # TODO: Once self.history has at least 2 vectors, compute the
        # variance of each subcarrier's amplitude across self.history
        # (np.var(np.stack(self.history), axis=0)), aggregate it to a
        # single score (e.g. float(np.mean(...))), and return
        # {"score": score, "motion": score > self.threshold}.
        return {"score": 0.0, "motion": False}


class PresenceDetectorWindow(QtWidgets.QWidget):
    def __init__(self, args, data_queue, detector, on_close=None):
        super().__init__()
        self.args = args
        self.data_queue = data_queue
        self.detector = detector
        self._on_close = on_close
        self.start_time = None
        self.sample_count = 0
        self.num_subcarriers = None

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

    def closeEvent(self, event) -> None:
        if self._on_close is not None:
            self._on_close()
        event.accept()

    def update(self) -> None:
        got_sample = False
        got_error = False
        latest_result = None
        latest_sample = None

        while True:
            try:
                kind, payload = self.data_queue.get_nowait()
            except queue.Empty:
                break

            if kind == "error":
                got_error = True
                self.status_label.setText(f"Error: {payload}")
                self.status_label.setStyleSheet("color: #B42318;")
                print(f"Error: {payload}", file=sys.stderr)
                continue

            elapsed, sample = payload
            amplitude = iq_to_amplitude(sample.iq_values)

            if self.num_subcarriers is None:
                self.num_subcarriers = len(amplitude)

            if len(amplitude) != self.num_subcarriers:
                continue

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

        if not got_error:
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
    return SerialCsiReader(
        args.port,
        args.baud,
        log_path=args.log,
        reset_on_connect=not args.no_reset_on_connect,
    )


def main():
    parser = argparse.ArgumentParser(description="WiFi CSI presence/motion detector (online + offline).")
    parser.add_argument("--port", default=None, help="Serial port for live detection, e.g. COM5 or /dev/cu.usbserial-2140")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate")
    parser.add_argument("--log", default=None, help="Path to record raw CSI lines for later --replay")
    parser.add_argument("--replay", default=None, help="Replay a log file recorded with --log instead of live serial")
    parser.add_argument("--replay-speed", type=float, default=1.0, help="Replay pacing multiplier; 0 = as fast as possible")
    parser.add_argument("--demo-signal", action="store_true", help="Use generated CSI-like data instead of serial/replay input")
    parser.add_argument(
        "--no-reset-on-connect",
        action="store_true",
        help="Do not pulse ESP32 reset lines when opening the serial port",
    )
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
    timer = QtCore.QTimer()
    signal_timer = QtCore.QTimer()
    cleaned_up = False

    def cleanup():
        nonlocal cleaned_up
        if cleaned_up:
            return
        cleaned_up = True
        timer.stop()
        signal_timer.stop()
        reader.stop()

    def request_exit(signum, _frame):
        app.exit(130 if signum == signal.SIGINT else 143)

    signal.signal(signal.SIGINT, request_exit)
    signal.signal(signal.SIGTERM, request_exit)

    signal_timer.timeout.connect(lambda: None)
    signal_timer.start(100)

    window = PresenceDetectorWindow(args, reader.queue, detector, on_close=cleanup)
    window.show()

    timer.timeout.connect(window.update)
    timer.start(max(1, int(1000 / args.fps)))

    app.aboutToQuit.connect(cleanup)
    exit_code = 0
    try:
        exit_code = app.exec()
    except KeyboardInterrupt:
        exit_code = 130
    finally:
        cleanup()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
