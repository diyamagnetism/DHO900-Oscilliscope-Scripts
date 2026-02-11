import re
import matplotlib.pyplot as plt
import math

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

            if temp != "":
                vrms_vals.append(float(vrms))
                temps.append(float(temp))

print(f"Read {len(temps)} valid data points")

#plot for output voltage vs temperature
plt.figure()
plt.plot(temps, vrms_vals, marker='o')
plt.xlabel("Temperature")
plt.ylabel("VRMS (V)")
plt.title("VRMS vs Temperature (60 dB Gain)")
plt.grid(True)
plt.xlim(180, 200)
plt.xticks(range(180, 201, 1), fontsize=8)
plt.show()

R = 1e6  # 1 MΩ scope input impedance

power_watts = [(v**2)/R for v in vrms_vals]

#plot for power in watts
plt.figure()
plt.plot(temps, power_watts, marker='o')
plt.xlabel("Temperature")
plt.ylabel("Power (W)")
plt.title("Power vs Temperature (1 MΩ Load)")
plt.grid(True)
plt.xlim(180, 200)
plt.xticks(range(180, 201, 1), fontsize=8)
plt.show()


power_dBm = [10 * math.log10(p / 1e-3) if p > 0 else float('-inf')
             for p in power_watts]

#plot for power in dBm with log ratio (output p/1mW)
plt.figure()
plt.plot(temps, power_dBm, marker='o')
plt.xlabel("Temperature")
plt.ylabel("Power (dBm)")
plt.title("Power (dBm) vs Temperature (1 MΩ Load)")
plt.grid(True)
plt.xlim(180, 200)
plt.xticks(range(180, 201, 1), fontsize=8)
plt.show()

Vmax = max(vrms_vals)

relative_dB = [20 * math.log10(v / Vmax) if v > 0 else float('-inf')
               for v in vrms_vals]

#plot for power in dB with log ratio (output p/p max)
plt.figure()
plt.plot(temps, relative_dB, marker='o')
plt.xlabel("Temperature")
plt.ylabel("Relative Power (dB)")
plt.title("Relative Power vs Temperature (Normalized to Peak)")
plt.grid(True)
plt.xlim(180, 200)
plt.xticks(range(180, 201, 1), fontsize=8)
plt.show()

relative_dB_2 = [10 * math.log10(p/0.2) if p > 0 else float('-inf')
             for p in power_watts]

plt.figure()
plt.plot(temps, relative_dB_2, marker='o')
plt.xlabel("Temperature")
plt.ylabel("Relative Power (dB)")
plt.title("Relative Power vs Temperature (Normalized to input power)")
plt.grid(True)
plt.xlim(180, 200)
plt.xticks(range(180, 201, 1), fontsize=8)
plt.show()
