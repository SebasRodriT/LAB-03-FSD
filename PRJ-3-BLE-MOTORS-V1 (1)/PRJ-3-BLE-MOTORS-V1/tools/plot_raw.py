"""Parte B: lee las muestras crudas del INMP441 por Serial y las grafica.

Requiere el firmware compilado con el entorno `raw` (MODO_SALIDA=1).
Cierra el monitor serie de PlatformIO antes de ejecutarlo (comparten el puerto).

Uso:
    python tools/plot_raw.py                  COM7, 2 segundos
    python tools/plot_raw.py -p COM5 -s 4
"""
import argparse
import time

import matplotlib.pyplot as plt
import numpy as np
import serial

FS = 16000


def capturar(puerto, segundos):
    muestras = []
    with serial.Serial(puerto, 115200, timeout=1) as ser:
        ser.reset_input_buffer()
        fin = time.time() + segundos
        while time.time() < fin:
            linea = ser.readline().decode(errors="ignore").strip()
            try:
                muestras.append(int(linea))
            except ValueError:
                pass  # líneas incompletas o comentarios
    return np.array(muestras[1:], dtype=np.int64)  # descarta la 1ª (puede venir cortada)


def diagnostico(x):
    print(f"Muestras: {len(x)}  min={x.min()}  max={x.max()}  media={x.mean():.1f}  "
          f"std={x.std():.1f}  pico-pico={x.max() - x.min()}")
    if np.all(x == 0):
        print("TODAS EN CERO: revisar VDD y GND, luego L/R a GND, y probar "
              "-DUSAR_CANAL_DERECHO=1.")
    elif x.std() < 20:
        print("Señal casi constante: revisar el cableado y probar el canal opuesto.")
    else:
        print("La señal responde. Habla, silba o reproduce un tono y compara el pico-pico.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-p", "--puerto", default="COM7")
    ap.add_argument("-s", "--segundos", type=float, default=2.0)
    ap.add_argument("--decimar", type=int, default=1,
                    help="el mismo valor de DECIMAR del firmware (ajusta la fs)")
    args = ap.parse_args()

    x = capturar(args.puerto, args.segundos)
    if len(x) < 100:
        print("Casi no llegaron muestras: ¿firmware en modo raw y monitor cerrado?")
        return
    diagnostico(x)

    fs = FS / args.decimar
    x = x - x.mean()
    t = np.arange(len(x)) / fs
    f = np.fft.rfftfreq(len(x), 1 / fs)
    esp = np.abs(np.fft.rfft(x * np.hanning(len(x))))

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 6))
    a1.plot(t, x)
    a1.set(xlabel="t (s)", ylabel="muestra (24 bits, sin DC)", title="Señal del INMP441")
    a2.plot(f, esp)
    a2.set(xlabel="Hz", ylabel="|FFT|", title="Espectro", xlim=(0, fs / 2))
    fig.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
