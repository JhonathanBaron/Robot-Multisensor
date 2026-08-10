# Adquisición y Transmisión de Datos en la Raspberry Pi

Este archivo documenta el script que se ejecuta en la **Raspberry Pi 3** a bordo del vehículo. La Raspberry actúa como **puerta de enlace** (*gateway*) entre los sensores y el clúster Beowulf. Sus funciones principales son:

- Capturar datos de los sensores de alto ancho de banda:
  - Dos cámaras USB (HP) con resolución reducida y compresión JPEG.
  - Sensor Kinect Xbox 360 (imagen RGB y mapa de profundidad).
  - LiDAR RPLIDAR A1 (nube de puntos 2D).
- Recibir la telemetría de la ESP32-S3 (IMU, encoders, GPS) a través del puerto serie (UART).
- Empaquetar y transmitir todos los flujos al clúster mediante un **único socket WebSocket**, utilizando prefijos de 4 bytes para identificar cada tipo de dato.
- Recibir comandos de movimiento desde el clúster y reenviarlos a la ESP32 para el control de los motores.

El script está diseñado para ser ligero y estable, haciendo uso de hilos (*threads*) para manejar cada sensor de forma concurrente.

---

## Requisitos de software

- **Sistema operativo**: Raspberry Pi OS (o Ubuntu Server) con Python 3.7+.
- **Librerías Python** (instalar con `pip`):
  - `opencv-python` (cv2)
  - `websocket-client`
  - `pyserial`
  - `numpy`
  - `rplidar` (librería para el LiDAR RPLIDAR)
  - `freenect` (para Kinect Xbox 360)
  - `logging` (incluido en la biblioteca estándar)

**Instalación rápida**:

    sudo apt update
    sudo apt install python3-pip python3-opencv
    pip3 install websocket-client pyserial numpy rplidar freenect

---

## Estructura del código

| Función / Hilo | Descripción |
|----------------|-------------|
| `shared_camera_sender()` | Captura desde una cámara USB (HP) y envía imágenes con prefijo `CAM1` o `CAM2`. |
| `kinect_sender()` | Captura el video RGB (prefijo `XBOX`) y el mapa de profundidad (prefijo `DEPT`) del Kinect. |
| `lidar_sender()` | Lee datos del LiDAR RPLIDAR y envía puntos con prefijo `LIDR`. |
| `esp32_reader()` | Lee la trama `$DATA` enviada por la ESP32 a través del puerto serie, la procesa y la reenvía al clúster con prefijo `TELE`. |
| `on_message()` | Recibe comandos del clúster (ej. `w`, `x`, `a`, `d`, `0`, etc.) y los envía a la ESP32. |
| `on_open()` | Inicia todos los hilos de sensores cuando la conexión WebSocket se establece. |

---

## Comunicación con la ESP32

La Raspberry y la ESP32 se comunican mediante un **enlace serie (UART)** a 115200 baudios. La ESP32 envía tramas `$DATA` que la Raspberry procesa y reenvía al clúster. La Raspberry también envía comandos de movimiento hacia la ESP32 en el mismo formato que acepta el firmware (descrito en el archivo `Firmware_ESP32.md`).

El script inicia el stream de datos en la ESP32 enviando el comando `DATA rate 100`, para que la ESP32 transmita tramas cada 100 ms (10 Hz). Luego, la Raspberry lee el puerto serie de forma continua y encapsula la telemetría en una trama binaria con el prefijo `TELE`.

---

## Formato de los mensajes WebSocket

Cada mensaje enviado al clúster comienza con un **prefijo de 4 bytes** (ASCII) para identificar el tipo de flujo:

| Prefijo | Datos | Descripción |
|---------|-------|-------------|
| `CAM1` | Imagen JPEG (bytes) | Cámara frontal (filtro de bordes). |
| `CAM2` | Imagen JPEG (bytes) | Cámara trasera (cuadrícula de reversa). |
| `XBOX` | Imagen JPEG (bytes) | Video RGB del Kinect (para detección de objetos). |
| `DEPT` | Imagen JPEG (bytes) | Mapa de profundidad del Kinect (codificado en pseudocolor). |
| `LIDR` | Datos binarios estructurados | Nube de puntos del LiDAR (ángulo y distancia). |
| `TELE` | Datos binarios estructurados | Telemetría (yaw, pitch, roll, IMU, GPS, odometría). |

