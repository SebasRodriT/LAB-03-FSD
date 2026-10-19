"""Detector de tonos de control (Parte D).

Captura audio del microfono (fs = 16000 Hz, bloques de N = 1024 muestras),
calcula el pico dominante del espectro (ventana de Hamming) y lo compara con
la tabla de tonos de control (+-45 Hz). Imprime un comando por ventana:
ADELANTE, ATRÁS, IZQUIERDA, DERECHA o SILENCIO, y "CONFIRMADO" cuando el
mismo comando aparece en 3 ventanas consecutivas.

Uso:
    python detector.py                 detector en vivo (Ctrl+C para salir)
    python detector.py --medir         mide la tasa de acierto (20 por tono)
    python detector.py -l              lista los dispositivos de audio
"""
import argparse
import queue
import sys

import numpy as np
import sounddevice as sd

FS = 16000
N = 1024
UMBRAL = 0.002             # magnitud lineal minima del pico para no ser SILENCIO
F_MIN = 300                # se ignora el ruido ambiente por debajo de esta frecuencia
TOLERANCIA = 45            # Hz
VENTANAS_CONFIRMACION = 3
INTENTOS = 20              # repeticiones por tono en el modo --medir
SEGUNDOS_INTENTO = 2

TONOS = {650: "ADELANTE", 950: "ATRÁS", 1250: "IZQUIERDA", 1550: "DERECHA"}

freqs = np.fft.rfftfreq(N, d=1/FS)
w = np.hamming(N)
q = queue.Queue()


def int_or_str(text):
    try:
        return int(text)
    except ValueError:
        return text


def calcular_pico(x):
    """Devuelve (frecuencia, magnitud) del pico dominante con ventana de Hamming."""
    mag = np.abs(np.fft.rfft(x * w)) / np.sum(w)
    mag[freqs < F_MIN] = 0
    idx = np.argmax(mag)
    return freqs[idx], mag[idx]


def clasificar(f_pico, mag, umbral):
    """Compara el pico con la tabla de tonos; sin coincidencia es SILENCIO."""
    if mag < umbral:
        return "SILENCIO"
    for f, comando in TONOS.items():
        if abs(f_pico - f) <= TOLERANCIA:
            return comando
    return "SILENCIO"


def procesar_ventana(x, umbral):
    f_pico, mag = calcular_pico(x)
    return clasificar(f_pico, mag, umbral), f_pico, mag


class Confirmador:
    """Avisa cuando el mismo comando aparece en n ventanas consecutivas."""

    def __init__(self, n=VENTANAS_CONFIRMACION):
        self.n = n
        self.ultimo = None
        self.cuenta = 0

    def actualizar(self, comando):
        if comando == self.ultimo:
            self.cuenta += 1
        else:
            self.ultimo, self.cuenta = comando, 1
        return comando != "SILENCIO" and self.cuenta == self.n


def audio_callback(indata, frames, time, status):
    if status:
        print(status, file=sys.stderr)
    q.put(indata[:, 0].copy())


def vaciar_cola():
    while True:
        try:
            q.get_nowait()
        except queue.Empty:
            return


def detectar(umbral):
    confirmador = Confirmador()
    print(f"Escuchando (fs = {FS} Hz, N = {N}, umbral = {umbral}). Ctrl+C para salir.")
    while True:
        comando, f_pico, mag = procesar_ventana(q.get(), umbral)
        print(f"{comando:<10} (pico {f_pico:7.1f} Hz, magnitud {mag:.4f})")
        if confirmador.actualizar(comando):
            print(f"CONFIRMADO: {comando}")


def probar_tono(umbral):
    """Escucha un intento y devuelve el primer comando confirmado (o None)."""
    confirmador = Confirmador()
    vaciar_cola()
    for _ in range(int(SEGUNDOS_INTENTO * FS / N)):
        comando, _, _ = procesar_ventana(q.get(timeout=1), umbral)
        if confirmador.actualizar(comando):
            return comando
    return None


def medir(umbral):
    aciertos = {}
    for f, esperado in TONOS.items():
        print(f"\n== {esperado} ({f} Hz) ==")
        aciertos[esperado] = 0
        for i in range(1, INTENTOS + 1):
            input(f"  Intento {i}/{INTENTOS}: pulsa Enter y reproduce el tono... ")
            detectado = probar_tono(umbral)
            ok = detectado == esperado
            aciertos[esperado] += ok
            print(f"    -> {detectado or 'SIN CONFIRMAR'} {'OK' if ok else 'FALLO'}")

    print("\nTasa de acierto")
    print(f"{'Comando':<10} {'Tono (Hz)':>9} {'Aciertos':>9} {'Tasa':>7}")
    for f, comando in TONOS.items():
        n_ok = aciertos[comando]
        print(f"{comando:<10} {f:>9} {n_ok:>6}/{INTENTOS} {100 * n_ok / INTENTOS:>6.0f}%")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-l', '--list-devices', action='store_true',
                        help='muestra los dispositivos de audio y sale')
    parser.add_argument('-d', '--device', type=int_or_str,
                        help='dispositivo de entrada (ID o texto)')
    parser.add_argument('-u', '--umbral', type=float, default=UMBRAL,
                        help='magnitud minima del pico (default: %(default)s)')
    parser.add_argument('--medir', action='store_true',
                        help='mide la tasa de acierto de cada tono')
    args = parser.parse_args()

    if args.list_devices:
        print(sd.query_devices())
        return

    try:
        with sd.InputStream(device=args.device, channels=1, samplerate=FS,
                            blocksize=N, callback=audio_callback):
            if args.medir:
                medir(args.umbral)
            else:
                detectar(args.umbral)
    except KeyboardInterrupt:
        print("\nDetector detenido.")
    except Exception as e:
        parser.exit(1, type(e).__name__ + ': ' + str(e) + '\n')


if __name__ == "__main__":
    main()
