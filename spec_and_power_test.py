

from toptica_and_spectrum_analyzer.ID_OSA_new_classes import *
from DAQ_reading.ni_usb6251_control import *
import matplotlib.pyplot as plt
import numpy as np
from nidaqmx.constants import AcquisitionType
from collections import deque



# ----------------------- USER-CONFIGURABLE SETTINGS -----------------------
DEVICE_NAME = "Dev1"          # Device name as it appears in NI MAX
AI_CHANNEL = "ai1"            # Analog input channel to read
MIN_VOLTAGE = -10.0           # Expected minimum input voltage (V)
MAX_VOLTAGE = 10.0            # Expected maximum input voltage (V)

FS = 10000            # Hz, hardware sample clock
N_AVG = 10000         # samples per reading (1 s per reading at 10 kS/s)


MOVING_AVG_WINDOW = 10         # Number of samples to average for moving average

SAMPLE_INTERVAL_S = 0.08       # Time between reads (seconds)
NUM_SAMPLES = 100              # Number of readings to take

OUTPUT_CSV_DIRECTORY = "DAQ_reading\\ppln_only_data\\spec_1_daq_99"  # Directory for output CSV files
OUTPUT_CSV_PREFIX = "piezo_54"  # Output CSV file prefix (timestamp is appended)


# ----------------------------------------------------------------------------


#----------------------- OSA SETTNGS -----------------------------------------
osa = ID_OSA_Serial('COM5')         # use the COM port shown in Device Manager

osa.setCenterSpanWL(1548.5, 3.5)

osa.writeSCPI("minstep")
osa.waitOPC()

osa.setScanAverages(100)


SAVE_PATH_SPEC = f'toptica_and_spectrum_analyzer\\spectrum_data\\spec_1_daq_99\\{OUTPUT_CSV_PREFIX}_spectrum_data'
is_save_spec = True
TIMEOUT = 200
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
        voltage, noise = read_voltage_avg(task)
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

for i in range(5):
    xy = osa.getXY()

    print(f' num points: {len(xy)}')      # num points

    # print first point
    print(xy[0])
    print(f'{xy[0][0]} Hz')     # x (Hz or m)
    print(f'{xy[0][1]} dB')     # power

    # plt.figure()
    # plt.plot([convert_Hz_to_nm(x[0]) for x in xy], [y[1] for y in xy])
    # plt.xlabel('Wavelength (nm)')
    # plt.ylabel('Power (dBm)')
    # plt.title('Spectrum Analysis')
    # plt.show()


    if is_save_spec:
        spec_start = datetime.now().strftime("%Y%m%d_%H%M")

        path_csv = os.path.join(f"{SAVE_PATH_SPEC}_{spec_start}.csv")
        
        path, data = osa.saveSpectrumCSV(path_csv)
        print("Saved spectrum data to:", path)

    # time.sleep(1)

osa.close()

