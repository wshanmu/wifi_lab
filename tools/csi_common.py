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
