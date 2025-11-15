HTML_PW = '''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Unicam Preview</title>
<style>
    html, body {
        margin: 0;
        padding: 0;
        background: #000;
        color: #fff;
        font-family: 'Roboto Mono', 'Courier New', monospace; /* look digital */
        overflow: hidden;
		
		display: flex;
		justify-content: center;
		align-items: center;
		height: 100vh;
    }
	
	button, .boton {
	  user-select: none;
	  -webkit-user-select: none;
	  -ms-user-select: none;
	}

    #video {
        display: block;
		will-change: transform;
		width: 100%;
		height: 100%;
		max-width: 100vw;
		max-height: 100vh;
		object-fit: contain; /* mantiene proporción */
    }

    /* ==== BOTONES SUPERIORES === */
    #controls {
        position: fixed;
        top: 10px;
        right: 10px;
        display: flex;
        gap: 10px;
        z-index: 10;
    }

    /* ==== BOTONES INFERIORES (ZOOM) === */
    #controls2 {
        position: fixed;
        bottom: 20px;
        left: 50%;
        transform: translateX(-50%);
        z-index: 8;
        display: flex;
        gap: 10px;
		user-select: none; /* Bloquea selección de texto */
		-webkit-user-select: none; /* Safari / Chrome móvil */
		-ms-user-select: none; /* Edge */
    }

    /* ==== ESTILO UNIFICADO PARA TODOS LOS BOTONES === */
    #controls button,
    #controls2 button {
        padding: 10px 14px;
        font-size: 10px;
        font-weight: 500;
        border: none;
    background-color: #fffff;
    color: #000000;
        cursor: pointer;
        opacity: 0.8;
        transition: all 0.25s ease;
        box-shadow: 0 2px 6px rgba(0,0,0,0.7);
		touch-action: manipulation; /* Evita gestos raros en móvil */
    }

    #controls button:hover,
    #controls2 button:hover {
        opacity: 1;
        background-color: #333;
        transform: scale(1.05);
    }

    /* Opcional: animación al presionar */
    #controls button:active,
    #controls2 button:active {
        transform: scale(0.95);
    }
    
    /* ==== NUEVO BLOQUE DE CONFIGURACIÓN DE CÁMARA ==== */
#config-controls {
    position: fixed;
    top: 70px;
    right: 10px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    z-index: 10;
}

#config-controls button {
    padding: 8px 12px;
    font-size: 10px;
    font-weight: 500;
    border: none;
    background-color: #fffff;
    color: #000000;
    cursor: pointer;
    opacity: 0.85;
    transition: all 0.2s ease;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
}

#config-controls button:hover {
    opacity: 1;
    background-color: #333;
    transform: scale(1.05);
}

/* ==== CONTENEDOR DE SELECTORES DE VIDEO ==== */
#video-settings {
    position: fixed;
    bottom: 80px;
    left: 10px;
    background: rgba(20, 20, 20, 0.2);
    padding: 12px 16px;
    border-radius: 10px;
    font-size: 10px;
    color: #fff;
    z-index: 10;
    box-shadow: 0 2px 6px rgba(0,0,0,0.5);
}

#video-settings label {
    display: block;
    margin-bottom: 10px;
    font-weight: 500;
}

#video-settings select {
    margin-left: 10px;
    padding: 5px 10px;
    background-color: #1e1e1e;
    border: 1px solid #444;
    border-radius: 6px;
    color: #fff;
    font-size: 10px;
    appearance: none;
    cursor: pointer;
    transition: border 0.2s;
}

#video-settings select:hover {
    border-color: #888;
}

#image-settings {
    position: fixed;
    bottom: 10px;
    right: 10px;
    background: rgba(20, 20, 20, 0.85);
    padding: 10px;
    border-radius: 10px;
    z-index: 10;
    color: white;
    font-size: 12px;
    width: 90vw;
    max-width: 600px;
    max-height: 40vh;
    overflow-y: auto;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.5);
}

#image-settings h3 {
    width: 100%;
    margin: 0 0 6px;
    font-size: 14px;
    color: #ccc;
    font-weight: 600;
}

.setting {
    flex: 1 1 calc(50% - 6px); /* dos columnas en horizontal */
    display: flex;
    align-items: center;
    gap: 5px;
    min-width: 150px;
}

#image-settings label {
    flex: 0 0 60px;
    font-weight: 500;
    font-size: 12px;
}

#image-settings input[type="range"] {
    flex: 1;
    cursor: pointer;
    accent-color: #ff69b4; /* rosa en vez de azul */
}

#image-settings select {
    flex: 1;
    padding: 3px 6px;
    border-radius: 6px;
    background-color: #1e1e1e;
    color: white;
    border: 1px solid #444;
}

#image-settings span {
    flex: 0 0 35px;
    text-align: right;
}

#image-settings button {
    padding: 6px 10px;
    font-size: 12px;
    font-weight: 500;
    border: none;
    border-radius: 8px;
    background-color: #1e1e1e;
    color: #fff;
    cursor: pointer;
    opacity: 0.85;
    transition: all 0.2s ease;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
}

#image-settings button:hover {
    opacity: 1;
    background-color: #333;
    transform: scale(1.05);
}

/* Ajuste especial para pantallas pequeñas */
@media (max-height: 450px) {
    #image-settings {
        font-size: 11px;
        gap: 4px;
    }
    .setting {
        flex: 1 1 100%;
    }
}

#video-settings {
    display: none;
}

#video-info {
    display: none;
}

#image-settings {
    display: none;
}

#video-settings, #image-settings {
  max-height: 90vh;
  overflow-y: auto;
}

#video-settings button {
    padding: 8px 12px;
    font-size: 15px;
    font-weight: 500;
    border: none;
    border-radius: 8px;
    background-color: #1e1e1e;
    color: #fff;
    cursor: pointer;
    opacity: 0.85;
    transition: all 0.2s ease;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
}

#video-settings button:hover {
    opacity: 1;
    background-color: #333;
    transform: scale(1.05);
}

#video-info {
    position: fixed;
    top: 40px;
    left: 10px;
    background: rgba(20, 20, 20, 0);
    padding: 10px 16px;
    font-size: 12px;
    z-index: 10;
}

#zoomcamplus-btn,
#zoomcammeno-btn,
#focusplus-btn,
#focusmeno-btn {
    display: none;
}

.rec-container {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 12px;
    position: fixed;
    top: 20px;
    left: 20px;
  }

  .rec-led {
    width: 14px;
    height: 14px;
    background: red;
    border-radius: 50%;
    animation: blink 1s infinite;
  }

  @keyframes blink {
    0%, 50%, 100% { opacity: 1; }
    25%, 75% { opacity: 0; }
  }

  .rec-text {
    color: white;
    font-weight: bold;
  }

  .rec-timer {
    color: white;
    font-weight: bold;
    font-size: 12px;
  }

.mid-info-container {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 12px;
    position: fixed;
    top: 10px;
    left: %50px;
  }

</style>
</head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<body>
    <div id="video-info"></div>

<div class="rec-container">
  <div class="rec-led"></div>
  <div id="rec-indicator" class="rec-text">LOADING</div>
  <div id="rec-timer" class="rec-timer">00:00:00:00</div>
</div>
<div id="mid-info-container" class="mid-info-container">LOADING</div>
<div id="controls">
    <button id="fullscreen-btn">PC</button>
    <button id="guide-btn">GS</button>
</div>
<div id="controls2">
    <button id="zoomplus-btn">+Z</button>
    <button id="zoommeno-btn">-Z</button>
	<button id="zoomcamplus-btn">📀 +</button>
    <button id="zoomcammeno-btn">📀 -</button>
	<button id="focusplus-btn">🔩 +</button>
    <button id="focusmeno-btn">🔩 -</button>
</div>
<div id="config-controls">
    <button id="data-btn">DT</button>
    <button id="settings-btn">CF</button>
</div>

<div id="video-settings">
	<h3>🎚️ Ajustes de Video</h3>
    <label>Resolución:
        <select id="resolution">
            <option>2560x1440</option>
            <option>1920x1080</option>
            <option>1280x720</option>
            <option>640x480</option>
        </select>
    </label>
    <label>FPS:
        <select id="fps">
			<option>90</option>
            <option>60</option>
            <option>30</option>
            <option>29</option>
			<option>24</option>
			<option>15</option>
			<option>5</option>
        </select>
    </label>
	<label>Calidad:
        <select id="calidad">
			<option>100</option>
            <option>90</option>
            <option>80</option>
            <option>70</option>
			<option>60</option>
			<option>50</option>
			<option>40</option>
			<option>30</option>
			<option>20</option>
			<option>10</option>
        </select>
    </label>
	<label>Resolución Vista:</label>
	<select id="resolutionVista">
            <option>2560x1440</option>
            <option>1920x1080</option>
            <option>1280x720</option>
            <option>640x480</option>
	</select>
	<label>FPS Vista:
	<select id="fpsVista">
			<option>90</option>
            <option>60</option>
            <option>30</option>
            <option>29</option>
			<option>24</option>
			<option>15</option>
			<option>5</option>
        </select>
    </label>
	<label>Calidad Vista:
	<select id="calidadVista">
		<option>100</option>
		<option>90</option>
		<option>80</option>
		<option>70</option>
		<option>60</option>
		<option>50</option>
		<option>40</option>
		<option>30</option>
		<option>20</option>
		<option>10</option>
        </select>
    </label>
	<button id="settings-btn-2">🔧 Enviar</button>
	<button id="settings-btn-3">❌ Cerrar</button>
</div>

<div id="image-settings">
    <h3>🎚️ Ajustes de Imagen</h3>
	
    <!-- Brillo -->
	<div class="setting">
        <label for="brightness">Brillo</label>
        <input type="range" id="brightness" min="-1" max="1" step="0.01" value="0">
        <span id="brightness-value">0</span><br>
	</div>

    <!-- Contraste -->
	<div class="setting">
        <label for="contrast">Contraste</label>
        <input type="range" id="contrast" min="0" max="4" step="0.1" value="1">
        <span id="contrast-value">1</span><br>
	</div>

    <!-- Saturación -->
	<div class="setting">
        <label for="saturation">Saturación</label>
        <input type="range" id="saturation" min="0" max="4" step="0.1" value="1">
        <span id="saturation-value">1</span><br>
	</div>
	
    <!-- Nitidez -->
	<div class="setting">
        <label for="sharpness">Nitidez</label>
        <input type="range" id="sharpness" min="0" max="4" step="0.1" value="1">
        <span id="sharpness-value">1</span><br>
	</div>

    <!-- Ganancia (AnalogueGain) -->
    <div class="setting">
        <label for="gain">Ganancia</label>
        <input type="range" id="gain" min="0" max="100" step="0.01" value="1">
        <span id="gain-value">1</span><br>
    </div>

    <!-- White Balance -->
    <div class="setting">
        <label for="whitebalance">White Balance</label>
        <select id="whitebalance">
            <option value="auto">Auto</option>
            <option value="manual">Manual</option>
        </select>
        <span id="whitebalance-value">auto</span>
    </div>

    <!-- Temperatura de color -->
    <div class="setting">
        <label for="temperature">Temperatura (K)</label>
        <input type="range" id="temperature" min="0" max="5000" step="10" value="4500">
        <span id="temperature-value">4500</span><br>
    </div>

    <!-- AWB Mode -->
    <div class="setting">
        <label for="awb-mode">AWB Mode</label>
        <select id="awb-mode">
            <option value="0">Auto</option>
            <option value="1">Incandescente</option>
            <option value="2">Fluorescente</option>
            <option value="3">Luz de día</option>
            <option value="4">Nublado</option>
            <option value="5">Sombra</option>
            <option value="6">Tungsteno</option>
            <option value="7">Flash</option>
        </select>
        <span id="awb-mode-value">0</span>
    </div>

    <!-- Exposure Mode -->
    <div class="setting">
        <label for="exposure-mode">Exposure Mode</label>
        <select id="exposure-mode">
            <option value="auto">Auto</option>
            <option value="manual">Manual</option>
        </select>
        <span id="exposure-mode-value">auto</span>
    </div>

    <!-- AE Exposure Mode -->
    <div class="setting">
        <label for="ae-exposure-mode">AE Exposure Mode</label>
        <select id="ae-exposure-mode">
            <option value="0">Normal</option>
            <option value="1">Corto</option>
            <option value="2">Largo</option>
            <option value="3">Custom</option>
        </select>
        <span id="ae-exposure-mode-value">0</span>
    </div>

    <!-- AE Metering -->
    <div class="setting">
        <label for="ae-metering">AE Metering</label>
        <select id="ae-metering">
            <option value="0">Promedio</option>
            <option value="1">Centro</option>
            <option value="2">Spot</option>
            <option value="3">Matriz</option>
        </select>
        <span id="ae-metering-value">0</span>
    </div>

    <!-- AE Constraint Mode -->
    <div class="setting">
        <label for="ae-constraint-mode">AE Constraint</label>
        <select id="ae-constraint-mode">
            <option value="0">Normal</option>
            <option value="1">Highlight</option>
            <option value="2">Shadows</option>
            <option value="3">Custom</option>
        </select>
        <span id="ae-constraint-mode-value">0</span>
    </div>

    <!-- AE Flicker Mode -->
    <div class="setting">
        <label for="ae-flicker-mode">AE Flicker</label>
        <select id="ae-flicker-mode">
            <option value="0">Off</option>
            <option value="1">Auto</option>
        </select>
        <span id="ae-flicker-mode-value">0</span>
    </div>

    <!-- Tiempo de exposición -->
    <div class="setting">
        <label for="exposure">Exposure Time (μs)</label>
        <input type="range" id="exposure" min="0" max="100000" step="100" value="20000">
        <span id="exposure-value">20000</span><br>
    </div>

    <!-- Exposure Value (EV compensation) -->
    <div class="setting">
        <label for="exposure-ev">Exposure Value (EV)</label>
        <input type="range" id="exposure-ev" min="-8" max="8" step="0.1" value="0">
        <span id="exposure-ev-value">0</span><br>
    </div>
</div>
	<script src="{{ url_for('static', filename='socket.io.min.js') }}"></script>
    <script>
	const testImage = new Image();
	testImage.src = "https://i.imgur.com/9oCV4tC.jpeg";
	let testImageLoaded = false;
	testImage.onload = () => {
	  testImageLoaded = true;
	  console.log("Imagen de test cargada");
	};
	
	let expectedFPS = 30;
	let expectedWidth = 1920;
	let expectedHeight = 1080;
	
    const settingsBtn = document.getElementById('settings-btn');
	const settingsBtn2 = document.getElementById('settings-btn-3');
    const videoSettings = document.getElementById('video-settings');
	const dataBtn = document.getElementById('data-btn');
    const data = document.getElementById('video-info');
	const image = document.getElementById('image-settings');

    let settingsVisible = false;
	let dataVisible = false;

    settingsBtn.addEventListener('click', () => {
        settingsVisible = !settingsVisible;
        videoSettings.style.display = settingsVisible ? 'block' : 'none';
		image.style.display = settingsVisible ? 'block' : 'none';
    });
	
	settingsBtn2.addEventListener('click', () => {
        settingsVisible = !settingsVisible;
        videoSettings.style.display = settingsVisible ? 'block' : 'none';
		image.style.display = settingsVisible ? 'block' : 'none';
    });
	
	dataBtn.addEventListener('click', () => {
        dataVisible = !dataVisible;
        data.style.display = dataVisible ? 'block' : 'none';
    });
	
	function isMobile() {
		return /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
	}
	
	// --- Sliders con valores numéricos ---
	const sliders = [
	  "brightness",   // -1.0 a 1.0
	  "contrast",     // 0.0 a 32.0
	  "saturation",   // 0.0 a 32.0
	  "sharpness",    // 0.0 a 16.0
	  //"gamma",        // 0.1 a 10.0
	  "gain",         // 1.0 a 16.0 (AnalogueGain)
	  "temperature",   // 2500 a 8000 (ColourTemperature)
	  "exposure",
	  "exposure-ev"
	];

	// --- Selects con opciones predefinidas ---
	const selects = {
	  "whitebalance": document.getElementById("whitebalance"),  // Auto, Off, Tungsten, etc.
	  "exposure-mode": document.getElementById("exposure-mode"),// auto/manual
	  "awb-mode": document.getElementById("awb-mode"),
	  "ae-exposure-mode": document.getElementById("ae-exposure-mode"),
	  "ae-metering": document.getElementById("ae-metering"),
	  "ae-constraint-mode": document.getElementById("ae-constraint-mode"),
	  "ae-flicker-mode": document.getElementById("ae-flicker-mode"),
	  "resolution": document.getElementById("resolution"),
	  "fps": document.getElementById("fps"),
	  "calidad": document.getElementById("calidad"),
	  "resolutionVista": document.getElementById("resolutionVista"),
	  "fpsVista": document.getElementById("fpsVista"),
	  "calidadVista": document.getElementById("calidadVista")
	};

	// Valores iniciales
	let resolutionOriginal = "1920x1080"
	let fpsOriginal = 30
	let calidadOriginal = 80
	let resolutionVista = "1920x1080"
	let fpsVista = 24
	let calidadVista = 10
	
	function cargarConfiguracion() {
		// Cargar configuración al iniciar
		fetch('/api/camera-config')
		  .then(res => res.json())
		  .then(config => {
			sliders.forEach(key => {
			  const el = document.getElementById(key);
			  if (el && config[key] !== undefined) {
				el.value = config[key];
				actualizarValor(key);
			  } else {
				console.warn("No existe el control para:", key);
			  }
			});

			Object.entries(selects).forEach(([key, el]) => {
			  if (el && config[key] !== undefined) {
				el.value = config[key];
				actualizarValor(key);
			  } else {
				console.warn("No existe el select para:", key);
			  }
			});

			[expectedWidth, expectedHeight] = config["resolutionVista"].toLowerCase().split("x").map(Number);
			expectedFPS = config["fpsVista"]

			resolutionOriginal = config["resolution"]
			fpsOriginal = config["fps"]
			calidadOriginal = config["calidad"]
			resolutionVista = config["resolutionVista"]
			fpsVista = config["fpsVista"]
			calidadVista = config["calidadVista"]
		  });
		  resizeCanvas();
	}
	// Ejecutar al iniciar
	cargarConfiguracion();
	// Repetir cada 1 minuto
	setInterval(cargarConfiguracion, 60000);

	// Guardar al cambiar valores
	function saveConfig() {
	  const config = {};
	  
	  // sliders (números)
	  sliders.forEach(key => {
		let val = parseFloat(document.getElementById(key).value);
		config[key] = isNaN(val) ? 0 : val;
	  });

	  // selects (texto o int)
	  Object.entries(selects).forEach(([key, el]) => {
		if (key === "fps" || key === "fpsVista") {
		  config[key] = parseInt(el.value);
		} else if (key.includes("calidad")) {
		  config[key] = parseInt(el.value);
		} else {
		  config[key] = el.value;
		}
	  });

	  fetch('/api/camera-config', {
		method: 'POST',
		headers: {'Content-Type': 'application/json'},
		body: JSON.stringify(config)
	  })
	  .then(res => res.json())
	  .then(data => console.log("Guardado:", data));

	[expectedWidth, expectedHeight] = config["resolutionVista"].toLowerCase().split("x").map(Number);
	  expectedFPS = config["fpsVista"]
	  resolutionOriginal = config["resolution"]
	  fpsOriginal = config["fps"]
	  calidadOriginal = config["calidad"]
	  resolutionVista = config["resolutionVista"]
	  fpsVista = config["fpsVista"]
	  calidadVista = config["calidadVista"]
	}

	// Lista de controles a monitorear (sin duplicados)
	const controles = [...sliders, ...Object.keys(selects)];
	controles.forEach(id => {
	  const control = document.getElementById(id);
	  if (control) {
		control.addEventListener('input', () => actualizarValor(id));
	  }
	});

	// Inicializar valores al cargar
	window.onload = () => {
	  controles.forEach(id => actualizarValor(id));
	};

	let debounceTimeout = null;

	function saveConfigDebounced() {
		if (debounceTimeout) clearTimeout(debounceTimeout);
		debounceTimeout = setTimeout(() => {
			saveConfig();
		}, 500);
	}
	
	document.getElementById("settings-btn-2").addEventListener("click", saveConfig);
		
        const infoBox = document.getElementById("video-info");
        let showGuides = false;
        const videoData = {
            baseInfo: '',         // Texto estático, como título o info del servidor
            frameWidth: null,     // Ancho del frame recibido
            frameHeight: null,    // Alto del frame
            frameSizeKB: null,    // Tamaño del frame en KB
            clientFPS: null       // FPS reales calculados en el cliente
        };

        // Opcional: escalado para adaptarse a la pantalla sin deformar
		function resizeCanvas() {
			document.getElementById("mid-info-container").textContent = "16:9 | " + resolutionOriginal + " | " + fpsOriginal + " FPS";
		}
		window.addEventListener("resize", resizeCanvas);
		resizeCanvas();

        const socket = io();
        let frameCounter = 0;
        let lastSecond = performance.now();

        // FPS real en cliente
        setInterval(() => {
            const now = performance.now();
            const fps = frameCounter / ((now - lastSecond) / 1000);
            frameCounter = 0;
            lastSecond = now;

            videoData.clientFPS = fps.toFixed(2)
        }, 1000);
       
		let latestBlob = null;
		let processing = false;
		let paused = false;
		let lastDrawnBlob = null;

		// Métricas
		let framesReceived = 0;
		let framesDrawn = 0;
		let frameDrops = 0;
		let lastFPSUpdate = performance.now();
		let fpsReceived = 0;
		let fpsDrawn = 0;
		let realFPSReceived = 0;
		let realFPSDrawn = 0;
		let lowPerfMode = false;
		let fpsAnterior = 30;
	   
		const frameQueue = [];
		const MAX_QUEUE_SIZE = 2;
		
		// Función para actualizar valores visibles
		function actualizarValor(id) {
		  const control = document.getElementById(id);
		  const valorSpan = document.getElementById(id + '-value');

		  if (control && valorSpan) {
			valorSpan.textContent = control.value;
		  } else {
			console.warn("Elemento no encontrado:", id, control, valorSpan);
		  }
		}
		
		let upTime = Date.now();
		async function updateSystemInfo() {
			try {
				const res = await fetch("/system-info");

				if (!res.ok) {
					throw new Error(`HTTP ${res.status} - ${res.statusText}`);
				}

				const data = await res.json();
				upTime = data.uptime;

				return {
					cpu: data.cpu,
					ram: `${data.ram_used}/${data.ram_total} GB`,
					temp: `${data.temperature}°C`,
					disk: `${data.disk}%`
				};
			} catch (err) {
				console.error("Error en updateSystemInfo:", err);
				return {
					cpu: "Error",
					ram: "Error",
					temp: "Error",
					disk: "Error"
				};
			}
		}
				
		function updateTimer() {
			let diff = Date.now() - upTime; // milisegundos

			let hours = Math.floor(diff / 3600000);
			diff %= 3600000;
			let minutes = Math.floor(diff / 60000);
			diff %= 60000;
			let seconds = Math.floor(diff / 1000);
			let milliseconds = Math.floor((diff % 1000) / 10); // dos dígitos

			// formato 00:00:00:00
			const formatted = 
				String(hours).padStart(2,'0') + ':' +
				String(minutes).padStart(2,'0') + ':' +
				String(seconds).padStart(2,'0') + ':' +
				String(milliseconds).padStart(2,'0');

			document.getElementById("rec-timer").textContent = formatted;
		}
		setInterval(updateTimer, 10);

		async function updateDisplay() {
			if (!dataVisible) { return }
				
			const now = performance.now();
			const delta = (now - lastFPSUpdate) / 1000;

			realFPSReceived = (fpsReceived / delta).toFixed(1);
			realFPSDrawn = (fpsDrawn / delta).toFixed(1);
			frameDrops = Math.max(0, fpsReceived - fpsDrawn);
			
			if (fpsReceived > 2) {
				document.getElementById("rec-indicator").textContent = "STR";
			}

			fpsReceived = 0;
			fpsDrawn = 0;
			lastFPSUpdate = now;

			// Comportamiento low performance
			if (realFPSDrawn < 10 && !lowPerfMode) {
				fpsAnterior = expectedFPS;
				expectedFPS = 10;
				lowPerfMode = true;
			} else if (realFPSDrawn >= 15 && lowPerfMode) {
				expectedFPS = fpsAnterior;
				lowPerfMode = false;
			}

			const sysInfo = await updateSystemInfo();

			const info = [];

			// Info base que tengas
			// info.push(videoData.baseInfo || "");
			info.push(`Resolución Cámara: ${resolutionOriginal}`);
			info.push(`Resolución Vista: ${resolutionVista}`);

			info.push(`FPS Cámara: ${fpsOriginal}`);
			info.push(`FPS Vista: ${fpsVista}`);
			info.push(`FPS Objetivo: ${expectedFPS}`);
			info.push(`FPS Recibidos: ${realFPSReceived}`);
			info.push(`FPS Dibujados: ${realFPSDrawn}`);
			info.push(`FPS Perdidos: ${frameDrops}`);

			info.push(`CPU: ${sysInfo.cpu}%`);
			info.push(`RAM: ${sysInfo.ram}`);
			info.push(`TMP: ${sysInfo.temp}`);
			info.push(`DSK: ${sysInfo.disk}`);

			infoBox.innerHTML = info.join('<br>');
		}

		// Loop que actualiza todo cada segundo
		setInterval(updateDisplay, 10000);

        document.getElementById("fullscreen-btn").addEventListener("click", () => {
            const el = document.documentElement;
            if (el.requestFullscreen) el.requestFullscreen();
            else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen();
            else if (el.msRequestFullscreen) el.msRequestFullscreen();
        });
        
        document.getElementById("guide-btn").addEventListener("click", () => {
            showGuides = !showGuides;
            console.log("Guías activadas:", showGuides);
        });
        
         // Zoom In
            const zoomInBtn = document.getElementById("zoomplus-btn");
			zoomInBtn.addEventListener("mousedown", () => {
                fetch('/zoom', {
					method: 'POST',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
					body: 'direction=in'
				});
            });
            zoomInBtn.addEventListener("touchstart", () => {
                fetch('/zoom', {
					method: 'POST',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
					body: 'direction=in'
				});
            });
			zoomInBtn.addEventListener("mouseup", () => {
				fetch('/zoom', {
					method: 'POST',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
					body: 'direction=stop'
				});
			});
			zoomInBtn.addEventListener("touchend", () => {
				fetch('/zoom', {
					method: 'POST',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
					body: 'direction=stop'
				});
			});

		// Zoom Out
            const zoomOutBtn = document.getElementById("zoommeno-btn");
			zoomOutBtn.addEventListener("mousedown", () => {
                fetch('/zoom', {
					method: 'POST',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
					body: 'direction=out'
				});
            });
            zoomOutBtn.addEventListener("touchstart", () => {
                fetch('/zoom', {
					method: 'POST',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
					body: 'direction=out'
				});
            });
			zoomOutBtn.addEventListener("mouseup", () => {
				fetch('/zoom', {
					method: 'POST',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
					body: 'direction=stop'
				});
			});
			zoomOutBtn.addEventListener("touchend", () => {
				fetch('/zoom', {
					method: 'POST',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
					body: 'direction=stop'
				});
			});

        window.addEventListener("load", () => {
            resizeCanvas();
        });
    </script>
</body>
</html>
'''

