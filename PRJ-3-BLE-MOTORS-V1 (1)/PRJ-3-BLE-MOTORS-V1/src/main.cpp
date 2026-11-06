// Semana 3 — control del robot por tonos con I2S, FFT y máquina de estados.
// Los motores se detienen si desaparece el tono validado.
//
// Conexión INMP441 -> ESP32-C3:
//   VDD -> 3V3 (nunca 5 V)   GND -> GND   L/R -> GND (canal izquierdo)
//   SCK -> GPIO6 (BCLK)      WS  -> GPIO7 (LRCLK)     SD -> GPIO10

#include <Arduino.h>
#include <driver/i2s.h>
#include <arduinoFFT.h>

// ── Modo de salida ──────────────────────────────────────────────────────────
// 0 = detector de tonos (Parte C/D)
// 1 = muestras crudas para el Serial Plotter (Parte B)
#ifndef MODO_SALIDA
#define MODO_SALIDA 0
#endif

// Si todas las muestras salen en 0 o constantes, probar el canal opuesto.
#ifndef USAR_CANAL_DERECHO
#define USAR_CANAL_DERECHO 0
#endif

// Solo modo 1: imprimir 1 de cada DECIMAR muestras (el Serial Plotter no
// sigue 16 000 puntos/s; con 16 se ve una señal de baja frecuencia).
#ifndef DECIMAR
#define DECIMAR 1
#endif

// ── Pines I2S ───────────────────────────────────────────────────────────────
constexpr int PIN_BCLK = 6;   // SCK
constexpr int PIN_WS   = 7;   // WS / LRCLK
constexpr int PIN_SD   = 10;  // SD (datos del micrófono)

// ── Parámetros de captura y FFT (iguales a detector.py) ─────────────────────
constexpr i2s_port_t I2S_PORT = I2S_NUM_0;
constexpr uint16_t N  = 1024;
constexpr double   FS = 16000.0;

constexpr double   UMBRAL = 0.000002;   // magnitud lineal mínima (escala de detector.py)
constexpr double   F_MIN = 300.0;    // se ignora el ruido por debajo de esta frecuencia
constexpr double   TOLERANCIA = 45.0;  // Hz
constexpr int      VENTANAS_CONFIRMACION = 3;

constexpr size_t   CHUNK = 256;      // muestras leídas por llamada a i2s_read

struct Tono { double freq; const char* comando; };
constexpr Tono TONOS[] = {
  {650.0,  "ADELANTE"},
  {950.0,  "ATRAS"},
  {1250.0, "IZQUIERDA"},
  {1550.0, "DERECHA"},
};
constexpr const char* SILENCIO = "SILENCIO";

// ── Motores (L298N) ─────────────────────────────────────────────────────────
constexpr int MOTOR_A_1 = 0;  // GPIO0 -> IN1
constexpr int MOTOR_A_2 = 1;  // GPIO1 -> IN2
constexpr int MOTOR_B_1 = 3;  // GPIO3 -> IN3
constexpr int MOTOR_B_2 = 4;  // GPIO4 -> IN4
constexpr int CH_A_1 = 0;
constexpr int CH_A_2 = 1;
constexpr int CH_B_1 = 2;
constexpr int CH_B_2 = 3;
constexpr int PWM_FREQ = 1000;
constexpr int PWM_RES = 8;
constexpr int VELOCIDAD_MOTOR = 160;

enum Estado { REPOSO, VALIDANDO, MOVIENDO };
Estado estado = REPOSO;
const char* comandoValidando = nullptr;
const char* comandoActual = nullptr;
int cuentaVentanas = 0;

// ── Buffers (N * 8 B * 2 = 16 KiB para N = 1024) ────────────────────────────
double vReal[N];
double vImag[N];
ArduinoFFT<double> FFT(vReal, vImag, N, FS);

int32_t bufI2S[CHUNK];
double  sumaVentana = 0;  // suma de los coeficientes de Hamming (normalización)

