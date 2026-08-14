const sliders2 = document.querySelectorAll('input[type="range"]');
sliders2.forEach(slider => {
  const valueText = document.createElement('div');
  valueText.style.fontSize = '12px';
  valueText.style.marginTop = '4px';
  valueText.style.color = '#fff';
  valueText.textContent = slider.value;
  slider.insertAdjacentElement('afterend', valueText);
  slider.addEventListener('input', () => {
    valueText.textContent = slider.value;
  });
});

async function checkInternet() {
  const led = document.getElementById('ledInternet');
  led.className = 'dot blink';
  try {
    await fetch('https://www.google.com', { mode: 'no-cors' });
    led.className = 'dot ok';
  } catch {
    led.className = 'dot err';
  }
}
window.addEventListener('DOMContentLoaded', checkInternet);

function updateCpuLed(cpuPercent) {
  const led = document.getElementById('ledCpu');
  led.className = cpuPercent > 80 ? 'dot blink err' : 'dot ok';
}

const led = document.querySelector('.dot');
led.classList.add('blink');

let temp = 0;
let cpu = 0;
let ram = 0;

function playNotificationSound() {
  try {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;
    const ctx = new AudioContextClass();
    const oscillator = ctx.createOscillator();
    const gain = ctx.createGain();
    oscillator.type = 'triangle';
    oscillator.frequency.setValueAtTime(1180, ctx.currentTime);
    oscillator.frequency.exponentialRampToValueAtTime(1760, ctx.currentTime + 0.12);
    gain.gain.setValueAtTime(0.0001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.09, ctx.currentTime + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.24);
    oscillator.connect(gain);
    gain.connect(ctx.destination);
    oscillator.start();
    oscillator.stop(ctx.currentTime + 0.22);
    setTimeout(() => ctx.close().catch(() => {}), 250);
  } catch (err) {
    console.warn('No se pudo reproducir el sonido de notificación:', err);
  }
}

function showNotification(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  if (!container) return;
  const cameraNumber = document.getElementById('camera_number')?.value || '1';
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = `Cam ${cameraNumber}: ${message}`;
  container.appendChild(toast);
  playNotificationSound();
  setTimeout(() => {
    toast.remove();
  }, 3200);
}

function updateCameraBadge() {
  const badge = document.getElementById('cameraBadge');
  const input = document.getElementById('camera_number');
  if (badge && input) {
    const value = input.value || '1';
    badge.textContent = `Camera ${value}`;
  }
}

function updateSystemStatus(data) {
  document.getElementById('cpuText').textContent = data.cpu + '%';
  document.getElementById('cpuBar').style.width = data.cpu + '%';
  document.getElementById('ramText').textContent = data.ram + '%';
  document.getElementById('ramBar').style.width = data.ram + '%';
  document.getElementById('tempText').textContent = data.temp + '°C';
  document.getElementById('tempBar').style.width = data.temp + '%';
  document.getElementById('diskText').textContent = data.disk + '%';
  document.getElementById('diskBar').style.width = data.disk + '%';
  document.getElementById('storageDiskText').textContent = (data.storage_disk || 0) + '%';
  document.getElementById('storageDiskBar').style.width = (data.storage_disk || 0) + '%';
  document.getElementById('cpu_freqText').textContent = data.cpu_freq;
  document.getElementById('batText').textContent = data.ups.battery_percent + '%';
  document.getElementById('batBar').style.width = data.ups.battery_percent + '%';
  document.getElementById('volText').textContent = data.ups.voltage_v;
  document.getElementById('loadText').textContent = data.ups.current_a;
  updateCpuLed(data.cpu);
  temp = data.temp;
  cpu = data.cpu;
  ram = data.ram;
  const ledCam = document.getElementById('ledCamara');
  ledCam.className = data.running ? 'dot ok' : 'dot blink err';
}

async function fetchSystemStatus() {
  try {
    const res = await fetch('/status');
    if (!res.ok) return;
    const data = await res.json();
    updateSystemStatus(data);
    document.getElementById('ledConectado').className = 'dot ok';
  } catch {
    document.getElementById('ledConectado').className = 'dot blink err';
  }
}
setInterval(fetchSystemStatus, 2000);

