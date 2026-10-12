
"""
Probe which SCPI query commands an ID Photonics ID OSA supports over its USB serial port.

Why: the manual (v2.1.0) lists commands, but older firmware (e.g. 1.2.0) may lack some.
An unsupported command returns "ERR 100, unknown command".

Safe by design: only QUERY commands (ending in "?") are sent, so no setting is changed.
The command list comes from the ID OSA manual, section 7 (the page of each is shown).

Usage:
    pip install pyserial
    python probe_osa_commands.py COM5
    python probe_osa_commands.py COM5 --out my_results.csv

Close PuTTY or any other program using the COM port first.
"""
import argparse
import csv
import re
import sys
import time

import serial
from serial.tools import list_ports

# (manual page, short form, long form). Each is tried in the short form first, then the
# long form, since the manual says either is accepted. Optional prefix levels such as
# "[:SENSe:SWEep:]" are left out, as the manual permits.
COMMANDS = [
    (27, "*IDN?", "*IDN?"),
    (28, "*OPC?", "*OPC?"),
    (28, "INFO?", "INFOrmation?"),
    (28, "ECHO?", "ECHO?"),
    (29, "DHCP?", "DHCP?"),
    (29, "IPADDR?", "IPADDRess?"),
    (29, "NETMASK?", "NETMASK?"),
    (30, "GATEWAYIP?", "GATEWAYIP?"),
    (30, "DNSIP?", "DNSIP?"),
    (30, "MACADDRESS?", "MACADDRESS?"),
    (30, "IPCCH?", "IPConfigCHanged?"),
    (30, "USBIPADDR?", "USBIPADDRess?"),
    (30, "USBNETMASK?", "USBNETMASK?"),
    (31, "REMO?", "REMOte?"),
    (31, "PASS?", "PASSword?"),
    (31, "TIME?", "TIME?"),
    (31, "ALAR?", "ALARm?"),
    (32, "ERR?", "ERRor?"),
    (32, "FAN?", "FAN?"),
    (32, "COMM:LOCK?", "COMMunicate:LOCKout?"),
    (32, "COMM:PREF?", "COMMunicate:ParameterREFresh?"),
    (33, "NUMB?", "NUMBer?"),
    (34, "LEV:SHIF?", "LEVel:SHIFt?"),
    (34, "LEV:SPECCAL:Y?", "LEVel:SPECtralCALibration:Y?"),
    (34, "LEV:SPECCAL:ENA?", "LEVel:SPECtralCALibration:ENAble?"),
    (35, "WAV:SHIF?", "WAVelength:SHIFt?"),
    (35, "POIN?", "POINts?"),
    (35, "POIN:AUTO?", "POINts:AUTO?"),
    (36, "MAXPOIN?", "MAXPOINts?"),
    (36, "INT?", "INTerval?"),
    (36, "CENT?", "CENTer?"),
    (37, "SPAN?", "SPAN?"),
    (37, "STAR?", "STARt?"),
    (37, "STOP?", "STOP?"),
    (38, "MINSTAR?", "MINSTARt?"),
    (38, "MAXSTOP?", "MAXSTOP?"),
    (38, "INPU?", "INPUt?"),
    (38, "STEP?", "STEP?"),
    (39, "STEP:FREQ?", "STEP:FREQuency?"),
    (39, "MINSTEP?", "MINSTEP?"),
    (39, "MAXSTEP?", "MAXSTEP?"),
    (40, "TRIPOL?", "TRIggerPOLarity?"),
    (40, "AVER:COUN?", "AVERage:COUNt?"),
    (40, "AVER:CURCOUN?", "AVERage:CURrentCOUNt?"),
    (41, "AVER:SCANCOUN?", "AVERage:SCANCOUNt?"),
    (41, "AVER:CURSCANCOUN?", "AVERage:CURrentSCANCOUNt?"),
    (41, "TRIDEL?", "TRIggerDELay?"),
    (42, "TRAC:SNUM?", "TRACe:DATA:SNUMber?"),
    (42, "TRAC:X?", "TRACe:DATA:X?"),
    (42, "TRAC:XAUTO?", "TRACe:DATA:XAUTO?"),
    (43, "TRAC:Y?", "TRACe:DATA:Y?"),
    (43, "TRAC:LINL?", "TRACe:DATA:LINLog?"),
    (43, "TRAC:XY?", "TRACe:DATA:XY?"),
    (44, "POW?", "POWer?"),
    (44, "PKHL?", "PeaKHoLD?"),
    (44, "RDY?", "ReaDY?"),
    (44, "FORM?", "FORMat?"),
    (45, "SMOD?", "SMODe?"),
    (46, "UNIT:X?", "UNIT:X?"),
    (46, "CALC:CAT?", "CALCulate:CATegory?"),
    (47, "CALC:DATA?", "CALCulate:DATA?"),
    (47, "CALC:DATA:CPOW?", "CALCulate:DATA:CPOWers?"),
    (47, "CALC:DATA:CSNR?", "CALCulate:DATA:CSNR?"),
    (47, "CALC:DATA:NCH?", "CALCulate:DATA:NCHannels?"),
    (47, "CALC:DATA:CWAV?", "CALCulate:DATA:CWAVelengths?"),
    (47, "CALC:PAR:WDM:TH?", "CALCulate:PARameter:WDM:TH?"),
    (48, "CALC:PAR:WDM:MDIF?", "CALCulate:PARameter:WDM:MDIFf?"),
    (48, "CALC:PAR:WDM:MAR?", "CALCulate:PARameter:WDM:MARea?"),
    (48, "CALC:PAR:WDM:MDIST?", "CALCulate:PARameter:WDM:MinDIST?"),
    (49, "CALC:PAR:WDM:POWINT?", "CALCulate:PARameter:WDM:POWerINTegrate?"),
]

