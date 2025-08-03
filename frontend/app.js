// app.js - Frontend logic for Real-Time Speech Translation MVP

class TranslationApp {
    constructor() {
        this.ws = null;
        this.mediaRecorder = null;
        this.audioContext = null;
        this.isRecording = false;
        this.audioChunks = [];
        
        // System audio capture
        this.isSystemRecording = false;
        this.systemMediaRecorder = null;
        this.systemAudioChunks = [];
        
        // Configuration
        this.config = {
            source_lang: 'auto',
            target_lang: 'en'
        };
        
        this.initializeElements();
        this.setupEventListeners();
    }
    
    initializeElements() {
        this.videoUrlInput = document.getElementById('video-url');
        this.startBtn = document.getElementById('start-btn');
        this.stopBtn = document.getElementById('stop-btn');
        this.statusDiv = document.getElementById('status');
        
        // Add language selection controls
        this.addLanguageControls();
    }
    
    addLanguageControls() {
        // Create language selection UI
        const controlsDiv = document.createElement('div');
        controlsDiv.innerHTML = `
            <div style="margin: 10px 0;">
                <label for="source-lang">Source Language:</label>
                <select id="source-lang">
                    <option value="auto">Auto-detect</option>
                    <option value="en">English</option>
                    <option value="ru">Russian</option>
                </select>
                
                <label for="target-lang" style="margin-left: 20px;">Target Language:</label>
                <select id="target-lang">
                    <option value="en">English</option>
                    <option value="ru">Russian</option>
                </select>
            </div>
            
            <div style="margin: 10px 0;">
                <button id="mic-btn">Use Microphone</button>
                <button id="system-audio-btn">Capture System Audio</button>
                <span id="audio-status">Ready</span>
            </div>
        `;
        
        // Insert after the URL input
        this.videoUrlInput.parentNode.insertBefore(controlsDiv, this.startBtn);
        
        // Get references to new elements
        this.sourceLangSelect = document.getElementById('source-lang');
        this.targetLangSelect = document.getElementById('target-lang');
        this.micBtn = document.getElementById('mic-btn');
        this.systemAudioBtn = document.getElementById('system-audio-btn');
        this.audioStatus = document.getElementById('audio-status');
    }
    
    setupEventListeners() {
        this.startBtn.addEventListener('click', () => this.startTranslation());
        this.stopBtn.addEventListener('click', () => this.stopTranslation());
        
        // Add microphone event listener (ensure element exists)
        if (this.micBtn) {
            this.micBtn.addEventListener('click', () => {
                console.log('Microphone button clicked');
                this.toggleMicrophone();
            });
        } else {
            console.error('Microphone button not found');
        }
        
        // Add system audio event listener
        if (this.systemAudioBtn) {
            this.systemAudioBtn.addEventListener('click', () => {
                console.log('System audio button clicked');
                this.toggleSystemAudio();
            });
        } else {
            console.error('System audio button not found');
        }
        
        // Language selection
        if (this.sourceLangSelect) {
            this.sourceLangSelect.addEventListener('change', (e) => {
                this.config.source_lang = e.target.value;
                this.updateConfig();
            });
        }
        
        if (this.targetLangSelect) {
            this.targetLangSelect.addEventListener('change', (e) => {
                this.config.target_lang = e.target.value;
                this.updateConfig();
            });
        }
    }
    
    async startTranslation() {
        try {
            this.updateStatus('Connecting to translation service...');
            
            // Connect to WebSocket
            await this.connectWebSocket();
            
            // Send configuration
            this.sendConfig();
            
            this.startBtn.disabled = true;
            this.stopBtn.disabled = false;
            this.updateStatus('Translation service connected. Ready to translate.');
            
        } catch (error) {
            this.updateStatus(`Error: ${error.message}`);
            console.error('Start translation error:', error);
        }
    }
    
    stopTranslation() {
        // Stop microphone if active
        if (this.isRecording) {
            this.stopMicrophone();
        }
        
        // Stop system audio if active
        if (this.isSystemRecording) {
            this.stopSystemAudio();
        }
        
        // Close WebSocket
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        
        this.startBtn.disabled = false;
        this.stopBtn.disabled = true;
        this.updateStatus('Translation stopped.');
    }
    
