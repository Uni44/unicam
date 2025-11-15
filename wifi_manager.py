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
        configurar_wifi(ssid, password)
        return "Configuración guardada. Reinicia la Raspberry Pi."
    return render_template_string(HTML_COF)

def configurar_wifi(ssid, password):
    subprocess.run(["sudo", "systemctl", "stop", "hostapd"])
        
    wpa_conf = f"""
network={{
    ssid="{ssid}"
    psk="{password}"
}}
"""
    with open("/etc/wpa_supplicant/wpa_supplicant-wlan0.conf", "w") as f:
        f.write('ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\n')
        f.write('update_config=1\n')
        f.write('country=AR\n')  # Ajusta tu país
        f.write(wpa_conf)
    # Reiniciar el servicio de Wi-Fi
    subprocess.run(["sudo", "systemctl", "stop", "hostapd"])
    subprocess.run(["sudo", "systemctl", "stop", "dnsmasq"])

    subprocess.run(["sudo", "systemctl", "restart", "dhcpcd"])
    subprocess.run(["sudo", "systemctl", "restart", "wpa_supplicant"])

    subprocess.run(["sudo", "wpa_cli", "-i", "wlan0", "reconfigure"])
    
    time.sleep(1)
    
    subprocess.run(["sudo", "reboot"])
    
    #ComprobeWifi()

def forzar_conexion_wifi():
    print("Forzando conexión WiFi...")

    # Reinicia los servicios de red
    subprocess.run(["sudo", "systemctl", "stop", "hostapd"])
    subprocess.run(["sudo", "systemctl", "stop", "dnsmasq"])
    subprocess.run(["sudo", "systemctl", "restart", "dhcpcd"])
    subprocess.run(["sudo", "systemctl", "restart", "wpa_supplicant"])

    # Espera unos segundos para que levante
    time.sleep(1)

    # Fuerza reconfiguración de wpa_supplicant
    subprocess.run(["sudo", "wpa_cli", "-i", "wlan0", "reconfigure"])
    subprocess.run(["sudo", "wpa_cli", "-i", "wlan0", "reassociate"])

    print("Intentando conectar a la red WiFi...")

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

def ComprobeWifi():
    forzar_conexion_wifi()
    print("Esperando a que la red se estabilice...")
    time.sleep(10)
    if not tiene_internet():
        print("No hay Internet, levantando AP...")
        subprocess.run(["sudo", "systemctl", "start", "hostapd"])
        subprocess.run(["sudo", "systemctl", "start", "dnsmasq"])
    else:
        print("Hay Internet, apagando AP...")
        subprocess.run(["sudo", "systemctl", "stop", "hostapd"])
        subprocess.run(["sudo", "systemctl", "stop", "dnsmasq"])
        
wifi_thread = threading.Thread(target=ComprobeWifi, daemon=True)
wifi_thread.start()