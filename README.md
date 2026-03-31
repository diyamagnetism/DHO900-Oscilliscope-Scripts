# DHO900 Oscilliscope Scripts

This repository is designed to read out and analyze second harmonic generation data from a DHO900 Oscilliscope.


## Usage

### voltage_reader.py 

### Read_Data.py

### TC300B_xml_file_writer

1. From the github download TC300B_xml_file_writer.py onto your local computer
2. Write out settings for the temperature steps at the bottom of the file. There is a helper function 'generate_steps', or you can write your own custom steps
3. After the file is created, store in the directory temp_xml. 
    a) I recommend making the file on your personal computer then adding the file to the github folder temp_xmls rather than editing TC300B_xml_file_writer.xml directly on the lab desktop, but thats not strictly necessary
4. On the lab desktop, download the xml file into the TEC settings folder
5. Open the TC300B application on the lab desktop
6. Click the button that is two circular arrows
7. Click the Load button and find your xml file. Click on the file
8. The table should be filled with the values you set for your xml file. 
9. Run the file on the TC300B!