// ── I2S ─────────────────────────────────────────────────────────────────────
void iniciarI2S() {
  i2s_config_t cfg;
  memset(&cfg, 0, sizeof(cfg));
  cfg.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX);
  cfg.sample_rate = (uint32_t)FS;
  cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;
#if USAR_CANAL_DERECHO
  cfg.channel_format = I2S_CHANNEL_FMT_ONLY_RIGHT;
#else
  cfg.channel_format = I2S_CHANNEL_FMT_ONLY_LEFT;
#endif
  cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  cfg.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  cfg.dma_buf_count = 8;
  cfg.dma_buf_len = CHUNK;
  cfg.use_apll = false;

  i2s_pin_config_t pines;
  memset(&pines, 0, sizeof(pines));
  pines.mck_io_num = I2S_PIN_NO_CHANGE;
  pines.bck_io_num = PIN_BCLK;
  pines.ws_io_num = PIN_WS;
  pines.data_out_num = I2S_PIN_NO_CHANGE;
  pines.data_in_num = PIN_SD;

  esp_err_t e = i2s_driver_install(I2S_PORT, &cfg, 0, nullptr);
  if (e == ESP_OK) e = i2s_set_pin(I2S_PORT, &pines);
  if (e != ESP_OK) {
    Serial.printf("ERROR I2S: %d\n", (int)e);
    while (true) delay(1000);
  }
}

// Descarta lo acumulado en el DMA mientras se calculaba la FFT, para que
// cada ventana sea un bloque contiguo de audio reciente.
void vaciarDMA() {
  size_t leidos;
  do {
    leidos = 0;
    i2s_read(I2S_PORT, bufI2S, sizeof(bufI2S), &leidos, 0);
  } while (leidos > 0);
}

// Captura N muestras en vReal, normalizadas a [-1, 1) (24 bits con signo).
void capturarVentana() {
  size_t n = 0;
  while (n < N) {
    size_t pedir = min((size_t)(N - n), CHUNK) * sizeof(int32_t);
    size_t leidos = 0;
    i2s_read(I2S_PORT, bufI2S, pedir, &leidos, portMAX_DELAY);
    size_t m = leidos / sizeof(int32_t);
    for (size_t i = 0; i < m; i++) {
      vReal[n + i] = (double)(bufI2S[i] >> 8) / 8388608.0;  // dato de 24 bits alineado a la izquierda
    }
    n += m;
  }
}

// ── Procesamiento ───────────────────────────────────────────────────────────
void quitarDC() {
  double media = 0;
  for (uint16_t i = 0; i < N; i++) media += vReal[i];
  media /= N;
  for (uint16_t i = 0; i < N; i++) {
    vReal[i] -= media;
    vImag[i] = 0;
  }
}

// Devuelve el pico dominante (>= F_MIN). La magnitud queda en la misma escala
// que detector.py: |FFT| / sum(ventana), con muestras en [-1, 1].
void calcularPico(double &fPico, double &mag) {
  quitarDC();
  FFT.windowing(FFTWindow::Hamming, FFTDirection::Forward);
  FFT.compute(FFTDirection::Forward);
  FFT.complexToMagnitude();

  const uint16_t binMin = (uint16_t)ceil(F_MIN * N / FS);
  for (uint16_t i = 0; i < binMin; i++) vReal[i] = 0;

  // El "magnitude" de majorPeak() es una segunda diferencia, no el valor del
  // bin; por eso la magnitud se toma directamente del bin máximo.
  double ignorada = 0;
  FFT.majorPeak(&fPico, &ignorada);
  if (!isfinite(fPico)) fPico = 0;

  uint16_t idx = binMin;
  for (uint16_t i = binMin + 1; i <= N / 2; i++) {
    if (vReal[i] > vReal[idx]) idx = i;
  }
  mag = vReal[idx] / sumaVentana;
}