function restartPi() { showNotification('Restarting system', 'warning'); fetch('/restart', { method: 'POST' }).catch(() => showNotification('Could not restart the system', 'error')); }
function shutdownPi() { showNotification('Shutting down system', 'warning'); fetch('/shutdown', { method: 'POST' }).catch(() => showNotification('Could not shut down the system', 'error')); }
function restartStream() { showNotification('Starting stream', 'success'); fetch('/start', { method: 'POST' }).catch(() => showNotification('Could not start the stream', 'error')); }
function stopStream() { showNotification('Stopping stream', 'warning'); fetch('/stop', { method: 'POST' }).catch(() => showNotification('Could not stop the stream', 'error')); }
function restartHdmi() { showNotification('Restarting HDMI', 'warning'); fetch('/api/hdmi/restart', { method: 'POST' }).catch(() => showNotification('Could not restart HDMI', 'error')); }

let talkbackWs = null;
let talkbackMediaStream = null;
let talkbackAudioCtx = null;
let talkbackProcessor = null;
let talkbackTalking = false;
let talkbackMicReady = false;

async function setupTalkbackMic() {
  if (!navigator.mediaDevices?.getUserMedia) return false;
  if (talkbackMicReady && talkbackMediaStream) return true;
  try {
    talkbackMediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        sampleRate: 48000,
        channelCount: 1,
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false
      }
    });
    talkbackAudioCtx = talkbackAudioCtx || new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 48000 });
    if (talkbackAudioCtx.state === 'suspended') {
      await talkbackAudioCtx.resume();
    }
    if (!talkbackProcessor) {
      const source = talkbackAudioCtx.createMediaStreamSource(talkbackMediaStream);
      talkbackProcessor = talkbackAudioCtx.createScriptProcessor(1920, 1, 1);
      talkbackProcessor.onaudioprocess = (event) => {
        if (!talkbackTalking || !talkbackWs || talkbackWs.readyState !== WebSocket.OPEN) return;
        const float32 = event.inputBuffer.getChannelData(0);
        const int16 = new Int16Array(float32.length);
        for (let i = 0; i < float32.length; i++) {
          const sample = Math.max(-1, Math.min(1, float32[i]));
          int16[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
        }
        talkbackWs.send(int16.buffer);
      };
      source.connect(talkbackProcessor);
    }
    talkbackMicReady = true;
    return true;
  } catch (err) {
    console.warn('Could not prepare the microphone for talkback:', err);
    return false;
  }
}

function connectTalkback() {
  if (talkbackWs && (talkbackWs.readyState === WebSocket.OPEN || talkbackWs.readyState === WebSocket.CONNECTING)) {
    return talkbackWs;
  }
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
  talkbackWs = new WebSocket(`${protocol}://${location.host}/talkback`);
  talkbackWs.onmessage = (event) => {
    const statusEl = document.getElementById('talkbackStatus');
    if (!statusEl) return;
    if (event.data === 'granted') {
      talkbackTalking = true;
      statusEl.textContent = 'Talking...';
    } else if (event.data === 'busy') {
      talkbackTalking = false;
      statusEl.textContent = 'Busy';
    } else if (event.data === 'released') {
      talkbackTalking = false;
      statusEl.textContent = 'Free';
    }
  };
  return talkbackWs;
}

