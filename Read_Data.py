import re
import matplotlib.pyplot as plt
import pandas as pd

# ---------------- CHANGE AS NEEDED ----------------
filename = r"oscilliscope_data/gain_setting_trials/60dB_gain.txt"
#------------------------------------------------


def get_data_from_txt():
    temps = []
    vrms_vals = []

    pattern = re.compile(
        r"VRMS\s*=\s*([0-9.]+)\s*V\s*TEMP\s*=\s*([0-9.]*)"
    )

    with open(filename, "r", encoding="utf-8") as f:
        for line in f:
            match = pattern.search(line)
            if match:
                vrms = match.group(1)
                temp = match.group(2)

                # Skip rows where TEMP is missing
                if temp != "":
                    vrms_vals.append(float(vrms))
                    temps.append(float(temp))

    print(f"Read {len(temps)} valid data points from txt")
    return (vrms, temp)

def get_data_from_csv():
    temps = []
    vrms_vals = []
    
    with open(filename, "r", encoding="utf-8") as f:
        for line in f:
            match = pattern.search(line)
            if match:
                vrms = match.group(1)
                temp = match.group(2)

                # Skip rows where TEMP is missing
                if temp != "":
                    vrms_vals.append(float(vrms))
                    temps.append(float(temp))

    print(f"Read {len(temps)} valid data points from txt")
    return (vrms, temp)

plt.figure()
plt.plot(temps, vrms_vals, marker='o')
plt.xlabel("Temperature")
plt.ylabel("VRMS (V)")
plt.title("VRMS vs Temperature (60 dB Gain)")
plt.grid(True)

plt.xlim(180, 200)
plt.xticks(range(180, 201, 1), fontsize=8)

plt.show()