HTML_OR = '''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Unicam Original</title>
<style>
    html, body {
        margin: 0;
        padding: 0;
        background: #000;
        color: #fff;
        font-family: 'Roboto Mono', 'Courier New', monospace; /* look digital */
        overflow: hidden;
		
		display: flex;
		justify-content: center;
		align-items: center;
		height: 100vh;
    }

    #videoCanvas {
        display: block;
		will-change: transform;
		image-rendering: auto;
		display: block;
		
		background: black;
		width: 100%;
		height: 100%;
		max-width: 100vw;
		max-height: 100vh;
		object-fit: contain; /* mantiene proporción */
    }
</style>
</head>
<body>
<canvas id="videoCanvas"></canvas>
<script src="{{ url_for('static', filename='socket.io.min.js') }}"></script>
<script>
const canvas = document.getElementById("videoCanvas");
const ctx = canvas.getContext("2d");

canvas.width = 1920;
canvas.height = 1080;
canvas.style.width = "100%";
canvas.style.height = "100%";

let latestBitmap = null;
let frameReady = false;

const socket = io();

// Recibir frames delta
let lastFrameTime = performance.now();
let frameCount = 0;
let fps = 0;

// Cada frame que llega
socket.on("video_frame", (data) => {
    createImageBitmap(new Blob([data], { type: "image/webp" }))
        .then(bitmap => {
            // Dibujar el frame
            ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);

            frameCount++; // Contamos cuántos frames llegaron
        });
});

// Actualizar FPS cada segundo
setInterval(() => {
    const now = performance.now();
    fps = frameCount / ((now - lastFrameTime) / 1000); // FPS promedio
    lastFrameTime = now;
    frameCount = 0;

    // Limpiar un área y dibujar FPS
    ctx.clearRect(0, 0, 100, 40);
    ctx.fillStyle = 'red';
    ctx.font = '20px Arial';
    ctx.fillText(`FPS: ${fps.toFixed(1)}`, 10, 30);
}, 1000);

// Loop de dibujo
function drawLoop() {
    if (frameReady && reconstructedFrame) {
        ctx.putImageData(reconstructedFrame, 0, 0);
        frameReady = false;
    }
    requestAnimationFrame(drawLoop);
}

drawLoop();
</script>
</body>
</html>
'''

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
		  <span class="dot ok"></span> Cámara
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
      <div class="status-text">Temperatura: <span id="tempText">0°C</span></div>
      <div class="status-bar"><div id="tempBar" class="status-fill"></div></div>
      <div class="status-text">Disco: <span id="diskText">0%</span></div>
      <div class="status-bar"><div id="diskBar" class="status-fill"></div></div>
    </div>
	
	<div class="chart-box">
	  <h3>Monitoreo del Sistema</h3>
	  <canvas id="unicamChart"></canvas>
	</div>
	
	<!-- Utilidades -->
    <div class="card">
      <h2>Funciones</h2>
      <button class="btn" onclick="restartPi()">Restart</button>
	  <h2> </h2>
      <button class="btn" onclick="shutdownPi()">Shutdown</button>
	  <h2> </h2>
      <button class="btn" onclick="window.location.href='/files'">Files</button>
	  <button class="btn" onclick="window.location.href='/browse/home/pi/Unicam/fotos'">Pictures</button>
	  <button class="btn" onclick="window.location.href='/browse/home/pi/Unicam/videos'">Videos</button>
	  <h2> </h2>
	  <button class="btn" onclick="restartStream()">START</button>
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
	<button id="settings-btn-1">Enviar</button>