const char* clasificar(double fPico, double mag) {
  if (mag < UMBRAL) return SILENCIO;
  for (const Tono &t : TONOS) {
    if (fabs(fPico - t.freq) <= TOLERANCIA) return t.comando;
  }
  return SILENCIO;
}

const char* nombreEstado(Estado e) {
  switch (e) {
    case REPOSO: return "REPOSO";
    case VALIDANDO: return "VALIDANDO";
    case MOVIENDO: return "MOVIENDO";
  }
  return "DESCONOCIDO";
}

bool esTonoValido(const char* comando) {
  return strcmp(comando, SILENCIO) != 0;
}

void cambiarEstado(Estado nuevo, double fPico) {
  if (estado != nuevo) {
    Serial.printf("%s -> %s (%.1f Hz)\n",
                  nombreEstado(estado), nombreEstado(nuevo), fPico);
    estado = nuevo;
  }
}

void apagarCanalPWM(int pin, int canal) {
  ledcWrite(canal, 0);
  ledcDetachPin(pin);
  pinMode(pin, OUTPUT);
  digitalWrite(pin, LOW);
}

void aplicarPWM(int pin, int canal, int velocidad) {
  pinMode(pin, OUTPUT);
  ledcAttachPin(pin, canal);
  ledcWrite(canal, velocidad);
}

void pararMotores() {
  apagarCanalPWM(MOTOR_A_1, CH_A_1);
  apagarCanalPWM(MOTOR_A_2, CH_A_2);
  apagarCanalPWM(MOTOR_B_1, CH_B_1);
  apagarCanalPWM(MOTOR_B_2, CH_B_2);
}

void moverMotorA(int velocidad, bool adelante) {
  apagarCanalPWM(MOTOR_A_1, CH_A_1);
  apagarCanalPWM(MOTOR_A_2, CH_A_2);
  if (velocidad > 0) {
    aplicarPWM(adelante ? MOTOR_A_1 : MOTOR_A_2,
               adelante ? CH_A_1 : CH_A_2, velocidad);
  }
}

void moverMotorB(int velocidad, bool adelante) {
  apagarCanalPWM(MOTOR_B_1, CH_B_1);
  apagarCanalPWM(MOTOR_B_2, CH_B_2);
  if (velocidad > 0) {
    aplicarPWM(adelante ? MOTOR_B_1 : MOTOR_B_2,
               adelante ? CH_B_1 : CH_B_2, velocidad);
  }
}

void ejecutarComando(const char* comando) {
  if (strcmp(comando, "ADELANTE") == 0) {
    moverMotorA(VELOCIDAD_MOTOR, true);
    moverMotorB(VELOCIDAD_MOTOR, true);
  } else if (strcmp(comando, "ATRAS") == 0) {
    moverMotorA(VELOCIDAD_MOTOR, false);
    moverMotorB(VELOCIDAD_MOTOR, false);
  } else if (strcmp(comando, "DERECHA") == 0) {
    moverMotorA(VELOCIDAD_MOTOR, true);
    moverMotorB(0, true);
  } else if (strcmp(comando, "IZQUIERDA") == 0) {
    moverMotorA(0, true);
    moverMotorB(VELOCIDAD_MOTOR, true);
  }
}

