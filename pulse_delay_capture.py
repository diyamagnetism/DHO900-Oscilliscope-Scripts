"""
Rigol DHO900 USB control and 1PPS delay-measurement helper.

This script was written around the DHO924 workflow used in the lab:
1. Connect the scope to Windows over the rear USB DEVICE port.
2. Confirm the scope enumerates as a USB-TMC instrument.
3. Trigger on the 1PPS pulse arriving on CH1.
4. Capture both CH1 and CH2 for the same event.
5. Measure the arrival-time delay CH2 - CH1 at the 50% crossing level.

The script also includes a small "doctor" mode so new users can verify that
Windows, PyVISA, and the scope are all talking before they start an experiment.
"""

# argparse builds the command-line interface such as:
#   python pulse_delay_capture.py doctor
#   python pulse_delay_capture.py pulse-capture --captures 10
import argparse

# csv is used to save downloaded waveforms and summary tables in a format that
# is easy to inspect in Excel, pandas, MATLAB, or plain text editors.
import csv

# json is used for machine-readable metadata and run summaries.
import json

# subprocess lets the script call PowerShell so it can inspect Windows USB
# device information without requiring the user to open Device Manager first.
import subprocess

# sys is used for exit codes and command-line flow control.
import sys

# time is used for trigger timeouts and timestamping each capture event.
import time

# warnings is used to hide noisy backend warnings that are not actionable for
# normal lab use once the script is working.
import warnings

# Path gives us safer, clearer file handling than raw string concatenation.
from pathlib import Path

# numpy is used for waveform processing and delay calculations.
import numpy as np

# pyvisa is the main interface used to talk to the oscilloscope over USB-TMC.
import pyvisa


# This is Rigol's USB vendor ID. We use it when searching Windows device info.
RIGOL_VENDOR_ID = 0x1AB1

# This is the DHO924 product ID observed on the lab scope.
DHO924_PRODUCT_ID = 0x044C

# Timeout used while opening a VISA resource.
OPEN_TIMEOUT_MS = 3000

# Timeout used for normal instrument reads/writes after a connection is open.
IO_TIMEOUT_MS = 5000
SCREENSHOT_TIMEOUT_MS = 20000

# By default, saved files will be written into a folder next to the script.
DEFAULT_OUTPUT_DIR = Path("scope_output")

# These notes are printed by the doctor command so users do not have to remember
# the USB wiring rules from the user guide.
MANUAL_NOTES = [
    "Use the rear-panel USB DEVICE port on the scope, not a USB HOST port.",
    "The DHO900 user guide says USB remote control uses USB-TMC discovery.",
    "Rigol Ultra Sigma can be used to test USB-TMC, but this script can work directly through pyvisa-py.",
]

# We try both the vendor VISA backend and the pure-Python backend.
# In the lab setup, pyvisa-py with WinUSB was the path that worked.
BACKENDS = [
    ("", "vendor VISA"),
    ("@py", "pyvisa-py"),
]

INVALID_MEASUREMENT_SENTINEL = 9.9e37

# pyvisa-py can print backend warnings that are useful during development but
# noisy during everyday lab use. We suppress them to keep the output readable.
warnings.filterwarnings("ignore", category=UserWarning, module="pyvisa_py")


def print_header(title):
    """Print a section divider so command output is easier to read."""

    print(f"\n=== {title} ===")


def decode_ps_json(raw):
    """
    Convert JSON emitted by PowerShell into a Python list.

    PowerShell sometimes returns one object instead of a list when there is only
    one match, so we normalize that here.
    """

    raw = raw.strip()
    if not raw:
        return []

    data = json.loads(raw)
    if isinstance(data, list):
        return data
    return [data]


def run_powershell_json(script):
    """
    Run a PowerShell snippet and parse its JSON output.

    If the command fails, we return an empty list so the rest of the script can
    keep going and report a useful diagnosis instead of crashing.
    """

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:
        return []

    return decode_ps_json(result.stdout)


def get_windows_usb_devices():
    """
    Ask Windows whether it sees the DHO924 USB device.

    We also request the service and driver provider so we can tell whether the
    device is bound to WinUSB/libwdi, which was the working configuration in
    this setup.
    """

    script = rf"""
$devices = Get-PnpDevice | Where-Object {{ $_.InstanceId -match 'VID_{RIGOL_VENDOR_ID:04X}&PID_{DHO924_PRODUCT_ID:04X}' }}
$rows = foreach ($dev in $devices) {{
  $present = $null
  $service = $null
  $driverProvider = $null
  try {{
    $present = (Get-PnpDeviceProperty -InstanceId $dev.InstanceId -KeyName 'DEVPKEY_Device_IsPresent').Data
  }} catch {{}}
  try {{
    $service = (Get-PnpDeviceProperty -InstanceId $dev.InstanceId -KeyName 'DEVPKEY_Device_Service').Data
  }} catch {{}}
  try {{
    $driverProvider = (Get-PnpDeviceProperty -InstanceId $dev.InstanceId -KeyName 'DEVPKEY_Device_DriverProvider').Data
  }} catch {{}}
  [pscustomobject]@{{
    FriendlyName = $dev.FriendlyName
    Status = $dev.Status
    InstanceId = $dev.InstanceId
    Present = $present
    Service = $service
    DriverProvider = $driverProvider
  }}
}}
$rows | ConvertTo-Json -Compress
"""
    return run_powershell_json(script)


