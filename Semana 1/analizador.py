"""Analizador en tiempo real: señal en el tiempo y espectro FFT.

Captura audio del microfono (fs = 16000 Hz, bloques de N = 1024 muestras),
muestra la señal en ms y el espectro con y sin ventana de Hamming, y marca
la frecuencia del pico dominante.
"""
import numpy as np
import sounddevice as sd
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import queue
import sys
import argparse

FS = 16000
N = 1024
UMBRAL = 0.002     # magnitud lineal minima para considerar que hay señal
USAR_DB = True     # True: espectro en dB, False: magnitud lineal
DB_MIN = -130      # piso del espectro en dB (microfono en silencio ~ -110 dB)
LIM_MIN = 0.005    # amplitud minima del eje de la señal en el tiempo
lim_t = LIM_MIN
DELTA_F = FS / N
T_VENTANA = N / FS * 1000
t = np.arange(N) / FS * 1000
freqs = np.fft.rfftfreq(N, d=1/FS)
w = np.hamming(N)

def int_or_str(text):
    """Helper function for argument parsing."""
    try:
        return int(text)
    except ValueError:
        return text


parser = argparse.ArgumentParser(add_help=False)
parser.add_argument(
    '-l', '--list-devices', action='store_true',
    help='show list of audio devices and exit')
args, remaining = parser.parse_known_args()
if args.list_devices:
    print(sd.query_devices())
    parser.exit(0)
parser = argparse.ArgumentParser(
    description=__doc__,
    formatter_class=argparse.RawDescriptionHelpFormatter,
    parents=[parser])
parser.add_argument(
    '-d', '--device', type=int_or_str,
    help='input device (numeric ID or substring)')
parser.add_argument(
    '-i', '--interval', type=float, default=30,
    help='minimum time between plot updates (default: %(default)s ms)')
args = parser.parse_args(remaining)
q = queue.Queue()


def calcular_espectro(x):
    mag_rect = np.abs(np.fft.rfft(x)) / N
    mag_ham = np.abs(np.fft.rfft(x * w)) / np.sum(w)

    idx = np.argmax(mag_ham[1:]) + 1
    f_pico = freqs[idx] if mag_ham[idx] >= UMBRAL else None

    if USAR_DB:
        mag_rect = 20 * np.log10(mag_rect + 1e-12)
        mag_ham = 20 * np.log10(mag_ham + 1e-12)

    return mag_rect, mag_ham, f_pico, mag_ham[idx]


def audio_callback(indata, frames, time, status):
    """This is called (from a separate thread) for each audio block."""
    if status:
        print(status, file=sys.stderr)
    q.put(indata[:, 0].copy())


def update_plot(frame):
    """Usa el bloque mas reciente de la cola; descarta los anteriores."""
    x = None
    while True:
        try:
            x = q.get_nowait()
        except queue.Empty:
            break
    if x is None:
        return artistas

    global lim_t
    pico_t = float(np.max(np.abs(x)))
    lim_t = min(1.0, max(LIM_MIN, 1.2 * pico_t, 0.9 * lim_t))
    ax1.set_ylim(-lim_t, lim_t)
    ax1.set_title(f"Pico de la señal: {pico_t:.4f}", fontsize=9)

    mag_rect, mag_ham, f_pico, m_pico = calcular_espectro(x)
    line_t.set_ydata(x)
    line_rect.set_ydata(mag_rect)
    line_ham.set_ydata(mag_ham)

    if f_pico is None:
        marker.set_data([], [])
        texto.set_text("")
    else:
        marker.set_data([f_pico], [m_pico])
        texto.set_text(f"Pico: {f_pico:.1f} Hz")
    return artistas


try:
    print(f"fs = {FS} Hz, N = {N}, "
          f"df = {DELTA_F:.3f} Hz, T_ventana = {T_VENTANA:.1f} ms")

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 7))
    fig.suptitle(f"fs = {FS} Hz | N = {N} | "
                 f"\u0394f = {DELTA_F:.3f} Hz | T = {T_VENTANA:.0f} ms")

    line_t, = ax1.plot(t, np.zeros(N))
    ax1.set_xlim(0, t[-1])
    ax1.set_ylim(-1, 1)
    ax1.set_xlabel("Tiempo (ms)")
    ax1.set_ylabel("Amplitud")
    ax1.grid(True)

    y0 = DB_MIN if USAR_DB else 0
    line_rect, = ax2.plot(freqs, np.full(len(freqs), y0), label="Sin ventana")
    line_ham, = ax2.plot(freqs, np.full(len(freqs), y0), label="Hamming")
    marker, = ax2.plot([], [], 'ro')
    texto = ax2.text(0.98, 0.95, "", transform=ax2.transAxes,
                     ha='right', va='top')
    ax2.set_xlim(0, FS / 2)
    if USAR_DB:
        ax2.set_ylim(DB_MIN, 0)
        ax2.set_ylabel("Magnitud (dB)")
    else:
        ax2.set_ylim(0, 0.1)
        ax2.set_ylabel("Magnitud")
    ax2.set_xlabel("Frecuencia (Hz)")
    ax2.legend(loc='upper left')
    ax2.grid(True)
    fig.tight_layout()

    artistas = (line_t, line_rect, line_ham, marker, texto)

    stream = sd.InputStream(
        device=args.device, channels=1, samplerate=FS,
        blocksize=N, callback=audio_callback)
    ani = FuncAnimation(fig, update_plot, interval=args.interval,
                        blit=False, cache_frame_data=False)
    with stream:
        plt.show()
except Exception as e:
    parser.exit(1, type(e).__name__ + ': ' + str(e) + '\n')