function speakTalkbackText(message) {
  if (!message || typeof window === 'undefined') return;
  if (!('speechSynthesis' in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(message);
  utterance.lang = 'es-ES';
  utterance.rate = 1.0;
  utterance.pitch = 1.0;
  window.speechSynthesis.speak(utterance);
}

function sendTalkbackText(message) {
  if (!message || !message.trim()) return false;
  const payload = `__TTS__:${message.trim()}`;
  if (!talkbackWs || talkbackWs.readyState !== WebSocket.OPEN) {
    const ws = connectTalkback();
    if (!ws) return false;
    ws.addEventListener('open', () => ws.send(payload), { once: true });
    return true;
  }
  talkbackWs.send(payload);
  return true;
}

function attachTalkbackControls() {
  const ptt = document.getElementById('ptt');
  const talkbackText = document.getElementById('talkbackText');
  const sendTtsBtn = document.getElementById('sendTtsBtn');
  if (!ptt) return;
  const sendPtt = (value) => {
    if (!talkbackWs || talkbackWs.readyState !== WebSocket.OPEN) {
      const ws = connectTalkback();
      if (!ws) return;
      ws.addEventListener('open', () => ws.send(value), { once: true });
      return;
    }
    talkbackWs.send(value);
  };
  const startTalk = async () => {
    const statusEl = document.getElementById('talkbackStatus');
    const micReady = await setupTalkbackMic();
    if (!micReady) {
      const text = talkbackText?.value?.trim() || '';
      if (text) {
        if (statusEl) statusEl.textContent = 'Sending text';
        speakTalkbackText(text);
        sendTalkbackText(text);
        if (statusEl) statusEl.textContent = 'Text sent';
      } else if (statusEl) {
        statusEl.textContent = 'Microphone denied';
      }
      return;
    }
    sendPtt('__PTT_DOWN__');
  };
  ptt.addEventListener('mousedown', () => { startTalk().catch(() => {}); });
  ptt.addEventListener('touchstart', (event) => { event.preventDefault(); startTalk().catch(() => {}); });
  ptt.addEventListener('mouseup', () => sendPtt('__PTT_UP__'));
  ptt.addEventListener('mouseleave', () => sendPtt('__PTT_UP__'));
  ptt.addEventListener('touchend', () => sendPtt('__PTT_UP__'));
  if (sendTtsBtn) {
    sendTtsBtn.addEventListener('click', () => {
      const statusEl = document.getElementById('talkbackStatus');
      const text = talkbackText?.value?.trim() || '';
      if (!text) {
        if (statusEl) statusEl.textContent = 'Write something first';
        return;
      }
      speakTalkbackText(text);
      sendTalkbackText(text);
      if (statusEl) statusEl.textContent = 'Text sent';
    });
  }
}

let zoomSpeedMode = 'fast';

async function sendOpticsAction(action) {
  try {
    const response = await fetch('/api/optics/control', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action })
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      console.warn('Optics action failed', data);
      return false;
    }
    if (data && typeof data.zoom_speed_mode === 'string') {
      zoomSpeedMode = data.zoom_speed_mode;
    }
    await fetchOpticsStatus();
    return data;
  } catch (error) {
    console.warn('No se pudo enviar la acción óptica', error);
    return false;
  }
}

async function sendOpticsCalibration() {
  try {
    const response = await fetch('/api/optics/calibrate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      console.warn('Optics calibration failed', data);
      alert(`Error calibrando autofocus: ${data.message || 'Error desconocido'}`);
      return null;
    }
    const count = data.table ? Object.keys(data.table).length : 0;
    alert(`Calibración completada con ${count} puntos`);
    return data;
  } catch (error) {
    console.warn('No se pudo enviar la calibración óptica', error);
    alert('Error de red al intentar calibrar autofocus');
    return null;
  }
}

async function fetchOpticsStatus() {
  try {
    const response = await fetch('/api/optics/status');
    if (!response.ok) return;
    const data = await response.json();
    const statusEl = document.getElementById('opticsStatus');
    if (!statusEl) return;
    if (typeof data.zoom_speed_mode === 'string') {
      zoomSpeedMode = data.zoom_speed_mode;
    }
    const zoomMode = data.zoom_speed_mode === 'fast' ? 'fast' : 'slow';
    const focusMode = data.focus_mode === 'autofocus' || data.focus_mode === 'AF-C' ? 'autofocus' : 'manual';
    const zoomState = data.zooming_in ? 'zoom +' : data.zooming_out ? 'zoom -' : 'zoom stop';
    const focusState = data.focus_moving ? `focus ${data.focus_direction || ''}`.trim() : 'focus stop';
    statusEl.textContent = `Zoom: ${zoomMode} • ${zoomState} • Focus: ${focusMode} • ${focusState}`;
  } catch (error) {
    console.warn('No se pudo cargar el estado óptico', error);
  }
}