def serial_from_instance_id(instance_id):
    """
    Extract the USB serial number from a Windows instance ID.

    Example:
      USB\\VID_1AB1&PID_044C\\DHO9A254401412
    becomes:
      DHO9A254401412
    """

    if not instance_id or "\\" not in instance_id:
        return None
    return instance_id.rsplit("\\", 1)[-1]


def configure_scope_session(scope):
    """
    Apply the VISA session settings that worked reliably for this scope.

    The newline terminations match normal SCPI text-command behavior.
    """

    scope.timeout = IO_TIMEOUT_MS
    scope.chunk_size = 20_000_000
    scope.write_termination = "\n"
    scope.read_termination = "\n"


def build_usb_resource_candidates(windows_devices):
    """
    Construct likely USB VISA resource strings from Windows device metadata.

    This is useful even when vendor VISA discovery returns nothing, because
    pyvisa-py can often still open the instrument if we provide the full string.
    """

    resources = []
    for dev in windows_devices:
        serial = serial_from_instance_id(dev.get("InstanceId"))
        if serial:
            resources.append(
                f"USB0::0x{RIGOL_VENDOR_ID:04X}::0x{DHO924_PRODUCT_ID:04X}::{serial}::INSTR"
            )
    return resources


def list_resources_for_backend(backend):
    """
    Ask one VISA backend which resources it can currently see.

    We return both the list and any error so the doctor command can show the
    user exactly what worked and what failed.
    """

    try:
        rm = pyvisa.ResourceManager(backend) if backend else pyvisa.ResourceManager()
        resources = list(rm.list_resources())
        rm.close()
        return resources, None
    except Exception as exc:
        return [], str(exc)


def collect_candidate_resources(extra_resource=None):
    """
    Gather every promising resource string we know how to try.

    The priority order is:
    1. A resource string the user passed explicitly.
    2. USB candidates inferred from Windows.
    3. Anything discovered by a VISA backend.
    """

    windows_devices = get_windows_usb_devices()
    candidates = []

    if extra_resource:
        candidates.append(extra_resource)

    candidates.extend(build_usb_resource_candidates(windows_devices))

    for backend, _label in BACKENDS:
        resources, _error = list_resources_for_backend(backend)
        for resource in resources:
            if resource.upper().startswith(("USB", "TCPIP")) and resource.upper().endswith("INSTR"):
                candidates.append(resource)

    return list(dict.fromkeys(candidates)), windows_devices


def open_scope(resource_name, backend):
    """
    Open one VISA resource and immediately verify it with *IDN?.

    Returning the resource manager alongside the scope object makes cleanup
    straightforward for the calling command.
    """

    rm = pyvisa.ResourceManager(backend) if backend else pyvisa.ResourceManager()
    try:
        scope = rm.open_resource(resource_name, open_timeout=OPEN_TIMEOUT_MS)
        configure_scope_session(scope)
        idn = scope.query("*IDN?").strip()
        return rm, scope, idn
    except Exception:
        rm.close()
        raise


def normalize_backend_choice(choice):
    """
    Convert friendly CLI names into pyvisa backend selectors.

    'vendor' becomes '' because pyvisa uses the empty string for the default
    vendor backend, while 'py' becomes '@py' for pyvisa-py.
    """

    if choice == "vendor":
        return ""
    if choice == "py":
        return "@py"
    return None


def try_connect(extra_resource=None, preferred_backend=None):
    """
    Try every resource/backend combination until one responds.

    The returned dictionary is used by multiple commands, so it includes both
    the successful session objects and the failed-attempt log.
    """

    candidates, windows_devices = collect_candidate_resources(extra_resource=extra_resource)
    backend_order = BACKENDS[:]

    if preferred_backend == "@py":
        backend_order = [("@py", "pyvisa-py"), ("", "vendor VISA")]
    elif preferred_backend == "":
        backend_order = [("", "vendor VISA"), ("@py", "pyvisa-py")]

    attempts = []

    for resource in candidates:
        for backend, label in backend_order:
            try:
                rm, scope, idn = open_scope(resource, backend)
                return {
                    "resource": resource,
                    "backend": backend,
                    "backend_label": label,
                    "idn": idn,
                    "resource_manager": rm,
                    "scope": scope,
                    "windows_devices": windows_devices,
                    "attempts": attempts,
                }
            except Exception as exc:
                attempts.append(f"{label} -> {resource} -> {exc}")

    return {
        "resource": None,
        "backend": None,
        "backend_label": None,
        "idn": None,
        "resource_manager": None,
        "scope": None,
        "windows_devices": windows_devices,
        "attempts": attempts,
    }


def read_ieee_block(scope, cmd):
    """
    Read a definite-length IEEE 488.2 binary block from the scope.

    Commands like :WAVeform:DATA? and :DISPlay:DATA? often respond using this
    format, which starts with a '#' header telling us how many bytes follow.
    """

    scope.write(cmd)
    first = scope.read_bytes(2, break_on_termchar=False)

    if not first.startswith(b"#"):
        return first + scope.read_raw()

    n_digits = int(first[1:2].decode())
    if n_digits == 0:
        return scope.read_raw()

    count_bytes = scope.read_bytes(n_digits, break_on_termchar=False)
    data_len = int(count_bytes.decode())
    return scope.read_bytes(data_len, break_on_termchar=False)


