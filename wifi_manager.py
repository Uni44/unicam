import subprocess
import time
import requests
import socket
import os
import threading
from flask import render_template_string, request
from htmlTemplates import HTML_COF

def wifi():
    if request.method == "POST":
        ssid = request.form['ssid']
        password = request.form['password']
        configurar_wifi_nm(ssid, password)
        return "Configuración guardada. Reinicia la Raspberry Pi."
    return render_template_string(HTML_COF)

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
        return False

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
    if not tiene_internet():
        print("❌ Sin Internet → Hotspot ON")
        levantar_hotspot()
    else:
        print("✔ Internet OK → Hotspot OFF")
        apagar_hotspot()
        
wifi_thread = threading.Thread(target=ComprobeWifi, daemon=True)
wifi_thread.start()