void procesarVentana(const char* comando, double fPico) {
  switch (estado) {
    case REPOSO:
      if (esTonoValido(comando)) {
        comandoValidando = comando;
        cuentaVentanas = 1;
        cambiarEstado(VALIDANDO, fPico);
      }
      break;

    case VALIDANDO:
      if (!esTonoValido(comando)) {
        comandoValidando = nullptr;
        cuentaVentanas = 0;
        cambiarEstado(REPOSO, fPico);
      } else if (strcmp(comando, comandoValidando) != 0) {
        comandoValidando = comando;
        cuentaVentanas = 1;
        Serial.printf("VALIDANDO: nuevo tono %s, contador=1\n", comando);
      } else if (++cuentaVentanas >= VENTANAS_CONFIRMACION) {
        ejecutarComando(comandoValidando);
        comandoActual = comandoValidando;
        cambiarEstado(MOVIENDO, fPico);
        Serial.printf("CONFIRMADO: %s\n", comandoActual);
      }
      break;

    case MOVIENDO:
      if (strcmp(comando, comandoActual) != 0) {
        pararMotores();
        comandoActual = nullptr;
        if (esTonoValido(comando)) {
          comandoValidando = comando;
          cuentaVentanas = 1;
          cambiarEstado(VALIDANDO, fPico);
        } else {
          comandoValidando = nullptr;
          cuentaVentanas = 0;
          cambiarEstado(REPOSO, fPico);
        }
      }
      break;
  }
}

void iniciarMotores() {
  const int pines[] = {MOTOR_A_1, MOTOR_A_2, MOTOR_B_1, MOTOR_B_2};
  for (int pin : pines) {
    pinMode(pin, OUTPUT);
    digitalWrite(pin, LOW);
  }
  ledcSetup(CH_A_1, PWM_FREQ, PWM_RES);
  ledcSetup(CH_A_2, PWM_FREQ, PWM_RES);
  ledcSetup(CH_B_1, PWM_FREQ, PWM_RES);
  ledcSetup(CH_B_2, PWM_FREQ, PWM_RES);
  pararMotores();
}

// ── Arduino ─────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  uint32_t t0 = millis();
  while (!Serial && millis() - t0 < 3000) delay(10);

  for (uint16_t i = 0; i < N; i++) {
    sumaVentana += 0.54 - 0.46 * cos(2.0 * PI * i / (N - 1));
  }

#if MODO_SALIDA == 0
  iniciarMotores();
#endif
  iniciarI2S();

  Serial.println("# INMP441 + FFT (ESP32-C3)");
  Serial.printf("# fs=%.0f Hz, N=%u, resolucion=%.2f Hz/bin, umbral=%.4f, tolerancia=%.0f Hz\n",
                FS, N, FS / N, UMBRAL, TOLERANCIA);
  Serial.printf("# RAM FFT: vReal+vImag = %u bytes (%.1f%% de 400 KiB). Heap libre: %u bytes\n",
                (unsigned)(sizeof(vReal) + sizeof(vImag)),
                100.0 * (sizeof(vReal) + sizeof(vImag)) / (400.0 * 1024.0),
                (unsigned)ESP.getFreeHeap());
}

void loop() {
#if MODO_SALIDA == 1
  // Una muestra (entero de 24 bits) por línea: Serial Plotter o plot_raw.py.
  // Se envía por bloques; con DECIMAR > 1 solo se imprime 1 de cada DECIMAR.
  static char linea[CHUNK * 10];
  static uint32_t contador = 0;
  size_t leidos = 0;
  i2s_read(I2S_PORT, bufI2S, sizeof(bufI2S), &leidos, portMAX_DELAY);
  size_t len = 0;
  for (size_t i = 0; i < leidos / sizeof(int32_t); i++) {
    if (contador++ % DECIMAR) continue;
    len += snprintf(linea + len, sizeof(linea) - len, "%ld\n", (long)(bufI2S[i] >> 8));
  }
  Serial.write((const uint8_t*)linea, len);
#else
  vaciarDMA();

  uint32_t t1 = micros();
  capturarVentana();
  uint32_t tCaptura = micros() - t1;

  uint32_t t2 = micros();
  double fPico = 0, mag = 0;
  calcularPico(fPico, mag);
  uint32_t tFFT = micros() - t2;

  const char* comando = clasificar(fPico, mag);

  Serial.printf("%-9s pico=%7.1f Hz  mag=%.5f  t_cap=%lu us  t_fft=%lu us\n",
                comando, fPico, mag, (unsigned long)tCaptura, (unsigned long)tFFT);
  procesarVentana(comando, fPico);
#endif
}
