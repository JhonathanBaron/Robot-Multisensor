#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import serial
import time
import sys

# ======================================================================
# CONFIGURACIÓN
# ======================================================================
PUERTO = 'COM13'        # Cambiar según el sistema (Windows: COMx, Linux: /dev/ttyACM0)
BAUDIOS = 115200
TIMEOUT_LECTURA = 0.1

# ======================================================================
# FUNCIONES AUXILIARES
# ======================================================================

def enviar_comando(ser, comando, espera=0.5):
    """Envía un comando al ESP32 y espera un momento."""
    ser.write((comando + '\n').encode('utf-8'))
    time.sleep(espera)

def esperar_respuesta(ser, texto_buscado, timeout_seg=5):
    """
    Lee el puerto serie buscando una línea que contenga 'texto_buscado'.
    Retorna (éxito, línea) si lo encuentra; (False, []) si no.
    """
    inicio = time.time()
    while time.time() - inicio < timeout_seg:
        if ser.in_waiting > 0:
            linea = ser.readline().decode('utf-8', errors='ignore').strip()
            if linea:
                if texto_buscado in linea:
                    return True, linea
    return False, []

def limpiar_buffer(ser):
    """Vacia el buffer de lectura."""
    ser.reset_input_buffer()

def leer_hasta(ser, texto_buscado, timeout_seg=10, imprimir=True):
    """
    Lee líneas del puerto serie hasta encontrar 'texto_buscado' o hasta que se agote el tiempo.
    Imprime cada línea si imprimir=True.
    Retorna True si encontró el texto, False en caso contrario.
    """
    inicio = time.time()
    while time.time() - inicio < timeout_seg:
        if ser.in_waiting > 0:
            linea = ser.readline().decode('utf-8', errors='ignore').strip()
            if linea and imprimir:
                print(f"   -> {linea}")
            if texto_buscado in linea:
                return True
    return False

# ======================================================================
# PROGRAMA PRINCIPAL
# ======================================================================

