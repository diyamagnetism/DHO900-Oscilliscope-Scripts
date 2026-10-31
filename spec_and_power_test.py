

from toptica_and_spectrum_analyzer.ID_OSA_new_classes import *
from DAQ_reading.ni_usb6251_control import *
import matplotlib.pyplot as plt
import numpy as np
from collections import deque


# ----------------------- USER-CONFIGURABLE SETTINGS -----------------------
DEVICE_NAME = "Dev1"          # Device name as it appears in NI MAX
AI_CHANNEL = "ai1"            # Analog input channel to read
MIN_VOLTAGE = -10.0           # Expected minimum input voltage (V)
MAX_VOLTAGE = 10.0            # Expected maximum input voltage (V)

SAMPLE_INTERVAL_S = 1.0       # Time between reads (seconds)
NUM_SAMPLES = 200              # Number of readings to take

OUTPUT_CSV_DIRECTORY = "DAQ_reading\\ppln_only_data\\photon_maxing"  # Directory for output CSV files
OUTPUT_CSV_PREFIX = "piezo_50"  # Output CSV file prefix (timestamp is appended)


SAVE_PATH_SPEC = f'toptica_and_spectrum_analyzer\\spectrum_data\\{OUTPUT_CSV_PREFIX}_spectrum_data.csv'
is_save_spec = True
TIMEOUT = 200
# ----------------------------------------------------------------------------


#----------------------- OSA SETTNGS -----------------------------------------
osa = ID_OSA_Serial('COM5')         # use the COM port shown in Device Manager

osa.setCenterSpanWL(1548.5, 3.5)

osa.writeSCPI("minstep")
osa.waitOPC()

osa.setScanAverages(100)
#--------------------------------------------------------------------------------


run_start = datetime.now().strftime("%Y%m%d_%H%M")
os.makedirs(OUTPUT_CSV_DIRECTORY, exist_ok=True)
output_csv = os.path.join(OUTPUT_CSV_DIRECTORY, f"{OUTPUT_CSV_PREFIX}_{run_start}.csv")
with open(output_csv, mode="w", newline="") as f, \
        nidaqmx.Task() as task:

    writer = csv.writer(f)
    writer.writerow(["timestamp", "measured_voltage_V", "moving_avg_V"])

    task.ai_channels.add_ai_voltage_chan(
        f"{DEVICE_NAME}/{AI_CHANNEL}",
        terminal_config=TerminalConfiguration.DEFAULT,
        min_val=MIN_VOLTAGE,
        max_val=MAX_VOLTAGE,
    )

    voltages = []
    window = deque(maxlen=MOVING_AVG_WINDOW)   # old samples drop off automatically
    for i in range(NUM_SAMPLES):
        voltage = read_voltage(task)
        voltages.append(voltage)
        window.append(voltage)
        moving_avg = np.mean(window)           # averages fewer points until the window fills

        timestamp = datetime.now().isoformat()
        writer.writerow([timestamp, voltage, moving_avg])
        f.flush()
        print(f"{timestamp}  ->  {voltage:.4f} V   "
              f"(moving avg, n={len(window)}: {moving_avg:.4f} V)")

        if i < NUM_SAMPLES - 1:
            time.sleep(SAMPLE_INTERVAL_S)

print(f"\nDone. Log written to: {output_csv}. "
      f"Overall avg: {np.mean(voltages):.4f} V, "
      f"final moving avg: {moving_avg:.4f} V")




# trigger a scan
osa.triggerScan(timeout=TIMEOUT)
# get scan data
xy = osa.getXY()

print(f' num points: {len(xy)}')      # num points

# print first point
print(xy[0])
print(f'{xy[0][0]} Hz')     # x (Hz or m)
print(f'{xy[0][1]} dB')     # power

plt.figure()
plt.plot([convert_Hz_to_nm(x[0]) for x in xy], [y[1] for y in xy])
plt.xlabel('Wavelength (nm)')
plt.ylabel('Power (dBm)')
plt.title('Spectrum Analysis')
plt.show()


if is_save_spec:
    path, data = osa.saveSpectrumCSV(SAVE_PATH_SPEC)
    print("Saved spectrum data to:", path)



osa.close()