function attachOpticsControls() {
  document.querySelectorAll('[data-optics-action]').forEach((button) => {
    const action = button.dataset.opticsAction;
    const isHoldAction = ['zoom_in', 'zoom_out', 'focus_in', 'focus_out'].includes(action);
    let isHolding = false;

    // El backend (start_zoom/start_focus) ya corre un loop continuo propio
    // mientras el estado zooming_in/zooming_out/focus_moving siga activo.
    // Mandar un solo "start" al bajar el dedo y un solo "stop" al soltar,
    // en vez de spamear la acción cada 80-150ms, evita que el hilo del loop
    // y las requests del navegador se pisen escribiendo el mismo estado
    // óptico al mismo tiempo (eso era lo que producía el tironeo adelante/atrás).
    const startAction = (event) => {
      if (event?.type === 'pointerdown') {
        event.preventDefault();
        if (typeof event.pointerId !== 'undefined') {
          try {
            button.setPointerCapture(event.pointerId);
          } catch (err) {
            // Ignorar si no hay captura disponible.
          }
        }
      }

      if (!isHoldAction || isHolding) {
        return;
      }

      isHolding = true;
      sendOpticsAction(action);

      window.addEventListener('pointerup', stopAction, { once: true });
      window.addEventListener('pointercancel', stopAction, { once: true });
    };

    const stopAction = (event) => {
      if (!isHoldAction || !isHolding) {
        return;
      }

      if (event?.type === 'pointerup' && typeof event.pointerId !== 'undefined') {
        try {
          button.releasePointerCapture(event.pointerId);
        } catch (err) {
          // Ignorar si no se pudo soltar la captura.
        }
      }

      isHolding = false;
      const stopActionName = action.startsWith('zoom') ? 'zoom_stop' : 'focus_stop';
      sendOpticsAction(stopActionName);
    };

    if (!isHoldAction) {
      button.addEventListener('click', (event) => {
        event.preventDefault();
        sendOpticsAction(action);
      });
      button.addEventListener('contextmenu', (event) => event.preventDefault());
      return;
    }

    button.addEventListener('pointerdown', startAction, { passive: false });
    button.addEventListener('pointerup', stopAction);
    button.addEventListener('pointercancel', stopAction);
    button.addEventListener('touchend', stopAction);
    button.addEventListener('touchcancel', stopAction);
    button.addEventListener('contextmenu', (event) => event.preventDefault());
  });

  const calibrateButton = document.getElementById('calibrateOptics');
  if (calibrateButton) {
    calibrateButton.addEventListener('click', async (event) => {
      event.preventDefault();
      calibrateButton.disabled = true;
      const originalText = calibrateButton.textContent;
      calibrateButton.textContent = 'CALIBRANDO...';
      await sendOpticsCalibration();
      calibrateButton.textContent = originalText;
      calibrateButton.disabled = false;
    });
  }
}

function setHdmiOverlay(enabled) {
  return fetch('/api/hdmi-overlay', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled: !!enabled })
  }).then(r => r.json()).catch(() => null);
}

function attachHdmiOverlayToggle() {
  const el = document.getElementById('hdmi_overlay');
  if (!el) return;
  el.addEventListener('change', async () => {
    const res = await setHdmiOverlay(el.checked);
    if (!res || res.status !== 'ok') {
      showNotification('No se pudo cambiar overlay HDMI', 'error');
    } else {
      showNotification(`Overlay HDMI ${el.checked ? 'activado' : 'desactivado'}`, 'success');
    }
  });
}

window.addEventListener('DOMContentLoaded', () => {
  connectTalkback();
  attachTalkbackControls();
  attachOpticsControls();
  attachHdmiOverlayToggle();
  fetchOpticsStatus();
});

const ctx = document.getElementById('unicamChart').getContext('2d');
const unicamChart = new Chart(ctx, {
  type: 'line',
  data: {
    labels: [],
    datasets: [
      { label: 'Temperatura °C', data: [], borderColor: '#facc15', backgroundColor: 'rgba(250,204,21,0.1)', borderWidth: 2, pointRadius: 0, tension: 0.25, fill: false },
      { label: 'CPU %', data: [], borderColor: '#00bcd4', backgroundColor: 'rgba(0,188,212,0.1)', borderWidth: 2, pointRadius: 0, tension: 0.25, fill: false },
      { label: 'RAM %', data: [], borderColor: '#00ff99', backgroundColor: 'rgba(0,255,153,0.1)', borderWidth: 2, pointRadius: 0, tension: 0.25, fill: false }
    ]
  },
  options: {
    responsive: true,
    maintainAspectRatio: true,
    animation: false,
    scales: {
      y: { min: 0, max: 100, ticks: { color: '#fff', font: { family: 'monospace', size: 12 } }, grid: { color: '#222' } },
      x: { display: false }
    },
    plugins: { legend: { labels: { color: '#facc15', font: { family: 'monospace', size: 12 } } } }
  }
});
setInterval(() => {
  unicamChart.data.labels.push('');
  unicamChart.data.datasets[0].data.push(temp);
  unicamChart.data.datasets[1].data.push(cpu);
  unicamChart.data.datasets[2].data.push(ram);
  if (unicamChart.data.labels.length > 30) {
    unicamChart.data.labels.shift();
    unicamChart.data.datasets.forEach(ds => ds.data.shift());
  }
  unicamChart.update();
}, 1000);

