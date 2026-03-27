"""
TC300B XML Generator
Generates XML configuration files for the TC300B temperature controller.
"""
 
import xml.etree.ElementTree as ET
from xml.dom import minidom
 
 
def generate_steps(start_temp, end_temp, ramp_time, hold_time, step_size=1):
    """
    Generate a list of step dictionaries from start_temp to end_temp.
 
    Args:
        start_temp (float): Starting temperature.
        end_temp (float): Ending temperature (inclusive).
        ramp_time (int): Ramp time for each step (seconds).
        hold_time (int): Hold time for each step (seconds).
        step_size (float): Temperature increment per step (default 1).
 
    Returns:
        List of step dicts with keys: RampTime, HoldTime, Temperature.
    """
    steps = []
    temp = start_temp
    while (step_size > 0 and temp <= end_temp) or (step_size < 0 and temp >= end_temp):
        steps.append({
            "RampTime": ramp_time,
            "HoldTime": hold_time,
            "Temperature": int(temp) if float(temp).is_integer() else round(temp, 2),
        })
        temp = round(temp + step_size, 10)
    return steps
 
 
def generate_tc300b_xml(
    # Output file path
    output_path="tc300b_output.xml",
    
    # Channel 1 settings
    ch1_enabled=True,
    ch1_target_temp=160.0,
    ch1_target_curr=100,
    ch1_pid_p=0.16,
    ch1_pid_i=10.30,
    ch1_pid_d=2.57,
 
    # Channel 2 settings
    ch2_enabled=False,
    ch2_target_temp=90.0,
    ch2_target_curr=100,
    ch2_pid_p=0.06,
    ch2_pid_i=16.75,
    ch2_pid_d=4.18,
 
    # Sequence settings
    is_cycle_mode=False,
    cycle_number=1,
 
    # Channel 1 cycle steps (list of dicts or use ramp shorthand below)
    ch1_steps=None,
    ch1_start_temp=180,
    ch1_end_temp=200,
    ch1_ramp_time=1,
    ch1_hold_time=6,
    ch1_step_size=1,
 
    # Channel 2 cycle steps
    ch2_steps=None,
    ch2_num_blank_steps=5,
 
    # Options
    brightness=50,
    is_dark_mode=False,
    is_quiet_mode=False,
 
):
    """
    Generate a TC300B XML configuration file.
 
    Channel steps can be provided explicitly as a list of dicts:
        [{"RampTime": 1, "HoldTime": 6, "Temperature": 180}, ...]
 
    Or auto-generated from a temperature ramp using:
        ch1_start_temp, ch1_end_temp, ch1_ramp_time, ch1_hold_time, ch1_step_size
    """
    #-----checking for errors----
    if (ch1_end_temp - ch1_start_temp) * (ch1_step_size) < 0:
        raise Exception("Direction of Ch1 Temperature change does not match step direction")
    
    if (ch1_end_temp > 200) | (ch1_start_temp > 200):
        raise Exception("Ch1 Temperature higher than max oven temp")



    # --- Build step lists ---
    if ch1_steps is None:
        ch1_steps = generate_steps(ch1_start_temp, ch1_end_temp, ch1_ramp_time, ch1_hold_time, ch1_step_size)
 
    if ch2_steps is None:
        ch2_steps = [{"RampTime": 0, "HoldTime": 0, "Temperature": 0}] * ch2_num_blank_steps
 
    # --- Root ---
    root = ET.Element("TC300B")
 
    # --- Settings ---
    settings = ET.SubElement(root, "Settings")
    ET.SubElement(settings, "Channel1",
        IsChEnabled=str(ch1_enabled),
        TargetTemp=f"{ch1_target_temp:.1f}",
        TargetCurr=str(ch1_target_curr),
        ModeIdx="0",
        PidP=f"{ch1_pid_p:.2f}",
        PidI=f"{ch1_pid_i:.2f}",
        PidD=f"{ch1_pid_d:.2f}",
        PidPeriod="100",
        IsTrigOut="True",
        DirectionIdx="1",
    )
    ET.SubElement(settings, "Channel2",
        IsChEnabled=str(ch2_enabled),
        TargetTemp=f"{ch2_target_temp:.3f}",
        TargetCurr=str(ch2_target_curr),
        ModeIdx="0",
        PidP=f"{ch2_pid_p:.2f}",
        PidI=f"{ch2_pid_i:.2f}",
        PidD=f"{ch2_pid_d:.2f}",
        PidPeriod="100",
        IsTrigOut="True",
        DirectionIdx="1",
    )
 
    # --- Sequence ---
    ET.SubElement(root, "Sequence",
        IsCycleMode=str(is_cycle_mode),
        CycleNumber=str(cycle_number),
    )
 
    # --- Cycle ---
    cycle = ET.SubElement(root, "Cycle")
 
    ch1_cycle = ET.SubElement(cycle, "Channel1",
        CycleNumber=str(cycle_number),
        StepNumber=str(len(ch1_steps)),
    )
    for i, step in enumerate(ch1_steps):
        ET.SubElement(ch1_cycle, "Step",
            Index=str(i),
            RampTime=str(step["RampTime"]),
            HoldTime=str(step["HoldTime"]),
            Temperature=str(step["Temperature"]),
        )
 
    ch2_cycle = ET.SubElement(cycle, "Channel2",
        CycleNumber=str(cycle_number),
        StepNumber=str(len(ch2_steps)),
    )
    for i, step in enumerate(ch2_steps):
        ET.SubElement(ch2_cycle, "Step",
            Index=str(i),
            RampTime=str(step["RampTime"]),
            HoldTime=str(step["HoldTime"]),
            Temperature=str(step["Temperature"]),
        )
 
    # --- Options ---
    ET.SubElement(root, "Options",
        Brightness=str(brightness),
        IsDarkMode=str(is_dark_mode),
        IsQuietMode=str(is_quiet_mode),
        Ch1SensorTypeIdx="2", Ch1SensorParamTypeIdx="4", Ch1NtcBValue="3976",
        Ch1ExtBValue="3988", Ch1T0Value="25", Ch1R0Value="10",
        Ch1HartA="1", Ch1HartB="1", Ch1HartC="1",
        Ch1MinTemprature="0", Ch1MaxTemprature="200",
        Ch1MaxCurrent="0.54", Ch1MaxVoltage="24.00", Ch1Offset="0.00",
        Ch1NTCHighAccuracyState="0",
        Ch2SensorTypeIdx="2", Ch2SensorParamTypeIdx="4", Ch2NtcBValue="3976",
        Ch2ExtBValue="3988", Ch2T0Value="25", Ch2R0Value="10",
        Ch2HartA="1", Ch2HartB="1", Ch2HartC="1",
        Ch2MinTemprature="0", Ch2MaxTemprature="200",
        Ch2MaxCurrent="2.00", Ch2MaxVoltage="24.00", Ch2Offset="0.00",
        Ch2NTCHighAccuracyState="1",
    )
 
    # --- Pretty-print and write ---
    raw = ET.tostring(root, encoding="unicode")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ")
    # Remove the extra <?xml?> declaration line minidom adds
    lines = pretty.split("\n")
    pretty_clean = "\n".join(lines[1:])  # strip first line (<?xml version...?>)
 
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(pretty_clean)
 
    print(f"XML written to: {output_path}")
    return output_path
 
 