    async connectWebSocket() {
        return new Promise((resolve, reject) => {
            const wsUrl = `ws://${window.location.host}/ws/translate`;
            this.ws = new WebSocket(wsUrl);
            
            this.ws.onopen = () => {
                console.log('WebSocket connected');
                resolve();
            };
            
            this.ws.onmessage = (event) => {
                this.handleWebSocketMessage(event);
            };
            
            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                reject(new Error('Failed to connect to translation service'));
            };
            
            this.ws.onclose = () => {
                console.log('WebSocket disconnected');
                this.updateStatus('Disconnected from translation service');
            };
        });
    }
    
    sendConfig() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            const configMessage = {
                type: 'config',
                source_lang: this.config.source_lang,
                target_lang: this.config.target_lang
            };
            this.ws.send(JSON.stringify(configMessage));
        }
    }
    
    updateConfig() {
        this.sendConfig();
    }
    
    handleWebSocketMessage(event) {
        if (typeof event.data === 'string') {
            // Text message (config acknowledgment, error, or debug info)
            try {
                const message = JSON.parse(event.data);
                
                if (message.type === 'config_ack') {
                    console.log('Config updated:', message);
                    this.updateStatus(`Translation configured: ${message.source_lang} → ${message.target_lang}`);
                    this.addDebugLog(`🔧 Config: ${message.source_lang} → ${message.target_lang}`);
                    
                } else if (message.type === 'debug_transcript') {
                    this.handleDebugTranscript(message);
                    
                } else if (message.type === 'debug_translation') {
                    this.handleDebugTranslation(message);
                    
                } else if (message.type === 'debug_pipeline_complete') {
                    this.handleDebugPipelineComplete(message);
                    
                } else if (message.type === 'debug_pipeline_error') {
                    this.handleDebugPipelineError(message);
                    
                } else if (message.type === 'error') {
                    this.updateStatus(`Error: ${message.message}`);
                    console.error('WebSocket error:', message);
                    this.addDebugLog(`❌ Error: ${message.message}`);
                    
                } else if (message.type === 'pipeline_error') {
                    this.handlePipelineError(message);
                    
                } else {
                    console.log('Unknown message type:', message);
                }
            } catch (e) {
                console.error('Failed to parse message:', e);
                this.addDebugLog(`❌ Parse error: ${e.message}`);
            }
        } else {
            // Binary message (translated audio)
            this.playTranslatedAudio(event.data);
        }
    }
    
    handlePipelineError(errorMessage) {
        const { message, stages, total_latency } = errorMessage;
        
        console.error('Pipeline error:', errorMessage);
        
        // Determine which stage failed
        let failedStage = 'unknown';
        if (stages) {
            for (const [stage, info] of Object.entries(stages)) {
                if (info.success === false) {
                    failedStage = stage;
                    break;
                }
            }
        }
        
        // Create user-friendly error message
        let userMessage;
        switch (failedStage) {
            case 'conversion':
                userMessage = 'Audio format conversion failed. Please check your microphone.';
                break;
            case 'asr':
                userMessage = message === 'No speech detected' ? 
                    'No speech detected. Please speak more clearly.' :
                    'Speech recognition failed. Please try again.';
                break;
            case 'mt':
                userMessage = 'Translation failed. Please check your internet connection.';
                break;
            case 'tts':
                userMessage = 'Speech synthesis failed. Please try again.';
                break;
            default:
                userMessage = `Translation error: ${message}`;
        }
        
        this.updateStatus(`${userMessage} (${failedStage} stage)`);
        
        // Log detailed information for debugging
        if (stages) {
            console.log('Pipeline stages:', stages);
            console.log(`Total latency: ${(total_latency * 1000).toFixed(1)}ms`);
        }
    }
    
    async playTranslatedAudio(audioData) {
        try {
            if (!this.audioContext) {
                this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            }
            
            // Convert blob to array buffer
            const arrayBuffer = await audioData.arrayBuffer();
            
            // Decode audio data
            const audioBuffer = await this.audioContext.decodeAudioData(arrayBuffer);
            
            // Play audio
            const source = this.audioContext.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(this.audioContext.destination);
            source.start(0);
            
            console.log('Playing translated audio');
            
        } catch (error) {
            console.error('Error playing translated audio:', error);
        }
    }
    
    async toggleMicrophone() {
        if (!this.isRecording) {
            await this.startMicrophone();
        } else {
            this.stopMicrophone();
        }
    }
    
    async startMicrophone() {
        try {
            // Request microphone permission
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    sampleRate: 16000,
                    channelCount: 1,
                    echoCancellation: true,
                    noiseSuppression: true
                }
            });
            
            // Setup MediaRecorder
            this.mediaRecorder = new MediaRecorder(stream, {
                mimeType: 'audio/webm;codecs=opus'
            });
            
            this.audioChunks = [];
            
            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.audioChunks.push(event.data);
                }
            };
            
            this.mediaRecorder.onstop = () => {
                const audioBlob = new Blob(this.audioChunks, { type: 'audio/wav' });
                this.sendAudioChunk(audioBlob);
                this.audioChunks = [];
            };
            
            // Start recording in chunks
            this.mediaRecorder.start();
            this.isRecording = true;
            
            // Stop and restart every 3 seconds to create chunks
            this.recordingInterval = setInterval(() => {
                if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
                    this.mediaRecorder.stop();
                    setTimeout(() => {
                        if (this.isRecording) {
                            this.mediaRecorder.start();
                        }
                    }, 100);
                }
            }, 3000);
            
            this.micBtn.textContent = 'Stop Microphone';
            this.audioStatus.textContent = 'Recording...';
            this.updateStatus('Microphone active. Speak to translate in real-time.');
            
        } catch (error) {
            console.error('Microphone error:', error);
            this.updateStatus(`Microphone error: ${error.message}`);
        }
    }
    
    stopMicrophone() {
        if (this.mediaRecorder) {
            this.mediaRecorder.stop();
            this.mediaRecorder.stream.getTracks().forEach(track => track.stop());
            this.mediaRecorder = null;
        }
        
        if (this.recordingInterval) {
            clearInterval(this.recordingInterval);
            this.recordingInterval = null;
        }
        
        this.isRecording = false;
        this.micBtn.textContent = 'Use Microphone';
        this.audioStatus.textContent = 'Stopped';
    }
    
    async sendAudioChunk(audioBlob) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            try {
                // Convert audio blob to WAV format if needed
                const arrayBuffer = await audioBlob.arrayBuffer();
                this.ws.send(arrayBuffer);
                console.log(`Sent audio chunk: ${arrayBuffer.byteLength} bytes`);
            } catch (error) {
                console.error('Error sending audio chunk:', error);
            }
        }
    }
    
    // System Audio Capture Methods
    async toggleSystemAudio() {
        if (!this.isSystemRecording) {
            await this.startSystemAudio();
        } else {
            this.stopSystemAudio();
        }
    }
    
    async startSystemAudio() {
        try {
            // Request system audio capture permission
            const stream = await navigator.mediaDevices.getDisplayMedia({
                video: false,
                audio: {
                    sampleRate: 16000,
                    channelCount: 1,
                    echoCancellation: false,
                    noiseSuppression: false
                }
            });
            
            // Setup MediaRecorder for system audio
            this.systemMediaRecorder = new MediaRecorder(stream, {
                mimeType: 'audio/webm;codecs=opus'
            });
            
            this.systemAudioChunks = [];
            
            this.systemMediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.systemAudioChunks.push(event.data);
                }
            };
            
            this.systemMediaRecorder.onstop = () => {
                const audioBlob = new Blob(this.systemAudioChunks, { type: 'audio/webm' });
                this.sendAudioChunk(audioBlob);
                this.systemAudioChunks = [];
            };
            
            // Start recording system audio in chunks
            this.systemMediaRecorder.start();
            this.isSystemRecording = true;
            
            // Stop and restart every 3 seconds to create chunks
            this.systemRecordingInterval = setInterval(() => {
                if (this.systemMediaRecorder && this.systemMediaRecorder.state === 'recording') {
                    this.systemMediaRecorder.stop();
                    setTimeout(() => {
                        if (this.isSystemRecording) {
                            this.systemMediaRecorder.start();
                        }
                    }, 100);
                }
            }, 3000);
            
            this.systemAudioBtn.textContent = 'Stop System Audio';
            this.audioStatus.textContent = 'Capturing System Audio...';
            this.updateStatus('System audio active. Play audio samples to translate in real-time.');
            
        } catch (error) {
            console.error('System audio error:', error);
            if (error.name === 'NotAllowedError') {
                this.updateStatus('System audio permission denied. Please allow screen/audio sharing.');
            } else {
                this.updateStatus(`System audio error: ${error.message}`);
            }
        }
    }
    
    stopSystemAudio() {
        if (this.systemMediaRecorder) {
            this.systemMediaRecorder.stop();
            this.systemMediaRecorder.stream.getTracks().forEach(track => track.stop());
            this.systemMediaRecorder = null;
        }
        
        if (this.systemRecordingInterval) {
            clearInterval(this.systemRecordingInterval);
            this.systemRecordingInterval = null;
        }
        
        this.isSystemRecording = false;
        this.systemAudioBtn.textContent = 'Capture System Audio';
        this.audioStatus.textContent = 'Stopped';
        this.updateStatus('System audio capture stopped.');
    }
    
    // Debug UI Update Methods
    handleDebugTranscript(message) {
        const transcriptText = document.getElementById('transcript-text');
        const asrStatus = document.getElementById('asr-status');
        const asrDetail = document.getElementById('asr-detail');
        
        if (transcriptText) transcriptText.textContent = message.text;
        if (asrStatus) {
            asrStatus.textContent = '✅ Complete';
            asrStatus.style.color = '#28a745';
        }
        if (asrDetail) {
            const latency = message.stage_latencies?.asr || 0;
            asrDetail.textContent = `Completed in ${latency.toFixed(0)}ms`;
        }
        
        this.addDebugLog(`🎤 ASR: "${message.text}"`);
    }
    
    handleDebugTranslation(message) {
        const translationText = document.getElementById('translation-text');
        const mtStatus = document.getElementById('mt-status');
        const mtDetail = document.getElementById('mt-detail');
        
        if (translationText) translationText.textContent = message.text;
        if (mtStatus) {
            mtStatus.textContent = '✅ Complete';
            mtStatus.style.color = '#28a745';
        }
        if (mtDetail) {
            const latency = message.total_latency_ms || 0;
            mtDetail.textContent = `Completed in ${latency.toFixed(0)}ms`;
        }
        
        this.addDebugLog(`🌐 MT: "${message.text}"`);
    }
    
    handleDebugPipelineComplete(message) {
        const ttsStatus = document.getElementById('tts-status');
        const ttsDetail = document.getElementById('tts-detail');
        const performanceText = document.getElementById('performance-text');
        
        if (ttsStatus) {
            ttsStatus.textContent = '✅ Complete';
            ttsStatus.style.color = '#28a745';
        }
        if (ttsDetail) {
            const ttsLatency = message.stage_latencies?.tts || 0;
            ttsDetail.textContent = `Generated ${message.audio_size} bytes in ${ttsLatency.toFixed(0)}ms`;
        }
        
        // Update performance display
        if (performanceText && message.stage_latencies) {
            const stages = message.stage_latencies;
            const total = message.total_latency_ms;
            performanceText.textContent = 
                `Total: ${total.toFixed(0)}ms | ASR: ${(stages.asr || 0).toFixed(0)}ms | ` +
                `MT: ${(stages.mt || 0).toFixed(0)}ms | TTS: ${(stages.tts || 0).toFixed(0)}ms`;
        }
        
        this.addDebugLog(`🔊 TTS: ${message.audio_size} bytes audio generated`);
        this.addDebugLog(`✅ Pipeline complete in ${message.total_latency_ms.toFixed(0)}ms`);
        
        // Reset status after a delay
        setTimeout(() => this.resetStageStatus(), 2000);
    }
    
    handleDebugPipelineError(message) {
        const failedStage = message.failed_stage;
        
        // Update failed stage
        const stageStatusMap = {
            'asr': 'asr-status',
            'mt': 'mt-status',  
            'tts': 'tts-status'
        };
        
        const statusId = stageStatusMap[failedStage];
        if (statusId) {
            const statusEl = document.getElementById(statusId);
            if (statusEl) {
                statusEl.textContent = '❌ Failed';
                statusEl.style.color = '#dc3545';
            }
            
            const detailId = statusId.replace('-status', '-detail');
            const detailEl = document.getElementById(detailId);
            if (detailEl) {
                detailEl.textContent = message.message;
                detailEl.style.color = '#dc3545';
            }
        }
        
        // Show any successful stages
        if (message.transcript) {
            this.handleDebugTranscript({
                text: message.transcript,
                stage_latencies: message.stage_latencies
            });
        }
        
        if (message.translation) {
            this.handleDebugTranslation({
                text: message.translation,
                stage_latencies: message.stage_latencies
            });
        }
        
        this.addDebugLog(`❌ ${failedStage.toUpperCase()} failed: ${message.message}`);
        
        // Reset status after a delay
        setTimeout(() => this.resetStageStatus(), 5000);
    }
    
    resetStageStatus() {
        // Reset all stage statuses to ready
        const stages = ['asr', 'mt', 'tts'];
        stages.forEach(stage => {
            const statusEl = document.getElementById(`${stage}-status`);
            const detailEl = document.getElementById(`${stage}-detail`);
            
            if (statusEl) {
                statusEl.textContent = 'Ready';
                statusEl.style.color = '';
            }
            if (detailEl) {
                detailEl.textContent = '';
                detailEl.style.color = '';
            }
        });
    }
    
    addDebugLog(message) {
        const debugLog = document.getElementById('debug-log');
        if (debugLog) {
            const timestamp = new Date().toLocaleTimeString();
            const logEntry = document.createElement('div');
            logEntry.textContent = `[${timestamp}] ${message}`;
            debugLog.appendChild(logEntry);
            
            // Auto-scroll to bottom
            debugLog.scrollTop = debugLog.scrollHeight;
            
            // Keep only last 50 entries
            while (debugLog.children.length > 50) {
                debugLog.removeChild(debugLog.firstChild);
            }
        }
        
        console.log(`Debug: ${message}`);
    }
    
    updateStatus(message) {
        this.statusDiv.textContent = `Status: ${message}`;
        console.log('Status:', message);
    }
}

// Initialize the application when the page loads
document.addEventListener('DOMContentLoaded', () => {
    console.log('Initializing Real-Time Speech Translation MVP');
    new TranslationApp();
});
