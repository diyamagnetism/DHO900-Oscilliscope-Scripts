
from ID_OSA_new_classes import *


osa = ID_OSA_IP('192.168.0.4')

# query device identification
print(osa.writeSCPI("*idn?"))
print(osa.writeSCPI("TRAC:X"))
print(osa.writeSCPI("TRAC:Y"))

osa.setStartStopFreq(193,194)
osa.setCenterSpanFreq(193.5,1.0)
osa.setStartStopWL(1545,1553)
osa.setCenterSpanWL(1549,3)


#osa.writeSCPI("maxstep")
osa.writeSCPI("minstep")
osa.waitOPC()

# trigger a scan
osa.triggerScan()

# get scan data
xy = osa.getXY()

print(len(xy))      # num points

# print first point
print(xy[0])
print(xy[0][0])     # wavelength
print(xy[0][1])     # pwr