ERR_RE = re.compile(rb"ERR\s*(\d+)")


def read_reply(ser, first_wait=3.0, idle=0.4, max_total=30.0):
    """Read one reply. Returns bytes, or None if nothing arrived."""
    ser.timeout = first_wait
    first = ser.read(1)
    if not first:
        return None
    buf = bytearray(first)
    ser.timeout = idle
    t0 = time.time()
    while time.time() - t0 < max_total:
        # Text replies end with ";" + line feed: stop right away (not for binary blocks).
        if not buf.startswith(b"#") and (buf.endswith(b";\n") or buf.endswith(b";\r\n")):
            break
        chunk = ser.read(max(1, ser.in_waiting))
        if not chunk:
            break
        buf += chunk
    return bytes(buf)


def send_query(ser, cmd):
    """Send one query with a single LF terminator and return (status, preview)."""
    if not cmd.endswith("?"):
        raise ValueError("Refusing to send non-query command: %r" % cmd)
    ser.reset_input_buffer()
    ser.write((cmd + "\n").encode("ascii"))
    reply = read_reply(ser)
    if reply is None:
        return "NOREPLY", ""
    head = reply[:200]
    m = ERR_RE.search(head) if not reply.startswith(b"#") else None
    preview = head[:60].decode("ascii", errors="replace").replace("\r", " ").replace("\n", " ").strip()
    if len(reply) > 60:
        preview += "... (%d bytes)" % len(reply)
    if m:
        return "ERR %s" % m.group(1).decode(), preview
    return "OK", preview


def probe(ser):
    results = []
    for page, short, long_ in COMMANDS:
        status, preview = send_query(ser, short)
        used = short
        verdict = None
        if status == "OK":
            verdict = "SUPPORTED"
        elif status == "ERR 100":
            if long_ != short:
                status2, preview2 = send_query(ser, long_)
                if status2 == "OK":
                    verdict, used, status, preview = "SUPPORTED (long form only)", long_, status2, preview2
                elif status2 != "ERR 100":
                    status, preview, used = status2, preview2, long_
            if verdict is None and status == "ERR 100":
                verdict = "NOT SUPPORTED"
        elif status == "NOREPLY":
            verdict = "NO REPLY"
        if verdict is None:
            verdict = "OTHER (%s)" % status
        results.append((page, short, long_, used, verdict, preview))
        print("p%-3d %-22s %-26s %s" % (page, short, verdict, preview[:50]))
        sys.stdout.flush()
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("port", nargs="?", help="COM port, e.g. COM5")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--out", default="osa_probe_results.csv", help="CSV file to write")
    args = ap.parse_args()

    if not args.port:
        print("Available serial ports:")
        for dev, desc in [(p.device, p.description) for p in list_ports.comports()]:
            print("  %s  %s" % (dev, desc))
        print("\nRun again with the port, e.g.:  python probe_osa_commands.py COM5")
        return

    with serial.Serial(args.port, args.baud, bytesize=8, parity="N", stopbits=1, timeout=3) as ser:
        status, idn = send_query(ser, "*IDN?")
        if status != "OK":
            print("No valid reply to *IDN? (%s). Check the COM port, baud rate and that no other "
                  "program (PuTTY) is using it." % status)
            sys.exit(1)
        print("Connected: %s\n" % idn)
        results = probe(ser)

    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["manual_page", "short_form", "long_form", "form_used", "result", "reply_preview"])
        w.writerows(results)

    ok = [r for r in results if r[4].startswith("SUPPORTED")]
    bad = [r for r in results if r[4] == "NOT SUPPORTED"]
    other = [r for r in results if r not in ok and r not in bad]
    print("\nSupported: %d   Not supported: %d   Other/no reply: %d   (of %d)"
          % (len(ok), len(bad), len(other), len(results)))
    if bad:
        print("\nNot supported on this firmware:")
        for r in bad:
            print("  %-22s (manual p.%d)" % (r[1], r[0]))
    if other:
        print("\nInconclusive:")
        for r in other:
            print("  %-22s %s" % (r[1], r[4]))
    print("\nFull results saved to %s" % args.out)


if __name__ == "__main__":
    main()