const sliders = [
  'Brightness','Contrast','Saturation','Sharpness','ColourTemperature','ColourGains','ExposureTime','ExposureValue','AnalogueGain','AeFlickerPeriod','LensPosition','SyncFrames','AfWindows','FrameDurationLimits','ScalerCrop'
];
const checks = ['AwbEnable','AeEnable','AfTrigger','StatsOutputEnable','CnnEnableInputTensor','AutoReconnect','audio_monitor_enabled','hdmi_overlay','hdmi_fallback_enabled','encoder_warning_enabled'];
const selects = ['AwbMode','AeExposureMode','AeConstraintMode','AeMeteringMode','AeFlickerMode','NoiseReductionMode','HdrMode','AfMode','AfRange','AfSpeed','AfMetering','AfPause','SyncMode','ExposureTimeMode','AnalogueGainMode','resolution','fps','modo','bitrate','preset','protocolo_stream','hdmi','storage_mode','audio_monitor_output'];

function cargarConfiguracion() {
  fetch('/api/camera-config')
    .then(res => res.json())
    .then(config => {
      sliders.forEach(id => {
        const el = document.getElementById(id);
        if (el && config[id] !== undefined) el.value = config[id];
      });
      checks.forEach(id => {
        const el = document.getElementById(id);
        if (el && config[id] !== undefined) el.checked = config[id] ? true : false;
      });
      selects.forEach(id => {
        const el = document.getElementById(id);
        if (el && config[id] !== undefined) {
          if (id === 'modo') {
            const normalized = ['Foto', 'Stream', 'Grabar'].includes(config[id]) ? config[id] : (config[id] === 'Photo' ? 'Foto' : config[id]);
            el.value = normalized;
          } else {
            el.value = config[id];
          }
        }
      });
      document.getElementById('destino').value = config.IPDestino || '';
      document.getElementById('sdp').value = config.IPSDP || '';
      document.getElementById('protocolo').value = config.protocolo || '';
      document.getElementById('IPDestinoSRT').value = config.IPDestinoSRT || '';
      document.getElementById('puertoDestinoSRT').value = config.puertoDestinoSRT || '';
      document.getElementById('extraDataSRT').value = config.extraDataSRT || '';
      document.getElementById('mic').value = config.mic || '';
      document.getElementById('audio_monitor_enabled').checked = !!config.audio_monitor_enabled;
      document.getElementById('audio_monitor_output').value = config.audio_monitor_output || 'default';
      document.getElementById('hdmi_fallback_enabled').checked = !!config.hdmi_fallback_enabled;
      document.getElementById('hdmi_fallback_image').value = config.hdmi_fallback_image || '';
      document.getElementById('storage_mode').value = config.storage_mode || 'default';
      document.getElementById('storage_path').value = config.storage_path || '';
      document.getElementById('camera_number').value = config.camera_number || '1';
      updateCameraBadge();
      const storageUsbInput = document.getElementById('storage_usb_path');
      if (storageUsbInput) storageUsbInput.value = config.storage_usb_path || '';
      const storageUsbSelect = document.getElementById('storage_usb_select');
      if (storageUsbSelect && storageUsbInput && storageUsbInput.value) {
        const hasValue = Array.from(storageUsbSelect.options).some(opt => opt.value === storageUsbInput.value);
        if (hasValue) storageUsbSelect.value = storageUsbInput.value;
      }
      actualizarSlidersAuto();
      actualizarVisibilidadAlmacenamiento();
      renderEncoderWarning(config.encoder_warning || null);
    });
}

function renderEncoderWarning(warning) {
  const banner = document.getElementById('encoderWarningBanner');
  if (!banner) return;
  if (!warning || !warning.active) {
    banner.className = 'encoder-warning-banner';
    banner.innerHTML = '';
    banner.style.display = 'none';
    return;
  }
  const levelClass = warning.level === 'error' ? 'error' : 'warning';
  banner.className = `encoder-warning-banner visible ${levelClass}`;
  banner.innerHTML = `<strong>${warning.level === 'error' ? '⚠️ Riesgo alto' : '⚠️ Cuidado'}</strong><br>${warning.message}`;
  banner.style.display = 'block';
}

