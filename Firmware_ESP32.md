# Firmware de la ESP32-S3 para el Robot Multisensor

Este archivo documenta el firmware implementado en el microcontrolador **ESP32-S3**, que actúa como el cerebro de bajo nivel del vehículo teleoperado. Sus funciones principales son:

- Controlar los cuatro motores DC mediante señales PWM (modulación por ancho de pulso).
- Leer los sensores de estado interno:
  - **IMU MPU6050** (acelerómetro y giroscopio) para estimar la orientación.
  - **Encoders ópticos** en cada rueda para odometría.
  - **GPS NEO-6M** para posicionamiento global.
- Recibir comandos de movimiento desde la Raspberry Pi a través del puerto serie (UART) y ejecutarlos.
- Transmitir periódicamente una trama unificada (`$DATA`) con todos los datos sensoriales hacia la Raspberry Pi.

El firmware está basado en **FreeRTOS**, con dos tareas principales que se ejecutan en núcleos separados para garantizar el determinismo y la capacidad de respuesta.

---

## Pines y conexiones

La siguiente tabla resume la asignación de pines utilizada en la ESP32-S3:

| Periférico      | Pin GPIO | Función                     |
|-----------------|----------|-----------------------------|
| **I2C (MPU)**   | 8 (SDA)  | Bus I2C para la IMU         |
|                 | 9 (SCL)  |                             |
| **GPS**         | 16 (RX)  | UART1 para recepción GPS    |
|                 | 15 (TX)  | (no usado en este firmware) |
| **Encoders**    | 46       | Rueda delantera izquierda   |
|                 | 3        | Rueda delantera derecha     |
|                 | 4        | Rueda trasera izquierda     |
|                 | 5        | Rueda trasera derecha       |
| **Motores**     |           |                             |
| *Front Left*    | 19 (EN)  | Habilitación (PWM)          |
|                 | 45 (IN1) | Dirección                   |
|                 | 48 (IN2) |                             |
| *Front Right*   | 36 (EN)  |                             |
|                 | 38 (IN1) |                             |
|                 | 37 (IN2) |                             |
| *Back Left*     | 20 (EN)  |                             |
|                 | 47 (IN1) |                             |
|                 | 21 (IN2) |                             |
| *Back Right*    | 35 (EN)  |                             |
|                 | 40 (IN1) |                             |
|                 | 39 (IN2) |                             |

---

## Comunicación serie (UART0)

El firmware se comunica con la Raspberry Pi a través del puerto serie **UART0** (pines TX/RX de la ESP32). La velocidad de transmisión es de **115200 baudios**. Todas las líneas de comando deben terminar con un salto de línea (`\n`).

### Comandos disponibles

| Comando                     | Descripción                                                                 |
|-----------------------------|-----------------------------------------------------------------------------|
| `w`                         | Avanzar con la potencia definida en `FWD_PWM` (200).                        |
| `x`                         | Retroceder con `BACK_PWM` (200).                                            |
| `a`                         | Giro a la izquierda (diferencial) con `TURN_PWM` (220).                     |
| `d`                         | Giro a la derecha con `TURN_PWM` (220).                                     |
| `0`                         | Detener todos los motores inmediatamente.                                   |
| `p L,R`                     | Control diferencial (skid‑steer): `L` y `R` son los PWMs (‑255 a 255).      |
| `m FL,FR,BL,BR`             | Control independiente de los 4 motores (valores entre ‑255 y 255).          |
| `o MOTOR VAL`               | Control de un solo motor: `MOTOR` = `fl`, `fr`, `bl` o `br`; `VAL` es PWM.   |
| `r`                         | Reiniciar los contadores de los encoders y el ángulo de guiñada (`yaw`).    |
| `DATA rate MS`              | Activar el envío continuo de tramas `$DATA` cada `MS` milisegundos (mínimo 10 ms). |
| `DATA stop`                 | Detener el envío continuo de tramas.                                        |
| `SNAPSHOT`                  | Enviar una única trama `$DATA` (sin activar el stream).                     |
| `TEST_IMU`                  | Ejecutar el diagnóstico del sensor MPU6050.                                 |
| `TEST_GPS`                  | Ejecutar el diagnóstico del GPS (escucha 2 segundos).                       |
| `TEST_ENC`                  | Probar cada encoder girando cada motor 1.5 segundos.                        |
| `TEST_MOT`                  | Probar cada motor individualmente (sin encoders).                           |
| `TEST_ALL`                  | Ejecutar todos los diagnósticos anteriores en secuencia.                    |
| `CAL_IMU`                   | Recalibrar el offset del giroscopio (¡no mover el robot durante la calibración!). |
| `HELP`                      | Mostrar un menú de ayuda con todos los comandos.                           |

Todos los comandos devuelven una respuesta con formato `$SYS,...` o `$DIAG,...` para confirmar la ejecución o proporcionar los resultados de las pruebas.

---

## Trama de datos `$DATA`

Cuando el stream está activo (o al enviar `SNAPSHOT`), el firmware transmite una trama con todos los datos sensoriales en el siguiente formato:

$DATA,seq,millis,
cFL,cFR,cBL,cBR,
rFL,rFR,rBL,rBR,
yaw_fused,
ax,ay,az,
gx,gy,gz,
lat,lon,sats,
pwmFL,pwmFR,pwmBL,pwmBR*XX


| Campo      | Tipo     | Descripción                                                          |
|------------|----------|----------------------------------------------------------------------|
| `seq`      | uint32_t | Número de secuencia (incrementa en cada trama).                      |
| `millis`   | uint32_t | Tiempo en milisegundos desde el arranque del ESP32.                  |
| `cFL...`   | long     | Conteo de pulsos de los encoders (FL, FR, BL, BR).                   |
| `rFL...`   | float    | RPM (revoluciones por minuto) de cada rueda.                         |
| `yaw_fused`| float    | Ángulo de guiñada fusionado (giroscopio + odometría diferencial).    |
| `ax,ay,az` | int16_t  | Valores crudos del acelerómetro (ejes X, Y, Z).                      |
| `gx,gy,gz` | int16_t  | Valores crudos del giroscopio (ejes X, Y, Z).                        |
| `lat,lon`  | float    | Latitud y longitud (si GPS tiene fijo; 0.0 en otro caso).            |
| `sats`     | int      | Número de satélites GPS visibles.                                    |
| `pwm...`   | int      | Últimos valores PWM aplicados a cada motor (FL, FR, BL, BR).         |
| `XX`       | uint8_t  | Checksum XOR de todos los caracteres entre `$` y `*` (en hexadecimal).|

La trama termina con `*` seguido del checksum en hexadecimal (dos dígitos). Este checksum permite verificar la integridad de los datos en el receptor (Raspberry Pi).

---

