import re
import matplotlib.pyplot as plt

filename = r"C:\Users\rncit\OneDrive\Desktop\QLATS\Oscilloscope Measurement Codes\Gain Settingg Trials\60dB Gain Setting (2-2-2026).txt"

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

print(f"Read {len(temps)} valid data points")

plt.figure()
plt.plot(temps, vrms_vals, marker='o')
plt.xlabel("Temperature")
plt.ylabel("VRMS (V)")
plt.title("VRMS vs Temperature (60 dB Gain)")
plt.grid(True)

plt.xlim(180, 200)
plt.xticks(range(180, 201, 1), fontsize=8)

plt.show()
