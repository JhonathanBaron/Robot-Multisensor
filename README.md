# Plataforma Robótica Multisensor para Exploración Terrestre 

Este repositorio documenta el diseño, implementación y verificación de un vehículo teleoperado (rover) construido como plataforma de pruebas para el clúster distribuido descrito en la tesis. El robot integra una amplia gama de sensores para percepción del entorno y estado interno, y está diseñado para transmitir flujos masivos de datos a una estación de procesamiento externa (clúster Beowulf) a través de un enlace Wi-Fi.

## Arquitectura general

El sistema se divide en dos subsistemas de procesamiento:

- **ESP32-S3**: Microcontrolador de bajo consumo encargado de la lectura de sensores de baja velocidad (IMU MPU6050, encoders ópticos, GPS NEO-6M) y el control de los motores DC mediante señales PWM. Comunica los datos al procesador principal vía UART.

- **Raspberry Pi 3**: Computadora de placa única que actúa como puerta de enlace. Captura los datos de los sensores de alto ancho de banda (LiDAR RPLIDAR A1, Kinect Xbox 360, dos cámaras web USB), los sincroniza temporalmente con la telemetría de la ESP32 y los transmite al clúster mediante un socket WebSocket.

## Sensores integrados

| Sensor | Tipo de dato | Frecuencia | Propósito |
|--------|--------------|------------|-----------|
| IMU MPU6050 | Aceleración, velocidad angular | 200 Hz | Estimación de inclinación y orientación |
| Encoders ópticos | Conteo de pulsos | Interrupción | Odometría y velocidad lineal |
| GPS NEO-6M | Latitud, longitud, velocidad | 1 Hz | Posicionamiento global |
| LiDAR RPLIDAR A1 | Nube de puntos 2D | 5-10 Hz | Mapeo y detección de obstáculos perimetrales |
| Kinect Xbox 360 | Imagen RGB + mapa de profundidad | 30 Hz | Percepción volumétrica y evasión de obstáculos |
| Cámaras web (x2) | Video 720p | 30 Hz | Visión para teleoperación |

## Estructura del repositorio

- `codigos_pruebas_individuales/`: Scripts para verificar el funcionamiento de cada sensor de forma aislada.
- `esp32_firmware.md`: Código completo del firmware para la ESP32-S3 (control de motores y lectura de sensores).
- `raspberry_adquisicion.md`: Código de la Raspberry Pi para adquisición, sincronización y transmisión de datos.

## Requisitos de software

- Raspberry Pi: Ubuntu Server / Raspberry Pi OS, Python 3, librerías: `rplidar`, `opencv-python`, `libfreenect`, `pyserial`, `websockets`.
- ESP32-S3: Arduino IDE o PlatformIO, librerías: `Wire`, `MPU6050`, `TinyGPS++`.

