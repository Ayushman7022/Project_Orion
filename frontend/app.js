// Initialize Lucide icons
lucide.createIcons();

// ===== CONFIGURATION =====
const API_BASE = "http://localhost:8000";

// ===== DOM ELEMENTS =====
const imageRootEl = document.getElementById("image-panel") || document.getElementById("image-receptor");
const elements = {
    // Core elements
    coreState: document.getElementById("core-state") || document.getElementById("orion-state-pill"),
    consciousnessStream:
        document.getElementById("consciousness-stream") || document.getElementById("live-transcript"),
    userInput: document.getElementById("user-input"),
    sendBtn: document.getElementById("send-btn"),
    micBtn: document.getElementById("mic-btn"),
    clearLog: document.getElementById("clear-log") || document.getElementById("clear-feed"),
    logStream: document.getElementById("log-stream") || document.getElementById("chat-window"),
    
    // Language & STT
    languageSelect: document.getElementById("language-select"),
    sttModeBtn: document.getElementById("stt-mode"),
    
    // API Keys
    sarvamKey: document.getElementById("sarvam-key") || document.getElementById("sarvam-key-input"),
    openaiKey: document.getElementById("openai-key") || document.getElementById("openai-key-input"),
    openaiModel: document.getElementById("openai-model") || document.getElementById("openai-model-input"),
    saveSarvamBtn:
        document.getElementById("save-sarvam") || document.getElementById("save-keys-btn"),
    
    // Image generation
    imageReceptor: imageRootEl,
    imageStatus: (imageRootEl && imageRootEl.querySelector("#image-status")) || document.getElementById("image-status"),
    generatedImage: (imageRootEl && imageRootEl.querySelector("#generated-image")) || document.getElementById("generated-image"),
    
    // Time display
    quantumTime: document.getElementById("quantum-time")
};

// ===== STATE VARIABLES =====
let lastDetectedLanguage = "en";
let mediaRecorder = null;
let audioChunks = [];
let micStream = null;
let replyAudio = null;
let lastReplyText = "";
let lastReplyLang = "en";
let audioUnlocked = false;
let pendingAutoPlay = false;
let pendingText = "";
let pendingLang = "en";
let sttBatchInFlight = false;

// ===== UTILITY FUNCTIONS =====

// Update core state display
function setCoreState(state, subtitle = "") {
    if (elements.coreState) {
        elements.coreState.textContent = state.toUpperCase();
    }
    if (elements.consciousnessStream && subtitle) {
        elements.consciousnessStream.textContent = `"${subtitle}"`;
    } else if (elements.consciousnessStream) {
        elements.consciousnessStream.textContent = `"system is ${state.toLowerCase()}"`;
    }
}

// Get selected language
function getSelectedLang() {
    const v = elements.languageSelect ? elements.languageSelect.value : "en";
    return v === "hi" || v === "mr" || v === "en" ? v : "en";
}

// Load saved language preference
function loadSavedLanguage() {
    try {
        const saved = localStorage.getItem("orion_language");
        if (saved && ["en", "hi", "mr"].includes(saved)) {
            elements.languageSelect.value = saved;
            lastDetectedLanguage = saved;
        }
    } catch (e) {
        console.warn("Could not load language preference", e);
    }
}

// Save language preference
function persistLanguage(lang) {
    try {
        localStorage.setItem("orion_language", lang);
    } catch (e) {
        console.warn("Could not save language preference", e);
    }
}

// Mask API key for display
function maskKey(key) {
    if (!key || key.length < 8) return "********";
    return `${key.slice(0, 4)}…${key.slice(-4)}`;
}

// Update time display
function updateTime() {
    if (elements.quantumTime) {
        const now = new Date();
        elements.quantumTime.textContent = now.toLocaleTimeString('en-GB', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        });
    }
}
setInterval(updateTime, 1000);
updateTime();

// ===== AUDIO HANDLING =====

// Unlock audio on user interaction
function unlockAudio() {
    if (audioUnlocked) return;
    try {
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        if (AudioContext) {
            const ctx = new AudioContext();
            if (ctx.state === "suspended") ctx.resume();
            // Silent oscillator to unlock audio
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            gain.gain.value = 0.0001;
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start();
            osc.stop(ctx.currentTime + 0.01);
        }
        audioUnlocked = true;
    } catch (e) {
        console.warn("Audio unlock failed", e);
        audioUnlocked = true;
    }
}

