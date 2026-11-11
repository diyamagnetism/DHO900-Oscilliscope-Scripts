from pathlib import Path
import re
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from toptica_and_spectrum_analyzer.ID_OSA_new_classes import *

def find_highest_mean_voltage(folder, pattern="*.csv", voltage_col="measured_voltage_V"):
    """
    Find the file in `folder` with the highest mean measured voltage.

    Each file is expected to contain a timestamp, a measured voltage,
    and a moving average voltage column.

    Returns
    -------
    (Path, float, dict)
        Best file path, its mean voltage, and a {Path: mean} dict for all files.
    """
    folder = Path(folder)
    means = {}

    for file in sorted(folder.glob(pattern)):
        try:
            df = pd.read_csv(file)
            means[file] = df[voltage_col].mean()
        except (KeyError, pd.errors.EmptyDataError, pd.errors.ParserError) as e:
            print(f"Skipping {file.name}: {e}")

    if not means:
        raise ValueError(f"No valid files found in {folder} matching {pattern!r}")

    best_file = max(means, key=means.get)
    return best_file, means[best_file], means


def plot_mean_voltage_vs_piezo_voltage(
    folder, pattern="piezo_*.csv", voltage_col="measured_voltage_V"
):
    """Plot each CSV's mean measured voltage against its filename's piezo voltage."""
    folder = Path(folder)
    csv_files = sorted(folder.glob(pattern))
    if not csv_files:
        raise ValueError(f"No CSV files found in {folder} matching {pattern!r}")

    piezo_voltages = []
    mean_voltages = []
    filename_pattern = re.compile(
        r"^piezo_(?P<voltage>\d+(?:_\d{1,6})?)_\d{8}(?:_|\.|$)"
    )

    for file in csv_files:
        match = filename_pattern.match(file.name)
        if match is None:
            raise ValueError(
                f"Could not extract a piezo voltage and 8-digit date from {file.name!r}"
            )

        piezo_voltage = float(match.group("voltage").replace("_", "."))
        df = pd.read_csv(file)
        mean_voltage = df[voltage_col].mean()
        if pd.isna(mean_voltage):
            raise ValueError(f"No measured voltages found in {file}")

        piezo_voltages.append(piezo_voltage)
        mean_voltages.append(mean_voltage)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.scatter(piezo_voltages, mean_voltages)
    ax.set_xlabel("Piezo voltage")
    ax.set_ylabel("Mean measured voltage (V)")
    ax.set_title("Mean Measured Voltage vs Piezo Voltage")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()
    return fig, ax


def plot_daq_voltage(CSV_PATH):
    df = pd.read_csv(CSV_PATH, parse_dates=["timestamp"])
    # print(f"Average voltage {np.mean(df["measured_voltage_V"])}")

    # Elapsed time (seconds) since the first sample, often easier to read than wall-clock time
    df["elapsed_s"] = (df["timestamp"] - df["timestamp"].iloc[0]).dt.total_seconds()

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df["elapsed_s"], df["measured_voltage_V"], marker="o", markersize=3, linewidth=1)
    ax.set_xlabel("Elapsed time (s)")
    ax.set_ylabel("Voltage (V)")
    ax.set_title("Voltage vs Time")
    ax.grid(True, alpha=0.3)
    # ax.set_xlim(left=0)
    # ax.set_ylim(bottom=0, top=6)

    plt.tight_layout()
    plt.show()


def plot_spec(xy):
    plt.figure()
    plt.plot([convert_Hz_to_nm(x[0]) for x in xy], [y[1] for y in xy])
    plt.xlabel('Wavelength (nm)')
    plt.ylabel('Power (dBm)')
    plt.title('Spectrum Analysis')
    plt.show()


# if __name__ == "__main__":
#     best, mean_v, all_means = find_highest_mean_voltage("data")
#     print(f"Highest mean voltage: {best.name} ({mean_v:.4f} V)")