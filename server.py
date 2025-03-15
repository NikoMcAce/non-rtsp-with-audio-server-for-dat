"""
ESP32 Camera & Audio Relay Server for Azure Ubuntu

This Flask application serves as a relay between your ESP32-S3-Korvo-2 and web clients.
It receives both video frames and audio data from the ESP32 and streams them to connected web browsers.

Setup Instructions:
1. Install requirements: pip install flask
2. Run this script: python camera_audio_relay_server.py
3. Access the stream at: http://your-azure-ip:8002/
"""

from flask import Flask, Response, render_template, request, jsonify
import threading
import time
import logging
import os
import datetime
import signal
import sys
import base64

# Configuration
PORT = 8002
DEBUG = False
MAX_CLIENTS = 10
FRAME_EXPIRY_SECONDS = 10  # Consider frame stale after this many seconds
AUDIO_EXPIRY_SECONDS = 5   # Consider audio stale after this many seconds

# Create Flask app
app = Flask(__name__)

# Setup logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('ESP32CameraAudioRelay')

# Global variables
current_frame = None
frame_time = 0
current_audio = None
audio_time = 0
clients_count = 0
audio_clients_count = 0
lock = threading.Lock()
audio_lock = threading.Lock()

# Create templates directory if it doesn't exist
os.makedirs('templates', exist_ok=True)