def main():
    print("=" * 60)
    print("   AUTODIAGNÓSTICO DEL ROBOT - FIRMWARE V8")
    print("=" * 60)
    print("⚠️  ASEGÚRATE DE QUE LAS RUEDAS ESTÉN EN EL AIRE.")
    print("   (Para evitar desplazamientos no deseados)")
    time.sleep(2)

    try:
        ser = serial.Serial(PUERTO, BAUDIOS, timeout=TIMEOUT_LECTURA)
        print(f"\n[*] Conectando al ESP32 en {PUERTO}...")
        time.sleep(2)          # Esperar a que el ESP32 se estabilice
        limpiar_buffer(ser)
        print("[+] Conexión establecida.\n")

        # ---- TEST 1: COMUNICACIÓN BÁSICA ----
        print(">> TEST 1: Verificando comunicación (comando 'HELP')")
        enviar_comando(ser, "HELP")
        exito, _ = esperar_respuesta(ser, "$SYS,HELP_START", timeout_seg=3)
        if exito:
            print("   [ OK ] El ESP32 responde correctamente.")
        else:
            print("   [ FAIL ] No hay respuesta. Verifica la conexión y el puerto.")
            return

        # ---- TEST 2: DIAGNÓSTICO DE LA IMU ----
        print("\n>> TEST 2: Diagnóstico de la IMU (comando 'TEST_IMU')")
        limpiar_buffer(ser)
        enviar_comando(ser, "TEST_IMU")
        exito = leer_hasta(ser, "$DIAG,IMU_PASS", timeout_seg=5)
        if exito:
            print("   [ OK ] IMU funcionando correctamente.")
        else:
            print("   [ FAIL ] La IMU no respondió o falló la prueba.")

        # ---- TEST 3: DIAGNÓSTICO DEL GPS ----
        print("\n>> TEST 3: Diagnóstico del GPS (comando 'TEST_GPS')")
        print("   (El GPS necesita cielo abierto para tener fijo)")
        limpiar_buffer(ser)
        enviar_comando(ser, "TEST_GPS")
        exito = leer_hasta(ser, "$DIAG,GPS_PASS", timeout_seg=6)
        if exito:
            print("   [ OK ] GPS recibiendo datos válidos.")
        else:
            print("   [ WARN ] GPS no tiene fijo o no hay datos (puede ser normal en interiores).")

        # ---- TEST 4: DIAGNÓSTICO DE ENCODERS ----
        print("\n>> TEST 4: Diagnóstico de encoders (comando 'TEST_ENC')")
        print("   (Los motores girarán brevemente para generar pulsos)")
        limpiar_buffer(ser)
        enviar_comando(ser, "TEST_ENC")
        exito = leer_hasta(ser, "$DIAG,ENC_PASS", timeout_seg=10)
        if exito:
            print("   [ OK ] Todos los encoders responden.")
        else:
            print("   [ FAIL ] Al menos un encoder no generó pulsos.")

        # ---- TEST 5: DIAGNÓSTICO DE MOTORES ----
        print("\n>> TEST 5: Diagnóstico de motores (comando 'TEST_MOT')")
        print("   (Cada motor girará unos segundos)")
        limpiar_buffer(ser)
        enviar_comando(ser, "TEST_MOT")
        exito = leer_hasta(ser, "$DIAG,MOT_DONE", timeout_seg=10)
        if exito:
            print("   [ OK ] Todos los motores respondieron.")
        else:
            print("   [ FAIL ] Al menos un motor no respondió.")

        # ---- TEST 6: SECUENCIA DE MOVIMIENTO (opcional) ----
        print("\n>> TEST 6: Prueba de movimiento con comandos básicos")
        print("   (El robot avanzará, retrocederá y girará brevemente)")
        limpiar_buffer(ser)

        # Activar stream de datos para ver encoders
        enviar_comando(ser, "DATA rate 100")
        time.sleep(0.5)

        # Secuencia de movimientos
        secuencia = [
            ("w", "Adelante (2s)"),
            ("0", "Parar (1s)"),
            ("x", "Atrás (2s)"),
            ("0", "Parar (1s)"),
            ("a", "Giro izquierda (1.5s)"),
            ("0", "Parar (1s)"),
            ("d", "Giro derecha (1.5s)"),
            ("0", "Parar (1s)")
        ]

        for cmd, desc in secuencia:
            print(f"   -> {desc}")
            enviar_comando(ser, cmd)
            # Esperar el tiempo indicado (extraer de la descripción)
            if "2s" in desc:
                time.sleep(2)
            elif "1.5s" in desc:
                time.sleep(1.5)
            else:
                time.sleep(1)

        # Detener y desactivar stream
        enviar_comando(ser, "0")
        enviar_comando(ser, "DATA stop")
        print("   [ OK ] Secuencia de movimiento completada.")

        # ---- TEST 7: VERIFICACIÓN DE ENCODERS DURANTE MOVIMIENTO ----
        print("\n>> TEST 7: Verificación de encoders durante movimiento")
        print("   (Se leyeron pulsos mientras el robot se movía)")
        # Buscar una trama $DATA que tenga algún contador distinto de cero
        # Para simplificar, revisamos las últimas líneas del buffer (ya leídas)
        # Como alternativa, esperamos 1 segundo y leemos una trama
        time.sleep(0.5)
        exito_encoder = False
        for _ in range(10):
            if ser.in_waiting > 0:
                linea = ser.readline().decode('utf-8', errors='ignore').strip()
                if linea.startswith("$DATA"):
                    partes = linea.split('*')[0].split(',')
                    if len(partes) >= 7:
                        # partes[3..6] son contadores FL, FR, BL, BR
                        cFL = int(partes[3])
                        cFR = int(partes[4])
                        cBL = int(partes[5])
                        cBR = int(partes[6])
                        if cFL > 0 or cFR > 0 or cBL > 0 or cBR > 0:
                            exito_encoder = True
                            print(f"   -> Pulsos detectados: FL={cFL} FR={cFR} BL={cBL} BR={cBR}")
                            break
            time.sleep(0.1)

        if exito_encoder:
            print("   [ OK ] Los encoders incrementaron durante el movimiento.")
        else:
            print("   [ WARN ] No se detectaron pulsos en los encoders (posible problema de hardware).")

        # ---- FINAL ----
        print("\n" + "=" * 60)
        print("               AUTODIAGNÓSTICO FINALIZADO")
        print("=" * 60)

    except serial.SerialException:
        print(f"\n[!] ERROR FATAL: No se pudo abrir el puerto {PUERTO}.")
        print("   Verifica que el ESP32 esté conectado y que el puerto sea correcto.")
    except KeyboardInterrupt:
        print("\n[!] Prueba cancelada por el usuario.")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print("[*] Puerto cerrado.")

if __name__ == "__main__":
    main()