
# Python API for ID OSA
# by Christian Schwarz / id-photonics.com

# Serial version is adapted from the TCP/IP version (ID_OSA_IP) by Christian Schwarz / id-photonics.com.
# Close PuTTY (or any other program) before running: only one program can hold the COM port.
# -----------------------------------------------------------------------------------

import socket
import time
from decimal import Decimal
import numpy
import serial
from serial.tools import list_ports


def find_ports():
    ''' Returns a list of (device, description) for all serial ports on this PC. '''
    return [(p.device, p.description) for p in list_ports.comports()]
 
 
class OSAError(IOError):
    ''' The unit answered a command with an error, e.g. "ERR 100, unknown command". '''
    pass
 
 
class ID_OSA_Serial:

 
    def __init__(self, port, baudrate=115200, timeout=10.0):
        ''' initializes ID OSA over its USB virtual COM port
            parameters:
                port:     COM port as string, e.g. 'COM5' (see Device Manager -> Ports)
                baudrate: 115200 per the ID OSA manual (8N1)
                timeout:  seconds to wait for a reply before raising TimeoutError.
                          Increase this if you use many scan averages.
        '''
        self.port = port
        self.ser = serial.Serial(port, baudrate=baudrate, bytesize=serial.EIGHTBITS,
                                 parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                                 timeout=timeout)
        self.ser.reset_input_buffer()
        self._xy_supported = None
 
    def close(self):
        if self.ser.is_open:
            self.ser.close()
 
    def __enter__(self):
        return self
 
    def __exit__(self, *exc):
        self.close()
 
    # ------------------------------------------------------------------ settings
 
    def setStartStopFreq(self, start, stop):
        ''' Sets start and stop frequency of the OSA in THz. '''
        # Minimum start freq for ID OSA is 191.25THz
        if start < 191.25:
            start = 191.25
 
        start = "{:.5E}".format(Decimal(str(start * 1e12)))
        stop = "{:.5E}".format(Decimal(str(stop * 1e12)))
        self.writeSCPI("star " + start)
        self.writeSCPI("stop " + stop)
 
    def setCenterSpanFreq(self, center, span):
        ''' Sets Center frequency and span of the OSA in THz. '''
        start = center - span * 1. / 2
        stop = center + span * 1. / 2
        self.setStartStopFreq(start, stop)
 
    def setStartStopWL(self, startWLnm, stopWLnm):
        ''' Sets start and stop wavelength of the OSA in nm. '''
        c = 299792458.0  # speed of light
        start = c / stopWLnm / 1000
        stop = c / startWLnm / 1000
        center = (start + stop) * 1. / 2
        span = stop - start
        self.setCenterSpanFreq(center, span)
 
    def setCenterSpanWL(self, centerWLnm, spanWLnm):
        ''' Sets center wavelength and span of the OSA in nm. '''
        c = 299792458.0  # speed of light
        stopWLnm = centerWLnm + spanWLnm * 1. / 2
        startWLnm = centerWLnm - spanWLnm * 1. / 2
        start = c / stopWLnm / 1000
        stop = c / startWLnm / 1000
        center = (start + stop) * 1. / 2
        span = stop - start
        self.setCenterSpanFreq(center, span)
 
    # ------------------------------------------------------------------ scanning
 
    def getScanNumber(self):
        return self.writeSCPI("numb?")
 
    def triggerScan(self, timeout=60.0):
        ''' Starts a single scan and blocks until the scan number has increased. '''
        num = self.getScanNumber()
        self.writeSCPI("SGL")
        t0 = time.time()
        while self.getScanNumber() == num:
            if time.time() - t0 > timeout:
                raise TimeoutError("Scan did not complete within %.0f s" % timeout)
            time.sleep(0.02)
 
    def getXY(self, form=None, scan_number_at="auto", timeout=60.0):
        ''' Returns an (N, 2) numpy array of (x, power[dB]) from the last scan, sorted by
            ascending x. x is in Hz or m depending on the UNIT:X setting.
            Uses TRAC:XY? when the unit has it. Firmware 1.2.0 does not, so this falls back
            to separate TRAC:XAUTO? and TRAC:Y? reads (form and scan_number_at only matter
            then; see getX()). Note the fallback returns Y in dBm or mW per TRAC:LINL,
            while XY? is always dB. '''
        if self._xy_supported is not False:
            old_timeout = self.ser.timeout
            self.ser.timeout = timeout
            try:
                data = self.writeSCPIBinary("trac:XY?")
                self._xy_supported = True
                arr = numpy.frombuffer(data, dtype='<f4')
                # reshape() returns a new array; assigning to arr.shape is deprecated in recent
                # NumPy. The result is a read-only view on the received bytes, so copy it.
                return arr.reshape(-1, 2).copy()
            except OSAError as err:
                if "ERR 100" not in str(err):
                    raise
                self._xy_supported = False      # unknown command: remember, use the fallback
            finally:
                self.ser.timeout = old_timeout
        xy = self.getXYSeparate(form, True, scan_number_at, timeout)
        return xy[numpy.argsort(xy[:, 0], kind="stable")]
 
    # ------------------------------------------------- separate X and Y vectors
    # For firmware without TRAC:XY?. Manual: sections 7.8.2 (X?, Y?, XAUTO?) and 7.8.3 (FORMat).
 
    _FORMS = {"ascii": "ASCII", "real32": "REAL,32", "real64": "REAL,64"}
 
    def getFormat(self):
        ''' Returns the unit's current data transfer format: "ascii", "real32" or "real64". '''
        answer = self.writeSCPI("form?").strip().upper().replace(" ", "")
        if answer.startswith("ASCII"):
            return "ascii"
        if answer == "REAL,32":
            return "real32"
        if answer in ("REAL,64", "REAL"):      # plain REAL is 64 bit per the manual
            return "real64"
        raise ValueError("Unexpected reply to FORM?: %r" % answer)
 
    def setFormat(self, form):
        ''' Sets the data transfer format used by X? and Y?.
            form: "ascii" (factory default), "real32" or "real64" (binary). '''
        if form not in self._FORMS:
            raise ValueError("form must be one of %s, not %r" % (sorted(self._FORMS), form))
        self.writeSCPI("form " + self._FORMS[form])
 
    def _readVector(self, command, form, timeout):
        ''' Reads one trace vector as a float64 numpy array. '''
        old_timeout = self.ser.timeout
        self.ser.timeout = timeout          # full-length traces can take a while
        try:
            if form is None:
                form = self.getFormat()     # use whatever the unit is set to
            else:
                self.setFormat(form)
            if form == "ascii":
                text = self.writeSCPI(command).strip().strip(",")
                return numpy.array(text.split(","), dtype=float)
            data = self.writeSCPIBinary(command)
            dtype = "<f4" if form == "real32" else "<f8"
            if len(data) % numpy.dtype(dtype).itemsize != 0:
                raise IOError("Binary reply of %d bytes does not fit %s values. Is the format "
                              "really %s?" % (len(data), dtype, form))
            # astype makes a new, writable float64 copy of the read-only buffer view
            return numpy.frombuffer(data, dtype=dtype).astype(numpy.float64)
        finally:
            self.ser.timeout = old_timeout
 
    def _expectedPoints(self):
        ''' Number of data points per trace. TRAC:SNUM? where available; firmware 1.2.0 does
            not have it, so fall back to POIN? (samples per sweep). '''
        try:
            return int(float(self.writeSCPI("trac:snum?")))
        except OSAError as err:
            if "ERR 100" not in str(err):
                raise
        return int(float(self.writeSCPI("poin?")))
 
    def _dropScanNumber(self, vec, scan_number_at):
        ''' The manual (newer firmware) says X? and Y? return one value more than the number of
            points, the extra one being the scan number, without saying at which end. Firmware
            1.2.0 returns exactly the number of points, and then nothing is removed. '''
        if scan_number_at == "none":
            return vec
        n = self._expectedPoints()
        extra = len(vec) - n
        if extra == 0:
            return vec
        if extra != 1:
            raise ValueError("Expected %d or %d values but received %d" % (n, n + 1, len(vec)))
        if scan_number_at == "first":
            return vec[1:]
        if scan_number_at == "last":
            return vec[:-1]
        # "auto": the extra value is the one equal to the current scan number (NUMB?)
        scan = float(self.writeSCPI("numb?"))
        first_is = vec[0] == scan
        last_is = vec[-1] == scan
        if first_is and not last_is:
            return vec[1:]
        if last_is and not first_is:
            return vec[:-1]
        raise ValueError("Could not tell which end holds the scan number. Pass "
                         "scan_number_at='first' or 'last'.")
 
    def getX(self, form=None, auto=False, scan_number_at="auto", timeout=60.0):
        ''' Returns the X axis of the last scan as a numpy array.
            form: None (default) uses the unit's current format (see getFormat()).
                  "ascii", "real32" or "real64" sets that format first. Binary is much faster.
            auto: False reads TRAC:X? (always wavelength in m).
                  True reads TRAC:XAUTO? (m or Hz depending on the UNIT:X setting).
            scan_number_at: "auto" (find it using NUMB?), "first", "last", or "none" to keep it.
            timeout: seconds to wait for the reply. '''
        command = "trac:xauto?" if auto else "trac:x?"
        vec = self._readVector(command, form, timeout)
        return self._dropScanNumber(vec, scan_number_at)
 
    def getY(self, form=None, scan_number_at="auto", timeout=60.0):
        ''' Returns the power data of the last scan as a numpy array (dBm or mW depending on
            TRAC:LINL). Ordered from shortest to longest wavelength. Arguments as in getX(). '''
        vec = self._readVector("trac:y?", form, timeout)
        return self._dropScanNumber(vec, scan_number_at)
 
    def getXYSeparate(self, form=None, auto=False, scan_number_at="auto", timeout=60.0):
        ''' Like getXY(), but built from separate X? and Y? reads, for firmware without XY?.
            Returns an (N, 2) numpy array. '''
        x = self.getX(form, auto, scan_number_at, timeout)
        y = self.getY(form, scan_number_at, timeout)
        if len(x) != len(y):
            raise ValueError("X has %d values but Y has %d" % (len(x), len(y)))
        return numpy.column_stack((x, y))
 
    
    def saveSpectrumCSV(self, filename, trigger=False, form=None, timeout=60.0, retries=3):
        ''' Reads the spectrum the OSA currently holds and writes it to a CSV file.
            Columns: wavelength_nm, frequency_THz, power_dBm (power_mW if TRAC:LINL is LIN).
            Rows are ordered from shortest to longest wavelength, as the unit returns them.
            filename: path of the CSV file; ".csv" is added if it has no extension.
            trigger:  True starts a new single scan first. False (default) saves the last scan
                      the unit has (the scan on its screen / web GUI).
            form:     data transfer format for X? / Y?, see getX(). None uses the current one.
            retries:  if a new scan arrives while X and Y are being read (continuous mode),
                      the two would not match, so the read is repeated up to this many times.
            Returns (path, data) where data is an (N, 3) numpy array of the saved columns. '''
        if not os.path.splitext(filename)[1]:
            filename += ".csv"
        if trigger:
            self.triggerScan()
        x = y = None
        for attempt in range(retries):
            scan_before = self.getScanNumber()
            x = self.getX(form=form, timeout=timeout)       # wavelength in m
            y = self.getY(form=form, timeout=timeout)
            if self.getScanNumber() == scan_before:
                break
            x = y = None                                    # a new scan arrived mid-read
        if x is None:
            raise IOError("The unit kept scanning while the data was read. Stop continuous "
                          "scanning (send SGL for a single scan) and try again.")
        if len(x) != len(y):
            raise ValueError("X has %d values but Y has %d" % (len(x), len(y)))
 
        try:
            scale = self.writeSCPI("trac:linl?").upper()
        except OSAError:
            scale = ""
        power_unit = "mW" if scale.startswith("LIN") else "dBm"
 
        c = 299792458.0                                     # speed of light in m/s
        wavelength_nm = x * 1e9
        frequency_THz = c / x / 1e12
        data = numpy.column_stack((wavelength_nm, frequency_THz, y))
        with open(filename, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["wavelength_nm", "frequency_THz", "power_" + power_unit])
            for row in data:
                writer.writerow(["%.9g" % row[0], "%.9g" % row[1], "%.9g" % row[2]])
        return os.path.abspath(filename), data
 
    def waitOPC(self):
        self.writeSCPI("*wai")
 
    # ------------------------------------------------------------------ low level
 
    def _send(self, commandstr):
        # Discard stale bytes, then send with a single line feed. The manual warns that
        # two terminators (e.g. ";" and LF) cause "ERR 100", so strip any trailing ";".
        self.ser.reset_input_buffer()
        self.ser.write((commandstr.strip().rstrip(";") + "\n").encode("ascii"))
 
    def _read_exact(self, count):
        data = self.ser.read(count)
        if len(data) != count:
            raise TimeoutError("Timed out: got %d of %d bytes from %s"
                               % (len(data), count, self.port))
        return data
 
    def writeSCPI(self, commandstr):
        ''' Sends one SCPI command and returns the reply without its trailing ";". '''
        self._send(commandstr)
        line = self.ser.read_until(b"\n")
        if not line.endswith(b"\n"):
            raise TimeoutError("No reply to %r from %s" % (commandstr, self.port))
        answer = line.decode("ascii", errors="replace").strip()
        if answer.endswith(";"):
            answer = answer[:-1]
        if answer.startswith("ERR"):
            raise OSAError("%s (command: %r)" % (answer, commandstr))
        return answer
 
    def writeSCPIBinary(self, commandstr):
        ''' Sends a command whose reply is an IEEE 488.2 binary block (#<n><len><data>). '''
        self._send(commandstr)
        first = self._read_exact(1)
        if first != b"#":
            # Not a binary block: most likely an error message, e.g. "ERR 250"
            rest = self.ser.read_until(b"\n")
            raise OSAError("Unexpected reply to %r: %r"
                           % (commandstr, (first + rest).decode("ascii", errors="replace").strip()))
        cntcnt = int(self._read_exact(1).decode("ascii"))
        cnt = int(self._read_exact(cntcnt).decode("ascii"))
        data = self._read_exact(cnt)
        self.ser.read_until(b"\n")      # consume the trailing ";" + line ending
        return data
 



