# ESP32 Korvo Audio & Video Streaming System 

Only video relay system github link is https://github.com/Mavis-Technologies/Non-RTSP-Stream-Relay
This server will help you implement vid/aud from esp32.
---


## Audio Implementation Guide

The audio part of the server works by receiving raw audio data from the ESP32 Korvo, storing it temporarily, and then streaming it to connected web clients.

### How the Audio System Works:

1. **Receiving Audio**:
   - ESP32 Korvo should send audio data to the `/upload-audio` endpoint via POST request
   - The server stores the latest audio data in the `current_audio` variable
   - Each audio upload refreshes the `audio_time` timestamp

2. **Streaming to Clients**:
   - Audio is streamed to clients using Server-Sent Events (SSE) via the `/audio-stream` endpoint
   - The audio data is base64 encoded before streaming
   - The browser decodes and plays audio using the Web Audio API

3. **Audio Format Requirements**:
   - Server expects raw PCM audio data (16-bit, mono)
   - Web client plays audio at 16kHz sample rate
   - The web client handles conversion from 16-bit PCM to float32 format for Web Audio API

### For ESP32 Korvo Developers:

To implement the client side:
1. Capture audio data from the microphone in 16-bit PCM format
2. Send the raw audio bytes to `/upload-audio` endpoint periodically
3. Keep sending video frames to `/upload` as currently implemented
4. No special synchronization is needed - the server handles audio and video as separate streams

Both streams operate independently, which helps maintain low latency. The web browser client manages playing the audio when the user clicks the "Start Audio" button.
