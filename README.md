# DHO900 Oscilloscope Scripts

This repository contains lab scripts for working with the Rigol `DHO900` series oscilloscope, especially the `DHO924`.

The newest addition is a USB-based delay-measurement tool for `1PPS` signals:
- it connects to the scope over `USB-TMC`
- triggers on `CH1`
- captures the same pulse on `CH1` and `CH2`
- timestamps each channel's arrival
- records the delay `CH2 - CH1`
- stores both the scope's built-in delay measurement and the Python-computed delay

This is useful for White Rabbit timing experiments where the main goal is not just to save a screenshot or a random waveform, but to measure how late `CH2` arrives relative to `CH1`.

## What "VISA" Means

`VISA` stands for `Virtual Instrument Software Architecture`.

In practice, it is just the resource naming system used by instrument-control software such as `PyVISA`, `NI-VISA`, and `pyvisa-py`.

Examples:
- `USB0::0x1AB1::0x044C::DHO9A254401412::INSTR`
- `TCPIP0::192.168.1.50::INSTR`

For this workflow, the important point is:
- `USB` control does not depend on `DHCP`
- `DHCP`, `Auto IP`, and `Static IP` are `LAN` settings
- the scope can still work over `USB-TMC` even if the front-panel VISA field shows an incomplete LAN-style string such as `TCPIP:::INSTR`

## What Was Learned During Setup

These points were confirmed while bringing the lab scope online:

- The DHO924 can be controlled directly from Python over `USB-TMC`.
- The working Windows driver on this machine showed up as `WinUSB` with provider `libwdi`.
- `pyvisa-py` successfully found and opened the scope even when vendor VISA resource discovery did not.
- `Ultra Sigma` can be useful for first-time testing, but it is not required for the final measurement workflow.
- The signal-processing goal is to wait for the `CH1` trigger, then measure when `CH2` arrives relative to `CH1`.
- Arrival time is measured at `50%` of each channel's excursion away from its local baseline by default.

## Files in This Repo

### New delay-measurement script

- `pulse_delay_capture.py`

This is the main script for USB connection testing and pulse delay capture.

It supports:
- `doctor`: check whether Windows and PyVISA can see the scope
- `idn`: query `*IDN?`
- `screenshot`: save the current display as a PNG
- `waveform`: download one or more displayed channels as CSV
- `pulse-capture`: trigger on `CH1`, capture `CH1` and `CH2`, and compute `CH2 - CH1`

### Older repo files

The repository also contains older scripts and notebooks, including:
- `voltage_reader.py`
- `Read_Data.py`
- `TC300B_xml_file_writer.py`
- several analysis notebooks

Those files are still available, but `pulse_delay_capture.py` is the recommended starting point for USB-based timing work on the DHO924.

## Easy Setup

### 1. Clone the repository

```powershell
git clone https://github.com/diyamagnetism/DHO900-Oscilliscope-Scripts.git
cd DHO900-Oscilliscope-Scripts
```

### 2. Create the conda environment

```powershell
conda env create -f environment.yml
conda activate qlats
```

The environment file installs:
- `numpy`
- `scipy`
- `pandas`
- `matplotlib`
- `pyvisa`
- `pyvisa-py`

### 3. Connect the scope correctly

Use the cable that came with the scope and connect:
- the scope's rear `USB DEVICE` port
- to the PC's normal `USB HOST` port

Do not use a front or rear `USB HOST` port on the scope for remote control.

### 4. Turn the scope on

Once the scope is on, Windows should eventually see it as a DHO924 USB device.

### 5. Run the connection doctor

```powershell
python pulse_delay_capture.py doctor
```

On a working setup, you should see something like:
- Windows sees `DHO924`
- `pyvisa-py` finds a USB resource
- `*IDN?` succeeds

## How to Tell If USB Is Really Working

The fastest check is:

```powershell
python pulse_delay_capture.py doctor
```

A good result looks like:
- `DHO924 | status=OK | present=True`
- `service=WinUSB`
- `provider=libwdi`
- a USB VISA resource is listed
- `*IDN?` returns a Rigol identity string

If that happens, Python control is working even if:
- the scope still shows `TCPIP:::INSTR`
- `Ultra Sigma` does not list the device cleanly

## Basic Usage

