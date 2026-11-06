"""Fringe-field calibration: magnet field vs the LS455 fringe gaussmeter.

Elena Long (2026-11-06, Ells's request): the Magnet tab plots the magnet
field (T, from the supply current by the field equation) against the fringe
field (G), with Clear and Fit.  Fit is a straight line for the magnet field
from the fringe reading,

    B_magnet = slope * B_fringe + offset        (T, with B_fringe in G),

by least squares over the points on the chart.

A point is taken when both readings are fresh and the field has moved by at
least MIN_STEP_T since the last point (about one a second while ramping at
3 A/min), or MAX_GAP_S has passed (a slow trickle while holding).  Every
point is also appended to a CSV, one file per chart (Clear starts a new file;
no file is ever deleted), and the latest file is reloaded when the IOC starts,
so a restart does not lose a calibration in progress.  The chart shows the
newest MAX_POINTS.
"""

from __future__ import annotations

import csv
import datetime as dt
import math
from pathlib import Path

MIN_STEP_T = 0.002
MAX_GAP_S = 300.0
MAX_POINTS = 20000


class FringeCalibration:
    def __init__(self, folder: Path | None = None):
        self.folder = Path(folder) if folder else None
        self.points: list[tuple[float, float]] = []     # (field T, fringe G)
        self._last_t = -math.inf
        self.file: Path | None = None
        self.fit_result: tuple[float, float, float, int] | None = None
        self._load_latest()

    # ------------------------------------------------------------ points
    def offer(self, field_t: float, fringe_g: float, now_s: float) -> bool:
        """Take the reading pair if it is due; True when a point was added."""
        if not (math.isfinite(field_t) and math.isfinite(fringe_g)):
            return False
        if self.points:
            moved = abs(field_t - self.points[-1][0]) >= MIN_STEP_T
            if not moved and now_s - self._last_t < MAX_GAP_S:
                return False
        self.points.append((float(field_t), float(fringe_g)))
        del self.points[:-MAX_POINTS]
        self._last_t = now_s
        self._save(field_t, fringe_g)
        return True

    def clear(self) -> None:
        """Empty the chart and start a new file (the old one is kept)."""
        self.points.clear()
        self._last_t = -math.inf
        self.fit_result = None
        self.file = None

    def arrays(self) -> tuple[list[float], list[float]]:
        return [p[0] for p in self.points], [p[1] for p in self.points]

    # ------------------------------------------------------------ fit
    def fit(self) -> tuple[float, float, float, int]:
        """(slope T/G, offset T, rms residual T, n) of B = slope * G + offset.
        ValueError if the points do not fix a line."""
        n = len(self.points)
        if n < 2:
            raise ValueError("need at least 2 points")
        mg = sum(g for _b, g in self.points) / n
        mb = sum(b for b, _g in self.points) / n
        sgg = sum((g - mg) ** 2 for _b, g in self.points)
        if not sgg > 1e-12 * n:
            raise ValueError("the fringe field has not changed")
        slope = sum((g - mg) * (b - mb) for b, g in self.points) / sgg
        offset = mb - slope * mg
        rms = math.sqrt(sum((b - slope * g - offset) ** 2 for b, g in self.points) / n)
        self.fit_result = (slope, offset, rms, n)
        return self.fit_result

    def line(self) -> tuple[list[float], list[float]]:
        """The fitted line across the chart's fringe range: (fields T, fringes G)."""
        if self.fit_result is None or not self.points:
            return [], []
        slope, offset = self.fit_result[:2]
        g = [min(p[1] for p in self.points), max(p[1] for p in self.points)]
        return [slope * x + offset for x in g], g

    @staticmethod
    def equation(slope: float, offset: float) -> str:
        sign = "-" if offset < 0 else "+"
        return f"B = {slope:.6g} T/G x Bf {sign} {abs(offset):.4g} T"

    # ------------------------------------------------------------ file
    def _save(self, field_t: float, fringe_g: float) -> None:
        if self.folder is None:
            return
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            if self.file is None:                   # a new chart: a new file, never reused
                stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
                self.file = self.folder / f"fringe_calibration_{stamp}.csv"
                n = 2
                while self.file.exists():
                    self.file = self.folder / f"fringe_calibration_{stamp}_{n}.csv"
                    n += 1
            new = not self.file.exists()
            with open(self.file, "a", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                if new:
                    w.writerow(["local_time", "magnet_field_T", "fringe_field_G"])
                w.writerow([dt.datetime.now().isoformat(timespec="seconds"),
                            f"{field_t:.8f}", f"{fringe_g:.6f}"])
        except OSError:
            pass                                    # the chart still works

    def _load_latest(self) -> None:
        if self.folder is None or not self.folder.is_dir():
            return
        files = sorted(self.folder.glob("fringe_calibration_*.csv"))
        if not files:
            return
        self.file = files[-1]
        try:
            with open(self.file, newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    self.points.append((float(row["magnet_field_T"]), float(row["fringe_field_G"])))
        except (OSError, KeyError, ValueError):
            self.points.clear()
        del self.points[:-MAX_POINTS]