## Arquitectura de tareas FreeRTOS

El firmware utiliza dos tareas que se ejecutan en núcleos distintos:

### Tarea `motorTask` (Core 0, prioridad 2)

- Recibe comandos de la cola `cmdQueue` y los aplica a los motores.
- Implementa un **failsafe**: si no se recibe ningún comando en 2.5 segundos, detiene todos los motores.
- Está registrada en el watchdog del sistema para evitar bloqueos.

### Tarea `serialTask` (Core 1, prioridad 1)

- Lee el puerto serie (UART0) para recibir comandos y los parsea.
- Lee el puerto serie del GPS (UART1) y actualiza la estructura `gps` de TinyGPS++.
- Actualiza el MPU6050 cada 5 ms.
- Si el stream está activo, envía la trama `$DATA` a la frecuencia configurada.
- Las lecturas de los encoders se realizan mediante interrupciones (ISR) que incrementan los contadores de forma atómica.

---

## Funciones de diagnóstico

El firmware incluye módulos de prueba que permiten verificar el estado de cada subsistema sin necesidad de herramientas externas. Al ejecutar `TEST_IMU`, `TEST_GPS`, `TEST_ENC` o `TEST_MOT`, el sistema responde con paquetes `$DIAG` que contienen valores crudos, estadísticas y un veredicto (`PASS`, `WARN` o `FAIL`). Estos diagnósticos son útiles para la puesta en marcha y la detección de fallos en el hardware.

---

## Código fuente completo

A continuación se presenta el código completo del firmware (`robot_v8.ino`). Este archivo debe cargarse en la ESP32-S3 utilizando el IDE de Arduino o PlatformIO.