// Map language to TTS voice
function mapLangToTts(lang) {
    const code = (lang || "").toLowerCase();
    if (code.startsWith("hi")) return { language_code: "hi-IN", speaker: "priya" };
    if (code.startsWith("mr")) return { language_code: "mr-IN", speaker: "shruti" };
    return { language_code: "en-IN", speaker: "amelia" };
}

// Play TTS reply
async function playReplyTTS(text, langCode) {
    if (!text || !text.trim()) return;
    
    lastReplyText = text;
    lastReplyLang = langCode || lastDetectedLanguage || "en";
    
    const { language_code, speaker } = mapLangToTts(langCode || lastDetectedLanguage);
    
    const formData = new FormData();
    formData.append("text", text);
    formData.append("language_code", language_code);
    formData.append("speaker", speaker);
    
    try {
        setCoreState("speaking", "neural vocalization active");
        pendingAutoPlay = false;
        
        const response = await fetch(`${API_BASE}/tts`, {
            method: "POST",
            body: formData
        });
        
        if (!response.ok) throw new Error(`TTS failed: ${response.status}`);
        
        const blob = await response.blob();
        
        if (replyAudio) {
            replyAudio.pause();
            URL.revokeObjectURL(replyAudio.src);
        }
        
        replyAudio = new Audio(URL.createObjectURL(blob));
        await replyAudio.play();
        setCoreState("idle", "awaiting neural input");
        
    } catch (e) {
        console.error("TTS error:", e);
        setCoreState("idle", "audio system ready");
        pendingAutoPlay = true;
        pendingText = text;
        pendingLang = lastReplyLang;
    }
}

// ===== MESSAGE HANDLING =====

// Append message to log
function appendMessage(role, text) {
    if (!elements.logStream) return;
    
    const entry = document.createElement("div");
    entry.className = `log-entry ${role}`;
    
    const timestamp = document.createElement("span");
    timestamp.className = "log-timestamp";
    timestamp.textContent = new Date().toLocaleTimeString('en-GB', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    });
    
    const message = document.createElement("span");
    message.className = "log-message";
    message.textContent = text;
    
    entry.appendChild(timestamp);
    entry.appendChild(message);
    
    elements.logStream.appendChild(entry);
    elements.logStream.scrollTop = elements.logStream.scrollHeight;
}

// Send message to chat API
async function sendMessage(text, langOverride) {
    if (!text.trim()) return;
    
    appendMessage("user", text);
    if (elements.userInput) elements.userInput.value = "";
    
    setCoreState("thinking", "processing neural patterns...");
    
    const language = langOverride || getSelectedLang() || "en";
    
    // Check for image generation request
    const lower = text.toLowerCase();
    const isImageRequest = 
        (lower.includes("image") && lower.includes("generate")) ||
        (lower.includes("create") && lower.includes("image")) ||
        (lower.includes("draw") && lower.includes("image")) ||
        lower.includes("make an image") ||
        lower.includes("generate image");
    
    if (isImageRequest) {
        // Extract prompt
        let prompt = text;
        const patterns = [
            /generate\s+(?:an?\s+)?image\s+(?:of\s+)?(.*)/i,
            /create\s+(?:an?\s+)?image\s+(?:of\s+)?(.*)/i,
            /draw\s+(?:an?\s+)?image\s+(?:of\s+)?(.*)/i,
            /image\s+of\s+(.*)/i
        ];
        
        for (const pattern of patterns) {
            const match = text.match(pattern);
            if (match && match[1]) {
                prompt = match[1].trim();
                break;
            }
        }
        
        try {
            if (elements.imageStatus) {
                elements.imageStatus.textContent = "Generating neural visualization...";
            }
            
            if (elements.generatedImage) {
                elements.generatedImage.src = "";
                elements.generatedImage.style.display = "none";
            }
            
            const formData = new FormData();
            formData.append("prompt", prompt);
            
            const response = await fetch(`${API_BASE}/image/generate`, {
                method: "POST",
                body: formData
            });
            
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.detail || `Image generation failed (${response.status})`);
            }
            
            if (data.image_data_url) {
                // Some UI variants use different classes; enforce visibility via inline style.
                const imgs = document.querySelectorAll("#generated-image");
                if (imgs && imgs.length) {
                    imgs.forEach((img) => {
                        if (img) {
                            img.src = data.image_data_url;
                            img.style.display = "block";
                        }
                    });
                } else if (elements.generatedImage) {
                    elements.generatedImage.src = data.image_data_url;
                    elements.generatedImage.style.display = "block";
                }
                elements.imageReceptor?.classList.add("has-image");
            }
            
            if (elements.imageStatus) {
                elements.imageStatus.textContent = "Neural visualization complete";
            }
            
            const confirmText = language.startsWith("hi") 
                ? "छवि तैयार है।" 
                : language.startsWith("mr") 
                    ? "प्रतिमा तयार आहे." 
                    : "Neural visualization complete.";
            
            appendMessage("ai", confirmText);
            await playReplyTTS(confirmText, language);
            
        } catch (e) {
            console.error("Image generation error:", e);
            const errorMsg = e.message || "Failed to generate image";
            if (elements.imageStatus) elements.imageStatus.textContent = errorMsg;
            appendMessage("ai", `⚠️ ${errorMsg}`);
        }
        
        return;
    }
    
    // Regular chat message
    const formData = new FormData();
    formData.append("message", text);
    formData.append("language", language);
    
    try {
        const response = await fetch(`${API_BASE}/chat`, {
            method: "POST",
            body: formData
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.detail || `Chat failed (${response.status})`);
        }
        
        const replyText = data.text || "[No response]";
        appendMessage("ai", replyText);
        await playReplyTTS(replyText, language);
        
    } catch (e) {
        console.error("Chat error:", e);
        appendMessage("ai", "⚠️ Neural link failed. Check connection.");
        setCoreState("idle", "connection error");
    }
}