class ID_OSA_IP:
    def __init__(self, ip_address):
        ''' initializes ID OSA
            parameters:
                ip_address: IP address as string
        '''
        self.ip_address = ip_address
        self.tcp_port = 2000
        self.socket = socket.socket()
        self.socket.connect((self.ip_address, self.tcp_port))
        self.socket.setblocking(0)

    def setStartStopFreq(self, start, stop):
        ''' Sets start and stop frequency of the OSA in THz. '''
        # center = (start+stop)*1./2
        # span=stop-start
        # self.setCenterSpanFreq(center, span)

        # Minimum start freq for ID OSA is 191.25THz
        if start < 191.25:
            start = 191.25

        start = "{:.5E}".format(Decimal(str(start * 1e12)))
        stop = "{:.5E}".format(Decimal(str(stop * 1e12)))
        # print "start:\t", start
        # print "stop:\t", stop
        self.writeSCPI(str("star "+start))
        self.writeSCPI(str("stop "+stop))
        # print self.writeSCPI("span?")
        # print self.writeSCPI("cent?")

    def setCenterSpanFreq(self, center, span):
        ''' Sets Center frequency and span of the OSA in THz. '''
        start = center - span*1./2
        stop = center + span*1./2
        self.setStartStopFreq(start, stop)

        # center = "{:.5E}".format(Decimal(str(center * 1e12)))
        # span = "{:.5E}".format(Decimal(str(span * 1e12)))
        # self.write(str("span "+span))
        # self.write(str("cent "+center))

    def setStartStopWL(self, startWLnm, stopWLnm):
        ''' Sets start and stop wavelength of the OSA in nm. '''
        c = 299792458.0 #speed of light
        start = c/stopWLnm/1000
        stop = c/startWLnm/1000
        center = (start+stop)*1./2
        span = stop-start
        self.setCenterSpanFreq(center, span)

    def setCenterSpanWL(self, centerWLnm, spanWLnm):
        ''' Sets center wavelength and span of the OSA in nm. '''
        c = 299792458.0 #speed of light
        stopWLnm=centerWLnm+spanWLnm*1./2
        startWLnm=centerWLnm-spanWLnm*1./2
        start = c/stopWLnm/1000
        stop = c/startWLnm/1000
        center = (start+stop)*1./2
        span = stop-start
        self.setCenterSpanFreq(center, span)

    def getScanNumber(self):
        return self.writeSCPI("numb?")

    def triggerScan(self):
        num = self.getScanNumber()
        self.writeSCPI("SGL")
        while self.getScanNumber() != num:
            time.sleep(0.02)

    def getXY(self):
        wave_data = self.writeSCPIBinary("TRAC:X?")
        pwr_data = self.writeSCPIBinary("TRAC:Y?")
        wave_arr = numpy.frombuffer(wave_data, dtype='<f4')
        pwr_arr = numpy.frombuffer(pwr_data, dtype='<f4')
        return numpy.column_stack((wave_arr, pwr_arr))

    def writeSCPI(self, commandstr):
        try:
            self.socket.recv(1024)      # skip possible old bytes (if any)
        except BlockingIOError:
            pass

        commandstr = commandstr + ";"
        #print("TX: >" + commandstr + "<")
        self.socket.sendall(commandstr.encode('utf-8'))
        answer = ''
        while True:
            try:
                answer = answer + self.socket.recv(1024).decode('utf-8').rstrip()
                if answer[len(answer)-1] == ';':
                    break
            except BlockingIOError:
                time.sleep(0.01)
                pass
        #print("RX: >" + answer + "<")
        answer = answer[:-1]        # chop off trailing ";"
        #print("RET:>" + answer + "<")
        return answer

    def writeSCPIBinary(self, commandstr):
        try:
            self.socket.recv(1024)      # skip possible old bytes (if any)
        except BlockingIOError:
            pass

        commandstr = commandstr + ";"
        #print("TX: >" + commandstr + "<")
        self.socket.sendall(commandstr.encode('utf-8'))

        answer = str(self.receiveBytes(1).decode('utf-8'))
        #print("RX0: >" + answer + "<")
        cntcnt = int(self.receiveBytes(1).decode('utf-8'))
        #print("RX1: >" + str(cntcnt) + "<")
        cnt = 0
        for i in range(0, cntcnt):
            cnt = cnt * 10 + int(self.receiveBytes(1).decode('utf-8'))
        #print("Count of bytes in reply: " + str(cnt) + " (cntcnt is " + str(cntcnt) + ")")

        data = self.receiveBytes(cnt + 3)
        data = data[:-3]        # chop off trailing ";\r\n"
        #print(str(len(data)))

        return data

    def waitOPC(self):
        self.writeSCPI("*wai")

    def receiveBytes(self, count):
        answer = bytearray()
        while True:
            try:
                answer1 = bytearray(self.socket.recv(count))
                if len(answer) == 0:
                    answer = answer1
                else:
                    # append
                    for b in answer1:
                        answer.append(b)

                #print("Got " + str(len(answer)) + " bytes, expected " + str(count))

                if len(answer) == count:
                    return answer
            except BlockingIOError:
                time.sleep(0.01)
                pass