Los comandos recibidos del clúster son cadenas de texto (`w`, `x`, `a`, `d`, `0`, `p 150,-150`, etc.) que se reenvían directamente a la ESP32.

---

## Código completo 

A continuación se presenta el código con comentarios.

    #!/usr/bin/env python3
    # -*- coding: utf-8 -*-

    import cv2
    import websocket
    import threading
    import time
    import os
    import signal
    import struct
    import serial
    import numpy as np
    import math
    import logging

    from freenect import sync_get_depth, sync_get_video, VIDEO_RGB
    from rplidar import RPLidar

    # ----------------------------------------------------------------------
    # CONFIGURACIÓN DEL SISTEMA
    # ----------------------------------------------------------------------

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )
    log = logging.getLogger()

    WEBSOCKET_URL = "ws://10.4.8.10:8765"

    LIDAR_DEV = "/dev/ttyUSB0"
    ESP32_DEV = "/dev/ttyACM0"

    ws_lock = threading.Lock()
    stop_event = threading.Event()
    esp32_ser = None

    # ----------------------------------------------------------------------
    # DETECCIÓN AUTOMÁTICA DE LA CÁMARA USB (HP)
    # ----------------------------------------------------------------------
    def get_hp_device():
        if os.path.exists("/dev/v4l/by-id"):
            for f in sorted(os.listdir("/dev/v4l/by-id")):
                if "HP_HD_Webcam" in f and f.endswith("-video-index0"):
                    return os.path.join("/dev/v4l/by-id", f)
        return 0

    hp_device = get_hp_device()

    CAM_CONFIG = {
        "width": 320,
        "height": 240,
        "fps": 5,
        "quality": 40
    }
    CAM_IDS = ["CAM1", "CAM2"]

    # ----------------------------------------------------------------------
    # HILO PARA CÁMARAS USB COMPARTIDAS (CAM1 y CAM2)
    # ----------------------------------------------------------------------
    def shared_camera_sender(ws, device, ids, config):
        while not stop_event.is_set():
            cap = cv2.VideoCapture(device)
            if not cap.isOpened():
                log.error(f"No se pudo abrir la cámara {device}, reintentando en 5s")
                time.sleep(5)
                continue

            cap.set(cv2.CAP_PROP_FRAME_WIDTH, config["width"])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config["height"])
            cap.set(cv2.CAP_PROP_FPS, config["fps"])

            interval = 1.0 / config["fps"]
            try:
                while not stop_event.is_set():
                    ret, frame = cap.read()
                    if not ret or frame is None:
                        time.sleep(0.1)
                        continue

                    _, jpeg = cv2.imencode(
                        '.jpg',
                        frame,
                        [cv2.IMWRITE_JPEG_QUALITY, config["quality"]]
                    )
                    jpeg_bytes = jpeg.tobytes()

                    with ws_lock:
                        for cid in ids:
                            ws.send(cid.encode() + jpeg_bytes, opcode=websocket.ABNF.OPCODE_BINARY)

                    time.sleep(interval)

            except Exception as e:
                log.error(f"Error en cámara HP: {e}")
            finally:
                cap.release()
                time.sleep(3)

    # ----------------------------------------------------------------------
    # HILO PARA KINECT (RGB + PROFUNDIDAD)
    # ----------------------------------------------------------------------
    def kinect_sender(ws):
        while not stop_event.is_set():
            try:
                video, _ = sync_get_video(0, VIDEO_RGB)
                if video is not None:
                    bgr = cv2.cvtColor(video, cv2.COLOR_RGB2BGR)
                    resized_rgb = cv2.resize(bgr, (320, 240))
                    _, jpeg_rgb = cv2.imencode(
                        '.jpg',
                        resized_rgb,
                        [cv2.IMWRITE_JPEG_QUALITY, 40]
                    )
                    with ws_lock:
                        ws.send(
                            b'XBOX' + jpeg_rgb.tobytes(),
                            opcode=websocket.ABNF.OPCODE_BINARY
                        )

                depth, _ = sync_get_depth(0)
                if depth is not None:
                    depth = np.clip(depth, 0, 2047)
                    depth_8bit = (depth / 8.0).astype(np.uint8)
                    small_depth = cv2.resize(depth_8bit, (320, 240))
                    colored = cv2.applyColorMap(small_depth, cv2.COLORMAP_JET)
                    _, jpeg_depth = cv2.imencode(
                        '.jpg',
                        colored,
                        [cv2.IMWRITE_JPEG_QUALITY, 60]
                    )
                    with ws_lock:
                        ws.send(
                            b'DEPT' + jpeg_depth.tobytes(),
                            opcode=websocket.ABNF.OPCODE_BINARY
                        )

            except Exception as e:
                log.error(f"Error en Kinect: {e}")

            time.sleep(0.2)

    # ----------------------------------------------------------------------
    # HILO PARA LIDAR RPLIDAR
    # ----------------------------------------------------------------------
    def lidar_sender(ws):
        while not stop_event.is_set():
            if not os.path.exists(LIDAR_DEV):
                time.sleep(2)
                continue

            lidar = RPLidar(LIDAR_DEV, timeout=3)
            try:
                lidar.connect()
                lidar.clean_input()
                lidar.start_motor()
                time.sleep(2)

                for scan in lidar.iter_scans():
                    if stop_event.is_set():
                        break
                    puntos = [(ang, dist) for (_, ang, dist) in scan if 0 < dist < 6000]
                    puntos = puntos[:360]

                    if puntos:
                        payload = struct.pack('<H', len(puntos))
                        for ang, dist in puntos:
                            ang_entero = int(ang * 10) % 3600
                            payload += struct.pack('<HH', ang_entero, int(dist))
                        with ws_lock:
                            ws.send(b'LIDR' + payload, opcode=websocket.ABNF.OPCODE_BINARY)

            except Exception as e:
                log.error(f"Error en LiDAR: {e}")
            finally:
                try:
                    lidar.stop()
                    lidar.stop_motor()
                    lidar.disconnect()
                except:
                    pass
                time.sleep(3)

    # ----------------------------------------------------------------------
    # HILO PARA LECTURA DE LA TELEMETRÍA DE LA ESP32
    # ----------------------------------------------------------------------
    def esp32_reader(ws):
        global esp32_ser
        while not stop_event.is_set():
            if not os.path.exists(ESP32_DEV):
                time.sleep(2)
                continue

            try:
                esp32_ser = serial.Serial(ESP32_DEV, 115200, timeout=1)
                esp32_ser.write(b"DATA rate 100\n")
                time.sleep(0.3)
                esp32_ser.write(b"SNAPSHOT\n")

                while not stop_event.is_set():
                    line = esp32_ser.readline().decode(errors='ignore').strip()
                    if line.startswith('$DATA'):
                        partes = line.split(',')
                        if len(partes) < 21:
                            continue
                        try:
                            seq = int(partes[1])
                            yaw = float(partes[11])
                            ax_raw = int(partes[12])
                            ay_raw = int(partes[13])
                            az_raw = int(partes[14])
                            gx_raw = int(partes[15])
                            gy_raw = int(partes[16])
                            gz_raw = int(partes[17])
                            lat = float(partes[18])
                            lon = float(partes[19])
                            sats = int(partes[20])

                            ESCALA_ACEL = 16384.0
                            ax_g = ax_raw / ESCALA_ACEL
                            ay_g = ay_raw / ESCALA_ACEL
                            az_g = az_raw / ESCALA_ACEL
                            pitch = math.atan2(ax_g, math.sqrt(ay_g**2 + az_g**2)) * 180 / math.pi
                            roll  = math.atan2(ay_g, math.sqrt(ax_g**2 + az_g**2)) * 180 / math.pi

                            datos = struct.pack(
                                '<I f f f h h h h h h d d b',
                                seq, yaw, pitch, roll,
                                ax_raw, ay_raw, az_raw,
                                gx_raw, gy_raw, gz_raw,
                                lat, lon, sats
                            )
                            with ws_lock:
                                ws.send(b'TELE' + datos, opcode=websocket.ABNF.OPCODE_BINARY)

                        except Exception:
                            pass

            except Exception as e:
                log.error(f"Error en comunicación con ESP32: {e}")
                time.sleep(2)

    # ----------------------------------------------------------------------
    # RECEPCIÓN DE COMANDOS DESDE EL CLÚSTER
    # ----------------------------------------------------------------------
    def on_message(ws, message):
        global esp32_ser
        if esp32_ser and esp32_ser.is_open:
            try:
                cmd_str = message.decode('utf-8') if isinstance(message, bytes) else message
                esp32_ser.write((cmd_str + '\n').encode())
            except Exception as e:
                log.error(f"Error al enviar comando a ESP32: {e}")

    # ----------------------------------------------------------------------
    # INICIO DE LA CONEXIÓN WEBSOCKET
    # ----------------------------------------------------------------------
    def on_open(ws):
        log.info("Conexión WebSocket establecida. Iniciando hilos de sensores...")
        threading.Thread(
            target=shared_camera_sender,
            args=(ws, hp_device, CAM_IDS, CAM_CONFIG),
            daemon=True
        ).start()
        threading.Thread(target=kinect_sender, args=(ws,), daemon=True).start()
        threading.Thread(target=lidar_sender, args=(ws,), daemon=True).start()
        threading.Thread(target=esp32_reader, args=(ws,), daemon=True).start()

    def on_close(ws, close_status_code, close_msg):
        log.info("Conexión WebSocket cerrada.")

    def on_error(ws, error):
        log.error(f"Error en WebSocket: {error}")

    # ----------------------------------------------------------------------
    # PROGRAMA PRINCIPAL
    # ----------------------------------------------------------------------
    if __name__ == "__main__":
        def signal_handler(sig, frame):
            log.info("Señal de interrupción recibida. Deteniendo...")
            stop_event.set()
            os._exit(0)

        signal.signal(signal.SIGINT, signal_handler)

        ws_app = websocket.WebSocketApp(
            WEBSOCKET_URL,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )

        log.info("Iniciando cliente robot...")
        while not stop_event.is_set():
            ws_app.run_forever()
            time.sleep(3)

