# adapted from https://github.com/mriscoc/Sparrow-Extended-GUI-for-RIGOL-DHO800_DHO900/discussions/12
import pyvisa
import time
import csv
import pandas as pd

CONN = 'TCPIP::localhost::INSTR'

def main():
    try:
        rm = pyvisa.ResourceManager('@py')  # Use pyvisa-py backend
        inst = rm.open_resource(CONN)
        inst.timeout = 5000  # Set timeout to 5 seconds (default, may change since saving a png might be taxing idk)

        # get instrument name
        idn = inst.query(':LAN:DESCription?')
        print(f'Instrument: {idn}')

        inst.write(':MEASure:SOURce CHAN1')
        headers = ['timestamp', 'time elapsed (s)', 'Vavg (V)']
        df = pd.DataFrame(columns = headers)
        df.to_csv('shg_voltage.csv')
       
        start_timestamp, start_time = get_sync_moment()
        start_vavg = get_vavg()

        ultra_sensitive = 0
        for i in range(10000):
            vavg = get_vavg()
            timestamp = time.ctime()
            meas_timestamp, meas_time = get_sync_moment()
            time_elapsed = start_time - meas_time
            row = {'timestamp': meas_timestamp, 
                   'time elapsed (s)': time_elapsed , 
                   'Vavg (V)': vavg}
            write_row(headers, row)

            # discuss exact parameters with quantum team
            if vavg >= 0.5:
                ultra_sensitive = 1
                if vavg >= 0.75:
                    take_photo(timestamp, vavg)
            elif vavg <= 2.00E-8:
                ultra_sensitive = 0.5

            if ultra_sensitive == 1:
                time.sleep(1) 
            if ultra_sensitive == 0.5:
                time.sleep(2)
            else:
                time.sleep(120)

        inst.close()
        rm.close()
    except pyvisa.VisaIOError as e:
        print(f"VISA Error: {e}")
    except Exception as e:
        print(f"Unexpected Error: {e}")

def get_sync_moment():
    # Calling these back-to-back minimizes the execution gap
    wall_time = time.ctime()
    perf_time = time.perf_counter()
    return wall_time, perf_time

def get_vavg():
    vavg = float(inst.query(':MEASure:ITEM? VAVG').strip())
    return vavg

def take_photo(timestamp, vavg):
    photo = inst.write(':SAVE:IMAGe:FORMat PNG')
    photo.save(f'images/{timestamp}_{vavg}V')

def write_row(headers, row):
    with open('shg_voltage.csv', 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writerow(row)
    print(f"Timestamp: {row['timestamp']}; Time elapsed: {row['time elapsed (s)']}; Vavg: {row['Vavg (V)']} V")
    

if __name__ == '__main__':
    main()