async function fetchEncoderWarning() {
  try {
    const res = await fetch('/api/encoder-warning');
    if (!res.ok) return;
    const warning = await res.json();
    renderEncoderWarning(warning);
    if (warning && warning.active) {
      showNotification(warning.message, warning.level === 'error' ? 'error' : 'warning');
    }
  } catch (error) {
    console.warn('No se pudo consultar la advertencia del encoder', error);
  }
}

function actualizarSlidersAuto() {
  document.querySelectorAll('input[type="range"]').forEach(slider => {
    const valueText = slider.nextElementSibling;
    if (valueText) valueText.textContent = slider.value;
  });
}

async function fetchMics() {
  try {
    const res = await fetch('/api/mics');
    if (!res.ok) return;
    const list = await res.json();
    const sel = document.getElementById('mic');
    if (!sel) return;
    sel.innerHTML = '';
    sel.add(new Option('Disabled (!)', '!'));
    sel.add(new Option('No mic (empty)', ''));
    list.forEach(item => sel.add(new Option(item.label, item.value)));
  } catch (e) {
    console.error('Error fetching mics:', e);
  }
}

async function fetchAudioOutputs() {
  try {
    const res = await fetch('/api/audio-outputs');
    if (!res.ok) return;
    const list = await res.json();
    const sel = document.getElementById('audio_monitor_output');
    if (!sel) return;
    sel.innerHTML = '';
    sel.add(new Option('Default output', 'default'));
    list.forEach(item => sel.add(new Option(item.label, item.value)));
    const current = document.getElementById('audio_monitor_output')?.dataset?.currentValue || '';
    if (current) {
      sel.value = current;
    }
  } catch (e) {
    console.error('Error fetching audio outputs:', e);
  }
}

async function fetchUsbFolders() {
  try {
    const res = await fetch('/api/storage-targets');
    if (!res.ok) return;
    const data = await res.json();
    const sel = document.getElementById('storage_usb_select');
    if (!sel) return;
    sel.innerHTML = '';
    const folders = (data.targets || []).filter(path => !path.toLowerCase().includes('/test') && !path.toLowerCase().includes('test'));
    folders.forEach(path => sel.add(new Option(path, path)));
    const currentPath = document.getElementById('storage_usb_path').value;
    if (folders.length) {
      if (currentPath && folders.includes(currentPath)) {
        sel.value = currentPath;
      } else {
        sel.value = folders[0];
      }
      document.getElementById('storage_usb_path').value = sel.value;
    }
  } catch (e) {
    console.error('Error fetching usb folders:', e);
  }
}

function actualizarVisibilidadAlmacenamiento() {
  const mode = document.getElementById('storage_mode').value;
  const pathBox = document.getElementById('storage_path');
  const usbBox = document.getElementById('storage_usb_box');
  const helpBox = document.getElementById('storage_usb_help');
  pathBox.parentElement.style.display = mode === 'custom' ? 'block' : 'none';
  usbBox.style.display = mode === 'usb' ? 'block' : 'none';
  helpBox.style.display = mode === 'usb' ? 'block' : 'none';
}

document.getElementById('storage_mode').addEventListener('change', () => {
  actualizarVisibilidadAlmacenamiento();
  if (document.getElementById('storage_mode').value === 'usb') fetchUsbFolders();
});
document.getElementById('storage_usb_select').addEventListener('change', () => {
  document.getElementById('storage_usb_path').value = document.getElementById('storage_usb_select').value;
});

window.onload = async function() {
  await fetchMics();
  await fetchAudioOutputs();
  await fetchUsbFolders();
  await cargarConfiguracion();
  actualizarVisibilidadAlmacenamiento();
  await fetchEncoderWarning();
};

