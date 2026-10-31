import nidaqmx, numpy as np, matplotlib.pyplot as plt
from nidaqmx.constants import AcquisitionType, TerminalConfiguration

FS = 20000          # Hz, hardware clock
DURATION = 2        # s
N = FS * DURATION

with nidaqmx.Task() as task:
    task.ai_channels.add_ai_voltage_chan(
        "Dev1/ai1", terminal_config=TerminalConfiguration.DEFAULT,
        min_val=-10, max_val=10)
    task.timing.cfg_samp_clk_timing(FS, sample_mode=AcquisitionType.FINITE,
                                    samps_per_chan=N)
    data = np.array(task.read(number_of_samples_per_channel=N, timeout=DURATION + 5))

data = data - data.mean()
spec = np.abs(np.fft.rfft(data * np.hanning(N)))
freqs = np.fft.rfftfreq(N, 1 / FS)

plt.semilogy(freqs, spec)
plt.xlim(0, 1000)
plt.xlabel("Frequency (Hz)")
plt.ylabel("Amplitude (a.u.)")
plt.show()
print("Dominant frequency:", freqs[np.argmax(spec[1:]) + 1], "Hz")