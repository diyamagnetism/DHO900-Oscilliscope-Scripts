from ID_OSA_new_classes import *
import matplotlib.pyplot as plt

SAVE_PATH = 'spectrum_data\\spectrum_data.csv'
is_save = False





print(find_ports())          # lists COM ports, handy for finding the right number

osa = ID_OSA_Serial('COM5')         # use the COM port shown in Device Manager

# query device identification
print(osa.writeSCPI("*idn?"))
print(osa.writeSCPI("TRAC:X?"))
print(osa.writeSCPI("TRAC:Y?"))
 
# print(osa.writeSCPI("unit:x 1"))     # 1 = frequency, 0 = wavelength


osa.setStartStopFreq(193, 194)
osa.setCenterSpanFreq(193.5, 1.4)
osa.setStartStopWL(1545, 1553)
osa.setCenterSpanWL(1548.5, 6)

osa.writeSCPI("minstep")
osa.waitOPC()

osa.setScanAverages(30)
# trigger a scan
osa.triggerScan()
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


if is_save:
    path, data = osa.saveSpectrumCSV(SAVE_PATH)
    print("Saved spectrum data to:", path)



osa.close()