async function saveConfig(options = {}) {
  const config = {};
  const modoEl = document.getElementById('modo');
  if (modoEl) {
    config.modo = modoEl.value;
  }
  sliders.forEach(id => {
    const el = document.getElementById(id);
    config[id] = parseFloat(el.value);
  });
  checks.forEach(id => {
    const el = document.getElementById(id);
    config[id] = el.checked;
  });
  selects.forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      config[id] = el.value;
    }
  });
  config.IPDestino = document.getElementById('destino').value;
  config.IPSDP = document.getElementById('sdp').value;
  config.protocolo = document.getElementById('protocolo').value;
  config.IPDestinoSRT = document.getElementById('IPDestinoSRT').value;
  config.puertoDestinoSRT = document.getElementById('puertoDestinoSRT').value;
  config.extraDataSRT = document.getElementById('extraDataSRT').value;
  config.mic = document.getElementById('mic').value;
  config.audio_monitor_enabled = document.getElementById('audio_monitor_enabled').checked;
  config.audio_monitor_output = document.getElementById('audio_monitor_output').value;
  config.storage_mode = document.getElementById('storage_mode').value;
  config.storage_path = document.getElementById('storage_path').value;
  config.camera_number = document.getElementById('camera_number').value;
  const storageUsbInput = document.getElementById('storage_usb_path');
  if (storageUsbInput) config.storage_usb_path = storageUsbInput.value;

  try {
    const res = await fetch('/api/camera-config', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config)
    });
    const data = await res.json();
    if (data && data.encoder_warning) {
      renderEncoderWarning(data.encoder_warning);
    }
    if (options.notify) {
      const modeLabel = config.modo || 'config';
      if (options.reason === 'mode') {
        showNotification(`Mode changed to ${modeLabel}`, 'success');
      } else {
        showNotification('Configuration applied', 'success');
      }
    }
    updateCameraBadge();
    return data;
  } catch (err) {
    if (options.notify) {
      showNotification('Could not apply the configuration', 'error');
    }
    console.error('Error guardando config:', err);
    throw err;
  }
}

const todos = [...sliders, ...checks, ...selects];
todos.forEach(id => {
  const el = document.getElementById(id);
  if (el) el.addEventListener('input', () => saveConfigDebounced());
});

let debounceTimeout = null;
function saveConfigDebounced() {
  if (debounceTimeout) clearTimeout(debounceTimeout);
  debounceTimeout = setTimeout(() => saveConfig(), 500);
}

async function forceReloadConfig() {
  try {
    const res = await fetch('/force_full_reload', { method: 'POST' });
    const data = await res.json();
    showNotification('Full reload applied', 'success');
    console.log('Config reloaded:', data);
  } catch (err) {
    showNotification('Could not reload the configuration', 'error');
    console.error('Error reloading config:', err);
  }
}

const modoEl = document.getElementById('modo');
if (modoEl) {
  modoEl.addEventListener('change', () => saveConfig({ notify: true, reason: 'mode' }));
}

const cameraNumberEl = document.getElementById('camera_number');
if (cameraNumberEl) {
  cameraNumberEl.addEventListener('change', () => saveConfig({ notify: true, reason: 'camera' }));
}

document.getElementById('settings-btn-1').addEventListener('click', () => saveConfig({ notify: true }));
document.getElementById('settings-btn-2').addEventListener('click', () => saveConfig({ notify: true }));
document.getElementById('settings-btn-3').addEventListener('click', forceReloadConfig);

async function abrirCarpetaDeGuardado() {
  try {
    const res = await fetch('/api/camera-config');
    if (!res.ok) return;
    const config = await res.json();
    const mode = (config.storage_mode || 'default').toLowerCase();
    let basePath = '';
    if (mode === 'custom') {
      basePath = config.storage_path || '';
    } else if (mode === 'usb') {
      basePath = config.storage_usb_path || config.storage_path || '';
    }
    if (!basePath) basePath = '/home/pi/Unicam';
    const url = `/browse/${encodeURIComponent(basePath.replace(/^\/+/, ''))}`;
    window.location.href = url;
  } catch (err) {
    console.error('Error abriendo carpeta:', err);
  }
}

async function wipeMediaStorage() {
  const confirmed = window.confirm('¿Borrar solo fotos y vídeos guardados en la carpeta de media?\nNo se tocarán archivos del sistema.');
  if (!confirmed) return;

  try {
    const res = await fetch('/api/media/cleanup', { method: 'POST' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      showNotification(data.message || 'No se pudo limpiar la media', 'error');
      return;
    }
    showNotification(`Media limpiada: ${data.removed_files || 0} archivos eliminados`, 'success');
  } catch (err) {
    console.error('Error limpiando media:', err);
    showNotification('No se pudo limpiar la media', 'error');
  }
}

document.getElementById('openPicturesBtn').addEventListener('click', () => abrirCarpetaDeGuardado());
document.getElementById('openVideosBtn').addEventListener('click', () => abrirCarpetaDeGuardado());
document.getElementById('wipeMediaBtn').addEventListener('click', wipeMediaStorage);