def save_screenshot(scope, out_path):
    """
    Ask the scope for a screenshot and save the returned PNG bytes.

    The fallback command is included because Rigol firmware sometimes accepts
    slightly different display-data command forms.
    """

    previous_timeout = scope.timeout
    scope.timeout = max(previous_timeout, SCREENSHOT_TIMEOUT_MS)

    try:
        try:
            png = read_ieee_block(scope, ":DISPlay:DATA? PNG")
        except Exception:
            png = read_ieee_block(scope, ":DISP:DATA?")

        out_path.write_bytes(png)
    finally:
        scope.timeout = previous_timeout


def get_waveform(scope, channel):
    """
    Download one channel's waveform and convert ADC bytes into volts and seconds.

    The scope reports scale factors in the waveform preamble. We read those
    first, then use them to reconstruct the real voltage and time axes.
    """

    scope.write(f":WAVeform:SOURce CHANnel{channel}")
    scope.write(":WAVeform:MODE NORMal")
    scope.write(":WAVeform:FORMat BYTE")

    preamble = scope.query(":WAVeform:PREamble?").strip()
    vals = [float(x) for x in preamble.split(",")]

    points = int(vals[2])
    xinc = vals[4]
    xorigin = vals[5]
    xref = vals[6]
    yinc = vals[7]
    yorigin = vals[8]
    yref = vals[9]

    raw = read_ieee_block(scope, ":WAVeform:DATA?")
    adc = np.frombuffer(raw, dtype=np.uint8)

    if len(adc) != points:
        print(f"Warning: expected {points} points, received {len(adc)} points.")

    idx = np.arange(len(adc))
    time_axis = (idx - xref) * xinc + xorigin
    volts = (adc.astype(float) - yref) * yinc + yorigin
    return time_axis, volts


def safe_write(scope, cmd):
    """
    Send a SCPI command without letting one unsupported command kill the run.

    This is mainly useful during scope-setup commands where some firmware
    variants may accept slightly different spellings.
    """

    try:
        scope.write(cmd)
    except Exception as exc:
        print(f"Warning: command failed: {cmd} -> {exc}")


def measurement_name_for_edge(edge_direction):
    """Map rising/falling timing onto Rigol's RRDelay/FFDelay names."""

    if edge_direction == "auto":
        raise ValueError("Scope delay measurement needs a concrete rising/falling edge.")
    return "RRDelay" if edge_direction == "rising" else "FFDelay"


def normalize_scope_measurement_value(raw_value):
    """
    Convert a scope-returned measurement into a float or NaN.

    Rigol returns a very large sentinel value when a measurement is not valid.
    """

    value = float(raw_value)
    if abs(value) >= INVALID_MEASUREMENT_SENTINEL * 0.99:
        return np.nan
    return value


def configure_scope_delay_measurement(scope, source_a, source_b, edge_direction):
    """
    Turn on the scope's own delay measurement/statistics display path.

    This mirrors the manual Measure -> Delay(f-f) / Statistics ON workflow.
    """

    measurement_name = measurement_name_for_edge(edge_direction)
    safe_write(scope, ":MEAS:STAT:DISP ON")
    safe_write(scope, ":MEAS:STAT:MODE ALL")
    safe_write(scope, f":MEAS:ITEM {measurement_name},CHAN{source_a},CHAN{source_b}")


def query_scope_delay(scope, source_a, source_b, edge_direction):
    """
    Ask the scope for its built-in current delay measurement.

    We try the direct measurement query first and then the statistics engine's
    current value query. If the scope says the measurement is invalid, we return
    NaN instead of the raw sentinel value.
    """

    measurement_name = measurement_name_for_edge(edge_direction)
    commands = [
        f":MEAS:ITEM? {measurement_name},CHAN{source_a},CHAN{source_b}",
        f":MEAS:STAT:ITEM? CURR,{measurement_name},CHAN{source_a},CHAN{source_b}",
    ]

    for command in commands:
        try:
            return normalize_scope_measurement_value(scope.query(command).strip())
        except Exception:
            continue

    return np.nan


def write_waveform_csv(time_axis, volts, out_path):
    """Save one waveform to a simple two-column CSV file."""

    with out_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["time_s", "voltage_v"])
        for t, v in zip(time_axis, volts):
            writer.writerow([t, v])


def filename_for_channel(filename, channel, multi_channel):
    """
    Expand a base filename into per-channel filenames when needed.

    Example:
      waveform.csv -> waveform_ch1.csv and waveform_ch2.csv
    """

    path = Path(filename)
    if not multi_channel:
        return path

    stem = path.stem[:-4] if path.stem.endswith("_ch1") else path.stem
    return path.with_name(f"{stem}_ch{channel}{path.suffix}")


def capture_filename(prefix, capture_index, channel, suffix):
    """Build deterministic per-capture filenames such as pulse_0003_ch2.csv."""

    return f"{prefix}_{capture_index:04d}_ch{channel}{suffix}"