</div>
</div>
<div class="card">
<div id="image-settings">
    <h3>Ajustes de Imagen</h3>
	
    <!-- Brillo -->
	<div class="setting">
        <label for="brightness">Brillo</label>
        <input type="range" id="brightness" min="-1" max="1" step="0.01" value="0">
        <span id="brightness-value">0</span><br>
	</div>

    <!-- Contraste -->
	<div class="setting">
        <label for="contrast">Contraste</label>
        <input type="range" id="contrast" min="0" max="4" step="0.1" value="1">
        <span id="contrast-value">1</span><br>
	</div>

    <!-- Saturación -->
	<div class="setting">
        <label for="saturation">Saturación</label>
        <input type="range" id="saturation" min="0" max="4" step="0.1" value="1">
        <span id="saturation-value">1</span><br>
	</div>
	
    <!-- Nitidez -->
	<div class="setting">
        <label for="sharpness">Nitidez</label>
        <input type="range" id="sharpness" min="0" max="4" step="0.1" value="1">
        <span id="sharpness-value">1</span><br>
	</div>

    <!-- Ganancia (AnalogueGain) -->
    <div class="setting">
        <label for="gain">Ganancia</label>
        <input type="range" id="gain" min="0" max="100" step="0.01" value="1">
        <span id="gain-value">1</span><br>
    </div>

    <!-- White Balance -->
    <div class="setting">
        <label for="whitebalance">White Balance</label>
        <select id="whitebalance">
            <option value="auto">Auto</option>
            <option value="manual">Manual</option>
        </select>
        <span id="whitebalance-value">auto</span>
    </div>

    <!-- Temperatura de color -->
    <div class="setting">
        <label for="temperature">Temperatura (K)</label>
        <input type="range" id="temperature" min="0" max="5000" step="10" value="4500">
        <span id="temperature-value">4500</span><br>
    </div>

    <!-- AWB Mode -->
    <div class="setting">
        <label for="awb-mode">AWB Mode</label>
        <select id="awb-mode">
            <option value="0">Auto</option>
            <option value="1">Incandescente</option>
            <option value="2">Fluorescente</option>
            <option value="3">Luz de día</option>
            <option value="4">Nublado</option>
            <option value="5">Sombra</option>
            <option value="6">Tungsteno</option>
            <option value="7">Flash</option>
        </select>
        <span id="awb-mode-value">0</span>
    </div>

    <!-- Exposure Mode -->
    <div class="setting">
        <label for="exposure-mode">Exposure Mode</label>
        <select id="exposure-mode">
            <option value="auto">Auto</option>
            <option value="manual">Manual</option>
        </select>
        <span id="exposure-mode-value">auto</span>
    </div>

    <!-- AE Exposure Mode -->
    <div class="setting">
        <label for="ae-exposure-mode">AE Exposure Mode</label>
        <select id="ae-exposure-mode">
            <option value="0">Normal</option>
            <option value="1">Corto</option>
            <option value="2">Largo</option>
            <option value="3">Custom</option>
        </select>
        <span id="ae-exposure-mode-value">0</span>
    </div>

    <!-- AE Metering -->
    <div class="setting">
        <label for="ae-metering">AE Metering</label>
        <select id="ae-metering">
            <option value="0">Promedio</option>
            <option value="1">Centro</option>
            <option value="2">Spot</option>
            <option value="3">Matriz</option>
        </select>
        <span id="ae-metering-value">0</span>
    </div>

    <!-- AE Constraint Mode -->
    <div class="setting">
        <label for="ae-constraint-mode">AE Constraint</label>
        <select id="ae-constraint-mode">
            <option value="0">Normal</option>
            <option value="1">Highlight</option>
            <option value="2">Shadows</option>
            <option value="3">Custom</option>
        </select>
        <span id="ae-constraint-mode-value">0</span>
    </div>

    <!-- AE Flicker Mode -->
    <div class="setting">
        <label for="ae-flicker-mode">AE Flicker</label>
        <select id="ae-flicker-mode">
            <option value="0">Off</option>
            <option value="1">Auto</option>
        </select>
        <span id="ae-flicker-mode-value">0</span>
    </div>

    <!-- Tiempo de exposición -->
    <div class="setting">
        <label for="exposure">Exposure Time (μs)</label>
        <input type="range" id="exposure" min="0" max="100000" step="100" value="20000">
        <span id="exposure-value">20000</span><br>
    </div>

    <!-- Exposure Value (EV compensation) -->
    <div class="setting">
        <label for="exposure-ev">Exposure Value (EV)</label>
        <input type="range" id="exposure-ev" min="-8" max="8" step="0.1" value="0">
        <span id="exposure-ev-value">0</span><br>
    </div>
	
	<div class="setting">
        <label for="noiseRed">Noise</label>
        <input type="range" id="noiseRed" min="0" max="4" step="1" value="0">
        <span id="noiseRed-value">0</span><br>
    </div>
	
	<div class="setting">
        <label for="hdr">HDR</label>
        <input type="range" id="hdr" min="0" max="4" step="1" value="0">
        <span id="hdr-value">0</span><br>
    </div>
	<br>
	<button id="settings-btn-2">Enviar</button>
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
		  <button type="submit" class="btn">Enviar</button>
		</form>
	</div>
  </section>

  <footer>By Uni44</footer>
  <script src="{{ url_for('static', filename='chart.js') }}"></script>
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
	  updateCpuLed(data.cpu);
	  temp = data.temp
	  cpu = data.cpu
	  ram = data.ram
	}

	// Actualización real de sistema
	async function fetchSystemStatus() {
	  try {
		const res = await fetch('/status');
		if (!res.ok) throw new Error('Error al obtener datos');
		const data = await res.json();
		updateSystemStatus(data);
	  } catch(e) {
		console.error(e);
	  }
	}

	// Actualiza cada 2 segundos
	setInterval(fetchSystemStatus, 2000);

	// Utilidades Pi (requiere backend)
	function restartPi(){fetch('/restart',{method:'POST'});}
	function shutdownPi(){fetch('/shutdown',{method:'POST'});}
	function restartStream(){fetch('/start',{method:'POST'});}
	
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
	
	
	
	
	
	
	// --- Sliders con valores numéricos ---
	const sliders = [
	  "brightness",   // -1.0 a 1.0
	  "contrast",     // 0.0 a 32.0
	  "saturation",   // 0.0 a 32.0
	  "sharpness",    // 0.0 a 16.0
	  //"gamma",        // 0.1 a 10.0
	  "gain",         // 1.0 a 16.0 (AnalogueGain)
	  "temperature",   // 2500 a 8000 (ColourTemperature)
	  "exposure",
	  "exposure-ev",
	  "noiseRed",
	  "hdr"
	];

	// --- Selects con opciones predefinidas ---
	const selects = {
	  "whitebalance": document.getElementById("whitebalance"),  // Auto, Off, Tungsten, etc.
	  "exposure-mode": document.getElementById("exposure-mode"),// auto/manual
	  "awb-mode": document.getElementById("awb-mode"),
	  "ae-exposure-mode": document.getElementById("ae-exposure-mode"),
	  "ae-metering": document.getElementById("ae-metering"),
	  "ae-constraint-mode": document.getElementById("ae-constraint-mode"),
	  "ae-flicker-mode": document.getElementById("ae-flicker-mode"),
	  "resolution": document.getElementById("resolution"),
	  "fps": document.getElementById("fps"),
	  "modo": document.getElementById("modo"),
	  "bitrate": document.getElementById("bitrate"),
	  "preset": document.getElementById("preset"),
	  "protocolo_stream": document.getElementById("protocolo_stream")
	};
	
	function cargarConfiguracion() {
		// Cargar configuración al iniciar
		fetch('/api/camera-config')
		  .then(res => res.json())
		  .then(config => {
			sliders.forEach(key => {
			  const el = document.getElementById(key);
			  if (el && config[key] !== undefined) {
				el.value = config[key];
				actualizarValor(key);
			  } else {
				console.warn("No existe el control para:", key);
			  }
			});

			Object.entries(selects).forEach(([key, el]) => {
			  if (el && config[key] !== undefined) {
				el.value = config[key];
				actualizarValor(key);
			  } else {
				console.warn("No existe el select para:", key);
			  }
			});
			
			document.getElementById("destino").value = config["IPDestino"];
			document.getElementById("sdp").value = config["IPSDP"];
			document.getElementById("protocolo").value = config["protocolo"];
			document.getElementById("IPDestinoSRT").value = config["IPDestinoSRT"];
			document.getElementById("puertoDestinoSRT").value = config["puertoDestinoSRT"];
			document.getElementById("extraDataSRT").value = config["extraDataSRT"];
		  });
	}
	// Ejecutar al iniciar
	cargarConfiguracion();
	// Repetir cada 1 minuto
	setInterval(cargarConfiguracion, 60000);

	// Guardar al cambiar valores
	function saveConfig() {
	  const config = {};
	  
	  // sliders (números)
	  sliders.forEach(key => {
		let val = parseFloat(document.getElementById(key).value);
		config[key] = isNaN(val) ? 0 : val;
	  });

	  // selects (texto o int)
	  Object.entries(selects).forEach(([key, el]) => {
		if (key === "fps" || key === "fpsVista") {
		  config[key] = parseInt(el.value);
		} else if (key.includes("calidad")) {
		  config[key] = parseInt(el.value);
		} else {
		  config[key] = el.value;
		}
	  });
	  
	  config["IPDestino"] = document.getElementById("destino").value;
	  config["IPSDP"] = document.getElementById("sdp").value;
	  config["protocolo"] = document.getElementById("protocolo").value;
	  config["IPDestinoSRT"] = document.getElementById("IPDestinoSRT").value;
	  config["puertoDestinoSRT"] = document.getElementById("puertoDestinoSRT").value;
	  config["extraDataSRT"] = document.getElementById("extraDataSRT").value;

	  fetch('/api/camera-config', {
		method: 'POST',
		headers: {'Content-Type': 'application/json'},
		body: JSON.stringify(config)
	  })
	  .then(res => res.json())
	  .then(data => console.log("Guardado:", data));
	}

	// Lista de controles a monitorear (sin duplicados)
	const controles = [...sliders, ...Object.keys(selects)];
	controles.forEach(id => {
	  const control = document.getElementById(id);
	  if (control) {
		control.addEventListener('input', () => actualizarValor(id));
	  }
	});

	// Inicializar valores al cargar
	window.onload = () => {
	  controles.forEach(id => actualizarValor(id));
	};

	let debounceTimeout = null;

	function saveConfigDebounced() {
		if (debounceTimeout) clearTimeout(debounceTimeout);
		debounceTimeout = setTimeout(() => {
			saveConfig();
		}, 500);
	}
	
	document.getElementById("settings-btn-1").addEventListener("click", saveConfig);
	document.getElementById("settings-btn-2").addEventListener("click", saveConfig);
	
	// Función para actualizar valores visibles
		function actualizarValor(id) {
		  const control = document.getElementById(id);
		  const valorSpan = document.getElementById(id + '-value');

		  if (control && valorSpan) {
			valorSpan.textContent = control.value;
		  } else {
			console.warn("Elemento no encontrado:", id, control, valorSpan);
		  }
		}
	</script>
</div>
</body>
</html>
'''

HTML_COF = '''
<form method="POST">
  SSID: <input name="ssid"><br>
  Password: <input name="password" type="password"><br>
  <input type="submit">
</form>
'''