// ===== SPEECH-TO-TEXT HANDLING =====

async function startSTTRecording() {
    if (sttBatchInFlight) return;
    
    sttBatchInFlight = true;
    audioChunks = [];
    
    try {
        if (!micStream) {
            micStream = await navigator.mediaDevices.getUserMedia({ 
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }
            });
        }
        
        mediaRecorder = new MediaRecorder(micStream, {
            mimeType: 'audio/webm;codecs=opus'
        });
        
        mediaRecorder.ondataavailable = (e) => {
            if (e.data && e.data.size > 0) {
                audioChunks.push(e.data);
            }
        };
        
        mediaRecorder.onstop = async () => {
            const lang = getSelectedLang();
            
            try {
                setCoreState("thinking", "decoding neural patterns...");
                
                const blob = new Blob(audioChunks, { type: "audio/webm" });
                
                if (blob.size < 1000) {
                    setCoreState("idle", "no input detected");
                    sttBatchInFlight = false;
                    return;
                }
                
                const formData = new FormData();
                formData.append("audio", blob, "speech.webm");
                formData.append("language_hint", lang);
                
                const response = await fetch(`${API_BASE}/stt`, {
                    method: "POST",
                    body: formData
                });
                
                const data = await response.json();
                
                if (!response.ok) {
                    throw new Error(data.detail || `STT failed (${response.status})`);
                }
                
                const text = data.text || "";
                const detected = (data.detected_language || lang || "en").slice(0, 2);
                lastDetectedLanguage = detected;
                
                if (elements.userInput) {
                    elements.userInput.value = text;
                }
                
                if (elements.consciousnessStream) {
                    elements.consciousnessStream.textContent = `"${text || '...'}"`;
                }
                
                if (text) {
                    await sendMessage(text, detected);
                } else {
                    setCoreState("idle", "no speech detected");
                }
                
            } catch (e) {
                console.error("STT error:", e);
                setCoreState("idle", "neural decoding failed");
            } finally {
                sttBatchInFlight = false;
            }
        };
        
        mediaRecorder.start();
        setCoreState("listening", "neural input active - release to process");
        
    } catch (e) {
        console.error("Mic access error:", e);
        setCoreState("idle", "mic access denied");
        sttBatchInFlight = false;
    }
}

function stopSTTRecording() {
    try {
        if (mediaRecorder && mediaRecorder.state === "recording") {
            setCoreState("thinking", "processing neural input");
            mediaRecorder.stop();
            
            // Stop tracks to release mic
            if (micStream) {
                micStream.getTracks().forEach(track => track.stop());
                micStream = null;
            }
        } else {
            sttBatchInFlight = false;
        }
    } catch (e) {
        console.error("Stop recording error:", e);
        sttBatchInFlight = false;
    }
}

// ===== API KEY HANDLING =====

