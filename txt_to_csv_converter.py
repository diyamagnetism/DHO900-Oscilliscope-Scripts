import re
import csv
import sys

def convert_log_to_csv(input_file, output_file):
    # Regex to capture: [Timestamp] VRMS = Value TEMP = Value
    # This ignores the header line 
    pattern = re.compile(r'\[(.*?)\] VRMS = ([\d\.]+) V TEMP = ([\d\.]+)')

    try:
        with open(input_file, 'r') as f_in, open(output_file, 'w', newline='') as f_out:
            writer = csv.writer(f_out)
            # Write the header required by your format
            writer.writerow(['Timestamp', 'Temperature', 'Voltage'])

            for line in f_in:
                match = pattern.search(line)
                if match:
                    timestamp = match.group(1)
                    voltage = match.group(2)
                    temperature = match.group(3)
                    
                    # Reordering to match your CSV: Timestamp, Temp, Voltage
                    writer.writerow([timestamp, temperature, voltage])
        
        print(f"Successfully converted '{input_file}' to '{output_file}'")

    except FileNotFoundError:
        print(f"Error: The file '{input_file}' was not found.")

if __name__ == "__main__":
    # You can change these filenames or pass them as arguments
    # input_filename = #input file here
    # output_filename = # output file here
    convert_log_to_csv(input_filename, output_filename)

