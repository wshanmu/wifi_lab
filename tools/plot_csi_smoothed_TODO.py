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
        # TODO: Implement the moving average update logic here
        pass


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
        got_error = False

        while True:
            try:
                kind, payload = self.data_queue.get_nowait()
            except queue.Empty:
                break

            if kind == "error":
                got_error = True
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

        if not got_error:
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
