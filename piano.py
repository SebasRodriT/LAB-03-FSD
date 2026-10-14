import sys
import threading
import tkinter as tk
import numpy as np
import sounddevice as sd
from pynput import keyboard

FS = 44100
AMPLITUD = 0.25
RAMPA_MS = 10      # subida/bajada del volumen para evitar clics

TECLADO = {
    "1": 650, "2": 950, "3": 1250, "4": 1550,
    'a': 261.6, 's': 293.7, 'd': 329.6, 'f': 349.2, 
    'g': 392.0, 'h': 440.0, 'j': 493.9, 'k': 523.3
}

TECLAS_ACTIVAS = set()
fases = {tecla: 0.0 for tecla in TECLADO}
volumenes = {tecla: 0.0 for tecla in TECLADO}
PASO_VOLUMEN = 1 / (RAMPA_MS / 1000 * FS)

NOTAS = {
    'a': 'Do4', 's': 'Re4', 'd': 'Mi4', 'f': 'Fa4',
    'g': 'Sol4', 'h': 'La4', 'j': 'Si4', 'k': 'Do5'
}
CONTROL = ['1', '2', '3', '4']
ANCHO_TECLA, ALTO_TECLA, ALTO_CONTROL, MARGEN = 80, 220, 90, 10
COLOR_ACTIVO = "#4fa3ff"
SALIR = threading.Event()
rectangulos = {}   # tecla -> (id del rectangulo, color en reposo)

def on_press(key):
    tecla = getattr(key, 'char', None)
    if tecla in TECLADO:
        TECLAS_ACTIVAS.add(tecla)

def on_release(key):
    tecla = getattr(key, 'char', None)
    TECLAS_ACTIVAS.discard(tecla)
    if key == keyboard.Key.esc:
        SALIR.set()
        return False

def audio_callback(outdata, frames, time, status):
    """Suma un seno por cada tecla; la fase continua entre bloques."""
    if status:
        print(status, file=sys.stderr)
    n = np.arange(frames)
    rampa = PASO_VOLUMEN * np.arange(1, frames + 1)
    salida = np.zeros(frames)
    for tecla, f in TECLADO.items():
        activa = tecla in TECLAS_ACTIVAS
        v0 = volumenes[tecla]
        if not activa and v0 == 0.0:
            continue
        env = np.minimum(1.0, v0 + rampa) if activa else np.maximum(0.0, v0 - rampa)
        fase0 = fases[tecla]
        salida += env * np.sin(fase0 + 2 * np.pi * f * n / FS)
        fases[tecla] = (fase0 + 2 * np.pi * f * frames / FS) % (2 * np.pi)
        volumenes[tecla] = env[-1]
    outdata[:, 0] = np.clip(AMPLITUD * salida, -1.0, 1.0)

def crear_piano():
    """Dibuja los tonos de control arriba y la octava de notas abajo."""
    root = tk.Tk()
    root.title("Piano (Esc para salir)")
    ancho = MARGEN * 2 + ANCHO_TECLA * len(NOTAS)
    alto = MARGEN * 3 + ALTO_CONTROL + ALTO_TECLA
    canvas = tk.Canvas(root, width=ancho, height=alto, bg="#222222")
    canvas.pack()

    ancho_control = (ancho - MARGEN * 2) / len(CONTROL)
    for i, tecla in enumerate(CONTROL):
        x0 = MARGEN + i * ancho_control
        rect = canvas.create_rectangle(
            x0 + 2, MARGEN, x0 + ancho_control - 2, MARGEN + ALTO_CONTROL,
            fill="#dddddd", outline="black", width=2)
        canvas.create_text(
            x0 + ancho_control / 2, MARGEN + ALTO_CONTROL / 2,
            text=f"{tecla}\n{TECLADO[tecla]:g} Hz", font=("Arial", 14, "bold"))
        rectangulos[tecla] = (rect, "#dddddd")

    y0 = MARGEN * 2 + ALTO_CONTROL
    for i, tecla in enumerate(NOTAS):
        x0 = MARGEN + i * ANCHO_TECLA
        rect = canvas.create_rectangle(
            x0, y0, x0 + ANCHO_TECLA, y0 + ALTO_TECLA,
            fill="white", outline="black", width=2)
        canvas.create_text(
            x0 + ANCHO_TECLA / 2, y0 + ALTO_TECLA - 60,
            text=f"{NOTAS[tecla]}\n{TECLADO[tecla]:g} Hz",
            font=("Arial", 11))
        canvas.create_text(
            x0 + ANCHO_TECLA / 2, y0 + ALTO_TECLA - 15,
            text=tecla.upper(), font=("Arial", 14, "bold"))
        rectangulos[tecla] = (rect, "white")
    return root, canvas

def actualizar_piano(root, canvas):
    """Resalta las teclas activas; se repite cada 30 ms."""
    if SALIR.is_set():
        root.destroy()
        return
    for tecla, (rect, reposo) in rectangulos.items():
        color = COLOR_ACTIVO if tecla in TECLAS_ACTIVAS else reposo
        canvas.itemconfig(rect, fill=color)
    root.after(30, actualizar_piano, root, canvas)

print("Piano listo. Teclas (Esc para salir):")
for tecla, f in TECLADO.items():
    print(f"  {tecla} -> {f} Hz")

with sd.OutputStream(samplerate=FS, channels=1, callback=audio_callback):
    with keyboard.Listener(
            on_press=on_press,
            on_release=on_release) as listener:
        root, canvas = crear_piano()
        actualizar_piano(root, canvas)
        root.mainloop()