### Check the connection

```powershell
python pulse_delay_capture.py doctor
```

### Query the identity string

```powershell
python pulse_delay_capture.py idn
```

### Save a screenshot

```powershell
python pulse_delay_capture.py screenshot
```

### Save CH1 as a CSV waveform

```powershell
python pulse_delay_capture.py waveform --channel 1 --filename waveform_ch1.csv
```

### Save CH1 and CH2 in one command

```powershell
python pulse_delay_capture.py waveform --both
```

## Main Delay-Measurement Workflow

This is the command that matches the White Rabbit use case:

```powershell
python pulse_delay_capture.py pulse-capture --captures 10 --trigger-channel 1 --measure-channel 2
```

What it does:
1. Puts the scope into a trigger-friendly running state.
2. Sets a coarse horizontal scale first so trigger setup works reliably.
3. Sets edge trigger source, slope, mode, level, and holdoff.
4. Zooms into the final edge-timing window.
5. Waits for a pulse on `CH1`.
6. Captures both `CH1` and `CH2` for that same event.
7. Finds the arrival time of each channel.
8. Computes `CH2 - CH1`.
9. Saves all of the data to disk.

### Current lab defaults baked into the script

The default `pulse-capture` settings now match the measurement procedure used at the scope:
- trigger source defaults to `CH1`
- trigger slope defaults to `NEGative` for a downward pulse/dip
- trigger holdoff defaults to `0.8 s`
- coarse setup time scale defaults to `100 us/div`
- final timing time scale defaults to `100 ns/div`
- `CH1` vertical scale defaults to `2 V/div`
- `CH2` vertical scale defaults to `1 V/div`

That `CH2` default is just the starting point. Because the present lab setup uses a `50 ohm` terminator on `CH2`, that pulse can be much smaller than `CH1`.

To handle that automatically, `pulse-capture` now does a warm-up capture by default and then tightens each channel's vertical scale before the real measurement run starts.

Important CH2 behavior:
- `CH2` is allowed to auto-scale down more aggressively than the other channels
- the default `CH2` minimum auto-scale is `20 mV/div`
- this makes it much more likely that the scope can clearly see the terminated pulse and return a valid delay measurement

If you want to disable that warm-up step, use:

```powershell
python pulse_delay_capture.py pulse-capture --no-auto-scale
```

If you want to make `CH2` even more sensitive, you can lower its minimum allowed scale:

```powershell
python pulse_delay_capture.py pulse-capture --ch2-min-scale 0.01
```

### Default timing rule

By default, the arrival time of each channel is measured at:
- `50% of that channel's excursion away from its local baseline for that capture`

This means:
- the script first decides whether each captured pulse is predominantly rising or falling
- `CH1` is timestamped at the first corresponding `50%` crossing for that pulse
- `CH2` is timestamped at the first corresponding `50%` crossing for that pulse

This matters because the two channels do not always look identical. One channel may be a large ringing pulse while the other is a much smaller positive step, especially when a `50 ohm` terminator is attached.

If you ever want to override that and use a fixed threshold instead, you can do:

```powershell
python pulse_delay_capture.py pulse-capture --captures 10 --edge-threshold 1.5
```

## Output Files

During `pulse-capture`, the script writes:

- one waveform CSV per pulse per channel
  - example: `pulse_0000_ch1.csv`
  - example: `pulse_0000_ch2.csv`
- one summary CSV
  - example: `pulse_summary.csv`
- one metadata JSON
  - example: `pulse_metadata.json`

If `--screenshot-each` is enabled, it also writes:
- one screenshot PNG per capture

## What Is In the Summary CSV

The summary CSV contains one row per trigger event.

Important columns include:
- `ch1_arrival_s`
- `ch2_arrival_s`
- `scope_delay_s`
- `scope_delay_ns`
- `scope_delay_ps`
- `ch2_minus_ch1_delay_s`
- `ch2_minus_ch1_delay_ns`
- `ch2_minus_ch1_delay_ps`

It also records extra waveform context:
- min voltage
- max voltage
- peak-to-peak voltage
- threshold used for timing

## What Is In the Metadata JSON

The metadata file records:
- the scope identity string
- the resource string used
- trigger settings
- time scale
- voltage scale
- capture count
- delay statistics for the whole run