# =============================================================================
# Example usage — edit these values to suit your experiment
# =============================================================================
if __name__ == "__main__":
 
    # # --- Example 1: Simple linear ramp (auto-generated steps) ---
    # generate_tc300b_xml(
    #     output_path="tc300b_ramp_180_to_200.xml",
    #     ch1_start_temp=180,
    #     ch1_end_temp=200,
    #     ch1_ramp_time=1,
    #     ch1_hold_time=6,
    #     ch1_step_size=1,
    #     ch2_num_blank_steps=5,
    # )
 
    # # --- Example 2: Custom steps with varying ramp/hold times ---
    # custom_steps = [
    #     {"RampTime": 5,  "HoldTime": 30, "Temperature": 100},
    #     {"RampTime": 10, "HoldTime": 60, "Temperature": 150},
    #     {"RampTime": 10, "HoldTime": 120, "Temperature": 200},
    #     {"RampTime": 5,  "HoldTime": 30, "Temperature": 180},
    # ]
    # generate_tc300b_xml(
    #     ch1_steps=custom_steps,
    #     ch1_target_temp=200.0,
    #     ch2_num_blank_steps=5,
    #     output_path="tc300b_custom_steps.xml",
    # )
 
    # Now I will try to reproduce the 5 xml files and check the accuracy
    generate_tc300b_xml(
        output_path="temp_xmls/tc300b_ramp_120_to_200.xml",
        ch1_start_temp=120,
        ch1_end_temp=200,
        ch1_ramp_time=1,
        ch1_hold_time=9,
        ch1_step_size=1,
        ch2_num_blank_steps=5,
    )
    generate_tc300b_xml(
        output_path="temp_xmls/tc300b_ramp_140_to_200.xml",
        ch1_start_temp=140,
        ch1_end_temp=200,
        ch1_ramp_time=1,
        ch1_hold_time=9,
        ch1_step_size=1,
        ch2_num_blank_steps=5,
    )
    generate_tc300b_xml(
        output_path="temp_xmls/tc300b_ramp_160_to_200.xml",
        ch1_start_temp=160,
        ch1_end_temp=200,
        ch1_ramp_time=1,
        ch1_hold_time=9,
        ch1_step_size=1,
        ch2_num_blank_steps=5,
    )
    generate_tc300b_xml(
        output_path="temp_xmls/tc300b_ramp_180_to_200.xml",
        ch1_start_temp=180,
        ch1_end_temp=200,
        ch1_ramp_time=1,
        ch1_hold_time=9,
        ch1_step_size=1,
        ch2_num_blank_steps=5,
    )

    # # test if it can handle conflicting info
    # generate_tc300b_xml(
    #     output_path="temp_xmls/tc300b_ramp_140_to_200.xml",
    #     ch1_start_temp=240,
    #     ch1_end_temp=200,
    #     ch1_ramp_time=1,
    #     ch1_hold_time=9,
    #     ch1_step_size=1,
    #     ch2_num_blank_steps=5,
    # )