# Create the HTML templates
with open('templates/index.html', 'w') as f:
    f.write("""
<!DOCTYPE html>
<html>
<head>
    <title>ESP32 Camera & Audio Stream</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial, sans-serif;
            text-align: center;
            margin: 0;
            padding: 20px;
            background-color: #f0f0f0;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
        }
        h1 {
            color: #333;
        }
        img {
            max-width: 100%;
            height: auto;
            border: 1px solid #ddd;
            border-radius: 4px;
        }
        .status {
            margin: 20px 0;
            padding: 10px;
            background-color: #f8f8f8;
            border-radius: 4px;
        }
        .footer {
            margin-top: 20px;
            font-size: 12px;
            color: #777;
        }
        .controls {
            margin: 15px 0;
            padding: 10px;
            background-color: #f0f0f0;
            border-radius: 4px;
        }
        button {
            padding: 8px 15px;
            margin: 0 5px;
            background-color: #4CAF50;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }
        button:hover {
            background-color: #45a049;
        }
        button:disabled {
            background-color: #cccccc;
            cursor: not-allowed;
        }
        .audio-indicator {
            display: inline-block;
            width: 20px;
            height: 20px;
            background-color: #ccc;
            border-radius: 50%;
            margin-left: 10px;
            vertical-align: middle;
        }
        .audio-active {
            background-color: #4CAF50;
            animation: pulse 1.5s infinite;
        }
        @keyframes pulse {
            0% { opacity: 0.5; }
            50% { opacity: 1; }
            100% { opacity: 0.5; }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>ESP32-S3-Korvo-2 Camera & Audio Stream</h1>
        <div class="status">
            <p>Status: <span id="status">Connecting...</span></p>
            <p>Connected Viewers: <span id="viewers">-</span></p>
            <p>Last Frame: <span id="lastFrame">-</span></p>
            <p>Audio Status: <span id="audioStatus">-</span> <span class="audio-indicator" id="audioIndicator"></span></p>
        </div>
        <div>
            <img src="/stream" id="stream" alt="Camera Stream">
        </div>
        <div class="controls">
            <button id="audioToggle">Start Audio</button>
            <span id="audioMessage"></span>
        </div>
        <div class="footer">
            <p>ESP32-S3-Korvo-2 Camera & Audio Relay Server</p>
        </div>
    </div>

    <script>
        // Audio elements and variables
        let audioContext;
        let audioPlayer;
        let audioBuffer = [];
        let isPlaying = false;
        let audioSource;
        let lastAudioTime = 0;
        
        // Initialize audio context
        function initAudio() {
            try {
                audioContext = new (window.AudioContext || window.webkitAudioContext)();
                audioPlayer = new Audio();
                document.getElementById('audioMessage').textContent = "Audio initialized";
                return true;
            } catch (e) {
                console.error("Web Audio API is not supported in this browser", e);
                document.getElementById('audioMessage').textContent = "Audio not supported in this browser";
                return false;
            }
        }
        
        // Toggle audio streaming
        document.getElementById('audioToggle').addEventListener('click', function() {
            if (!isPlaying) {
                if (!audioContext && !initAudio()) {
                    return;
                }
                
                isPlaying = true;
                this.textContent = "Stop Audio";
                document.getElementById('audioMessage').textContent = "Streaming audio...";
                startAudioStream();
            } else {
                isPlaying = false;
                this.textContent = "Start Audio";
                document.getElementById('audioMessage').textContent = "Audio stopped";
                stopAudioStream();
            }
        });
        
        // Start audio streaming
        function startAudioStream() {
            const audioWorker = new EventSource('/audio-stream');
            
            audioWorker.onmessage = function(event) {
                if (!isPlaying) {
                    audioWorker.close();
                    return;
                }
                
                try {
                    const data = JSON.parse(event.data);
                    if (data.audio) {
                        // Convert base64 to audio
                        const audioData = atob(data.audio);
                        playAudioData(audioData);
                        
                        // Update audio indicator
                        document.getElementById('audioIndicator').classList.add('audio-active');
                        setTimeout(() => {
                            document.getElementById('audioIndicator').classList.remove('audio-active');
                        }, 500);
                        
                        lastAudioTime = Date.now();
                    }
                } catch (e) {
                    console.error("Error processing audio data", e);
                }
            };
            
            audioWorker.onerror = function(event) {
                console.error("Audio stream error", event);
                document.getElementById('audioMessage').textContent = "Audio stream error. Reconnecting...";
                audioWorker.close();
                
                // Try to reconnect after 2 seconds
                if (isPlaying) {
                    setTimeout(startAudioStream, 2000);
                }
            };
            
            // Set up stale audio check
            setInterval(() => {
                if (isPlaying && Date.now() - lastAudioTime > 5000) {
                    document.getElementById('audioStatus').textContent = "No audio data received";
                }
            }, 5000);
        }
        
        // Stop audio streaming
        function stopAudioStream() {
            if (audioSource) {
                audioSource.stop();
                audioSource = null;
            }
        }
        
        // Play audio data
        function playAudioData(audioData) {
            const pcmData = new Float32Array(audioData.length / 2);
            let index = 0;
            
            // Convert 16-bit PCM to float32
            for (let i = 0; i < audioData.length; i += 2) {
                const sample = (audioData.charCodeAt(i) & 0xff) | ((audioData.charCodeAt(i + 1) & 0xff) << 8);
                // Convert from unsigned to signed
                const signedSample = sample > 0x7fff ? sample - 0x10000 : sample;
                // Normalize to -1.0 to 1.0
                pcmData[index++] = signedSample / 32768.0;
            }
            
            // Create audio buffer and play
            const buffer = audioContext.createBuffer(1, pcmData.length, 16000); // 16kHz sample rate
            buffer.getChannelData(0).set(pcmData);
            
            audioSource = audioContext.createBufferSource();
            audioSource.buffer = buffer;
            audioSource.connect(audioContext.destination);
            audioSource.start(0);
            
            document.getElementById('audioStatus').textContent = "Receiving audio";
        }

        // Update status periodically
        setInterval(function() {
            fetch('/status')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('status').textContent = data.status;
                    document.getElementById('viewers').textContent = data.clients;
                    document.getElementById('lastFrame').textContent = data.last_frame;
                    document.getElementById('audioStatus').textContent = data.audio_status;
                })
                .catch(error => {
                    console.error('Error fetching status:', error);
                    document.getElementById('status').textContent = 'Error';
                });
        }, 5000);

        // Handle stream errors by reloading
        document.getElementById('stream').onerror = function() {
            setTimeout(() => {
                this.src = "/stream?" + new Date().getTime();
            }, 2000);
        };
    </script>
</body>
</html>
    """)

