import subprocess
import time
import requests
import socket
import os
import threading
from flask import render_template_string, request
from htmlTemplates import HTML_COF

def wifi():
    message = None
    if request.method == "POST":
        ssid = request.form['ssid']
        password = request.form['password']
        result = configurar_wifi_nm(ssid, password)
        if result is True:
            message = f"✅ Conectado a {ssid}. La Raspberry Pi intentará mantener esta conexión incluso sin Internet."
        else:
            message = f"❌ No se pudo conectar a {ssid}: {result}. Se ha activado el hotspot."
    return render_template_string(HTML_COF, message=message)

def get_wifi_device_status():
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "DEVICE,STATE,CONNECTION", "device", "status"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return None, None
        for line in result.stdout.splitlines():
            cols = line.strip().split(":")
            if len(cols) >= 3 and cols[0] == "wlan0":
                return cols[1], cols[2]
    except Exception:
        pass
    return None, None


def conectado_wifi():
    state, connection = get_wifi_device_status()
    if state == "connected" and connection and connection.lower() != "hotspot":
        return True
    return False


def configurar_wifi_nm(ssid, password):
    print("📡 Preparando WiFi (NetworkManager)...")

    # Asegurar WiFi encendido
    subprocess.run(["sudo", "nmcli", "radio", "wifi", "on"])

    # Por si venía de hotspot o estado raro
    subprocess.run(["sudo", "nmcli", "device", "disconnect", "wlan0"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Forzar escaneo
    subprocess.run(
        ["sudo", "nmcli", "device", "wifi", "rescan", "ifname", "wlan0"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    time.sleep(2)  # MUY IMPORTANTE

    print(f"🔗 Conectando a {ssid}...")

    # Conectar
    result = subprocess.run(
        [
            "sudo", "nmcli", "device", "wifi", "connect",
            ssid,
            "password", password,
            "ifname", "wlan0"
        ],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print("❌ Error conectando WiFi:")
        print(result.stderr)
        levantar_hotspot()
        return result.stderr.strip() or "Error conectando WiFi"

    # Autoconectar siempre
    subprocess.run([
        "sudo", "nmcli", "connection", "modify",
        ssid,
        "connection.autoconnect", "yes"
    ])

    print("✅ WiFi conectado y guardado")
    return True

def tiene_internet():
    # Primero prueba con socket TCP a 1.1.1.1:80 (Cloudflare)
    try:
        socket.create_connection(("1.1.1.1", 80), timeout=2)
        print("✔ Internet OK (TCP 1.1.1.1:80)")
        return True
    except Exception:
        pass
    # Si falla, prueba con HTTP a una IP pública
    try:
        requests.get("http://1.1.1.1", timeout=2)
        print("✔ Internet OK (HTTP 1.1.1.1)")
        return True
    except Exception:
        pass
    # Último recurso, prueba con HTTP a google.com (requiere DNS)
    try:
        requests.get("http://google.com", timeout=2)
        print("✔ Internet OK (HTTP google.com)")
        return True
    except Exception:
        print("✖ Sin acceso a Internet.")
        return False

def apagar_hotspot():
    subprocess.run(["sudo", "nmcli", "connection", "down", "Hotspot"], stderr=subprocess.DEVNULL)

def levantar_hotspot():
    print("Levantando Hotspot...")

    subprocess.run([
        "sudo", "nmcli", "device", "wifi", "hotspot",
        "ifname", "wlan0",
        "ssid", "Unicam",
        "password", "1234567890"
    ])


def ComprobeWifi():
    print("Esperando a que la red se estabilice...")
    time.sleep(10)
    if conectado_wifi():
        print("✔ WiFi conectado → Hotspot OFF")
        apagar_hotspot()
    else:
        print("❌ WiFi desconectado → Hotspot ON")
        levantar_hotspot()
        
wifi_thread = threading.Thread(target=ComprobeWifi, daemon=True)
wifi_thread.start()