#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import serial
import time
import threading
import sys

# ======================================================================
# CONFIGURACIÓN
# ======================================================================
PUERTO = "COM13"        # Cambiar según el sistema (Windows: COMx, Linux: /dev/ttyACM0)
BAUDIOS = 115200

# ======================================================================
# CLASE PARA PRUEBA DE MOTORES Y ENCODERS
# ======================================================================
class PruebaMotores:
    def __init__(self):
        try:
            self.ser = serial.Serial(PUERTO, BAUDIOS, timeout=1)
            time.sleep(2)
            self.ser.reset_input_buffer()
            print(f"✅ Conectado a {PUERTO}")
        except Exception as e:
            print(f"❌ Error al conectar a {PUERTO}: {e}")
            sys.exit()
        
        self.ejecutando = True
        # Contadores y RPM para cada rueda
        self.contador_FL = 0
        self.contador_FR = 0
        self.contador_BL = 0
        self.contador_BR = 0
        self.rpm_FL = 0.0
        self.rpm_FR = 0.0
        self.rpm_BL = 0.0
        self.rpm_BR = 0.0

    # ------------------------------------------------------------------
    # Enviar comando a la ESP32
    # ------------------------------------------------------------------
    def enviar_comando(self, comando):
        if self.ser.is_open:
            self.ser.write(f"{comando}\n".encode())

    # ------------------------------------------------------------------
    # Iniciar la prueba (bucle principal)
    # ------------------------------------------------------------------
    def iniciar(self):
        # Activar el stream de datos (envía tramas cada 100 ms = 10 Hz)
        self.enviar_comando("DATA rate 100")
        time.sleep(0.5)
        # Resetear encoders y ángulo de guiñada
        self.enviar_comando("r")
        time.sleep(0.1)

        # Hilo para leer el puerto serie en segundo plano
        hilo_lectura = threading.Thread(target=self.leer_serie, daemon=True)
        hilo_lectura.start()

        print("\n=== PRUEBA DE MOTORES Y ENCODERS ===")
        print(" [W] Adelante   [S] Atrás")
        print(" [A] Giro Izq   [D] Giro Der")
        print(" [X] Parar      [R] Reset encoders")
        print(" [Q] Salir")
        print("------------------------------------------")

        try:
            while self.ejecutando:
                # Mostrar información en una sola línea
                sys.stdout.write(
                    f"\r🏎️  RPM: FL={self.rpm_FL:5.1f} FR={self.rpm_FR:5.1f} BL={self.rpm_BL:5.1f} BR={self.rpm_BR:5.1f}  |  "
                    f"PULSOS: FL={self.contador_FL:6} FR={self.contador_FR:6} BL={self.contador_BL:6} BR={self.contador_BR:6}   "
                )
                sys.stdout.flush()

                # Captura de teclas en Windows (con msvcrt)
                if sys.platform == 'win32':
                    import msvcrt
                    if msvcrt.kbhit():
                        tecla = msvcrt.getwch().lower()
                        if tecla == 'q':
                            self.detener()
                        elif tecla == 'w':
                            self.enviar_comando("w")   # Adelante
                        elif tecla == 's':
                            self.enviar_comando("x")   # Atrás
                        elif tecla == 'a':
                            self.enviar_comando("a")   # Giro izquierda
                        elif tecla == 'd':
                            self.enviar_comando("d")   # Giro derecha
                        elif tecla == 'x':
                            self.enviar_comando("0")   # Parar
                        elif tecla == 'r':
                            self.enviar_comando("r")   # Reset encoders
                time.sleep(0.05)

        except KeyboardInterrupt:
            self.detener()

    # ------------------------------------------------------------------
    # Detener la prueba y cerrar conexión
    # ------------------------------------------------------------------
    def detener(self):
        self.enviar_comando("0")       # Parar motores
        self.ejecutando = False
        self.ser.close()
        print("\n🔌 Desconectado.")

    # ------------------------------------------------------------------
    # Hilo de lectura del puerto serie
    # ------------------------------------------------------------------
    def leer_serie(self):
        while self.ejecutando:
            try:
                linea = self.ser.readline().decode(errors='ignore').strip()
                if linea.startswith("$DATA"):
                    partes = linea.split('*')[0].split(',')
                    if len(partes) >= 11:  # Necesitamos hasta rpm_BR (índice 10)
                        # Índices (0="$DATA", 1=seq, 2=millis, 3=cFL, 4=cFR, 5=cBL, 6=cBR, 7=rFL, 8=rFR, 9=rBL, 10=rBR)
                        self.contador_FL = int(partes[3])
                        self.contador_FR = int(partes[4])
                        self.contador_BL = int(partes[5])
                        self.contador_BR = int(partes[6])
                        self.rpm_FL = float(partes[7])
                        self.rpm_FR = float(partes[8])
                        self.rpm_BL = float(partes[9])
                        self.rpm_BR = float(partes[10])
            except Exception:
                pass

# ======================================================================
# PUNTO DE ENTRADA
# ======================================================================
if __name__ == "__main__":
    PruebaMotores().iniciar()