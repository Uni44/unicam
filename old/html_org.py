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
    <canvas id="videoCanvas"></canvas>
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
        <input type="range" id="gain" min="1" max="4" step="0.01" value="1">
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
	let lastFrameTime = performance.now();
	const canvas = document.getElementById("videoCanvas");
	
	canvas.style.transform = "translateZ(0)"; // fuerza aceleración GPU en algunos navegadores
	
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

	// En vez de "input" directo a saveConfig, conectamos a saveConfigDebounced:
	//[...sliders.map(id => document.getElementById(id)), ...Object.values(selects)]
	//	.forEach(el => el.addEventListener("input", saveConfigDebounced));

	// Botón "Enviar" para guardar inmediatamente al apretarlo:
	document.getElementById("settings-btn-2").addEventListener("click", saveConfig);
		
        const ctx = canvas.getContext("2d");
        const infoBox = document.getElementById("video-info");
        let showGuides = false;
        const videoData = {
            baseInfo: '',         // Texto estático, como título o info del servidor
            frameWidth: null,     // Ancho del frame recibido
            frameHeight: null,    // Alto del frame
            frameSizeKB: null,    // Tamaño del frame en KB
            clientFPS: null       // FPS reales calculados en el cliente
        };
        let zoomInInterval;
        let zoomOutInterval;

        // Opcional: escalado para adaptarse a la pantalla sin deformar
		function resizeCanvas() {
			canvas.width = expectedWidth;
			canvas.height = expectedHeight;
			canvas.style.width = expectedWidth + "px";
			canvas.style.height = expectedHeight + "px";
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
	   
		// Receptor de frames
		socket.on("video_preview", (data) => {
			if (frameQueue.length < MAX_QUEUE_SIZE) {
				frameQueue.push(new Blob([data], { type: "image/jpeg" }));
				fpsReceived++;
			}
			lastFrameTime = performance.now();
		});
		
		const bitmapQueue = [];

		async function processFrames() {
			while (true) {
				if (frameQueue.length > 0) {
					const blob = frameQueue.shift();
					try {
						const bitmap = await createImageBitmap(blob);
						if (bitmapQueue.length < 2) {
							bitmapQueue.push(bitmap);
						}
					} catch {}
				}
				await new Promise(r => setTimeout(r, 0)); // micro-pausa
			}
		}
		
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
  
		processFrames()

		const baseWidth = 1920;
		const baseHeight = 1080;

		function scaleX(x) {
		  return x * canvas.width / baseWidth;
		}

		function scaleY(y) {
		  return y * canvas.height / baseHeight;
		}

		function drawLoop() {
			requestAnimationFrame(drawLoop);
			
			const now = performance.now();
			
			// Si no llegan frames, mostrar imagen de test
			if (now - lastFrameTime > 10000 && testImageLoaded) {
				ctx.clearRect(0, 0, canvas.width, canvas.height);
				ctx.drawImage(testImage, 0, 0, canvas.width, canvas.height);
				document.getElementById("rec-indicator").textContent = "ERROR";
				//console.log("Mostrando imagen de test (no llegan frames)");
				return;
			}
			
			if (paused || bitmapQueue.length === 0) return;

			const bitmap = bitmapQueue.shift();
			ctx.clearRect(0, 0, canvas.width, canvas.height);
			ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
				
			if (showGuides) {
			  ctx.strokeStyle = 'rgba(255,255,255,0.5)';
			  ctx.lineWidth = 2;

			  // Ejemplo de líneas fijas en base 1920x1080:
			  // Dividimos el canvas en tercios pero usando escala para que siempre quede igual

			  const line1X = scaleX(baseWidth / 3);       // 640 en base 1920
			  const line2X = scaleX(2 * baseWidth / 3);   // 1280 en base 1920
			  const line1Y = scaleY(baseHeight / 3);      // 360 en base 1080
			  const line2Y = scaleY(2 * baseHeight / 3);  // 720 en base 1080

			  ctx.beginPath();
			  ctx.moveTo(line1X, 0);           ctx.lineTo(line1X, canvas.height);
			  ctx.moveTo(line2X, 0);           ctx.lineTo(line2X, canvas.height);
			  ctx.moveTo(0, line1Y);           ctx.lineTo(canvas.width, line1Y);
			  ctx.moveTo(0, line2Y);           ctx.lineTo(canvas.width, line2Y);
			  ctx.stroke();
			}
				
			fpsDrawn++;
			
			//videoData.frameSizeKB = (blob.size / 1024).toFixed(1);
			videoData.frameWidth = expectedWidth;
			videoData.frameHeight = expectedHeight;
		}

		drawLoop(); // ← iniciá el render loop una vez
		
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
        
        const startZooming = (direction) => {
        const interval = setInterval(() => {
                fetch('/zoom', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded'
                    },
                    body: 'direction=' + direction
                });
            }, 1000); // cada 100ms

            return interval;
        };
		
		let interval2;
		function startZoom(direction) {
			if (interval2) return;  // Evita crear múltiples intervalos
			interval2 = setInterval(() => {
				fetch('/zoom', {
					method: 'POST',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
					body: 'direction=' + direction
				});
			}, 1000);  // cada 100ms para no saturar
		}
        
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
				clearInterval(zoomInInterval);
				fetch('/zoom', {
					method: 'POST',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
					body: 'direction=stop'
				});
			});
			zoomInBtn.addEventListener("touchend", () => {
				clearInterval(zoomInInterval);
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
				clearInterval(zoomInInterval);
				fetch('/zoom', {
					method: 'POST',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
					body: 'direction=stop'
				});
			});
			zoomOutBtn.addEventListener("touchend", () => {
				clearInterval(zoomInInterval);
				fetch('/zoom', {
					method: 'POST',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
					body: 'direction=stop'
				});
			});

         // ZoomCamera In
            const zoomInBtnCamera = document.getElementById("zoomcamplus-btn");
            zoomInBtnCamera.addEventListener("mousedown", () => {
                fetch('/zoom', {
					method: 'POST',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
					body: 'direction=inCamera'
				});
            });
            zoomInBtnCamera.addEventListener("touchstart", () => {
                fetch('/zoom', {
					method: 'POST',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
					body: 'direction=inCamera'
				});
            });
			zoomInBtnCamera.addEventListener("mouseup", () => {
				clearInterval(zoomInInterval);
				fetch('/zoom', {
					method: 'POST',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
					body: 'direction=stopCamera'
				});
			});
			zoomInBtnCamera.addEventListener("touchend", () => {
				clearInterval(zoomInInterval);
				fetch('/zoom', {
					method: 'POST',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
					body: 'direction=stopCamera'
				});
			});

		// ZoomCamera Out
            const zoomOutBtnCamera = document.getElementById("zoomcammeno-btn");
            zoomOutBtnCamera.addEventListener("mousedown", () => {
                fetch('/zoom', {
					method: 'POST',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
					body: 'direction=outCamera'
				});
            });
            zoomOutBtnCamera.addEventListener("touchstart", () => {
                fetch('/zoom', {
					method: 'POST',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
					body: 'direction=outCamera'
				});
            });
			zoomOutBtnCamera.addEventListener("mouseup", () => {
				clearInterval(zoomInInterval);
				fetch('/zoom', {
					method: 'POST',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
					body: 'direction=stopCamera'
				});
			});
			zoomOutBtnCamera.addEventListener("touchend", () => {
				clearInterval(zoomInInterval);
				fetch('/zoom', {
					method: 'POST',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
					body: 'direction=stopCamera'
				});
			});

		// Focus In
            const focusInBtnCamera = document.getElementById("focusplus-btn");
            focusInBtnCamera.addEventListener("mousedown", () => {
                fetch('/zoom', {
					method: 'POST',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
					body: 'direction=inFocus'
				});
            });
            focusInBtnCamera.addEventListener("touchstart", () => {
                fetch('/zoom', {
					method: 'POST',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
					body: 'direction=inFocus'
				});
            });
			focusInBtnCamera.addEventListener("mouseup", () => {
				clearInterval(zoomInInterval);
				fetch('/zoom', {
					method: 'POST',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
					body: 'direction=stopFocus'
				});
			});
			focusInBtnCamera.addEventListener("touchend", () => {
				clearInterval(zoomInInterval);
				fetch('/zoom', {
					method: 'POST',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
					body: 'direction=stopFocus'
				});
			});

		// Focus Out
            const focusOutBtnCamera = document.getElementById("focusmeno-btn");
            focusOutBtnCamera.addEventListener("mousedown", () => {
                fetch('/zoom', {
					method: 'POST',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
					body: 'direction=outFocus'
				});
            });
            focusOutBtnCamera.addEventListener("touchstart", () => {
                fetch('/zoom', {
					method: 'POST',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
					body: 'direction=outFocus'
				});
            });
			focusOutBtnCamera.addEventListener("mouseup", () => {
				clearInterval(zoomInInterval);
				fetch('/zoom', {
					method: 'POST',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
					body: 'direction=stopFocus'
				});
			});
			focusOutBtnCamera.addEventListener("touchend", () => {
				clearInterval(zoomInInterval);
				fetch('/zoom', {
					method: 'POST',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
					body: 'direction=stopFocus'
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
	const testImage = new Image();
	testImage.src = "https://i.imgur.com/9oCV4tC.jpeg";
	let testImageLoaded = false;
	testImage.onload = () => {
	  testImageLoaded = true;
	  console.log("Imagen de test cargada");
	};
	let lastFrameTime = performance.now();

	const canvas = document.getElementById("videoCanvas");
	const ctx = canvas.getContext("2d");
	
	canvas.style.transform = "translateZ(0)"; // fuerza aceleración GPU en algunos navegadores
	
	let expectedFPS = 30;
	let expectedWidth = 1920;
	let expectedHeight = 1080;

    let settingsVisible = false;
	let dataVisible = false;
	
	let viewscale = 1;
	
	// Cargar configuración al iniciar
	function cargarConfiguracion() {
		// Cargar configuración al iniciar
		fetch('/api/camera-config')
		  .then(res => res.json())
		  .then(config => {
			[expectedWidth, expectedHeight] = config["resolution"].toLowerCase().split("x").map(Number);
			expectedFPS = config["fps"]
		  });
		  resizeCanvas();
	}
	// Ejecutar al iniciar
	cargarConfiguracion();
	// Repetir cada 1 minuto
	setInterval(cargarConfiguracion, 60000);
		
	// Opcional: escalado para adaptarse a la pantalla sin deformar
	function resizeCanvas() {
		canvas.width = expectedWidth;
		canvas.height = expectedHeight;
		canvas.style.width = expectedWidth + "px";
		canvas.style.height = expectedHeight + "px";
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

            // videoData.clientFPS = fps.toFixed(2)
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
	   
		// Receptor de frames
		socket.on("video_frame", (data) => {
			fpsReceived++; // ← suma al recibir un frame
			latestBlob = new Blob([data], { type: "image/jpeg" });
			lastFrameTime = performance.now();
		});

		function drawLoop() {
			requestAnimationFrame(drawLoop);
			
			const now = performance.now();
			
			// Si no llegan frames, mostrar imagen de test
			if (now - lastFrameTime > 10000 && testImageLoaded) {
				ctx.clearRect(0, 0, canvas.width, canvas.height);
				ctx.drawImage(testImage, 0, 0, canvas.width, canvas.height);
				//console.log("Mostrando imagen de test (no llegan frames)");
				return;
			}

			if (paused || !latestBlob || processing) return;		
			if (latestBlob === lastDrawnBlob) return; // 👈 evita dibujar el mismo blob

			processing = true;
			const blob = latestBlob;
			lastDrawnBlob = latestBlob;
			latestBlob = null;
			
			createImageBitmap(blob).then((bitmap) => {
				ctx.clearRect(0, 0, canvas.width, canvas.height);
				ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
				
				fpsDrawn++;
				
				// videoData.frameSizeKB = (blob.size / 1024).toFixed(1);
				// videoData.frameWidth = expectedWidth;
				// videoData.frameHeight = expectedHeight;
				// videoData.frameWidthView = expectedWidth * viewscale;
				// videoData.frameHeightView = expectedHeight * viewscale;
				
				//updateVideoInfoDisplay();
				processing = false;
			}).catch(() => {
				processing = false;
			});
		}

		drawLoop(); // ← iniciá el render loop una vez
		
		setInterval(() => {
			const now = performance.now();
			const delta = (now - lastFPSUpdate) / 1000;

			realFPSReceived = (fpsReceived / delta).toFixed(1);
			realFPSDrawn = (fpsDrawn / delta).toFixed(1);

			// Los drops se calculan por diferencia entre recibidos y dibujados
			frameDrops = Math.max(0, fpsReceived - fpsDrawn);

			// Reiniciamos contadores para la próxima medición
			fpsReceived = 0;
			fpsDrawn = 0;
			lastFPSUpdate = now;
			//updateVideoInfoDisplay(); // ← ¡Invocalo acá!
		}, 1000);

        function updateVideoInfoDisplay() {
	const infoDiv = document.getElementById("video-info");

	infoDiv.innerHTML = `
		<style>
			#video-info {
				position: fixed;
				top: 10px;
				left: 10px;
				background: rgba(0,0,0,0.6);
				color: white;
				padding: 8px 12px;
				font-family: monospace;
				font-size: 14px;
				border-radius: 8px;
				z-index: 9999;
				pointer-events: none;
			}
		</style>
		<b>Resolución esperada:</b> ${expectedWidth}×${expectedHeight}<br>
		<b>Resolución mostrada:</b> ${videoData.frameWidthView}×${videoData.frameHeightView}<br>
		<b>Tamaño frame:</b> ${videoData.frameSizeKB ?? "?"} KB<br>
		<b>FPS Recibidos:</b> ${realFPSReceived} fps<br>
		<b>FPS Dibujados:</b> ${realFPSDrawn} fps<br>
		<b>FPS Cliente:</b> ${videoData.clientFPS} fps<br>
		<b>Frames Perdidos:</b> ${frameDrops}
	`;
}


        window.addEventListener("load", () => {
            resizeCanvas();
        });
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
    --text: #eee;
    --accent: #ff69b4;
    --card: #111;
    --radius: 12px;
    --shadow: 0 6px 18px rgba(0,0,0,0.5);
  }
  * { box-sizing: border-box; }
  body { margin:0; font-family:sans-serif; background:var(--bg); color:var(--text); }
  .wrap { max-width:1000px; margin:0 auto; padding:20px; }

  header {
    display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;
  }
  h1 { font-size:24px; color:var(--accent); margin:0; }

  .grid { display:grid; grid-template-columns:1fr 1fr; gap:20px; }
  @media(max-width:700px){ .grid{ grid-template-columns:1fr; } }

  .card {
    background:var(--card); border-radius:var(--radius); box-shadow:var(--shadow); padding:16px;
  }
  .card h2 { margin-top:0; color:var(--accent); font-size:18px; }

  video { width:100%; border-radius:var(--radius); background:#000; }
  canvas { display:none; }

  .btn {
    padding:10px 16px; border:none; border-radius:8px; background:var(--accent);
    color:#000; font-weight:600; cursor:pointer; margin-right:8px;
    transition: transform 0.1s;
  }
  .btn:hover { transform:scale(1.05); }

  footer { margin-top:30px; text-align:center; color:#777; font-size:13px; }

  .status { margin-top:10px; font-size:14px; }
  .status span { font-weight:bold; color:var(--accent); }
  .status-bar{background:#222;border-radius:6px;height:16px;overflow:hidden;margin:6px 0;}
.status-fill{height:100%;background:var(--accent);width:0%;}
.status-text{font-size:12px;margin-bottom:6px;}
  .dot {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #555;
  display: inline-block;
  margin-right: 6px;
  box-shadow: 0 0 4px rgba(0,0,0,0.7);
}
.dot.ok { background: #22c55e; } /* verde */
.dot.active { background: #ff69b4; } /* rosa */
.dot.err { background: #ef4444; } /* rojo */
@keyframes blink {
  0%, 50%, 100% { opacity: 1; }
  25%, 75% { opacity: 0.2; }
}

.dot.blink {
  animation: blink 1s infinite;
}

.leds-row {
  display: flex;
  gap: 20px;       /* separación entre LEDs */
  align-items: center;
}

.led-item {
  display: flex;
  align-items: center;
  gap: 8px;        /* espacio entre LED y texto */
  font-size: 14px;
  color: var(--text);
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
      <div class="status-text">RAM: <span id="ramText">0%</span></div>
      <div class="status-bar"><div id="ramBar" class="status-fill"></div></div>
      <div class="status-text">Temperatura: <span id="tempText">0°C</span></div>
      <div class="status-bar"><div id="tempBar" class="status-fill"></div></div>
      <div class="status-text">Disco: <span id="diskText">0%</span></div>
      <div class="status-bar"><div id="diskBar" class="status-fill"></div></div>
    </div>
	
	<canvas id="tempChart" width="300" height="150"></canvas>
	
	<!-- Utilidades -->
    <div class="card">
      <h2>Utilidades Pi</h2>
      <button class="btn" onclick="restartPi()">Restart Pi</button>
	  <h2> </h2>
      <button class="btn" onclick="shutdownPi()">Shutdown Pi</button>
    </div>

  
    <div class="card">
      <h2>Accesos Rápidos</h2>
      <a href="/preview" class="btn">/preview</a>
      <a href="/original" class="btn">/original</a>
      <a href="/wifi" class="btn">/wifi</a>
    </div>
	
	  <div class="card">
		<h2>Configurar Wifi</h2>
		<form method="POST" action="/wifi">
		  <label>SSID:</label>
		  <input name="ssid" placeholder="Nombre de la red"><br><br>

		  <label>Password:</label>
		  <input name="password" type="password" placeholder="Contraseña"><br><br>

		  <button type="submit" class="btn">Guardar</button>
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
	  updateCpuLed(data.cpu);
	  updateTempChart(data.temp);
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
	
	const ctx = document.getElementById('tempChart').getContext('2d');
	const tempChart = new Chart(ctx, {
		type: 'line',
		data: {
			labels: [], // tiempo
			datasets: [{
				label: 'Temperatura',
				data: [],
				borderColor: '#ff69b4',
				backgroundColor: 'rgba(255,105,180,0.2)',
			}]
		},
		options: {
        responsive: true,
        animation: false,
        scales: {
            y: {
                min: 0,   // valor mínimo
                max: 80,  // valor máximo
                ticks: {
                    stepSize: 10, // opcional, para marcar cada 10 unidades
                    color: '#fff' // color de números
                },
                grid: {
                    color: '#444' // color de las líneas de la grilla
                }
            },
            x: {
                display: false // no mostrar eje X si querés
            }
        },
        plugins: {
            legend: { labels: { color: '#fff' } }
        }
    }
	});
	
	// Actualización en tiempo real
	function updateTempChart(temp){
		const now = new Date().toLocaleTimeString();
		tempChart.data.labels.push(now);
		tempChart.data.datasets[0].data.push(temp);
		if(tempChart.data.labels.length>20){ // limitar a 20 puntos
			tempChart.data.labels.shift();
			tempChart.data.datasets[0].data.shift();
		}
		tempChart.update();
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