def configure_pulse_capture(
    scope,
    trigger_channel,
    channels,
    trigger_level,
    time_scale,
    setup_time_scale,
    channel_scales,
    trigger_holdoff,
    trigger_slope,
):
    """
    Configure the scope for repeated single-shot 1PPS captures.

    This intentionally mirrors the manual workflow used in the lab:
    use a faster horizontal scale first so the trigger locks reliably, set the
    trigger source/slope/level/holdoff, and then zoom to the final edge window.
    """

    safe_write(scope, ":RUN")

    for channel in channels:
        safe_write(scope, f":CHANnel{channel}:DISPlay ON")
        safe_write(scope, f":CHANnel{channel}:COUPling DC")
        safe_write(scope, f":CHANnel{channel}:SCALe {channel_scales[channel]}")
        safe_write(scope, f":CHANnel{channel}:OFFSet 0")

    # Start at a coarse but still trigger-friendly scale before the final zoom.
    safe_write(scope, f":TIMebase:SCALe {setup_time_scale}")
    safe_write(scope, ":TIMebase:POSition 0")

    safe_write(scope, ":TRIGger:MODE EDGE")
    safe_write(scope, ":TRIGger:SWEep NORMal")
    safe_write(scope, f":TRIGger:EDGE:SOURce CHANnel{trigger_channel}")
    safe_write(scope, f":TRIGger:EDGE:SLOPe {trigger_slope}")
    safe_write(scope, f":TRIGger:LEVel CHANnel{trigger_channel},{trigger_level}")
    safe_write(scope, f":TRIGger:EDGE:LEVel {trigger_level}")
    safe_write(scope, f":TRIGger:HOLDoff {trigger_holdoff}")
    safe_write(scope, ":ACQuire:TYPE NORMal")

    # After trigger configuration is stable, zoom in around the pulse edge.
    safe_write(scope, f":TIMebase:SCALe {time_scale}")


def update_channel_scales(scope, channel_scales):
    """Apply a new volts/div setting to each listed channel."""

    for channel, scale in channel_scales.items():
        safe_write(scope, f":CHANnel{channel}:SCALe {scale}")


def wait_for_single_trigger(scope, timeout_s):
    """
    Arm a single acquisition and wait until the trigger event occurs.

    For a 1PPS signal, each loop iteration should correspond to one pulse.
    """

    safe_write(scope, ":SINGle")
    deadline = time.time() + timeout_s
    last_status = "unknown"

    while time.time() < deadline:
        try:
            last_status = scope.query(":TRIGger:STATus?").strip().upper()
            if "STOP" in last_status:
                return
        except Exception:
            time.sleep(min(timeout_s, 1.2))
            return

        time.sleep(0.05)

    raise TimeoutError(
        f"No trigger detected before timeout. Last trigger status was {last_status}."
    )