The delay statistics include:
- mean delay
- standard deviation
- min delay
- max delay
- peak-to-peak delay

## Matching the Manual Scope Procedure

When the measurement is done by hand, the process is usually:
- run the scope
- use a faster horizontal scale such as `1 ms/div` or `100 us/div`
- set trigger type to `Edge`
- set the trigger source to the Alice channel
- choose the falling edge when the pulse is a downward dip
- set trigger mode to `Normal`
- set the trigger level to about halfway through the pulse
- set holdoff to about `800 ms`
- zoom into the edge timing window, for example `1 us/div`, `100 ns/div`, or `20 ns/div`
- use `Measure -> Delay(f-f)` with Alice as source A and Bob as source B

`pulse_delay_capture.py` automates the same measurement intent, but instead of relying on the scope's on-screen measurement menu, it downloads the captured waveforms and computes the arrival times and delay directly in Python.
It also queries the scope's own built-in `Delay(f-f)` or `Delay(r-r)` measurement when available, so you can compare the scope-reported value with the Python-computed value.

## Recommended First Real Test

Once USB is working, a good first test is:

```powershell
python pulse_delay_capture.py pulse-capture --captures 3 --trigger-channel 1 --measure-channel 2 --screenshot-each
```

That gives you:
- a few waveform CSVs
- screenshots for visual confirmation
- a summary table showing the measured delay

## Helpful Knobs to Tune

If your pulse is not captured well, these are the most useful parameters:

- `--trigger-level`
  - the voltage used by the scope trigger on `CH1`
- `--time-scale`
  - seconds per division on the horizontal axis
- `--ch1-scale`
  - starting volts per division for `CH1`
- `--ch2-scale`
  - starting volts per division for `CH2`
- `--ch2-min-scale`
  - smallest volts/div the auto-scaler may choose for the smaller terminated `CH2` pulse
- `--no-auto-scale`
  - disables the warm-up auto-scaling pass if you want fixed manual scales
- `--trigger-timeout`
  - how long the script waits for the next pulse
- `--trigger-holdoff`
  - helps prevent retriggering on noise after the main edge

Example:

```powershell
python pulse_delay_capture.py pulse-capture --captures 10 --trigger-level 1.5 --time-scale 100e-9 --ch1-scale 2.0 --ch2-scale 1.0 --ch2-min-scale 0.02
```

## If Something Goes Wrong

### Case 1: Windows does not see the scope

Check:
- cable is plugged into the rear `USB DEVICE` port on the scope
- scope is powered on
- cable is seated well
- try a direct USB port instead of a hub

### Case 2: Windows sees the scope but the script does not

Run:

```powershell
python pulse_delay_capture.py doctor
```

If Windows sees `DHO924` and `pyvisa-py` finds a USB resource, you are close.

### Case 3: Ultra Sigma is unhelpful

That does not automatically mean the Python setup is broken.

This script can work even when:
- Ultra Sigma hangs
- Ultra Sigma does not list the USB-TMC device cleanly
- vendor VISA does not enumerate the resource

### Case 4: Delay cannot be computed

That usually means one of the edges was not found.

Try:
- adjusting `--time-scale`
- adjusting `--ch1-scale` and `--ch2-scale`
- allowing the warm-up auto-scaler to shrink `CH2` further with `--ch2-min-scale`
- checking whether both channels are actually displaying the pulse clearly
- using a fixed `--edge-threshold` if the pulse shape is unusual

## Contributing

If you have direct write access to the lab repository, create a branch and push it normally.

If you do not have direct write access:
1. Fork the repository to your own GitHub account.
2. Create a branch in your fork.
3. Push your changes there.
4. Open a pull request back into the lab repository's `main` branch.

Because the repository is public:
- anyone can read it
- anyone can clone it
- anyone can fork it
- only approved maintainers can push directly to the lab repo

## Existing Scripts

For completeness, the repo still includes older tools for other workflows:

- `voltage_reader.py`: older scope readout experiment script
- `Read_Data.py`: older parsing/plotting helper
- `TC300B_xml_file_writer.py`: TEC XML settings writer

Those scripts are not replaced by this README, but the recommended USB timing workflow for DHO924 1PPS measurements is now `pulse_delay_capture.py`.