```cpp
// ===================================================================================
// ROBOT V8 — ESP32-S3 
// ===================================================================================

#include <Arduino.h>
#include <Wire.h>
#include <TinyGPSPlus.h>
#include <esp_task_wdt.h>

#define I2C_SDA  8
#define I2C_SCL  9

#define GPS_RX  16
#define GPS_TX  15

#define ENC_FL  46
#define ENC_FR   3
#define ENC_BL   4
#define ENC_BR   5
 
#define FL_EN   19    // Front Left  
#define FL_IN1  45
#define FL_IN2  48

#define FR_EN   36    // Front Right  
#define FR_IN1  38
#define FR_IN2  37

#define BL_EN   20    // Back Left   
#define BL_IN1  47
#define BL_IN2  21

#define BR_EN   35    // Back Right  
#define BR_IN1  40
#define BR_IN2  39

// -----------------------------------------------------------------------------------
// CONSTANTES
// -----------------------------------------------------------------------------------
const int     MPU_ADDR          = 0x68;
const float   PULSES_PER_REV    = 20.0f;
const float   WHEEL_DIAMETER    = 0.078f;
const float   TRACK_WIDTH       = 0.240f;
const float   WHEEL_CIRCUMFERENCE = PI * WHEEL_DIAMETER;

const int     FWD_PWM           = 200;
const int     BACK_PWM          = 200;
const int     TURN_PWM          = 220;

const unsigned long FAILSAFE_MS = 2500;   // Motores se paran si no hay comando en 2.5 s
const int     WDT_TIMEOUT_S     = 5;      // Watchdog de tarea motor en segundos

const float   FUSION_ALPHA      = 0.98f;  // Peso del giroscopio en fusión yaw

// -----------------------------------------------------------------------------------
// MPU6050 — Variables globales protegidas con mpuMux (TODOS los ejes)
// -----------------------------------------------------------------------------------
float         gyroZ_offset      = 0.0f;
float         gyroX_offset      = 0.0f;
float         gyroY_offset      = 0.0f;
volatile float yaw_angle        = 0.0f;     // integrado de gz (giro en plano horizontal)
volatile float gyro_rate_global = 0.0f;     // tasa gz filtrada (deg/s)
volatile int16_t raw_gx         = 0;
volatile int16_t raw_gy         = 0;
volatile int16_t raw_gz         = 0;
volatile int16_t raw_ax         = 0;
volatile int16_t raw_ay         = 0;
volatile int16_t raw_az         = 0;
volatile float omega_odom       = 0.0f;
unsigned long last_mpu_time     = 0;
portMUX_TYPE  mpuMux            = portMUX_INITIALIZER_UNLOCKED;

// -----------------------------------------------------------------------------------
// GPS
// -----------------------------------------------------------------------------------
TinyGPSPlus   gps;
HardwareSerial SerialGPS(1);

// -----------------------------------------------------------------------------------
// ENCODERS / MOTORES
// -----------------------------------------------------------------------------------
struct MotorState {
  volatile long    count;
  volatile uint32_t last_enc_time;
  volatile int8_t  direction;   // +1 adelante · -1 atrás · 0 parado
  float            rpm;
  portMUX_TYPE     mux;
};

MotorState mFL = {0, 0, 0, 0.0f, portMUX_INITIALIZER_UNLOCKED};
MotorState mFR = {0, 0, 0, 0.0f, portMUX_INITIALIZER_UNLOCKED};
MotorState mBL = {0, 0, 0, 0.0f, portMUX_INITIALIZER_UNLOCKED};
MotorState mBR = {0, 0, 0, 0.0f, portMUX_INITIALIZER_UNLOCKED};

int pwmFL = 0, pwmFR = 0, pwmBL = 0, pwmBR = 0;
bool motorsActive = false;

// -----------------------------------------------------------------------------------
// COLA DE COMANDOS (motor ← serial)
// -----------------------------------------------------------------------------------
enum CmdType {
  CMD_STOP,    // Parar todo
  CMD_SIMPLE,  // p L,R  — skid steer
  CMD_4W,      // m FL,FR,BL,BR
  CMD_ONE,     // o MOTOR VAL  — un solo motor
  CMD_RESET,   // r — reset encoders + yaw
  CMD_NOOP
};

struct MotorCmd {
  CmdType type;
  int     params[4];   // FL, FR, BL, BR (o L,R para CMD_SIMPLE)
};

QueueHandle_t cmdQueue;

// -----------------------------------------------------------------------------------
// ESTADO DEL STREAM
// -----------------------------------------------------------------------------------
volatile bool  streamActive    = false;
volatile uint32_t streamRateMs = 50;    // Tasa por defecto cuando se activa (ms)

// -----------------------------------------------------------------------------------
// ISR ENCODERS (IRAM, debounce 200 µs)
// -----------------------------------------------------------------------------------
void IRAM_ATTR isrFL() {
  if (mFL.direction == 0) return;
  uint32_t now = micros();
  if (now - mFL.last_enc_time > 200) {
    mFL.last_enc_time = now;
    portENTER_CRITICAL_ISR(&mFL.mux);
    mFL.count += mFL.direction;
    portEXIT_CRITICAL_ISR(&mFL.mux);
  }
}
void IRAM_ATTR isrFR() {
  if (mFR.direction == 0) return;
  uint32_t now = micros();
  if (now - mFR.last_enc_time > 200) {
    mFR.last_enc_time = now;
    portENTER_CRITICAL_ISR(&mFR.mux);
    mFR.count += mFR.direction;
    portEXIT_CRITICAL_ISR(&mFR.mux);
  }
}
void IRAM_ATTR isrBL() {
  if (mBL.direction == 0) return;
  uint32_t now = micros();
  if (now - mBL.last_enc_time > 200) {
    mBL.last_enc_time = now;
    portENTER_CRITICAL_ISR(&mBL.mux);
    mBL.count += mBL.direction;
    portEXIT_CRITICAL_ISR(&mBL.mux);
  }
}
void IRAM_ATTR isrBR() {
  if (mBR.direction == 0) return;
  uint32_t now = micros();
  if (now - mBR.last_enc_time > 200) {
    mBR.last_enc_time = now;
    portENTER_CRITICAL_ISR(&mBR.mux);
    mBR.count += mBR.direction;
    portEXIT_CRITICAL_ISR(&mBR.mux);
  }
}

// -----------------------------------------------------------------------------------
// CONTROL DE MOTORES
// -----------------------------------------------------------------------------------
void setMotor(int en, int in1, int in2, int pwm, MotorState &m) {
  pwm = constrain(pwm, -255, 255);
  portENTER_CRITICAL(&m.mux);
  m.direction = (pwm > 0) ? 1 : (pwm < 0) ? -1 : 0;
  portEXIT_CRITICAL(&m.mux);
  if (pwm > 0) {
    digitalWrite(in1, HIGH); digitalWrite(in2, LOW);  analogWrite(en,  pwm);
  } else if (pwm < 0) {
    digitalWrite(in1, LOW);  digitalWrite(in2, HIGH); analogWrite(en, -pwm);
  } else {
    digitalWrite(in1, LOW);  digitalWrite(in2, LOW);  analogWrite(en,    0);
  }
}

void applyMotors(int fl, int fr, int bl, int br) {
  setMotor(FL_EN, FL_IN1, FL_IN2, fl, mFL);
  setMotor(FR_EN, FR_IN1, FR_IN2, fr, mFR);
  setMotor(BL_EN, BL_IN1, BL_IN2, bl, mBL);
  setMotor(BR_EN, BR_IN1, BR_IN2, br, mBR);
  pwmFL = fl; pwmFR = fr; pwmBL = bl; pwmBR = br;
  motorsActive = (fl || fr || bl || br);
}

void stopAll() { applyMotors(0, 0, 0, 0); }

// -----------------------------------------------------------------------------------
// RPM + ODOMETRÍA
// -----------------------------------------------------------------------------------
void calculateRPM() {
  static long prev[4] = {0, 0, 0, 0};
  static unsigned long lastCalc = 0;
  unsigned long now = millis();
  float dt = (now - lastCalc) / 60000.0f;   // minutos para RPM directa
  if (dt <= 0 || lastCalc == 0) {
    lastCalc = now;
    portENTER_CRITICAL(&mFL.mux); prev[0] = mFL.count; portEXIT_CRITICAL(&mFL.mux);
    portENTER_CRITICAL(&mFR.mux); prev[1] = mFR.count; portEXIT_CRITICAL(&mFR.mux);
    portENTER_CRITICAL(&mBL.mux); prev[2] = mBL.count; portEXIT_CRITICAL(&mBL.mux);
    portENTER_CRITICAL(&mBR.mux); prev[3] = mBR.count; portEXIT_CRITICAL(&mBR.mux);
    return;
  }
  long cur[4];
  portENTER_CRITICAL(&mFL.mux); cur[0] = mFL.count; portEXIT_CRITICAL(&mFL.mux);
  portENTER_CRITICAL(&mFR.mux); cur[1] = mFR.count; portEXIT_CRITICAL(&mFR.mux);
  portENTER_CRITICAL(&mBL.mux); cur[2] = mBL.count; portEXIT_CRITICAL(&mBL.mux);
  portENTER_CRITICAL(&mBR.mux); cur[3] = mBR.count; portEXIT_CRITICAL(&mBR.mux);

  mFL.rpm = (cur[0] - prev[0]) / PULSES_PER_REV / dt;
  mFR.rpm = (cur[1] - prev[1]) / PULSES_PER_REV / dt;
  mBL.rpm = (cur[2] - prev[2]) / PULSES_PER_REV / dt;
  mBR.rpm = (cur[3] - prev[3]) / PULSES_PER_REV / dt;

  for (int i = 0; i < 4; i++) prev[i] = cur[i];
  lastCalc = now;

  // Odometría diferencial (fallback si ruedas delanteras no giran)
  float rpmLeft, rpmRight;
  if (abs(mFL.rpm) < 1.0f && abs(mFR.rpm) < 1.0f &&
      (abs(mBL.rpm) > 1.0f || abs(mBR.rpm) > 1.0f)) {
    rpmLeft  = mBL.rpm;
    rpmRight = mBR.rpm;
  } else {
    rpmLeft  = (mFL.rpm + mBL.rpm) / 2.0f;
    rpmRight = (mFR.rpm + mBR.rpm) / 2.0f;
  }
  float vL = (rpmLeft  * WHEEL_CIRCUMFERENCE) / 60.0f;
  float vR = (rpmRight * WHEEL_CIRCUMFERENCE) / 60.0f;
  portENTER_CRITICAL(&mpuMux);
  omega_odom = (vR - vL) / TRACK_WIDTH;
  portEXIT_CRITICAL(&mpuMux);
}

// -----------------------------------------------------------------------------------
// MPU6050 — Setup y actualización (Wire directo, sin biblioteca)
// -----------------------------------------------------------------------------------
bool setupMPU() {
  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(400000);
  delay(100);   // Dar tiempo al bus I2C y al MPU6050 para estabilizarse tras el reset

  // Verificar presencia antes de configurar
  Wire.beginTransmission(MPU_ADDR);
  if (Wire.endTransmission() != 0) {
    Serial.println(F("$SYS,MPU_NOT_FOUND*00"));
    return false;
  }

  // Wake up (salir de sleep)
  Wire.beginTransmission(MPU_ADDR); Wire.write(0x6B); Wire.write(0x00); Wire.endTransmission(true);
  delay(50);   // El MPU6050 necesita ~50 ms tras despertar para estabilizar el oscilador

  // Gyro ±500 °/s → sensibilidad 65.5 LSB/(°/s)
  Wire.beginTransmission(MPU_ADDR); Wire.write(0x1B); Wire.write(0x08); Wire.endTransmission(true);
  // DLPF 20 Hz
  Wire.beginTransmission(MPU_ADDR); Wire.write(0x1A); Wire.write(0x04); Wire.endTransmission(true);
  delay(10);

  Serial.println(F("$SYS,MPU_CONFIGURED*00"));
  return true;
}

void calibrateMPU(bool sendResult = true) {
  if (sendResult) Serial.println(F("$SYS,CAL_START,NO_MOVER*00"));
  long sumX = 0, sumY = 0, sumZ = 0;
  for (int i = 0; i < 2000; i++) {
    Wire.beginTransmission(MPU_ADDR); Wire.write(0x43); Wire.endTransmission(false);
    Wire.requestFrom(MPU_ADDR, 6, true);   // 0x43..0x48 = GYRO_XOUT, YOUT, ZOUT
    int16_t gx = Wire.read() << 8 | Wire.read();
    int16_t gy = Wire.read() << 8 | Wire.read();
    int16_t gz = Wire.read() << 8 | Wire.read();
    sumX += gx; sumY += gy; sumZ += gz;
    delay(1);
  }
  gyroX_offset = sumX / 2000.0f;
  gyroY_offset = sumY / 2000.0f;
  gyroZ_offset = sumZ / 2000.0f;
  portENTER_CRITICAL(&mpuMux); yaw_angle = 0.0f; portEXIT_CRITICAL(&mpuMux);
  last_mpu_time = micros();
  if (sendResult) {
    char buf[96];
    snprintf(buf, sizeof(buf), "$SYS,CAL_DONE,offX=%.2f,offY=%.2f,offZ=%.2f*00",
             gyroX_offset, gyroY_offset, gyroZ_offset);
    Serial.println(buf);
  }
}

void updateMPU() {
  // Lectura en burst de los 14 bytes contiguos: ACCEL_XOUT(0x3B)..GYRO_ZOUT(0x48)
  // Esto incluye ax,ay,az,temp,gx,gy,gz en una sola transacción I2C — más eficiente
  // y evita desincronización entre lecturas de distintos sensores
  Wire.beginTransmission(MPU_ADDR); Wire.write(0x3B); Wire.endTransmission(false);
  Wire.requestFrom(MPU_ADDR, 14, true);
  if (Wire.available() < 14) return;

  int16_t ax = Wire.read() << 8 | Wire.read();
  int16_t ay = Wire.read() << 8 | Wire.read();
  int16_t az = Wire.read() << 8 | Wire.read();
  Wire.read(); Wire.read();   // TEMP_OUT — descartado (no usado por ahora)
  int16_t gx = Wire.read() << 8 | Wire.read();
  int16_t gy = Wire.read() << 8 | Wire.read();
  int16_t gz = Wire.read() << 8 | Wire.read();

  portENTER_CRITICAL(&mpuMux);
  raw_ax = ax; raw_ay = ay; raw_az = az;
  raw_gx = gx; raw_gy = gy; raw_gz = gz;
  portEXIT_CRITICAL(&mpuMux);

  unsigned long now = micros();
  float dt = (now - last_mpu_time) / 1000000.0f;
  last_mpu_time = now;

  // Solo Z se integra a yaw (giro en plano horizontal del robot).
  // X e Y quedan disponibles crudos en la trama para detectar inclinación/vuelco.
  float rate = (gz - gyroZ_offset) / 65.5f;
  if (abs(rate) > 0.2f) {
    portENTER_CRITICAL(&mpuMux);
    yaw_angle += rate * dt;
    gyro_rate_global = rate;
    portEXIT_CRITICAL(&mpuMux);
  } else {
    portENTER_CRITICAL(&mpuMux);
    gyro_rate_global = 0.0f;
    portEXIT_CRITICAL(&mpuMux);
  }
}

// -----------------------------------------------------------------------------------
// DIAGNÓSTICO IMU
// -----------------------------------------------------------------------------------
void testIMU() {
  Serial.println(F("$DIAG,IMU_START*00"));
  Wire.beginTransmission(MPU_ADDR);
  int err = Wire.endTransmission();
  if (err != 0) {
    Serial.println(F("$DIAG,IMU_FAIL,no_device*00"));
    return;
  }
  Wire.beginTransmission(MPU_ADDR); Wire.write(0x75); Wire.endTransmission(false);
  Wire.requestFrom(MPU_ADDR, 1, true);
  uint8_t whoami = Wire.available() ? Wire.read() : 0;
  char buf[160];
  snprintf(buf, sizeof(buf), "$DIAG,IMU_WHO_AM_I,0x%02X*00", whoami);
  Serial.println(buf);

  // Burst read de los 6 ejes (igual que updateMPU) — 10 muestras para estadística
  long sAx=0, sAy=0, sAz=0, sGx=0, sGy=0, sGz=0;
  int16_t lastAx=0, lastAy=0, lastAz=0, lastGx=0, lastGy=0, lastGz=0;
  for (int i = 0; i < 10; i++) {
    Wire.beginTransmission(MPU_ADDR); Wire.write(0x3B); Wire.endTransmission(false);
    Wire.requestFrom(MPU_ADDR, 14, true);
    if (Wire.available() < 14) continue;
    int16_t ax = Wire.read() << 8 | Wire.read();
    int16_t ay = Wire.read() << 8 | Wire.read();
    int16_t az = Wire.read() << 8 | Wire.read();
    Wire.read(); Wire.read();
    int16_t gx = Wire.read() << 8 | Wire.read();
    int16_t gy = Wire.read() << 8 | Wire.read();
    int16_t gz = Wire.read() << 8 | Wire.read();
    sAx += ax; sAy += ay; sAz += az;
    sGx += gx; sGy += gy; sGz += gz;
    lastAx=ax; lastAy=ay; lastAz=az; lastGx=gx; lastGy=gy; lastGz=gz;
    delay(10);
  }

  // Acelerómetro: rango por defecto ±2g → sensibilidad 16384 LSB/g
  snprintf(buf, sizeof(buf),
           "$DIAG,IMU_ACCEL_RAW,ax=%ld,ay=%ld,az=%ld*00", sAx/10, sAy/10, sAz/10);
  Serial.println(buf);
  snprintf(buf, sizeof(buf),
           "$DIAG,IMU_ACCEL_G,ax=%.3f,ay=%.3f,az=%.3f*00",
           (sAx/10) / 16384.0f, (sAy/10) / 16384.0f, (sAz/10) / 16384.0f);
  Serial.println(buf);

  // Giroscopio: rango configurado ±500°/s → sensibilidad 65.5 LSB/(°/s)
  snprintf(buf, sizeof(buf),
           "$DIAG,IMU_GYRO_RAW,gx=%ld,gy=%ld,gz=%ld*00", sGx/10, sGy/10, sGz/10);
  Serial.println(buf);
  snprintf(buf, sizeof(buf),
           "$DIAG,IMU_GYRO_DPS,gx=%.2f,gy=%.2f,gz=%.2f*00",
           (sGx/10 - gyroX_offset) / 65.5f,
           (sGy/10 - gyroY_offset) / 65.5f,
           (sGz/10 - gyroZ_offset) / 65.5f);
  Serial.println(buf);

  // az en reposo debería rondar ~16384 (1g) si el robot está sobre superficie plana.
  // Si az ronda 0, la IMU probablemente está montada de canto o no responde bien.
  bool az_plausible = (abs(sAz/10) > 5000);
  snprintf(buf, sizeof(buf), "$DIAG,IMU_LEVEL_CHECK,az_plausible=%d*00", az_plausible ? 1 : 0);
  Serial.println(buf);

  snprintf(buf, sizeof(buf), "$DIAG,IMU_YAW_NOW,%.3f,rate=%.3f*00", yaw_angle, gyro_rate_global);
  Serial.println(buf);

  bool pass = (whoami == 0x68) && az_plausible;
  Serial.println(pass ? F("$DIAG,IMU_PASS*00") : F("$DIAG,IMU_WARN,revisar_montaje_o_calibracion*00"));
}

// -----------------------------------------------------------------------------------
// DIAGNÓSTICO GPS
// -----------------------------------------------------------------------------------
void testGPS() {
  Serial.println(F("$DIAG,GPS_START*00"));
  char buf[200];
  snprintf(buf, sizeof(buf), "$DIAG,GPS_PINS,RX=%d,TX=%d,baud=9600*00", GPS_RX, GPS_TX);
  Serial.println(buf);

  // --- Paso 1: escuchar 9600 baud (configuración actual) y mostrar bytes crudos ---
  unsigned long t0 = millis();
  int chars = 0;
  char rawSample[41]; int rawIdx = 0;
  while (millis() - t0 < 2000) {
    while (SerialGPS.available()) {
      char c = SerialGPS.read();
      gps.encode(c);
      chars++;
      if (rawIdx < 40) rawSample[rawIdx++] = c;
    }
  }
  rawSample[rawIdx] = '\0';
  snprintf(buf, sizeof(buf), "$DIAG,GPS_CHARS_2S,%d*00", chars);
  Serial.println(buf);

  if (chars > 0) {
    // Mostrar muestra cruda — debería verse algo como "$GPGGA,...." o "$GNRMC,...."
    // Reemplazamos caracteres no imprimibles para no romper el protocolo de trama
    for (int i = 0; i < rawIdx; i++) {
      if (rawSample[i] < 32 || rawSample[i] > 126) rawSample[i] = '.';
    }
    snprintf(buf, sizeof(buf), "$DIAG,GPS_RAW_SAMPLE,%s*00", rawSample);
    Serial.println(buf);

    snprintf(buf, sizeof(buf),
             "$DIAG,GPS_STATUS,sats=%d,valid=%d,fix_age=%lu*00",
             (int)gps.satellites.value(),
             (int)gps.location.isValid(),
             gps.location.age());
    Serial.println(buf);
    if (gps.location.isValid()) {
      snprintf(buf, sizeof(buf),
               "$DIAG,GPS_POS,lat=%.6f,lon=%.6f,kmph=%.2f*00",
               gps.location.lat(), gps.location.lng(), gps.speed.kmph());
      Serial.println(buf);
      Serial.println(F("$DIAG,GPS_PASS*00"));
    } else {
      Serial.println(F("$DIAG,GPS_WARN,recibe_datos_sin_fix,esperar_cielo_abierto*00"));
    }
    return;
  }

  // --- Paso 2: si no hubo nada a 9600, probar otros baudrates comunes ---
  // Esto detecta si el módulo viene configurado a un baud distinto de fábrica
  Serial.println(F("$DIAG,GPS_0CHARS,probando_otros_baudrates*00"));
  const long bauds[] = {4800, 9600, 19200, 38400, 57600, 115200};
  long foundBaud = 0;
  for (int b = 0; b < 6; b++) {
    SerialGPS.end();
    delay(20);
    SerialGPS.begin(bauds[b], SERIAL_8N1, GPS_RX, GPS_TX);
    delay(150);
    int c2 = 0;
    unsigned long tb = millis();
    while (millis() - tb < 300) {
      while (SerialGPS.available()) { SerialGPS.read(); c2++; }
    }
    snprintf(buf, sizeof(buf), "$DIAG,GPS_BAUD_TEST,%ld,chars=%d*00", bauds[b], c2);
    Serial.println(buf);
    if (c2 > 5 && foundBaud == 0) foundBaud = bauds[b];
  }
  // Restaurar a 9600 (el firmware solo opera a 9600)
  SerialGPS.end();
  delay(20);
  SerialGPS.begin(9600, SERIAL_8N1, GPS_RX, GPS_TX);

  if (foundBaud > 0) {
    snprintf(buf, sizeof(buf),
             "$DIAG,GPS_FAIL,modulo_responde_a_%ld_no_9600,reconfigurar_modulo_o_firmware*00",
             foundBaud);
    Serial.println(buf);
  } else {
    Serial.println(F("$DIAG,GPS_FAIL,sin_respuesta_en_ningun_baudrate*00"));
    Serial.println(F("$DIAG,GPS_HINT,verificar_TX_modulo_a_RX_GPIO16,VCC,GND*00"));
  }
}

// -----------------------------------------------------------------------------------
// DIAGNÓSTICO ENCODERS
// -----------------------------------------------------------------------------------
void testENC() {
  Serial.println(F("$DIAG,ENC_START*00"));

  // --- Paso 1: nivel lógico en reposo (sin mover) ---
  // Permite detectar si el pin está flotando, pegado a GND o a VCC
  char buf[160];
  snprintf(buf, sizeof(buf),
    "$DIAG,ENC_PINS_IDLE,FL=%d,FR=%d,BL=%d,BR=%d*00",
    digitalRead(ENC_FL), digitalRead(ENC_FR),
    digitalRead(ENC_BL), digitalRead(ENC_BR));
  Serial.println(buf);

  // --- Paso 2: reset de contadores ---
  portENTER_CRITICAL(&mFL.mux); mFL.count = 0; portEXIT_CRITICAL(&mFL.mux);
  portENTER_CRITICAL(&mFR.mux); mFR.count = 0; portEXIT_CRITICAL(&mFR.mux);
  portENTER_CRITICAL(&mBL.mux); mBL.count = 0; portEXIT_CRITICAL(&mBL.mux);
  portENTER_CRITICAL(&mBR.mux); mBR.count = 0; portEXIT_CRITICAL(&mBR.mux);

  // --- Paso 3: test encoder individual por motor ---
  // Gira cada motor 1.5 s con PWM alto para dar tiempo a generar pulsos
  // incluso con ruedas en el aire o con carga
  const char* labels[] = {"FL", "FR", "BL", "BR"};
  const int   fls[] = {180,   0,   0,   0};
  const int   frs[] = {  0, 180,   0,   0};
  const int   bls[] = {  0,   0, 180,   0};
  const int   brs[] = {  0,   0,   0, 180};
  MotorState* motors[] = {&mFL, &mFR, &mBL, &mBR};

  long counts[4] = {0};
  for (int i = 0; i < 4; i++) {
    portENTER_CRITICAL(&motors[i]->mux); motors[i]->count = 0; portEXIT_CRITICAL(&motors[i]->mux);
    applyMotors(fls[i], frs[i], bls[i], brs[i]);
    delay(1500);
    stopAll();
    delay(300);
    portENTER_CRITICAL(&motors[i]->mux); counts[i] = motors[i]->count; portEXIT_CRITICAL(&motors[i]->mux);
    snprintf(buf, sizeof(buf), "$DIAG,ENC_%s,pulses=%ld,ok=%d*00",
             labels[i], counts[i], counts[i] > 3 ? 1 : 0);
    Serial.println(buf);
  }

  // --- Paso 4: resumen ---
  int ok_count = 0;
  for (int i = 0; i < 4; i++) if (counts[i] > 3) ok_count++;
  snprintf(buf, sizeof(buf), "$DIAG,ENC_SUMMARY,ok=%d/4,FL=%ld,FR=%ld,BL=%ld,BR=%ld*00",
           ok_count, counts[0], counts[1], counts[2], counts[3]);
  Serial.println(buf);

  if (ok_count == 4) {
    Serial.println(F("$DIAG,ENC_PASS*00"));
  } else if (ok_count == 0) {
    Serial.println(F("$DIAG,ENC_FAIL,todos_cero,verificar_alimentacion_y_cables*00"));
  } else {
    Serial.println(F("$DIAG,ENC_WARN,algunos_cero*00"));
  }
}

// -----------------------------------------------------------------------------------
// DIAGNÓSTICO MOTORES (sin encoders — solo confirma que giran)
// -----------------------------------------------------------------------------------
void testMOT() {
  Serial.println(F("$DIAG,MOT_START*00"));
  const char* labels[] = {"FL", "FR", "BL", "BR"};
  int fls[]  = {FWD_PWM, 0, 0, 0};
  int frs[]  = {0, FWD_PWM, 0, 0};
  int bls[]  = {0, 0, FWD_PWM, 0};
  int brs[]  = {0, 0, 0, FWD_PWM};
  for (int i = 0; i < 4; i++) {
    applyMotors(fls[i], frs[i], bls[i], brs[i]);
    char buf[64];
    snprintf(buf, sizeof(buf), "$DIAG,MOT_%s,pwm=%d*00", labels[i], FWD_PWM);
    Serial.println(buf);
    delay(700);
    stopAll();
    delay(300);
  }
  Serial.println(F("$DIAG,MOT_DONE*00"));
}

// -----------------------------------------------------------------------------------
// TRAMA $DATA — generación con checksum XOR
// -----------------------------------------------------------------------------------
void sendDataFrame(uint32_t &seq) {
  // Leer estado de forma atómica
  long c0, c1, c2, c3;
  float r0, r1, r2, r3;
  portENTER_CRITICAL(&mFL.mux); c0 = mFL.count; r0 = mFL.rpm; portEXIT_CRITICAL(&mFL.mux);
  portENTER_CRITICAL(&mFR.mux); c1 = mFR.count; r1 = mFR.rpm; portEXIT_CRITICAL(&mFR.mux);
  portENTER_CRITICAL(&mBL.mux); c2 = mBL.count; r2 = mBL.rpm; portEXIT_CRITICAL(&mBL.mux);
  portENTER_CRITICAL(&mBR.mux); c3 = mBR.count; r3 = mBR.rpm; portEXIT_CRITICAL(&mBR.mux);

  float yaw_copy, omega_copy;
  int16_t ax_c, ay_c, az_c, gx_c, gy_c, gz_c;
  portENTER_CRITICAL(&mpuMux);
  yaw_copy   = yaw_angle;
  omega_copy = omega_odom;
  ax_c = raw_ax; ay_c = raw_ay; az_c = raw_az;
  gx_c = raw_gx; gy_c = raw_gy; gz_c = raw_gz;
  portEXIT_CRITICAL(&mpuMux);

  // Fusión yaw (gyro + odometría)
  static float yaw_fused = 0.0f;
  static float yaw_odom  = 0.0f;
  static unsigned long lastFusion = 0;
  static bool fusionInit = false;
  unsigned long now = millis();
  if (!fusionInit) {
    yaw_fused = yaw_copy;
    yaw_odom  = yaw_copy;
    lastFusion = now;
    fusionInit = true;
  }
  float dt_f = (now - lastFusion) / 1000.0f;
  lastFusion = now;
  yaw_odom += omega_copy * 57.2958f * dt_f;
  yaw_fused = FUSION_ALPHA * yaw_copy + (1.0f - FUSION_ALPHA) * yaw_odom;

  // GPS (sin bloquear)
  float lat = gps.location.isValid() ? gps.location.lat()  : 0.0f;
  float lon = gps.location.isValid() ? gps.location.lng()  : 0.0f;
  int   sats = (int)gps.satellites.value();

  char buf[280];
  int len = snprintf(buf, sizeof(buf),
    "$DATA,%lu,%lu,"            // seq, millis
    "%ld,%ld,%ld,%ld,"          // cFL,cFR,cBL,cBR
    "%.2f,%.2f,%.2f,%.2f,"     // rFL,rFR,rBL,rBR
    "%.3f,"                     // yaw_fused
    "%d,%d,%d,"                // raw_ax,raw_ay,raw_az
    "%d,%d,%d,"                // raw_gx,raw_gy,raw_gz
    "%.6f,%.6f,%d,"            // lat, lon, sats
    "%d,%d,%d,%d",             // pwmFL,pwmFR,pwmBL,pwmBR
    (unsigned long)seq++, now,
    c0, c1, c2, c3,
    r0, r1, r2, r3,
    yaw_fused,
    ax_c, ay_c, az_c,
    gx_c, gy_c, gz_c,
    lat, lon, sats,
    pwmFL, pwmFR, pwmBL, pwmBR
  );

  uint8_t cs = 0;
  for (int i = 1; i < len; i++) cs ^= (uint8_t)buf[i];
  Serial.print(buf); Serial.print('*');
  if (cs < 0x10) Serial.print('0');
  Serial.println(cs, HEX);
}

// -----------------------------------------------------------------------------------
// TAREA MOTOR — Core 0, Priority 2
// -----------------------------------------------------------------------------------
void motorTask(void *param) {
  esp_task_wdt_add(NULL);  // Registrar esta tarea en el WDT
  unsigned long lastCmd = millis();
  MotorCmd cmd;
  while (1) {
    esp_task_wdt_reset();
    if (xQueueReceive(cmdQueue, &cmd, pdMS_TO_TICKS(5)) == pdTRUE) {
      switch (cmd.type) {
        case CMD_STOP:   stopAll(); break;
        case CMD_SIMPLE: applyMotors(cmd.params[0], cmd.params[1],
                                     cmd.params[0], cmd.params[1]); break;
        case CMD_4W:     applyMotors(cmd.params[0], cmd.params[1],
                                     cmd.params[2], cmd.params[3]); break;
        case CMD_ONE: {
          int idx = cmd.params[0], val = cmd.params[1];
          int fl = pwmFL, fr = pwmFR, bl = pwmBL, br = pwmBR;
          if      (idx == 0) fl = val;
          else if (idx == 1) fr = val;
          else if (idx == 2) bl = val;
          else if (idx == 3) br = val;
          applyMotors(fl, fr, bl, br);
          break;
        }
        case CMD_RESET:
          portENTER_CRITICAL(&mFL.mux); mFL.count = 0; portEXIT_CRITICAL(&mFL.mux);
          portENTER_CRITICAL(&mFR.mux); mFR.count = 0; portEXIT_CRITICAL(&mFR.mux);
          portENTER_CRITICAL(&mBL.mux); mBL.count = 0; portEXIT_CRITICAL(&mBL.mux);
          portENTER_CRITICAL(&mBR.mux); mBR.count = 0; portEXIT_CRITICAL(&mBR.mux);
          portENTER_CRITICAL(&mpuMux); yaw_angle = 0.0f; portEXIT_CRITICAL(&mpuMux);
          break;
        default: break;
      }
      lastCmd = millis();
    }
    // Failsafe: parar si no hay comandos en FAILSAFE_MS
    if (motorsActive && (millis() - lastCmd > FAILSAFE_MS)) {
      stopAll();
    }
  }
}

// -----------------------------------------------------------------------------------
// PARSER DE COMANDOS — llamado desde serialTask
// -----------------------------------------------------------------------------------
// Protocolo (cada línea termina en '\n'):
//
//  MOVIMIENTO BÁSICO:
//    w              → adelante (FWD_PWM)
//    x              → atrás (BACK_PWM)
//    a              → giro izquierda (TURN_PWM)
//    d              → giro derecha (TURN_PWM)
//    0              → STOP
//
//  CONTROL AVANZADO:
//    p L,R          → skid-steer independiente  ej: "p 150,-150"
//    m FL,FR,BL,BR  → 4WD independiente         ej: "m 200,200,200,200"
//    o MOTOR VAL    → un motor solo              ej: "o fl 150"
//    r              → reset encoders + yaw
//
//  STREAM DE DATOS (bajo demanda — ancho de banda libre por defecto):
//    DATA rate MS   → activar stream, tasa en ms  ej: "DATA rate 50"
//    DATA stop      → desactivar stream
//
//  DIAGNÓSTICOS (responden con paquetes $DIAG):
//    TEST_IMU       → test MPU6050
//    TEST_GPS       → test GPS (2 s de escucha)
//    TEST_ENC       → test encoders (1 s movimiento)
//    TEST_MOT       → test motores individuales
//    TEST_ALL       → todos los tests
//    CAL_IMU        → recalibrar offset giroscopio (no mover!)
//    SNAPSHOT       → trama $DATA única sin activar stream
//    HELP           → menú de ayuda
// -----------------------------------------------------------------------------------
void parseCommand(const char *line) {
  MotorCmd cmd;
  cmd.type = CMD_NOOP;
  bool valid = true;
  size_t len = strlen(line);

  // --- Movimiento básico ---
  if (len == 1 && line[0] == '0') {
    cmd.type = CMD_STOP;
  } else if (len == 1 && line[0] == 'w') {
    cmd.type = CMD_SIMPLE; cmd.params[0] = FWD_PWM;  cmd.params[1] = FWD_PWM;
  } else if (len == 1 && line[0] == 'x') {
    cmd.type = CMD_SIMPLE; cmd.params[0] = -BACK_PWM; cmd.params[1] = -BACK_PWM;
  } else if (len == 1 && line[0] == 'a') {
    cmd.type = CMD_SIMPLE; cmd.params[0] = -TURN_PWM; cmd.params[1] = TURN_PWM;
  } else if (len == 1 && line[0] == 'd') {
    cmd.type = CMD_SIMPLE; cmd.params[0] = TURN_PWM;  cmd.params[1] = -TURN_PWM;
  } else if (len == 1 && line[0] == 'r') {
    cmd.type = CMD_RESET;

  // --- Control avanzado ---
  } else if (line[0] == 'p' && len > 1) {
    int L = 0, R = 0;
    if (sscanf(line + 2, "%d,%d", &L, &R) == 2) {
      cmd.type = CMD_SIMPLE; cmd.params[0] = L; cmd.params[1] = R;
    } else valid = false;
  } else if (line[0] == 'm' && len > 1) {
    int fl, fr, bl, br;
    if (sscanf(line + 2, "%d,%d,%d,%d", &fl, &fr, &bl, &br) == 4) {
      cmd.type = CMD_4W;
      cmd.params[0] = fl; cmd.params[1] = fr;
      cmd.params[2] = bl; cmd.params[3] = br;
    } else valid = false;
  } else if (line[0] == 'o' && len > 1) {
    char motor[4]; int val;
    if (sscanf(line + 2, "%3s %d", motor, &val) == 2) {
      // lowercase
      for (int i = 0; motor[i]; i++) motor[i] = tolower(motor[i]);
      int idx = -1;
      if (strcmp(motor, "fl") == 0) idx = 0;
      else if (strcmp(motor, "fr") == 0) idx = 1;
      else if (strcmp(motor, "bl") == 0) idx = 2;
      else if (strcmp(motor, "br") == 0) idx = 3;
      if (idx >= 0) { cmd.type = CMD_ONE; cmd.params[0] = idx; cmd.params[1] = val; }
      else valid = false;
    } else valid = false;

  // --- Stream bajo demanda ---
  } else if (strncmp(line, "DATA rate ", 10) == 0) {
    uint32_t rate = atoi(line + 10);
    if (rate >= 10 && rate <= 5000) {
      streamRateMs = rate;
      streamActive = true;
      Serial.print(F("$SYS,STREAM_ON,ms="));
      Serial.print(rate); Serial.println(F("*00"));
    } else valid = false;
  } else if (strcmp(line, "DATA stop") == 0) {
    streamActive = false;
    Serial.println(F("$SYS,STREAM_OFF*00"));

  // --- Diagnósticos ---
  } else if (strcmp(line, "TEST_IMU")  == 0) { testIMU(); return;
  } else if (strcmp(line, "TEST_GPS")  == 0) { testGPS(); return;
  } else if (strcmp(line, "TEST_ENC")  == 0) { testENC(); return;
  } else if (strcmp(line, "TEST_MOT")  == 0) { testMOT(); return;
  } else if (strcmp(line, "TEST_ALL")  == 0) {
    testIMU(); testGPS(); testENC(); testMOT();
    Serial.println(F("$DIAG,ALL_DONE*00"));
    return;
  } else if (strcmp(line, "CAL_IMU")  == 0) {
    stopAll();
    calibrateMPU(true);
    return;
  } else if (strcmp(line, "SNAPSHOT") == 0) {
    static uint32_t snap_seq = 0xFFFF0000;
    sendDataFrame(snap_seq);
    return;
  } else if (strcmp(line, "HELP")     == 0) {
    Serial.println(F("$SYS,HELP_START*00"));
    Serial.println(F("  w/x/a/d/0    Movimiento basico"));
    Serial.println(F("  p L,R        Skid steer"));
    Serial.println(F("  m FL,FR,BL,BR  4WD independiente"));
    Serial.println(F("  o MOTOR VAL  Un motor (fl/fr/bl/br)"));
    Serial.println(F("  r            Reset encoders + yaw"));
    Serial.println(F("  DATA rate MS Activar stream (ms>=10)"));
    Serial.println(F("  DATA stop    Detener stream"));
    Serial.println(F("  SNAPSHOT     Trama unica $DATA"));
    Serial.println(F("  TEST_IMU / TEST_GPS / TEST_ENC / TEST_MOT / TEST_ALL"));
    Serial.println(F("  CAL_IMU      Recalibrar gyro (no mover!)"));
    Serial.println(F("$SYS,HELP_END*00"));
    return;
  } else {
    valid = false;
  }

  if (!valid) {
    Serial.println(F("$SYS,CMD_UNKNOWN*00"));
    return;
  }
  if (cmd.type != CMD_NOOP) {
    xQueueSend(cmdQueue, &cmd, 0);
  }
}

// -----------------------------------------------------------------------------------
// TAREA SERIAL — Core 1, Priority 1
// -----------------------------------------------------------------------------------
void serialTask(void *param) {
  uint32_t seq = 0;
  unsigned long lastStream   = 0;
  unsigned long lastMPUUpdate = 0;
  char lineBuf[128];
  int  lineIdx = 0;

  while (1) {
    // --- Procesar GPS ---
    while (SerialGPS.available()) gps.encode(SerialGPS.read());

    // --- Actualizar MPU cada 5 ms ---
    unsigned long now = millis();
    if (now - lastMPUUpdate >= 5) {
      lastMPUUpdate = now;
      updateMPU();
    }

    // --- Leer comandos por Serial ---
    while (Serial.available()) {
      char c = Serial.read();
      if (c == '\r') continue;
      if (c == '\n') {
        lineBuf[lineIdx] = '\0';
        if (lineIdx > 0) parseCommand(lineBuf);
        lineIdx = 0;
      } else if (lineIdx < (int)(sizeof(lineBuf) - 1)) {
        lineBuf[lineIdx++] = c;
      }
    }

    // --- Stream bajo demanda ---
    now = millis();
    if (streamActive && (now - lastStream >= streamRateMs)) {
      lastStream = now;
      calculateRPM();
      sendDataFrame(seq);
    }

    taskYIELD();
  }
}

// -----------------------------------------------------------------------------------
// SETUP
// -----------------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(200);   // Dar tiempo al USB para estar listo antes de cualquier println

  // Configurar WDT — IDF v5.1+ requiere esp_task_wdt_config_t
  const esp_task_wdt_config_t wdt_cfg = {
    .timeout_ms    = WDT_TIMEOUT_S * 1000,
    .idle_core_mask = 0,
    .trigger_panic  = true
  };
  esp_task_wdt_init(&wdt_cfg);

  // Pines de motor
  const int motorPins[] = {
    FL_EN, FL_IN1, FL_IN2,
    FR_EN, FR_IN1, FR_IN2,
    BL_EN, BL_IN1, BL_IN2,
    BR_EN, BR_IN1, BR_IN2
  };
  for (int p : motorPins) { pinMode(p, OUTPUT); digitalWrite(p, LOW); }
  stopAll();

  // GPS — reportar pines para verificación
  SerialGPS.setRxBufferSize(512);
  SerialGPS.begin(9600, SERIAL_8N1, GPS_RX, GPS_TX);
  Serial.print(F("$SYS,GPS_INIT,RX="));
  Serial.print(GPS_RX); Serial.print(F(",TX=")); Serial.println(GPS_TX);

  // MPU6050 — esperar estabilización antes de calibrar
  bool mpuOk = setupMPU();
  if (mpuOk) {
    delay(200);         // Estabilización extra antes de las 2000 lecturas de calibración
    calibrateMPU(false);
  }

  // Encoders
  pinMode(ENC_FL, INPUT_PULLUP); attachInterrupt(digitalPinToInterrupt(ENC_FL), isrFL, RISING);
  pinMode(ENC_FR, INPUT_PULLUP); attachInterrupt(digitalPinToInterrupt(ENC_FR), isrFR, RISING);
  pinMode(ENC_BL, INPUT_PULLUP); attachInterrupt(digitalPinToInterrupt(ENC_BL), isrBL, RISING);
  pinMode(ENC_BR, INPUT_PULLUP); attachInterrupt(digitalPinToInterrupt(ENC_BR), isrBR, RISING);

  // Cola y tareas FreeRTOS
  cmdQueue = xQueueCreate(10, sizeof(MotorCmd));
  xTaskCreatePinnedToCore(motorTask,  "motor",  4096, NULL, 2, NULL, 0);
  xTaskCreatePinnedToCore(serialTask, "serial", 6144, NULL, 1, NULL, 1);

  Serial.println(F("$SYS,ROBOT_V8_READY*00"));
  Serial.println(F("$SYS,PINES_V12_ACTIVOS,FL=19,BL=20,FR=36,BR=35*00"));
  Serial.println(F("$SYS,STREAM_OFF_DEFAULT,send:DATA_rate_MS*00"));
}

// -----------------------------------------------------------------------------------
// loop() queda vacío — todo el trabajo lo hacen las tareas FreeRTOS
// -----------------------------------------------------------------------------------
void loop() {
  vTaskDelay(portMAX_DELAY);
}