def baseline_voltage(time_axis, volts):
    """
    Estimate the idle baseline voltage before the pulse arrives.

    We prefer the pre-trigger samples because that reflects the quiet level just
    before the 1PPS edge. If there are too few pre-trigger points, we fall back
    to the first part of the capture.
    """

    time_axis = np.asarray(time_axis)
    volts = np.asarray(volts)
    pre_trigger = volts[time_axis < 0]
    if len(pre_trigger) >= 8:
        return float(np.median(pre_trigger))

    head = volts[: max(8, len(volts) // 10)]
    return float(np.median(head))


def resolve_edge_direction(time_axis, volts, edge_direction):
    """
    Decide whether this captured pulse is effectively rising or falling.

    In auto mode we compare the positive and negative excursion away from the
    baseline and choose the stronger one. This makes the script adapt when one
    channel is a small positive step while another channel is a negative dip.
    """

    if edge_direction != "auto":
        return edge_direction

    baseline = baseline_voltage(time_axis, volts)
    positive_excursion = float(np.max(volts) - baseline)
    negative_excursion = float(baseline - np.min(volts))
    return "rising" if positive_excursion >= negative_excursion else "falling"


def edge_arrival_time(time_axis, volts, threshold=None, edge_direction="falling"):
    """
    Estimate the arrival time of one threshold crossing.

    If the user does not choose a fixed threshold, we measure the pulse at 50%
    of its excursion away from the local baseline. In auto mode we first detect
    whether the pulse is predominantly rising or falling.
    """

    volts = np.asarray(volts)
    time_axis = np.asarray(time_axis)
    edge_direction = resolve_edge_direction(time_axis, volts, edge_direction)
    baseline = baseline_voltage(time_axis, volts)

    if threshold is None:
        if edge_direction == "rising":
            threshold = baseline + 0.5 * float(np.max(volts) - baseline)
        else:
            threshold = baseline - 0.5 * float(baseline - np.min(volts))

    if edge_direction == "rising":
        crossings = np.where((volts[:-1] < threshold) & (volts[1:] >= threshold))[0]
    else:
        crossings = np.where((volts[:-1] > threshold) & (volts[1:] <= threshold))[0]
    if len(crossings) == 0:
        return np.nan, float(threshold), edge_direction

    # For delay work, the physically meaningful timestamp is the first arrival
    # crossing, not whichever crossing lands closest to the trigger marker.
    # That avoids jumping onto later ringing cycles.
    crossing_index = int(crossings[0])
    dv = volts[crossing_index + 1] - volts[crossing_index]

    if dv == 0:
        return float(time_axis[crossing_index]), float(threshold), edge_direction

    frac = (threshold - volts[crossing_index]) / dv
    edge_time = time_axis[crossing_index] + frac * (
        time_axis[crossing_index + 1] - time_axis[crossing_index]
    )
    return float(edge_time), float(threshold), edge_direction


def summarize_pulse(time_axis, volts, edge_threshold=None, edge_direction="falling"):
    """
    Compute waveform statistics for one captured pulse.

    Even though the primary lab metric is delay, we also store the voltage range
    and threshold used for timing because that context helps with debugging and
    reproducibility.
    """

    v_min = float(np.min(volts))
    v_max = float(np.max(volts))
    v_low = float(np.percentile(volts, 10))
    v_high = float(np.percentile(volts, 90))
    baseline = baseline_voltage(time_axis, volts)
    edge_time, threshold, resolved_direction = edge_arrival_time(
        time_axis,
        volts,
        threshold=edge_threshold,
        edge_direction=edge_direction,
    )

    return {
        "baseline_v": baseline,
        "v_min_v": v_min,
        "v_max_v": v_max,
        "v_pp_v": v_max - v_min,
        "v_low_v": v_low,
        "v_high_v": v_high,
        "pulse_voltage_v": v_max,
        "edge_time_s": edge_time,
        "edge_threshold_v": threshold,
        "edge_direction_used": resolved_direction,
    }


def recommended_vertical_scale(volts, min_scale=0.02, max_scale=2.0, target_divisions=6.0):
    """
    Convert a captured waveform span into a more useful volts/div setting.

    A smaller volts/div makes a small pulse occupy more of the screen, which
    helps both humans and the scope's own built-in measurement engine.
    """

    span = float(np.max(volts) - np.min(volts))
    if span <= 0:
        return max_scale

    scale = span / target_divisions
    scale = max(min_scale, min(max_scale, scale))
    return scale


def write_summary_csv(rows, out_path):
    """Write the per-capture summary table if at least one row exists."""

    if not rows:
        return

    fieldnames = list(rows[0].keys())
    with out_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def delay_statistics(rows, trigger_channel, measure_channel):
    """
    Reduce the per-capture delays into a small run-level statistics summary.

    This gives users the mean, jitter-like spread, and peak-to-peak variation
    for the whole acquisition.
    """

    key = f"ch{measure_channel}_minus_ch{trigger_channel}_delay_s"
    values = np.array(
        [row[key] for row in rows if key in row and not np.isnan(row[key])],
        dtype=float,
    )

    if len(values) == 0:
        return None

    return {
        "n_captures": int(len(values)),
        "mean_delay_s": float(np.mean(values)),
        "mean_delay_ns": float(np.mean(values) * 1e9),
        "std_delay_s": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
        "std_delay_ps": float(np.std(values, ddof=1) * 1e12) if len(values) > 1 else 0.0,
        "min_delay_s": float(np.min(values)),
        "max_delay_s": float(np.max(values)),
        "peak_to_peak_delay_ps": float((np.max(values) - np.min(values)) * 1e12),
    }


def print_doctor_report(extra_resource=None):
    """
    Print a connection-health report for Windows + VISA + the scope.

    This is the fastest way for a new user to answer:
    "Does the PC actually see the scope over USB?"
    """

    print_header("Manual")
    for note in MANUAL_NOTES:
        print(f"- {note}")

    windows_devices = get_windows_usb_devices()

    print_header("Windows USB View")
    if not windows_devices:
        print("No DHO924 USB device is currently visible to Windows.")
    else:
        for dev in windows_devices:
            print(
                f"- {dev.get('FriendlyName') or 'Unknown'} | "
                f"status={dev.get('Status')} | present={dev.get('Present')} | "
                f"service={dev.get('Service')} | provider={dev.get('DriverProvider')} | "
                f"instance={dev.get('InstanceId')}"
            )

    print_header("VISA Resources")
    for backend, label in BACKENDS:
        resources, error = list_resources_for_backend(backend)
        if error:
            print(f"- {label}: ERROR: {error}")
        else:
            print(f"- {label}: {resources if resources else 'no resources found'}")

    print_header("Connection Attempt")
    result = try_connect(extra_resource=extra_resource)

    if result["scope"] is not None:
        print(f"Connected with {result['backend_label']}")
        print(f"Resource: {result['resource']}")
        print(f"*IDN?: {result['idn']}")
        result["scope"].close()
        result["resource_manager"].close()
        return 0

    print("Could not open the scope.")
    for attempt in result["attempts"]:
        print(f"- {attempt}")

    print_header("Likely Next Steps")
    if windows_devices and any(dev.get("Present") is False for dev in windows_devices):
        print("- Windows has a stale DHO924 entry but the device is not present right now.")
        print("- Turn the scope on, reconnect the USB cable, and use the rear USB DEVICE port.")
    else:
        print("- If the scope is on USB, reconnect it and then test with Rigol Ultra Sigma using USB-TMC search.")
    print("- On the scope, open Utility > I/O and confirm the VISA address is populated.")
    print("- If pyvisa-py sees the scope but vendor VISA does not, that is still okay for this script.")
    return 1


def connect_or_fail(extra_resource=None, preferred_backend=None):
    """
    Open the scope or raise a clear error directing the user to doctor mode.
    """

    result = try_connect(extra_resource=extra_resource, preferred_backend=preferred_backend)
    if result["scope"] is None:
        raise RuntimeError(
            "Could not connect to the oscilloscope.\n"
            "Run `python pulse_delay_capture.py doctor` first, then reconnect the scope and confirm "
            "that Windows and PyVISA can see it over USB-TMC."
        )
    return result


def cmd_idn(args):
    """Implementation of the `idn` subcommand."""

    result = connect_or_fail(extra_resource=args.resource, preferred_backend=args.backend)
    try:
        print(result["idn"])
    finally:
        result["scope"].close()
        result["resource_manager"].close()


def cmd_screenshot(args):
    """Implementation of the `screenshot` subcommand."""

    out_dir = Path(args.out_dir)
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / args.filename

    result = connect_or_fail(extra_resource=args.resource, preferred_backend=args.backend)
    try:
        save_screenshot(result["scope"], out_path)
        print(f"Saved screenshot to {out_path}")
    finally:
        result["scope"].close()
        result["resource_manager"].close()


def cmd_waveform(args):
    """Implementation of the `waveform` subcommand."""

    out_dir = Path(args.out_dir)
    out_dir.mkdir(exist_ok=True)

    if args.both:
        channels = [1, 2]
    elif args.channel is not None:
        channels = [args.channel]
    else:
        channels = args.channels

    channels = list(dict.fromkeys(channels))

    result = connect_or_fail(extra_resource=args.resource, preferred_backend=args.backend)
    try:
        multi_channel = len(channels) > 1
        for channel in channels:
            out_path = out_dir / filename_for_channel(args.filename, channel, multi_channel)
            time_axis, volts = get_waveform(result["scope"], channel)
            write_waveform_csv(time_axis, volts, out_path)
            print(f"Saved CH{channel} waveform to {out_path}")
            print(f"Captured {len(time_axis)} points from {result['idn']}")
    finally:
        result["scope"].close()
        result["resource_manager"].close()


def cmd_pulse_capture(args):
    """
    Implementation of the `pulse-capture` subcommand.

    This is the main lab workflow:
    - trigger on CH1
    - capture both channels for the same 1PPS event
    - timestamp both arrivals
    - compute CH2 - CH1
    """

    out_dir = Path(args.out_dir)
    out_dir.mkdir(exist_ok=True)

    channels = [args.trigger_channel, args.measure_channel]
    channels = list(dict.fromkeys(channels))
    channel_scales = {
        1: args.ch1_scale,
        2: args.ch2_scale,
    }
    for channel in channels:
        channel_scales.setdefault(channel, args.default_channel_scale)

    result = connect_or_fail(extra_resource=args.resource, preferred_backend=args.backend)
    summary_rows = []

    metadata = {
        "idn": result["idn"],
        "resource": result["resource"],
        "trigger_channel": args.trigger_channel,
        "measure_channel": args.measure_channel,
        "captures": args.captures,
        "trigger_level_v": args.trigger_level,
        "edge_threshold_v": args.edge_threshold,
        "edge_direction_requested": args.edge_direction,
        "time_scale_s_per_div": args.time_scale,
        "setup_time_scale_s_per_div": args.setup_time_scale,
        "trigger_slope": args.trigger_slope,
        "ch1_scale_v_per_div": args.ch1_scale,
        "ch2_scale_v_per_div": args.ch2_scale,
        "trigger_timeout_s": args.trigger_timeout,
        "trigger_holdoff_s": args.trigger_holdoff,
        "auto_scale_channels": args.auto_scale,
    }

    try:
        configure_pulse_capture(
            result["scope"],
            trigger_channel=args.trigger_channel,
            channels=channels,
            trigger_level=args.trigger_level,
            time_scale=args.time_scale,
            setup_time_scale=args.setup_time_scale,
            channel_scales=channel_scales,
            trigger_holdoff=args.trigger_holdoff,
            trigger_slope=args.trigger_slope,
        )
        scope_edge_direction = args.edge_direction
        if args.auto_scale or args.edge_direction == "auto":
            warmup_reason = []
            if args.auto_scale:
                warmup_reason.append("refine channel scales")
            if args.edge_direction == "auto":
                warmup_reason.append("detect pulse polarity")
            print(f"Running a warm-up capture to {' and '.join(warmup_reason)}...")
            wait_for_single_trigger(result["scope"], timeout_s=args.trigger_timeout)
            warmup_waveforms = {}
            scaled_channels = {}
            for channel in channels:
                time_axis, volts = get_waveform(result["scope"], channel)
                warmup_waveforms[channel] = (time_axis, volts)
                if args.auto_scale:
                    min_scale = args.ch2_min_scale if channel == 2 else args.min_channel_scale
                    new_scale = recommended_vertical_scale(
                        volts,
                        min_scale=min_scale,
                        max_scale=args.max_channel_scale,
                        target_divisions=args.target_vertical_divisions,
                    )
                    scaled_channels[channel] = new_scale
                    print(f"Recommended CH{channel} scale: {new_scale:.4f} V/div")

            if args.edge_direction == "auto":
                scope_edge_direction = resolve_edge_direction(
                    *warmup_waveforms[args.trigger_channel],
                    edge_direction="auto",
                )
                print(f"Detected trigger-channel pulse polarity: {scope_edge_direction}")

            if args.auto_scale:
                channel_scales.update(scaled_channels)
                metadata["auto_scaled_channel_scales_v_per_div"] = scaled_channels
                update_channel_scales(result["scope"], scaled_channels)
                time.sleep(0.2)

        metadata["scope_measurement_edge_direction"] = scope_edge_direction
        configure_scope_delay_measurement(
            result["scope"],
            source_a=args.trigger_channel,
            source_b=args.measure_channel,
            edge_direction=scope_edge_direction,
        )

        for capture_index in range(args.captures):
            print(f"Waiting for pulse {capture_index + 1}/{args.captures}...")
            wait_for_single_trigger(result["scope"], timeout_s=args.trigger_timeout)

            row = {
                "capture": capture_index,
                "captured_at_unix_s": time.time(),
            }

            for channel in channels:
                time_axis, volts = get_waveform(result["scope"], channel)
                waveform_name = capture_filename(args.prefix, capture_index, channel, ".csv")
                write_waveform_csv(time_axis, volts, out_dir / waveform_name)

                pulse = summarize_pulse(
                    time_axis,
                    volts,
                    edge_threshold=args.edge_threshold,
                    edge_direction=args.edge_direction,
                )
                for key, value in pulse.items():
                    row[f"ch{channel}_{key}"] = value

                print(f"Saved pulse {capture_index + 1} CH{channel} waveform to {out_dir / waveform_name}")

                edge_ns = (
                    pulse["edge_time_s"] * 1e9
                    if not np.isnan(pulse["edge_time_s"])
                    else float("nan")
                )
                print(f"CH{channel} arrival at {edge_ns:.3f} ns")

            trigger_edge = row.get(f"ch{args.trigger_channel}_edge_time_s", np.nan)
            measure_edge = row.get(f"ch{args.measure_channel}_edge_time_s", np.nan)

            row[f"ch{args.trigger_channel}_arrival_s"] = trigger_edge
            row[f"ch{args.measure_channel}_arrival_s"] = measure_edge
            scope_delay_s = query_scope_delay(
                result["scope"],
                source_a=args.trigger_channel,
                source_b=args.measure_channel,
                edge_direction=scope_edge_direction,
            )
            row["scope_delay_s"] = scope_delay_s
            row["scope_delay_ns"] = scope_delay_s * 1e9 if not np.isnan(scope_delay_s) else np.nan
            row["scope_delay_ps"] = scope_delay_s * 1e12 if not np.isnan(scope_delay_s) else np.nan

            if not np.isnan(trigger_edge) and not np.isnan(measure_edge):
                delay_s = measure_edge - trigger_edge
                row[f"ch{args.measure_channel}_minus_ch{args.trigger_channel}_delay_s"] = delay_s
                row[f"ch{args.measure_channel}_minus_ch{args.trigger_channel}_delay_ns"] = delay_s * 1e9
                row[f"ch{args.measure_channel}_minus_ch{args.trigger_channel}_delay_ps"] = delay_s * 1e12
                print(f"Delay CH{args.measure_channel}-CH{args.trigger_channel}: {delay_s * 1e9:.3f} ns")
            else:
                row[f"ch{args.measure_channel}_minus_ch{args.trigger_channel}_delay_s"] = np.nan
                row[f"ch{args.measure_channel}_minus_ch{args.trigger_channel}_delay_ns"] = np.nan
                row[f"ch{args.measure_channel}_minus_ch{args.trigger_channel}_delay_ps"] = np.nan
                print("Could not compute delay for this capture because one edge was not found.")

            if not np.isnan(scope_delay_s):
                print(
                    f"Scope Delay({measurement_name_for_edge(scope_edge_direction)}): "
                    f"{scope_delay_s * 1e9:.3f} ns"
                )
            else:
                print("Scope-built delay measurement is currently unavailable for this capture.")

            if args.screenshot_each:
                screenshot_name = f"{args.prefix}_{capture_index:04d}.png"
                screenshot_path = out_dir / screenshot_name
                try:
                    save_screenshot(result["scope"], screenshot_path)
                    print(f"Saved screenshot to {screenshot_path}")
                except Exception as exc:
                    print(f"Warning: screenshot save failed for capture {capture_index + 1}: {exc}")

            summary_rows.append(row)

        write_summary_csv(summary_rows, out_dir / f"{args.prefix}_summary.csv")

        stats = delay_statistics(
            summary_rows,
            trigger_channel=args.trigger_channel,
            measure_channel=args.measure_channel,
        )

        metadata["delay_statistics"] = stats
        (out_dir / f"{args.prefix}_metadata.json").write_text(json.dumps(metadata, indent=2))

        print(f"Wrote summary to {out_dir / f'{args.prefix}_summary.csv'}")

        if stats:
            print(
                f"Mean delay CH{args.measure_channel}-CH{args.trigger_channel}: "
                f"{stats['mean_delay_ns']:.3f} ns"
            )
            print(f"Std dev: {stats['std_delay_ps']:.3f} ps")
            print(f"Peak-to-peak: {stats['peak_to_peak_delay_ps']:.3f} ps")
    finally:
        result["scope"].close()
        result["resource_manager"].close()


def build_parser():
    """
    Define the command-line interface for the script.

    Keeping all parser configuration in one place makes the available commands
    easy for future contributors to expand.
    """

    parser = argparse.ArgumentParser(
        description="Rigol DHO900 USB connection doctor and 1PPS delay-capture tool."
    )

    parser.add_argument(
        "--resource",
        default=None,
        help="Optional VISA resource string to try first, for example USB0::0x1AB1::0x044C::SERIAL::INSTR",
    )

    parser.add_argument(
        "--backend",
        default="auto",
        choices=["auto", "vendor", "py"],
        help="Choose backend order: auto, vendor VISA first, or pyvisa-py first.",
    )

    subparsers = parser.add_subparsers(dest="command")

    doctor = subparsers.add_parser("doctor", help="Inspect Windows/VISA visibility and try *IDN?.")
    doctor.set_defaults(func=lambda args: sys.exit(print_doctor_report(extra_resource=args.resource)))

    idn = subparsers.add_parser("idn", help="Query *IDN? from the scope.")
    idn.set_defaults(func=cmd_idn)

    screenshot = subparsers.add_parser("screenshot", help="Save a screenshot of the current scope display.")
    screenshot.add_argument("--out-dir", default=str(DEFAULT_OUTPUT_DIR))
    screenshot.add_argument("--filename", default="scope_screenshot.png")
    screenshot.set_defaults(func=cmd_screenshot)

    waveform = subparsers.add_parser("waveform", help="Download one or more displayed waveform channels as CSV.")
    waveform.add_argument("--channel", type=int, help="Single channel to capture, for example 1 or 2.")
    waveform.add_argument("--channels", nargs="+", type=int, default=[1], help="One or more channels to capture.")
    waveform.add_argument("--both", action="store_true", help="Capture CH1 and CH2 in one command.")
    waveform.add_argument("--out-dir", default=str(DEFAULT_OUTPUT_DIR))
    waveform.add_argument("--filename", default="waveform_ch1.csv")
    waveform.set_defaults(func=cmd_waveform)

    pulse_capture = subparsers.add_parser(
        "pulse-capture",
        help="Trigger on each 1PPS pulse, timestamp CH1 and CH2, and record CH2 - CH1 delay.",
    )
    pulse_capture.add_argument("--trigger-channel", type=int, default=1)
    pulse_capture.add_argument("--measure-channel", type=int, default=2)
    pulse_capture.add_argument("--captures", type=int, default=5)
    pulse_capture.add_argument("--trigger-level", type=float, default=1.5)
    pulse_capture.add_argument(
        "--trigger-slope",
        default="NEGative",
        choices=["POSitive", "NEGative"],
        help="Scope trigger slope. Use NEGative for a downward 1PPS dip and POSitive for an upward pulse.",
    )
    pulse_capture.add_argument(
        "--edge-direction",
        default="auto",
        choices=["auto", "rising", "falling"],
        help="Which threshold crossing to treat as the pulse arrival when computing CH2 - CH1. Auto detects whether the captured pulse is rising or falling.",
    )
    pulse_capture.add_argument(
        "--edge-threshold",
        type=float,
        default=None,
        help="Voltage threshold used to timestamp arrivals on both channels. Default: 50%% of the observed max voltage on each capture.",
    )
    pulse_capture.add_argument(
        "--setup-time-scale",
        type=float,
        default=100e-6,
        help="Coarse horizontal scale used while establishing the trigger, in seconds per division.",
    )
    pulse_capture.add_argument(
        "--time-scale",
        type=float,
        default=100e-9,
        help="Final zoomed-in horizontal scale used for edge timing, in seconds per division.",
    )
    pulse_capture.add_argument(
        "--ch1-scale",
        type=float,
        default=2.0,
        help="Vertical scale for CH1 in volts per division.",
    )
    pulse_capture.add_argument(
        "--ch2-scale",
        type=float,
        default=1.0,
        help="Vertical scale for CH2 in volts per division. This matches the current 50 ohm terminated setup.",
    )
    pulse_capture.add_argument(
        "--default-channel-scale",
        type=float,
        default=1.0,
        help="Fallback volts per division if you use a channel other than CH1 or CH2.",
    )
    pulse_capture.add_argument(
        "--auto-scale",
        dest="auto_scale",
        action="store_true",
        default=True,
        help="Use one warm-up pulse to tighten the displayed volts/div before the measured captures start.",
    )
    pulse_capture.add_argument(
        "--no-auto-scale",
        dest="auto_scale",
        action="store_false",
        help="Skip the warm-up auto-scaling step and use the requested channel scales as-is.",
    )
    pulse_capture.add_argument(
        "--min-channel-scale",
        type=float,
        default=0.05,
        help="Smallest volts/div the auto-scaler may choose for general channels.",
    )
    pulse_capture.add_argument(
        "--ch2-min-scale",
        type=float,
        default=0.02,
        help="Smallest volts/div the auto-scaler may choose for CH2. This helps with the 50 ohm terminated channel.",
    )
    pulse_capture.add_argument(
        "--max-channel-scale",
        type=float,
        default=2.0,
        help="Largest volts/div the auto-scaler may choose.",
    )
    pulse_capture.add_argument(
        "--target-vertical-divisions",
        type=float,
        default=6.0,
        help="How many vertical divisions the captured pulse span should try to occupy after auto-scaling.",
    )
    pulse_capture.add_argument("--trigger-timeout", type=float, default=3.0)
    pulse_capture.add_argument("--trigger-holdoff", type=float, default=0.8)
    pulse_capture.add_argument("--screenshot-each", action="store_true")
    pulse_capture.add_argument("--out-dir", default=str(DEFAULT_OUTPUT_DIR))
    pulse_capture.add_argument("--prefix", default="pulse")
    pulse_capture.set_defaults(func=cmd_pulse_capture)

    return parser


def main():
    """
    Parse arguments, normalize backend names, and dispatch to the chosen command.
    """

    parser = build_parser()
    args = parser.parse_args()
    args.backend = normalize_backend_choice(args.backend)

    if not args.command:
        sys.exit(print_doctor_report(extra_resource=args.resource))

    args.func(args)


# This guard ensures the script only runs when invoked directly from the shell.
if __name__ == "__main__":
    main()