---

## Ejecución y puesta en marcha

1. **Conectar los dispositivos**:
   - Conectar la ESP32 al puerto USB de la Raspberry (normalmente `/dev/ttyACM0`).
   - Conectar el LiDAR RPLIDAR al puerto USB (normalmente `/dev/ttyUSB0`).
   - Conectar las cámaras USB y el Kinect (cada uno a un puerto USB).

2. **Verificar los puertos**:

       ls -l /dev/ttyUSB* /dev/ttyACM*

   Ajustar las variables `LIDAR_DEV` y `ESP32_DEV` si los nombres difieren.

3. **Ejecutar el script**:

       python3 codigo.py

4. **Control remoto**: Desde el clúster (o cualquier cliente WebSocket), enviar comandos de movimiento como `w`, `x`, `a`, `d`, `0`, `p 150,-150`, etc. La Raspberry los reenviará a la ESP32 y el robot se moverá en consecuencia.

---

## Notas de diseño

- **Resolución de imágenes**: Se redujo a 320×240 para minimizar el ancho de banda y la carga de CPU en la Raspberry Pi 3.
- **Compresión JPEG**: Calidad al 40 % para las cámaras y Kinect RGB, y 60 % para la profundidad (que es menos sensible a la pérdida).
- **Multiplexación**: Todos los flujos se envían por un solo WebSocket, usando prefijos de 4 bytes para identificar el tipo.
- **Tolerancia a fallos**: Si algún sensor falla, su hilo se reinicia automáticamente después de un breve retraso.
- **Frecuencia de envío**: Las cámaras USB envían a 5 FPS, el Kinect también a 5 FPS (con un intervalo de 200 ms), el LiDAR envía cada escaneo completo, y la telemetría llega a 10 Hz (configurada con `DATA rate 100`).

---
