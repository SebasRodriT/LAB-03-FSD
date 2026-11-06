"""Parte D: validación del detector de la ESP32 (matriz de confusión y falsos positivos).

Usa el firmware del entorno `esp32c3mini` (el que imprime "CONFIRMADO: X").
Cierra el monitor serie de PlatformIO antes de ejecutarlo (comparten el puerto).
Con el firmware de Semana 3 los tonos activan los motores: realiza las pruebas
con las ruedas levantadas y el carrito asegurado.

Prueba de tonos (4 tonos + silencio, 20 intentos cada uno, a una distancia):
    python tools/matriz_confusion.py medir -d 20
    python tools/matriz_confusion.py medir -d 50
    python tools/matriz_confusion.py medir -d 100

Falsos positivos con voz o música de fondo (sin tonos de control):
    python tools/matriz_confusion.py fondo --fuente musica --segundos 120

Matrices acumuladas de todo lo medido:
    python tools/matriz_confusion.py resumen
"""
import argparse
import csv
import os
import re
import time
from collections import Counter

CLASES = ["ADELANTE", "ATRAS", "IZQUIERDA", "DERECHA", "SILENCIO"]
TONOS = {"ADELANTE": 650, "ATRAS": 950, "IZQUIERDA": 1250, "DERECHA": 1550}
CSV_TONOS = os.path.join(os.path.dirname(__file__), "resultados_tonos.csv")
CSV_FONDO = os.path.join(os.path.dirname(__file__), "resultados_fondo.csv")
PATRON = re.compile(r"CONFIRMADO:\s*(\w+)")


def abrir(puerto):
    import serial  # import perezoso: "resumen" no lo necesita
    ser = serial.Serial()
    ser.port, ser.baudrate, ser.timeout = puerto, 115200, 0.2
    ser.dtr = ser.rts = False  # evita reiniciar la placa al abrir el puerto
    try:
        ser.open()
    except serial.SerialException:
        raise SystemExit(
            f"No se pudo abrir {puerto}. En Windows, 'Acceso denegado' suele "
            "significar que otra aplicación ya está usando el puerto. Cierra "
            "el Monitor serie de PlatformIO/Arduino y vuelve a intentar. "
            f"Si continúa, confirma en el Administrador de dispositivos que "
            f"la placa sigue conectada en {puerto}."
        ) from None
    return ser


def comandos_confirmados(ser, segundos, parar_al_primero):
    """Lee el Serial y devuelve los comandos confirmados durante `segundos`."""
    ser.reset_input_buffer()
    encontrados = []
    fin = time.time() + segundos
    while time.time() < fin:
        m = PATRON.search(ser.readline().decode(errors="ignore"))
        if m and m.group(1) in CLASES:
            encontrados.append(m.group(1))
            if parar_al_primero:
                break
    return encontrados


def guardar(ruta, filas, cabecera):
    nuevo = not os.path.exists(ruta)
    with open(ruta, "a", newline="") as f:
        w = csv.writer(f)
        if nuevo:
            w.writerow(cabecera)
        w.writerows(filas)


def imprimir_matriz(titulo, pares):
    """pares: lista de (emitido, detectado)."""
    cuenta = Counter(pares)
    print(f"\n{titulo}")
    print(f"{'emitido \\ detectado':<20}" + "".join(f"{c:>11}" for c in CLASES) + f"{'acierto':>10}")
    for e in CLASES:
        total = sum(cuenta[(e, d)] for d in CLASES)
        fila = "".join(f"{cuenta[(e, d)]:>11}" for d in CLASES)
        tasa = f"{100 * cuenta[(e, e)] / total:>8.0f}%" if total else f"{'-':>9}"
        print(f"{e:<20}{fila}{tasa}")


def medir(args):
    ser = abrir(args.puerto)
    filas = []
    print(f"Distancia {args.distancia} cm. Cada intento escucha {args.ventana:.1f} s.")
    try:
        for emitido in CLASES:
            if emitido == "SILENCIO":
                print("\n== SILENCIO: no emitas nada (puede haber ruido ambiente normal) ==")
            else:
                print(f"\n== {emitido} ({TONOS[emitido]} Hz) ==")
            for i in range(1, args.intentos + 1):
                input(f"  Intento {i}/{args.intentos}: pulsa Enter y "
                      f"{'espera en silencio' if emitido == 'SILENCIO' else 'reproduce el tono'}... ")
                lista = comandos_confirmados(ser, args.ventana, parar_al_primero=True)
                detectado = lista[0] if lista else "SILENCIO"
                filas.append((args.distancia, emitido, detectado))
                print(f"    -> {detectado} {'OK' if detectado == emitido else 'FALLO'}")
    except KeyboardInterrupt:
        print("\nInterrumpido: se guardan los intentos hechos.")
    finally:
        ser.close()
        if filas:
            guardar(CSV_TONOS, filas, ["distancia_cm", "emitido", "detectado"])
            imprimir_matriz(f"Matriz a {args.distancia} cm", [(e, d) for _, e, d in filas])
            print(f"\nGuardado en {CSV_TONOS}")


def fondo(args):
    ser = abrir(args.puerto)
    print(f"Fuente de fondo: {args.fuente}. Escuchando {args.segundos:.0f} s "
          "(sin reproducir tonos de control)...")
    try:
        lista = comandos_confirmados(ser, args.segundos, parar_al_primero=False)
    except KeyboardInterrupt:
        lista = []
    finally:
        ser.close()
    cuenta = Counter(lista)
    por_min = len(lista) / (args.segundos / 60)
    print(f"Falsos positivos: {len(lista)} ({por_min:.1f}/min)  detalle: {dict(cuenta)}")
    guardar(CSV_FONDO, [(args.fuente, args.segundos, len(lista), dict(cuenta))],
            ["fuente", "segundos", "falsos_positivos", "detalle"])


def resumen(_args):
    if os.path.exists(CSV_TONOS):
        with open(CSV_TONOS, newline="") as f:
            filas = list(csv.DictReader(f))
        for d in sorted({int(r["distancia_cm"]) for r in filas}):
            imprimir_matriz(f"Matriz a {d} cm",
                            [(r["emitido"], r["detectado"]) for r in filas
                             if int(r["distancia_cm"]) == d])
        imprimir_matriz("Matriz total", [(r["emitido"], r["detectado"]) for r in filas])
    else:
        print("Aún no hay resultados de tonos (ejecuta 'medir').")
    if os.path.exists(CSV_FONDO):
        print("\nFalsos positivos con fondo")
        with open(CSV_FONDO, newline="") as f:
            for r in csv.DictReader(f):
                print(f"  {r['fuente']:<10} {float(r['segundos']):>6.0f} s  "
                      f"{r['falsos_positivos']} falsos positivos  {r['detalle']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-p", "--puerto", default="COM7")
    sub = ap.add_subparsers(dest="modo", required=True)

    m = sub.add_parser("medir", help="matriz de confusión a una distancia")
    m.add_argument("-d", "--distancia", type=int, required=True, help="cm (20, 50, 100)")
    m.add_argument("-n", "--intentos", type=int, default=20)
    m.add_argument("--ventana", type=float, default=2.5, help="segundos de escucha por intento")
    m.set_defaults(func=medir)

    f = sub.add_parser("fondo", help="falsos positivos con voz o música de fondo")
    f.add_argument("--fuente", default="musica", help="p. ej. voz, musica, ruido")
    f.add_argument("--segundos", type=float, default=120)
    f.set_defaults(func=fondo)

    r = sub.add_parser("resumen", help="muestra las matrices acumuladas")
    r.set_defaults(func=resumen)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
