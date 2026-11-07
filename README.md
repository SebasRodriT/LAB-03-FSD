# LAB-03-FSD — Control del robot por tonos

Repositorio del laboratorio de Fundamentos de Sistemas Digitales. El laboratorio
se desarrolla en cuatro semanas, que corresponden a las semanas 10 a 13 del
curso.

## Entregables disponibles

| Semana del laboratorio | Semana del curso | Entregables en este repositorio |
|---|---:|---|
| 1 — Tonos, muestreo y FFT en Python | 10 | [`Semana 1/piano.py`](<Semana 1/piano.py>) genera los tonos de control y notas musicales; [`Semana 1/analizador.py`](<Semana 1/analizador.py>) visualiza la señal y su espectro FFT; [`Semana 1/detector.py`](<Semana 1/detector.py>) reconoce los tonos y permite medir aciertos. |
| 2 — INMP441 por I2S y FFT en ESP32 | 11 | Proyecto PlatformIO en [`PRJ-3-BLE-MOTORS-V1 (1)/PRJ-3-BLE-MOTORS-V1/`](<PRJ-3-BLE-MOTORS-V1 (1)/PRJ-3-BLE-MOTORS-V1/>). [`src/main.cpp`](<PRJ-3-BLE-MOTORS-V1 (1)/PRJ-3-BLE-MOTORS-V1/src/main.cpp>) contiene la captura I2S y FFT; [`tools/plot_raw.py`](<PRJ-3-BLE-MOTORS-V1 (1)/PRJ-3-BLE-MOTORS-V1/tools/plot_raw.py>) ayuda a visualizar las muestras crudas. El diagrama de conexión está en [`Figura5_diagrama_conexion.png`](Figura5_diagrama_conexion.png). |
| 3 — Integración con el robot y máquina de estados | 12 | El mismo proyecto PlatformIO incluye en [`src/main.cpp`](<PRJ-3-BLE-MOTORS-V1 (1)/PRJ-3-BLE-MOTORS-V1/src/main.cpp>) el control de motores por tonos y la máquina de estados. |
| 4 — Validación y métricas | 13 | [`tools/matriz_confusion.py`](<PRJ-3-BLE-MOTORS-V1 (1)/PRJ-3-BLE-MOTORS-V1/tools/matriz_confusion.py>) ejecuta y resume pruebas del detector; [`tools/resultados_tonos.csv`](<PRJ-3-BLE-MOTORS-V1 (1)/PRJ-3-BLE-MOTORS-V1/tools/resultados_tonos.csv>) contiene resultados registrados. [`tools/plot_raw.py`](<PRJ-3-BLE-MOTORS-V1 (1)/PRJ-3-BLE-MOTORS-V1/tools/plot_raw.py>) también sirve para diagnosticar la captura. |

> El firmware actual reúne funcionalidades de las semanas 2 y 3; no se
> encuentran proyectos separados para cada etapa.

## Contenido organizado por carpeta

```text
.
├── Semana 1/
│   ├── analizador.py
│   ├── detector.py
│   └── piano.py
├── PRJ-3-BLE-MOTORS-V1 (1)/
│   └── PRJ-3-BLE-MOTORS-V1/
│       ├── platformio.ini
│       ├── src/main.cpp
│       └── tools/
│           ├── matriz_confusion.py
│           ├── plot_raw.py
│           └── resultados_tonos.csv
└── Figura5_diagrama_conexion.png
```

## Elementos del paquete final por completar

La guía solicita entregar un informe PDF junto con el código. No se encontró
ese informe en el repositorio. La guía también pide incluir en el informe el
diagrama de estados, la caracterización del ruido de los motores, las métricas
y la comparación Python–ESP32 de la semana 4, las respuestas de análisis, la
reflexión sobre UART/BLE/I2S y, si aplica, la bitácora de uso de IA. Estos
documentos o evidencias no aparecen como archivos independientes en el
repositorio.
