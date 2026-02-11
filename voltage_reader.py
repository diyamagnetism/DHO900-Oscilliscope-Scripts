import pyvisa
import time
import os

# ---------------- USER SETTINGS ----------------
CONN = "USB0::0x1AB1::0x044C::DHO9A264M00069::INSTR"
INTERVAL = 420  # seconds
LOG_FILE = "oscilliscope_data/.../rms_voltage_log.txt" # adjust directory to save to the correct folder
SCREENSHOT_DIR = "screenshots"
CHANNEL = "CHAN1"   # change if needed
START_TEMP = 180 # Starting temperature
TEMP_STEP = 1 # temperature step per interval
# -----------------------------------------------


start_time = time.time()
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

rm = pyvisa.ResourceManager()
inst = rm.open_resource(CONN)

# Recommended settings for Rigol scopes
inst.timeout = 10000
#inst.write(":STOP")          # freeze display for consistent screenshots (ALSO FREEZD MEASUREMENTS)
inst.write(":WAV:MODE NORM")

print(inst.query("*IDN?").strip())

def plot_vrms(temp_vals, vrms_vals):
    plt.figure()
    plt.plot(temp_vals, vrms_vals, marker='o')
    plt.xlabel("Temperature")
    plt.ylabel("VRMS (V)")
    plt.title("VRMS vs Temperature")
    plt.grid(True)

    plt.xlim(180, 200)
    plt.xticks(range(180, 201, 1), fontsize=8)

    plt.show()

def get_vrms():
    return float(inst.query(f":MEAS:ITEM? VRMS,{CHANNEL}"))

def take_screenshot(filename):
    inst.write(":DISP:DATA?")
    raw = inst.read_raw()

    # Find the PNG header explicitly
    png_start = raw.find(b'\x89PNG\r\n\x1a\n')
    if png_start == -1:
        raise RuntimeError("PNG header not found in scope data")

    png_data = raw[png_start:]

    with open(filename, "wb") as f:
        f.write(png_data)

try:
    with open(LOG_FILE, "a") as log:
        log.write("# Time (epoch), VRMS (V)\n")

        while True:
            timestamp = time.time()
            vrms = get_vrms()
            vrms_vals.append(vrms)
            temp_vals.append((START_TEMP + np.floor((timestamp - start_time)/INTERVAL)))

            # Log data
            log.write(f"{timestamp:.3f}, {vrms:.6f}\n")
            log.flush()

            # Screenshot
            screenshot_name = f"{SCREENSHOT_DIR}/scope_{int(timestamp)}.png"
            take_screenshot(screenshot_name)

            print(f"[{time.ctime()}] VRMS = {vrms:.6f} V")

            plot_vrms(temp_vals, vrms_vals)

            if vrms > 3:
                print("WARNING: VOLTAGE SATURATION.\n DATA FROM THIS POINT MAY BE UNRELIABLE\n")

            time.sleep(INTERVAL)

except KeyboardInterrupt:
    print("\nMeasurement stopped by user.")

finally:
    inst.write(":RUN")
    inst.close()
    rm.close()

