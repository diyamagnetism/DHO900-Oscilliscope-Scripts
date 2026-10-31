"""
NI USB-6251 voltage reading with CSV logging
------------------------------------------------------
Reads an analog input channel at a user-defined sampling interval, for a
user-defined number of samples, and logs each reading + timestamp to a
CSV file.

Requirements:
    pip install nidaqmx

Hardware:
    NI USB-6251 (or any NI DAQ with an analog input channel), NI-DAQmx
    driver installed, and the device configured in NI MAX (note its device
    name, e.g. "Dev1").
"""
import os
import csv
import time
from datetime import datetime

import nidaqmx
from nidaqmx.constants import TerminalConfiguration

from nidaqmx.constants import AcquisitionType





# ----------------------- USER-CONFIGURABLE SETTINGS -----------------------
DEVICE_NAME = "Dev1"          # Device name as it appears in NI MAX
AI_CHANNEL = "ai1"            # Analog input channel to read
MIN_VOLTAGE = -10.0           # Expected minimum input voltage (V)
MAX_VOLTAGE = 10.0            # Expected maximum input voltage (V)

FS = 10000            # Hz, hardware sample clock
N_AVG = 10000         # samples per reading (1 s per reading at 10 kS/s)


SAMPLE_INTERVAL_S = 0.1      # Time between reads (seconds)
NUM_SAMPLES = 400              # Number of readings to take

OUTPUT_CSV_DIRECTORY = "DAQ_reading\\ppln_only_data\\1550_calibration"  # Directory for output CSV files
OUTPUT_CSV_PREFIX = "calibration_voltage"  # Output CSV file prefix (timestamp is appended)
# ----------------------------------------------------------------------------
 
task.timing.cfg_samp_clk_timing(
    FS, sample_mode=AcquisitionType.FINITE, samps_per_chan=N_AVG)




def read_voltage_avg(task):
    data = np.array(task.read(number_of_samples_per_channel=N_AVG,
                              timeout=N_AVG / FS + 5))
    return data.mean(), data.std()
 
def main():
    run_start = datetime.now().strftime("%Y%m%d_%H%M")
    os.makedirs(OUTPUT_CSV_DIRECTORY, exist_ok=True)
    output_csv = os.path.join(OUTPUT_CSV_DIRECTORY, f"{OUTPUT_CSV_PREFIX}_{run_start}.csv")

    with open(output_csv, mode="w", newline="") as f, \
         nidaqmx.Task() as task:
 
        writer = csv.writer(f)
        writer.writerow(["timestamp", "measured_voltage_V"])
 
        task.ai_channels.add_ai_voltage_chan(
            f"{DEVICE_NAME}/{AI_CHANNEL}",
            terminal_config=TerminalConfiguration.DEFAULT,
            min_val=MIN_VOLTAGE,
            max_val=MAX_VOLTAGE,
        )
 
        for i in range(NUM_SAMPLES):
            voltage = read_voltage(task)
            timestamp = datetime.now().isoformat()
            writer.writerow([timestamp, voltage])
            f.flush()
            print(f"{timestamp}  ->  {voltage:.4f} V")
 
            if i < NUM_SAMPLES - 1:
                time.sleep(SAMPLE_INTERVAL_S)
 
    print(f"\nDone. Log written to: {output_csv}")
 
 
if __name__ == "__main__":
    main()
 