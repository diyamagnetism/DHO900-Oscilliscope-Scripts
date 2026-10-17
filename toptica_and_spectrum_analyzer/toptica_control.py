"""Thin wrapper around the TOPTICA DLC pro synchronous high-level API.

Install:  pip install toptica-lasersdk

NOTE: The SDK ships one module per DLC pro firmware version. The import below
uses v2_0_3 (as in the SDK examples); change it to match your firmware, e.g.
`toptica.lasersdk.dlcpro.v3_0_1`.
"""

import math
import time
from typing import Callable, List, Optional, Tuple

from toptica.lasersdk.dlcpro.v2_0_3 import (
    DLCpro,
    NetworkConnection,
    DeviceNotFoundError,
    DecopError,
)


# DOUBLE CHECK: IP ADDRESS OF LASER
# WHAT DOES VOLTAGE MEAN?



SweepPoint = Tuple[float, float]  # (voltage_set, voltage_actual)


class TopticaLaser:
    """Wrapper for one laser head (default: laser1) on a DLC pro.

    Usage:
        with TopticaLaser("172.16.109.105") as laser:
            print(laser.get_piezo_voltage())
            data = laser.sweep_piezo(start=40.0, stop=60.0, step=0.5, dwell=0.1)
    """

    def __init__(self, address: str, laser: str = "laser1"):
        """
        address: IP address, serial number, system label or DNS name of the DLC pro.
        laser:   'laser1' or 'laser2' (for dual-laser controllers).
        """
        self._address = address
        self._laser_name = laser
        self._dlc: Optional[DLCpro] = None

    # ------------------------------------------------------------------ #
    # Connection handling
    # ------------------------------------------------------------------ #
    def connect(self) -> None:
        if self._dlc is not None:
            return
        dlc = DLCpro(NetworkConnection(self._address))
        try:
            dlc.open()
        except DeviceNotFoundError as exc:
            raise ConnectionError(f"DLC pro not found at '{self._address}'") from exc
        self._dlc = dlc

    def close(self) -> None:
        if self._dlc is not None:
            self._dlc.close()
            self._dlc = None

    def __enter__(self) -> "TopticaLaser":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @property
    def _laser(self):
        if self._dlc is None:
            raise RuntimeError("Not connected. Call connect() or use a 'with' block.")
        return getattr(self._dlc, self._laser_name)

    # ------------------------------------------------------------------ #
    # Basic readbacks
    # ------------------------------------------------------------------ #
    def get_info(self) -> dict:
        """Return basic device info."""
        return {
            "firmware": self._dlc.fw_ver.get(),
            "uptime": self._dlc.uptime.get(),
            "system_health": self._dlc.system_health_txt.get(),
            "emission": self._dlc.emission.get(),
        }

    def get_current(self) -> float:
        """Actual laser diode current in mA."""
        return self._laser.dl.cc.current_act.get()

    def get_temperature(self) -> float:
        """Actual laser diode temperature in deg C."""
        return self._laser.dl.tc.temp_act.get()

    # ------------------------------------------------------------------ #
    # Piezo
    # ------------------------------------------------------------------ #
    def get_piezo_limits(self) -> Tuple[float, float]:
        """(min, max) piezo voltage allowed by the controller, in V."""
        pc = self._laser.dl.pc
        return pc.voltage_min.get(), pc.voltage_max.get()

    def get_piezo_voltage(self, actual: bool = False) -> float:
        """Piezo voltage in V. actual=True reads the measured output instead of the setpoint."""
        pc = self._laser.dl.pc
        return pc.voltage_act.get() if actual else pc.voltage_set.get()

    def set_piezo_voltage(self, voltage: float) -> None:
        """Set the piezo voltage in V, checked against the controller limits."""
        vmin, vmax = self.get_piezo_limits()
        if not (vmin <= voltage <= vmax):
            raise ValueError(
                f"Piezo voltage {voltage} V outside allowed range [{vmin}, {vmax}] V"
            )
        self._laser.dl.pc.voltage_set.set(float(voltage))

    def sweep_piezo(
        self,
        start: float,
        stop: float,
        step: float,
        dwell: float = 0.1,
        settle: float = 0.0,
        restore: bool = False,
        callback: Optional[Callable[[float, float], None]] = None,
    ) -> List[SweepPoint]:
        """Step the piezo voltage from `start` to `stop` (inclusive) in increments of `step`.

        start, stop: voltages in V. stop < start gives a downward sweep.
        step:        step size in V (positive; direction is inferred from start/stop).
        dwell:       seconds to wait at each point before reading back / calling callback.
        settle:      extra seconds to wait after moving to `start` before the first point.
        restore:     if True, return the piezo to its original voltage when done
                     (also on error / Ctrl-C).
        callback:    optional fn(voltage_set, voltage_actual) called at every point,
                     e.g. to take a measurement from another instrument.

        Returns a list of (voltage_set, voltage_actual) tuples.
        """
        if step <= 0:
            raise ValueError("step must be positive")
        if dwell < 0 or settle < 0:
            raise ValueError("dwell and settle must be >= 0")

        # Validate the whole range up front so we never start a sweep we can't finish.
        vmin, vmax = self.get_piezo_limits()
        for v in (start, stop):
            if not (vmin <= v <= vmax):
                raise ValueError(
                    f"Sweep endpoint {v} V outside allowed range [{vmin}, {vmax}] V"
                )

        # Compute points by index (not by repeated addition) to avoid float drift,
        # and always land exactly on `stop`.
        span = stop - start
        n_steps = int(math.floor(abs(span) / step + 1e-9))
        direction = 1.0 if span >= 0 else -1.0
        voltages = [start + direction * i * step for i in range(n_steps + 1)]
        if abs(voltages[-1] - stop) > 1e-9:
            voltages.append(stop)

        original = self.get_piezo_voltage()
        results: List[SweepPoint] = []
        try:
            self.set_piezo_voltage(voltages[0])
            if settle:
                time.sleep(settle)

            for v in voltages:
                self.set_piezo_voltage(v)
                if dwell:
                    time.sleep(dwell)
                actual = self.get_piezo_voltage(actual=True)
                results.append((v, actual))
                if callback is not None:
                    callback(v, actual)
        finally:
            if restore:
                self.set_piezo_voltage(original)

        return results


if __name__ == "__main__":
    import sys

    addr = sys.argv[1] if len(sys.argv) > 1 else "172.16.109.105"
    try:
        with TopticaLaser(addr) as laser:
            lo, hi = laser.get_piezo_limits()
            print(f"Piezo limits: {lo} .. {hi} V, currently {laser.get_piezo_voltage()} V")

            mid = (lo + hi) / 2
            data = laser.sweep_piezo(
                start=mid - 5,
                stop=mid + 5,
                step=1.0,
                dwell=0.2,
                restore=True,
                callback=lambda s, a: print(f"set {s:7.3f} V  ->  actual {a:7.3f} V"),
            )
            print(f"Sweep done, {len(data)} points.")
    except DecopError as err:
        print(f"Device error: {err}")
    except ConnectionError as err:
        print(err)