HTML_INICIO = '''
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Unicam • Dashboard</title>
<style>
:root {
  --bg: #000;
  --text: #f1f1f1;
  --accent: #facc15; /* amarillo principal */
  --card: #0a0a0a;
  --line: #1f1f1f;
  --radius: 4px;
  --shadow: 0 0 20px rgba(0,0,0,0.6);
  --font: "Consolas", "Roboto Mono", monospace;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: var(--font);
  background: var(--bg);
  color: var(--text);
  letter-spacing: 0.3px;
}

.wrap {
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px;
}

/* HEADER */
header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 2px solid var(--accent);
  padding-bottom: 8px;
  margin-bottom: 24px;
}

h1 {
  font-size: 26px;
  color: var(--accent);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1px;
}

/* GRID */
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
  gap: 20px;
}

/* CARD */
.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-left: 3px solid var(--accent);
  padding: 16px 18px;
  box-shadow: var(--shadow);
}

.card h2, .card h3 {
  color: var(--accent);
  font-size: 16px;
  text-transform: uppercase;
  margin-top: 0;
  border-bottom: 1px solid var(--line);
  padding-bottom: 6px;
  margin-bottom: 12px;
}

/* TEXT / LABELS */
label {
  display: block;
  margin-bottom: 4px;
  font-size: 13px;
  color: #ddd;
}

.setting {
  margin-bottom: 14px;
}

/* INPUTS */
input[type="text"], input[type="password"], input[type="number"],
select, textarea {
  width: 100%;
  padding: 6px 10px;
  border: 1px solid #333;
  border-radius: var(--radius);
  background: #111;
  color: var(--text);
  font-family: var(--font);
  font-size: 13px;
}

input:focus, select:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 4px var(--accent);
}

/* RANGE */
input[type="range"] {
  -webkit-appearance: none;
  width: 100%;
  height: 5px;
  background: #222;
  border-radius: 3px;
  outline: none;
}
input[type="range"]::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 14px;
  height: 14px;
  background: var(--accent);
  border: none;
  cursor: pointer;
}
input[type="range"]::-moz-range-thumb {
  width: 14px;
  height: 14px;
  background: var(--accent);
  border: none;
  cursor: pointer;
}

/* BOTONES */
.btn, button {
  background: var(--accent);
  color: #000;
  border: none;
  padding: 8px 14px;
  font-weight: 700;
  font-family: var(--font);
  border-radius: var(--radius);
  cursor: pointer;
  transition: background 0.1s, transform 0.1s;
  text-transform: uppercase;
}
.btn:hover, button:hover {
  background: #fff200;
  transform: scale(1.03);
}

/* LEDS / STATUS */
.dot {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #444;
  display: inline-block;
  margin-right: 6px;
  box-shadow: 0 0 4px rgba(0,0,0,0.7);
}
.dot.ok { background: #22c55e; }
.dot.active { background: var(--accent); }
.dot.err { background: #ef4444; }

@keyframes blink {
  0%, 50%, 100% { opacity: 1; }
  25%, 75% { opacity: 0.2; }
}
.dot.blink { animation: blink 1s infinite; }

.leds-row {
  display: flex;
  gap: 14px;
  align-items: center;
}
.led-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

/* STATUS BARS */
.status-text { font-size: 13px; margin-bottom: 4px; }
.status-bar {
  background: #151515;
  border: 1px solid #222;
  border-radius: 2px;
  height: 10px;
  overflow: hidden;
  margin-bottom: 8px;
}
.status-fill {
  height: 100%;
  background: var(--accent);
  width: 0%;
}

/* VIDEO */
video {
  width: 100%;
  background: #000;
  border: 1px solid var(--line);
}

/* FOOTER */
footer {
  margin-top: 30px;
  text-align: center;
  color: #777;
  font-size: 12px;
  border-top: 1px solid #111;
  padding-top: 10px;
}

/* SCROLLBAR */
::-webkit-scrollbar { width: 8px; }
::-webkit-scrollbar-thumb { background: #222; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: var(--accent); }

.chart-box {
  background: #0a0a0a;
  border: 1px solid #333;
  border-left: 3px solid #facc15;
  padding: 10px;
  border-radius: 4px;
  position: relative;
  width: 100%;
  max-width: 600px;
  margin: auto;
}

.chart-box h3 {
  font-family: monospace;
  font-size: 13px;
  color: #facc15;
  margin-bottom: 8px;
}

.chart-box canvas {
  width: 100%;
  height: 220px;
}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Unicam</h1>
  </header>

  <section class="grid">
	<div class="card">
	  <h2>Estado</h2>
	  <div class="leds-row">
		<div class="led-item">
		  <span id="ledCamara" class="dot ok"></span> Cámara
		</div>
		<div class="led-item">
		  <span id="ledConectado" class="dot ok"></span> Conexión
		</div>
		<div class="led-item">
		  <span id="ledInternet" class="dot blink"></span> Internet
		</div>
		<div class="led-item">
		  <span id="ledCpu" class="dot blink"></span> CPU
		</div>
	  </div>
	</div>

	<!-- Información del sistema -->
    <div class="card">
      <h2>Sistema</h2>
      <div class="status-text">CPU: <span id="cpuText">0%</span></div>
      <div class="status-bar"><div id="cpuBar" class="status-fill"></div></div>
	  <div class="status-text">CPU FREQ: <span id="cpu_freqText">0</span></div>
      <div class="status-text">RAM: <span id="ramText">0%</span></div>
      <div class="status-bar"><div id="ramBar" class="status-fill"></div></div>
      <div class="status-text">Temp: <span id="tempText">0°C</span></div>
      <div class="status-bar"><div id="tempBar" class="status-fill"></div></div>
      <div class="status-text">Disk: <span id="diskText">0%</span></div>
      <div class="status-bar"><div id="diskBar" class="status-fill"></div></div>
	  <div class="status-text">BAT: <span id="batText">0%</span></div>
	  <div class="status-bar"><div id="batBar" class="status-fill"></div></div>
	  <div class="status-text">Vol: <span id="volText">0.0</span></div>
	  <div class="status-text">Load: <span id="loadText">0.0</span></div>
    </div>
	
	<div class="chart-box">
	  <h3>Monitoreo del Sistema</h3>
	  <canvas id="unicamChart"></canvas>
	</div>
	
	<!-- Utilidades -->
    <div class="card">
      <h2>Funciones</h2>
      <button class="btn" onclick="restartStream()">START</button>
      <button class="btn" onclick="stopStream()">STOP</button>
      <button class="btn" onclick="restartHdmi()">HDMI Restart</button>
      <label style="display:inline-block;margin-left:10px; color:#ddd; font-size:13px;">
        <input type="checkbox" id="AutoReconnect" style="margin-right:6px;"> Auto Reconnect
      </label>
      <button class="btn" id="zoomIn">ZOOM +</button>
      <button class="btn" id="zoomOut">ZOOM -</button>
	  <h2> </h2>
      <button class="btn" onclick="window.location.href='/files'">Files</button>
	  <button class="btn" onclick="window.location.href='/browse/home/pi/Unicam/fotos'">Pictures</button>
	  <button class="btn" onclick="window.location.href='/browse/home/pi/Unicam/videos'">Videos</button>
	  <h2> </h2>
	  <button class="btn" onclick="restartPi()">Restart</button>
      <button class="btn" onclick="shutdownPi()">Shutdown</button>
    </div>

  
    <!--<div class="card">
      <h2>Accesos Rápidos</h2>
      <a href="/preview" class="btn">/preview</a>
      <a href="/original" class="btn">/original</a>
      <a href="/wifi" class="btn">/wifi</a>
    </div>-->
	
	<div class="card">
	<div id="video-settings">
	<h3>Ajustes de Video</h3>
	<label>Modo:
        <select id="modo">
            <option>Foto</option>
            <option>Stream</option>
            <option>Grabar</option>
        </select>
    </label>
	<br>
    <label>Resolución:
        <select id="resolution">
            <option>2560x1440</option>
            <option>1920x1080</option>
            <option>1280x720</option>
            <option>640x480</option>
        </select>
    </label>
	<br>
    <label>HDMI:
        <select id="hdmi">
            <option>Full</option>
            <option>Mid</option>
            <option>Low</option>
            <option>Off</option>
        </select>
    </label>
	<br>
    <label>FPS:
        <select id="fps">
			<option>90</option>
            <option>60</option>
			<option>59</option>
            <option>30</option>
            <option>29</option>
			<option>24</option>
			<option>15</option>
			<option>5</option>
        </select>
    </label>
	<br>
    <label>Protocolo STR:
        <select id="protocolo_stream">
			<option>RTSP</option>
            <option>SRT</option>
        </select>
    </label>
	<br><br>
	<label>Bitrate:
	<select id="bitrate">
		<option>16M</option>
		<option>15M</option>
		<option>14M</option>
		<option>13M</option>
		<option>12M</option>
		<option>10M</option>
		<option>9M</option>
		<option>8M</option>
		<option>7M</option>
		<option>6M</option>
		<option>5M</option>
		<option>4M</option>
		<option>3M</option>
		<option>2M</option>
		<option>1M</option>
        </select>
    </label>
	<br>
	<label>Preset:
	<select id="preset">
		<option>ultrafast</option>
		<option>superfast</option>
		<option>veryfast</option>
		<option>faster</option>
		<option>fast</option>
		<option>medium</option>
		<option>slow</option>
		<option>slower</option>
		<option>placebo</option>
        </select>
    </label>
	<br><br>
	<div class="setting">
		<label>Protocolo de envio RTSP:</label>
		<input type="text" id="protocolo" placeholder="tcp">
	</div>
	<br>
	<div class="setting">
		<label>Destino RTSP:</label>
		<input type="text" id="destino" placeholder="rtsp://192.168.0.12:8554/cam">
	</div>
	<br>
	<div class="setting">
		<label>IP SDP RTSP:</label>
		<input type="text" id="sdp" placeholder="127.0.0.1">
	</div>
	<br><br>
	<div class="setting">
		<label>IP Destino SRT:</label>
		<input type="text" id="IPDestinoSRT" placeholder="192.168.0.12">
	</div>
	<br>
	<div class="setting">
		<label>Puerto Destino SRT:</label>
		<input type="text" id="puertoDestinoSRT" placeholder="0000">
	</div>
	<br>
	<div class="setting">
		<label>Extra SRT:</label>
		<input type="text" id="extraDataSRT" placeholder="?streamid=publish:cam&pkt_size=1316&latency=0">
	</div>
	<br><br>
  <div class="setting">
    <label>Mic:</label>
    <select id="mic">
      <option value="!">Disabled (!)</option>
      <option value="">No mic (empty)</option>
    </select>
    <div style="font-size:12px;color:#aaa;margin-top:6px;">Selecciona el mic o "Disabled" para desactivar (se usa '!' para ignorar).</div>
  </div>
	<br><br>
	<button id="settings-btn-1">Send</button>
</div>
</div>
<div class="card">
<div class="camera-controls">

    <!-- ===================== -->
    <!--  AJUSTES BÁSICOS      -->
    <!-- ===================== -->
    <h3>Ajustes Básicos</h3>

    <label>Brightness (-1 a 1)</label>
    <input type="range" id="Brightness" min="-1" max="1" step="0.01">

    <label>Contrast (0 a 32)</label>
    <input type="range" id="Contrast" min="0" max="32" step="0.1">

    <label>Saturation (0 a 32)</label>
    <input type="range" id="Saturation" min="0" max="32" step="0.1">

    <label>Sharpness (0 a 16)</label>
    <input type="range" id="Sharpness" min="0" max="16" step="0.1">

    <label>Noise Reduction Mode</label>
    <select id="NoiseReductionMode">
        <option value="0">Off</option>
        <option value="1">Fast</option>
        <option value="2">High Quality</option>
        <option value="3">Minimal</option>
        <option value="4">Custom</option>
    </select>

    <label>HDR Mode</label>
    <select id="HdrMode">
        <option value="0">Off</option>
        <option value="1">HDR1</option>
        <option value="2">HDR2</option>
        <option value="3">HDR3</option>
        <option value="4">HDR4</option>
    </select>


    <!-- ===================== -->
    <!--  WHITE BALANCE (AWB)  -->
    <!-- ===================== -->
    <h3>White Balance</h3>

    <label>AWB Activado</label>
    <input type="checkbox" id="AwbEnable">

    <label>AWB Mode</label>
    <select id="AwbMode">
        <option value="0">Auto</option>
        <option value="1">Incandescent</option>
        <option value="2">Tungsten</option>
        <option value="3">Fluorescent</option>
        <option value="4">Indoor</option>
        <option value="5">Daylight</option>
        <option value="6">Cloudy</option>
        <option value="7">Custom</option>
    </select>

    <label>Colour Temperature (100 - 100000)</label>
    <input type="range" id="ColourTemperature" min="100" max="100000" step="100">

    <label>Colour Gains (0 - 32)</label>
    <input type="range" id="ColourGains" min="0" max="32" step="0.1">


    <!-- ===================== -->
    <!--     EXPOSICIÓN        -->
    <!-- ===================== -->
    <h3>Exposición</h3>

    <label>AE Activado</label>
    <input type="checkbox" id="AeEnable">

    <label>Exposure Time (13 - 112015096)</label>
    <input type="range" id="ExposureTime" min="13" max="112015096" step="100">

    <label>Exposure Value (-8 a 8)</label>
    <input type="range" id="ExposureValue" min="-8" max="8" step="0.1">

    <label>Analogue Gain (1.12 a 16.0)</label>
    <input type="range" id="AnalogueGain" min="1.12" max="16" step="0.01">

    <label>AE Exposure Mode</label>
    <select id="AeExposureMode">
        <option value="0">Normal</option>
        <option value="1">Short</option>
        <option value="2">Long</option>
        <option value="3">Custom</option>
    </select>

    <label>AE Constraint Mode</label>
    <select id="AeConstraintMode">
        <option value="0">Normal</option>
        <option value="1">Highlight</option>
        <option value="2">Shadow</option>
        <option value="3">Custom</option>
    </select>

    <label>AE Metering Mode</label>
    <select id="AeMeteringMode">
        <option value="0">Centre</option>
        <option value="1">Spot</option>
        <option value="2">Matrix</option>
        <option value="3">Custom</option>
    </select>

    <label>AE Flicker Mode</label>
    <select id="AeFlickerMode">
        <option value="0">Off</option>
        <option value="1">Auto</option>
    </select>

    <label>AE Flicker Period</label>
    <input type="range" id="AeFlickerPeriod" min="100" max="1000000" step="100">


    <!-- ===================== -->
    <!--       AUTOFOCUS       -->
    <!-- ===================== -->
    <h3>Autofocus</h3>

    <label>AF Mode</label>
    <select id="AfMode">
        <option value="0">Manual</option>
        <option value="1">Auto</option>
        <option value="2">Continuous</option>
    </select>

    <label>AF Range</label>
    <select id="AfRange">
        <option value="0">Normal</option>
        <option value="1">Macro</option>
        <option value="2">Full</option>
    </select>

    <label>AF Speed</label>
    <select id="AfSpeed">
        <option value="0">Normal</option>
        <option value="1">Fast</option>
    </select>

    <label>AF Metering</label>
    <select id="AfMetering">
        <option value="0">Auto</option>
        <option value="1">Manual</option>
    </select>

    <label>AF Pause</label>
    <select id="AfPause">
        <option value="0">None</option>
        <option value="1">Short</option>
        <option value="2">Long</option>
    </select>

    <label>Lens Position (0 - 15)</label>
    <input type="range" id="LensPosition" min="0" max="15" step="0.05">

    <label>AF Trigger</label>
    <input type="checkbox" id="AfTrigger">


    <!-- ===================== -->
    <!--        OTROS          -->
    <!-- ===================== -->
    <h3>Otros</h3>

    <label>Stats Output Enable</label>
    <input type="checkbox" id="StatsOutputEnable">

    <label>Sync Mode</label>
    <select id="SyncMode">
        <option value="0">Off</option>
        <option value="1">Sensor Sync</option>
        <option value="2">Frame Sync</option>
    </select>

    <label>Sync Frames (1 - 1000000)</label>
    <input type="range" id="SyncFrames" min="1" max="1000000" step="1">

    <label>CNN Input Tensor</label>
    <input type="checkbox" id="CnnEnableInputTensor">
	
	<!-- ===================== -->
	<!--   CONTROLES EXTRA     -->
	<!-- ===================== -->
	<h3>Controles Avanzados del Sensor</h3>

	<!-- Exposure Time Mode -->
	<label>Exposure Time Mode</label>
	<select id="ExposureTimeMode">
		<option value="0">Manual</option>
		<option value="1">Auto</option>
	</select>

	<!-- Analogue Gain Mode -->
	<label>Analogue Gain Mode</label>
	<select id="AnalogueGainMode">
		<option value="0">Manual</option>
		<option value="1">Auto</option>
	</select>

	<!-- AF Windows -->
	<label>AF Windows (x, y, width, height)</label>
	<input type="text" id="AfWindows" placeholder="0,0,65535,65535">

	<!-- Frame Duration Limits -->
	<label>Frame Duration Limits (min - max)</label>
	<input type="text" id="FrameDurationLimits" placeholder="17849,112075593">

	<!-- Scaler Crop -->
	<label>Scaler Crop (x, y, width, height)</label>
	<input type="text" id="ScalerCrop" placeholder="0,0,4608,2592">
	<br><br>
	<button id="settings-btn-2">Send</button>
	<button id="settings-btn-3">Reload all config</button>
</div>

	</div>
	  <div class="card">
		<h2>Configurar Wifi</h2>
		<form method="POST" action="/wifi">
			<div class="setting">
				<label>SSID:</label>
				<input type="text" name="ssid" placeholder="Nombre de la red"><br><br>
			</div>
			
			<div class="setting">
				<label>Password:</label>
				<input name="password" type="text" placeholder="Contraseña">
			</div>
			<br><br>
		  <button type="submit" class="btn">Send</button>
		</form>
	</div>
  </section>

  <footer>By Uni44</footer>
  <footer>Version 2.3.3</footer>
  <script src="{{ url_for('static', filename='chart.js') }}"></script>
  
<script>
// Seleccionar todos los sliders (input type="range")
const sliders2 = document.querySelectorAll('input[type="range"]');

sliders2.forEach(slider => {

    // Crear un texto debajo del slider
    const valueText = document.createElement("div");
    valueText.style.fontSize = "12px";
    valueText.style.marginTop = "4px";
    valueText.style.color = "#fff";
    valueText.textContent = slider.value;

    // Insertar texto después del slider
    slider.insertAdjacentElement("afterend", valueText);

    // Actualizar cuando cambia
    slider.addEventListener("input", () => {
        valueText.textContent = slider.value;
    });
});
</script>

  <script>
	async function checkInternet() {
		const led = document.getElementById('ledInternet');
		led.className = 'dot blink'; // mientras intenta
		try {
			await fetch('https://www.google.com', {mode:'no-cors'});
			led.className = 'dot ok'; // verde si conecta
		} catch {
			led.className = 'dot err'; // rojo si falla
		}
	}

	// Ejecutar al cargar la página
	window.addEventListener('DOMContentLoaded', checkInternet);
	
	function updateCpuLed(cpuPercent){
		const led = document.getElementById('ledCpu');
		if(cpuPercent>80){
			led.className='dot blink err';
		} else {
			led.className='dot ok';
		}
	}
  
	const led = document.querySelector('.dot');
	led.classList.add('blink');   // empieza a titilar

	let temp = 0;
	let cpu  = 0;
	let ram  = 0;

	// Info del sistema (mock)
	function updateSystemStatus(data){
	  document.getElementById('cpuText').textContent = data.cpu+'%';
	  document.getElementById('cpuBar').style.width = data.cpu+'%';
	  document.getElementById('ramText').textContent = data.ram+'%';
	  document.getElementById('ramBar').style.width = data.ram+'%';
	  document.getElementById('tempText').textContent = data.temp+'°C';
	  document.getElementById('tempBar').style.width = data.temp+'%';
	  document.getElementById('diskText').textContent = data.disk+'%';
	  document.getElementById('diskBar').style.width = data.disk+'%';
	  document.getElementById('cpu_freqText').textContent = data.cpu_freq;
      document.getElementById('batText').textContent = data.ups.battery_percent+'%';
	  document.getElementById('batBar').style.width = data.ups.battery_percent+'%';
	  document.getElementById('volText').textContent = data.ups.voltage_v;
	  document.getElementById('loadText').textContent = data.ups.current_a;
	  
	  updateCpuLed(data.cpu);
	  temp = data.temp
	  cpu = data.cpu
	  ram = data.ram
	  
	  if (data.running) {
		const led = document.getElementById('ledCamara');
		led.className='dot ok';
	  } else {
		const led = document.getElementById('ledCamara');
		led.className='dot blink err';
	  }
	}

	// Actualización real de sistema
	async function fetchSystemStatus() {
	  try {
		const res = await fetch('/status');

		if (!res.ok) {
		  console.log("Servidor respondió con error");
		  return;
		}

		const data = await res.json();
		updateSystemStatus(data);
		
		const led = document.getElementById('ledConectado');
		led.className='dot ok';
	  } catch (err) {
		console.log("No hay conexión o fetch falló");
		const led = document.getElementById('ledConectado');
		led.className='dot blink err';
	  }
	}

	// Actualiza cada 2 segundos
	setInterval(fetchSystemStatus, 2000);

  // Utilidades Pi (requiere backend)
  function restartPi(){fetch('/restart',{method:'POST'});}
  function restartHdmi(){
    fetch('/api/hdmi/restart',{method:'POST'}).then(res=>{
      if(res.ok){
        console.log('Solicitud de reinicio HDMI enviada');
      } else {
        console.warn('Fallo al solicitar reinicio HDMI');
      }
    }).catch(err=>{console.error('Error reiniciando HDMI:', err)});
  }
  function shutdownPi(){fetch('/shutdown',{method:'POST'});}
  function restartStream(){fetch('/start',{method:'POST'});}
  function stopStream(){fetch('/stop',{method:'POST'});}
	
	const ctx = document.getElementById('unicamChart').getContext('2d');
	const unicamChart = new Chart(ctx, {
  type: 'line',
  data: {
    labels: [],
    datasets: [
      {
        label: 'Temperatura °C',
        data: [],
        borderColor: '#facc15', // Amarillo Unicam
        backgroundColor: 'rgba(250, 204, 21, 0.1)',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.25,
        fill: false
      },
      {
        label: 'CPU %',
        data: [],
        borderColor: '#00bcd4', // Celeste
        backgroundColor: 'rgba(0, 188, 212, 0.1)',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.25,
        fill: false
      },
      {
        label: 'RAM %',
        data: [],
        borderColor: '#00ff99', // Verde
        backgroundColor: 'rgba(0, 255, 153, 0.1)',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.25,
        fill: false
      }
    ]
  },
  options: {
    responsive: true,
    maintainAspectRatio: true,
    animation: false,
    scales: {
      y: {
        min: 0,
        max: 100,
        ticks: {
          color: '#fff',
          font: { family: 'monospace', size: 12 }
        },
        grid: { color: '#222' }
      },
      x: {
        display: false
      }
    },
    plugins: {
      legend: {
        labels: {
          color: '#facc15',
          font: { family: 'monospace', size: 12 }
        }
      }
    }
  }
});
	
	// Actualización en tiempo real
	setInterval(() => {
	  unicamChart.data.labels.push('');
	  unicamChart.data.datasets[0].data.push(temp);
	  unicamChart.data.datasets[1].data.push(cpu);
	  unicamChart.data.datasets[2].data.push(ram);

	  // Mantener 30 puntos visibles
	  if (unicamChart.data.labels.length > 30) {
		unicamChart.data.labels.shift();
		unicamChart.data.datasets.forEach(ds => ds.data.shift());
	  }

	  unicamChart.update();
	}, 1000);
	
	
	
	
	
	
	
	//CONFIG
	
	// ================================
//      LISTA DE CONTROLES
// ================================

// Sliders numéricos reales del IMX708
const sliders = [
  "Brightness",
  "Contrast",
  "Saturation",
  "Sharpness",
  "ColourTemperature",
  "ColourGains",
  "ExposureTime",
  "ExposureValue",
  "AnalogueGain",
  "AeFlickerPeriod",
  "LensPosition",
  "SyncFrames",
  "AfWindows",
  "FrameDurationLimits",
  "ScalerCrop"
];

// Checkboxes
const checks = [
  "AwbEnable",
  "AeEnable",
  "AfTrigger",
  "StatsOutputEnable",
  "CnnEnableInputTensor",
  "AutoReconnect"
];

// Selects
const selects = [
  "AwbMode",
  "AeExposureMode",
  "AeConstraintMode",
  "AeMeteringMode",
  "AeFlickerMode",
  "NoiseReductionMode",
  "HdrMode",
  "AfMode",
  "AfRange",
  "AfSpeed",
  "AfMetering",
  "AfPause",
  "SyncMode",
  "ExposureTimeMode",
  "AnalogueGainMode",
  "resolution",
  "fps",
  "modo",
  "bitrate",
  "preset",
  "protocolo_stream",
  "hdmi"
];
	
	// ================================
	//   Cargar configuración
	// ================================
	function cargarConfiguracion() {
	  fetch('/api/camera-config')
		.then(res => res.json())
		.then(config => {

		  // sliders
		  sliders.forEach(id => {
			const el = document.getElementById(id);
			if (el && config[id] !== undefined) {
			  el.value = config[id];
			}
		  });

		  // checkboxes
		  checks.forEach(id => {
			const el = document.getElementById(id);
			if (el && config[id] !== undefined) {
			  el.checked = config[id] ? true : false;
			}
		  });

		  // selects
		  selects.forEach(id => {
			const el = document.getElementById(id);
			if (el && config[id] !== undefined) {
			  el.value = config[id];
			}
		  });

		  // Configs extras (las dejo tal cual tenías)
		  document.getElementById("destino").value = config["IPDestino"];
		  document.getElementById("sdp").value = config["IPSDP"];
		  document.getElementById("protocolo").value = config["protocolo"];
		  document.getElementById("IPDestinoSRT").value = config["IPDestinoSRT"];
		  document.getElementById("puertoDestinoSRT").value = config["puertoDestinoSRT"];
		  document.getElementById("extraDataSRT").value = config["extraDataSRT"];
		  document.getElementById("mic").value = config["mic"];
		  actualizarSlidersAuto();
		});
	}
	
	// Función para actualizar todos los sliders creados automáticamente
	function actualizarSlidersAuto() {
		document.querySelectorAll('input[type="range"]').forEach(slider => {
			const valueText = slider.nextElementSibling;
			if (valueText) {
				valueText.textContent = slider.value;
			}
		});
	}

    // Obtener lista de micrófonos desde backend y cargar configuración al inicio
    async function fetchMics() {
      try {
        const res = await fetch('/api/mics');
        if (!res.ok) return;
        const list = await res.json();
        const sel = document.getElementById('mic');
        if (!sel) return;
        // limpiar y añadir opciones básicas
        sel.innerHTML = '';
        const disabledOpt = new Option('Disabled (!)', '!');
        sel.add(disabledOpt);
        const noneOpt = new Option('No mic (empty)', '');
        sel.add(noneOpt);
        list.forEach(item => {
          const opt = new Option(item.label, item.value);
          sel.add(opt);
        });
      } catch (e) {
        console.error('Error fetching mics:', e);
      }
    }

    // Ejecutar al inicio: primero traer mics, luego cargar configuración
    window.onload = async function() {
      await fetchMics();
      cargarConfiguracion();
    };
	//setInterval(cargarConfiguracion, 60000);

	// ================================
	//   Guardar configuración
	// ================================
	function saveConfig() {
		const config = {};
		
		// sliders numéricos
		sliders.forEach(id => {
			const el = document.getElementById(id);
			config[id] = parseFloat(el.value);
		});
		
		// checkboxes
		checks.forEach(id => {
			const el = document.getElementById(id);
			config[id] = el.checked;
		});
		
		// selects
		selects.forEach(id => {
			const el = document.getElementById(id);
			config[id] = el.value;
		});
		
		// extras
		config["IPDestino"] = document.getElementById("destino").value;
		config["IPSDP"] = document.getElementById("sdp").value;
		config["protocolo"] = document.getElementById("protocolo").value;
		config["IPDestinoSRT"] = document.getElementById("IPDestinoSRT").value;
		config["puertoDestinoSRT"] = document.getElementById("puertoDestinoSRT").value;
		config["extraDataSRT"] = document.getElementById("extraDataSRT").value;
		config["mic"] = document.getElementById("mic").value;
		
		// enviar al backend
		fetch('/api/camera-config', {
			method: 'POST',
			headers: {'Content-Type': 'application/json'},
			body: JSON.stringify(config)
		})
		.then(res => res.json())
		.then(d => console.log("Guardado OK:", d));
		}
	
	// ================================
	//   Registrar eventos
	// ================================
	const todos = [...sliders, ...checks, ...selects];
	todos.forEach(id => {
	  const el = document.getElementById(id);
	  if (el) {
		el.addEventListener("input", () => saveConfigDebounced());
	  }
	});

	let debounceTimeout = null;

	function saveConfigDebounced() {
		if (debounceTimeout) clearTimeout(debounceTimeout);
		debounceTimeout = setTimeout(() => {
			saveConfig();
		}, 500);
	}
	
	function forceReloadConfig() {
    fetch("/force_full_reload", { method: "POST" })
        .then(res => res.json())
        .then(data => console.log("Config recargada:", data))
        .catch(err => console.error("Error recargando config:", err));
	}
	
	
	document.getElementById("settings-btn-1").addEventListener("click", saveConfig);
	document.getElementById("settings-btn-2").addEventListener("click", saveConfig);
	document.getElementById("settings-btn-3").addEventListener("click", forceReloadConfig);
	
	function enviarZoom(direccion) {
            const formData = new FormData();
            formData.append('direction', direccion);

            fetch("/zoom", {
                method: 'POST',
                body: formData
            }).catch(err => console.error("Error:", err));
        }

        function configurarBoton(id, dir) {
            const btn = document.getElementById(id);
            
            // Cuando presionas: Envia 'in' o 'out'
            btn.addEventListener('mousedown', () => enviarZoom(dir));
            
            // Cuando sueltas (o sales del botón): Envia 'stop'
            btn.addEventListener('mouseup', () => enviarZoom('stop'));
            btn.addEventListener('mouseleave', () => enviarZoom('stop'));

            // Soporte para pantallas táctiles
            btn.addEventListener('touchstart', (e) => { e.preventDefault(); enviarZoom(dir); });
            btn.addEventListener('touchend', () => enviarZoom('stop'));
        }

        configurarBoton('zoomIn', 'in');
        configurarBoton('zoomOut', 'out');
	</script>
</div>
</body>
</html>
'''

HTML_COF = '''
{% if message %}
  <div style="margin-bottom: 12px; padding: 10px; border: 1px solid #ccc; background: #f8f8f8;">
    {{ message }}
  </div>
{% endif %}
<form method="POST">
  SSID: <input name="ssid"><br>
  Password: <input name="password" type="password"><br>
  <input type="submit" value="Guardar WiFi">
</form>
'''