@app.route('/')
def index():
    """Serve the main page with camera stream"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    """Receive frames from ESP32 camera"""
    global current_frame, frame_time
    
    if not request.data:
        return "No data", 400
    
    with lock:
        current_frame = request.data
        frame_time = time.time()
    
    logger.debug(f"Received frame: {len(current_frame)} bytes")
    return "OK", 200

@app.route('/upload-audio', methods=['POST'])
def upload_audio():
    """Receive audio from ESP32 microphone"""
    global current_audio, audio_time
    
    if not request.data:
        return "No data", 400
    
    with audio_lock:
        current_audio = request.data
        audio_time = time.time()
    
    logger.debug(f"Received audio: {len(current_audio)} bytes")
    return "OK", 200

def gen_frames():
    """Generate frames for MJPEG streaming"""
    global clients_count
    clients_count += 1
    logger.info(f"New client connected. Total clients: {clients_count}")
    
    try:
        while True:
            with lock:
                frame = current_frame
                last_frame_time = frame_time
            
            # Check if we have a frame and it's not too old
            if frame is not None and time.time() - last_frame_time < FRAME_EXPIRY_SECONDS:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            else:
                # If no frame available, send a placeholder or wait
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + b'\r\n')
            
            # Sleep to control frame rate and CPU usage
            time.sleep(0.05)
    
    finally:
        with lock:
            clients_count -= 1
        logger.info(f"Client disconnected. Total clients: {clients_count}")

def gen_audio():
    """Generate audio data for server-sent events (SSE)"""
    global audio_clients_count
    audio_clients_count += 1
    logger.info(f"New audio client connected. Total audio clients: {audio_clients_count}")
    
    try:
        while True:
            with audio_lock:
                audio = current_audio
                last_audio_time = audio_time
            
            # Check if we have audio and it's not too old
            if audio is not None and time.time() - last_audio_time < AUDIO_EXPIRY_SECONDS:
                audio_b64 = base64.b64encode(audio).decode('utf-8')
                yield f"data: {{'audio': '{audio_b64}'}}\n\n"
            else:
                # If no audio available, just send a heartbeat
                yield f"data: {{'heartbeat': {time.time()}}}\n\n"
            
            # Sleep to control transmission rate
            time.sleep(0.1)
    
    finally:
        with audio_lock:
            audio_clients_count -= 1
        logger.info(f"Audio client disconnected. Total audio clients: {audio_clients_count}")

@app.route('/stream')
def stream():
    """Stream MJPEG to connected clients"""
    return Response(gen_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/audio-stream')
def audio_stream():
    """Stream audio data as server-sent events"""
    return Response(gen_audio(),
                    mimetype='text/event-stream')

@app.route('/status')
def status():
    """Return status information as JSON"""
    with lock:
        has_frame = current_frame is not None
        frame_age = time.time() - frame_time if has_frame else float('inf')
        
        if not has_frame:
            status_text = "No frames received yet"
        elif frame_age > FRAME_EXPIRY_SECONDS:
            status_text = f"Camera offline (last frame {int(frame_age)}s ago)"
        else:
            status_text = "Online"
            
        last_frame = datetime.datetime.fromtimestamp(frame_time).strftime('%H:%M:%S') if has_frame else "Never"
    
    with audio_lock:
        has_audio = current_audio is not None
        audio_age = time.time() - audio_time if has_audio else float('inf')
        
        if not has_audio:
            audio_status = "No audio received yet"
        elif audio_age > AUDIO_EXPIRY_SECONDS:
            audio_status = f"Microphone offline (last audio {int(audio_age)}s ago)"
        else:
            audio_status = "Receiving audio"
    
    return jsonify({
        "status": status_text,
        "clients": clients_count,
        "audio_clients": audio_clients_count,
        "last_frame": last_frame,
        "audio_status": audio_status
    })

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    logger.info("Shutting down...")
    sys.exit(0)

if __name__ == '__main__':
    # Register signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    # Print startup message
    logger.info("=" * 50)
    logger.info("ESP32 Camera & Audio Relay Server")
    logger.info("=" * 50)
    logger.info(f"Server starting on port {PORT}")
    logger.info(f"Access the stream at: http://YOUR_SERVER_IP:{PORT}/")
    logger.info("Press Ctrl+C to exit")
    
    # Start the Flask app
    app.run(host='0.0.0.0', port=PORT, debug=DEBUG, threaded=True)