async function saveKeysToBackend() {
    const sarvamKey = elements.sarvamKey?.value.trim() || "";
    const openaiKey = elements.openaiKey?.value.trim() || "";
    const openaiModel = elements.openaiModel?.value.trim() || "gpt-4o";
    
    try {
        const formData = new FormData();
        formData.append("sarvam_api_key", sarvamKey);
        formData.append("cloud_provider", "openai_compatible");
        formData.append("cloud_api_key", openaiKey);
        formData.append("cloud_base_url", "https://api.openai.com");
        formData.append("cloud_model", openaiModel);
        
        const response = await fetch(`${API_BASE}/config`, {
            method: "POST",
            body: formData
        });
        
        if (!response.ok) throw new Error("Failed to save configuration");
        
        // Save to localStorage
        localStorage.setItem("sarvam_api_key", sarvamKey);
        localStorage.setItem("openai_api_key", openaiKey);
        localStorage.setItem("openai_model", openaiModel);
        
        // Show success (you could add a toast notification here)
        console.log("API keys saved successfully");
        
    } catch (e) {
        console.error("Failed to save API keys:", e);
    }
}

// Load saved API keys
function loadSavedKeys() {
    try {
        const sarvamKey = localStorage.getItem("sarvam_api_key");
        const openaiKey = localStorage.getItem("openai_api_key");
        const openaiModel = localStorage.getItem("openai_model");
        
        if (sarvamKey && elements.sarvamKey) {
            elements.sarvamKey.value = sarvamKey;
        }
        
        if (openaiKey && elements.openaiKey) {
            elements.openaiKey.value = openaiKey;
        }
        
        if (openaiModel && elements.openaiModel) {
            elements.openaiModel.value = openaiModel;
        }
        
        // Attempt to sync with backend
        if (sarvamKey || openaiKey) {
            saveKeysToBackend();
        }
        
    } catch (e) {
        console.warn("Could not load saved keys:", e);
    }
}

// ===== EVENT LISTENERS =====

// Send button
if (elements.sendBtn) {
    elements.sendBtn.addEventListener("click", () => {
        unlockAudio();
        if (elements.userInput?.value.trim()) {
            sendMessage(elements.userInput.value);
        }
    });
}

// Mic button - push to talk
if (elements.micBtn) {
    elements.micBtn.addEventListener("mousedown", (e) => {
        e.preventDefault();
        unlockAudio();
        startSTTRecording();
    });
    
    elements.micBtn.addEventListener("mouseup", stopSTTRecording);
    elements.micBtn.addEventListener("mouseleave", stopSTTRecording);
}

// Enter key in textarea
if (elements.userInput) {
    elements.userInput.addEventListener("keydown", (e) => {
        unlockAudio();
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (elements.userInput.value.trim()) {
                sendMessage(elements.userInput.value);
            }
        }
    });
}

// Clear log
if (elements.clearLog) {
    elements.clearLog.addEventListener("click", () => {
        if (elements.logStream) {
            elements.logStream.innerHTML = "";
        }
    });
}

// Language select
if (elements.languageSelect) {
    loadSavedLanguage();
    elements.languageSelect.addEventListener("change", () => {
        const lang = getSelectedLang();
        persistLanguage(lang);
        lastDetectedLanguage = lang;
        if (elements.consciousnessStream) {
            const langNames = { en: "English", hi: "Hindi", mr: "Marathi" };
            elements.consciousnessStream.textContent = `"language: ${langNames[lang]}"`;
        }
    });
}

// Save API keys
if (elements.saveSarvamBtn) {
    elements.saveSarvamBtn.addEventListener("click", saveKeysToBackend);
}

// STT mode toggle (just visual for now)
if (elements.sttModeBtn) {
    elements.sttModeBtn.addEventListener("click", () => {
        const modes = ["WHISPER", "BATCH", "REALTIME"];
        const current = elements.sttModeBtn.textContent;
        const nextIndex = (modes.indexOf(current) + 1) % modes.length;
        elements.sttModeBtn.textContent = modes[nextIndex];
    });
}

// ===== INITIALIZATION =====

// Load saved keys
loadSavedKeys();

// Set initial state
setCoreState("idle", "neural interface initialized");

// Add welcome message
appendMessage("system", "ORION neural interface v3.1.0 initialized");
appendMessage("ai", "Awaiting your command. All systems operational.");

// Clean up on page unload
window.addEventListener("beforeunload", () => {
    if (micStream) {
        micStream.getTracks().forEach(track => track.stop());
    }
    if (replyAudio) {
        replyAudio.pause();
        URL.revokeObjectURL(replyAudio.src);
    }
});