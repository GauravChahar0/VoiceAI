/**
 * VoiceAI - Vanilla JavaScript Frontend Controller
 * Controls Voice Assistant and Call Summarization (English & Hindi).
 */

// Point to FastAPI backend on port 8000 even if frontend is served by VS Code Live Server (port 5500)
const BACKEND_PORT = "8000";
const API_BASE = (window.location.protocol.startsWith("http") && window.location.port === BACKEND_PORT)
    ? window.location.origin
    : `http://${window.location.hostname && window.location.hostname !== "" ? window.location.hostname : "127.0.0.1"}:${BACKEND_PORT}`;

// Global App State
const state = {
    provider: "ollama",
    model: "llama3.1:8b",
    language: "auto",
    isListening: false,
    isProcessing: false,
    isCallActive: false,
    callStartTime: 0,
    callTimerInterval: null,
    currentCallId: null,
    lastAudioBase64: null,
    lastAudioFormat: "wav",
    recognition: null,
    mediaRecorder: null,
    audioChunks: [],
    callMediaRecorder: null,
    callAudioChunks: []
};

// DOM References
const el = {
    aiProviderSelect: document.getElementById("aiProviderSelect"),
    aiModelSelect: document.getElementById("aiModelSelect"),
    appLanguageSelect: document.getElementById("appLanguageSelect"),
    systemStatusBadge: document.getElementById("systemStatusBadge"),
    systemStatusText: document.getElementById("systemStatusText"),
    themeToggleBtn: document.getElementById("themeToggleBtn"),

    // Tabs
    tabBtns: document.querySelectorAll(".tab-btn"),
    tabContents: document.querySelectorAll(".tab-content"),

    // Voice Section
    micToggleBtn: document.getElementById("micToggleBtn"),
    micOrbContainer: document.querySelector(".mic-orb-container"),
    startListeningBtn: document.getElementById("startListeningBtn"),
    stopListeningBtn: document.getElementById("stopListeningBtn"),
    micStatusBadge: document.getElementById("micStatusBadge"),
    micStateLabel: document.getElementById("micStateLabel"),
    manualTextInput: document.getElementById("manualTextInput"),
    sendTextBtn: document.getElementById("sendTextBtn"),
    conversationStream: document.getElementById("conversationStream"),
    replayLastAudioBtn: document.getElementById("replayLastAudioBtn"),
    clearHistoryBtn: document.getElementById("clearHistoryBtn"),
    sendToCallSummaryBtn: document.getElementById("sendToCallSummaryBtn"),

    // Call Section
    callActionCard: document.querySelector(".call-action-card"),
    callRecStatusText: document.getElementById("callRecStatusText"),
    callTimerDisplay: document.getElementById("callTimerDisplay"),
    startCallBtn: document.getElementById("startCallBtn"),
    endCallBtn: document.getElementById("endCallBtn"),
    savedCallsSelect: document.getElementById("savedCallsSelect"),
    callTranscriptTextarea: document.getElementById("callTranscriptTextarea"),
    saveTranscriptBtn: document.getElementById("saveTranscriptBtn"),
    charCountDisplay: document.getElementById("charCountDisplay"),
    generateSummaryBtn: document.getElementById("generateSummaryBtn"),
    callSummaryBody: document.getElementById("callSummaryBody"),
    downloadTranscriptBtn: document.getElementById("downloadTranscriptBtn"),
    downloadSummaryBtn: document.getElementById("downloadSummaryBtn"),

    // Audio Player
    ttsAudioPlayer: document.getElementById("ttsAudioPlayer")
};

// ── Initialization ─────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
    initTheme();
    initTabs();
    initControls();
    initSpeechRecognition();
    initCallSummarizer();
    await checkSystemStatusAndModels();
    await loadSavedCallsList();
});

// ── Theme & Tabs ───────────────────────────────────────────────────────

function initTheme() {
    const saved = localStorage.getItem("voiceai_theme") || "dark";
    document.documentElement.setAttribute("data-theme", saved);
    updateThemeIcon(saved);

    el.themeToggleBtn.addEventListener("click", () => {
        const current = document.documentElement.getAttribute("data-theme");
        const next = current === "dark" ? "light" : "dark";
        document.documentElement.setAttribute("data-theme", next);
        localStorage.setItem("voiceai_theme", next);
        updateThemeIcon(next);
    });
}

function updateThemeIcon(theme) {
    el.themeToggleBtn.innerHTML = theme === "dark" ? '<i class="fas fa-sun"></i>' : '<i class="fas fa-moon"></i>';
}

function initTabs() {
    el.tabBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            el.tabBtns.forEach(b => b.classList.remove("active"));
            el.tabContents.forEach(c => c.classList.remove("active"));

            btn.classList.add("active");
            const targetId = btn.getAttribute("data-tab");
            const targetContent = document.getElementById(targetId);
            if (targetContent) targetContent.classList.add("active");
        });
    });
}

function switchToTab(tabId) {
    el.tabBtns.forEach(b => {
        if (b.getAttribute("data-tab") === tabId) b.classList.add("active");
        else b.classList.remove("active");
    });
    el.tabContents.forEach(c => {
        if (c.id === tabId) c.classList.add("active");
        else c.classList.remove("active");
    });
}

function initControls() {
    el.aiProviderSelect.addEventListener("change", async (e) => {
        state.provider = e.target.value;
        await updateModelDropdown();
    });

    el.aiModelSelect.addEventListener("change", (e) => {
        state.model = e.target.value;
    });

    el.appLanguageSelect.addEventListener("change", (e) => {
        state.language = e.target.value;
    });

    el.clearHistoryBtn.addEventListener("click", () => {
        el.conversationStream.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-comment-dots"></i>
                <p>Press <strong>Start Listening</strong> or type a message to begin.</p>
                <span>आप अंग्रेज़ी या हिन्दी में बात कर सकते हैं।</span>
            </div>
        `;
    });

    el.replayLastAudioBtn.addEventListener("click", () => {
        if (state.lastAudioBase64) {
            playBase64Audio(state.lastAudioBase64, state.lastAudioFormat);
        } else {
            alert("No audio response available to replay.");
        }
    });

    el.sendTextBtn.addEventListener("click", handleManualTextSend);
    el.manualTextInput.addEventListener("keypress", (e) => {
        if (e.key === "Enter") handleManualTextSend();
    });

    // Send entire conversation history directly to Call Summarization
    el.sendToCallSummaryBtn.addEventListener("click", () => {
        const bubbles = el.conversationStream.querySelectorAll(".chat-bubble");
        if (!bubbles || bubbles.length === 0) {
            alert("No conversation history to send.");
            return;
        }

        let fullText = "";
        bubbles.forEach(b => {
            const role = b.classList.contains("user") ? "User" : "Assistant";
            const textEl = b.querySelector("div:not(.chat-meta)");
            if (textEl && !b.id.startsWith("thinking_")) {
                fullText += `${role}: ${textEl.textContent.trim()}\n`;
            }
        });

        if (!fullText.trim()) {
            alert("Conversation history is empty.");
            return;
        }

        // Transfer text to Call Summarization textarea
        el.callTranscriptTextarea.value = fullText;
        updateCharCount();
        saveCurrentTranscriptToFile(fullText);
        switchToTab("call-summary-tab");
    });
}

// ── Check Server Health & Load Models ─────────────────────────────────

async function checkSystemStatusAndModels() {
    try {
        const res = await fetch(`${API_BASE}/api/ai/models`);
        if (res.ok) {
            const data = await res.json();
            window.modelsCache = data;
            await updateModelDropdown();
            setSystemStatus("connected", "Ready");
        } else {
            setSystemStatus("error", "Server Issue");
        }
    } catch (err) {
        setSystemStatus("error", "Offline");
        console.error("Could not reach backend:", err);
    }
}

async function updateModelDropdown() {
    const cache = window.modelsCache || {
        ollama: { models: ["llama3.1:8b", "qwen3.5:9b"] },
        gemini: { models: ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash"] }
    };
    const provider = el.aiProviderSelect.value;
    const models = cache[provider]?.models || [];

    const previousSelected = el.aiModelSelect.value;
    el.aiModelSelect.innerHTML = "";

    models.forEach(m => {
        const opt = document.createElement("option");
        opt.value = m;
        opt.textContent = m;
        if (m === previousSelected) opt.selected = true;
        el.aiModelSelect.appendChild(opt);
    });

    if (!el.aiModelSelect.value && models.length > 0) {
        el.aiModelSelect.value = models[0];
    }
    state.model = el.aiModelSelect.value;
}

function setSystemStatus(type, text) {
    el.systemStatusBadge.className = `status-badge ${type}`;
    el.systemStatusText.textContent = text;
}

// ── Speech-to-Text & Audio Recording ──────────────────────────────────

let speechDebounceTimer = null;
let currentSpeechAccumulator = "";

function initSpeechRecognition() {
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRec) {
        state.recognition = new SpeechRec();
        state.recognition.continuous = false;
        state.recognition.interimResults = true;

        state.recognition.onstart = () => {
            setListeningState(true);
            currentSpeechAccumulator = "";
        };

        state.recognition.onresult = (event) => {
            if (state.isProcessing) return;

            let interim = "";
            for (let i = event.resultIndex; i < event.results.length; ++i) {
                const text = event.results[i][0].transcript;
                if (event.results[i].isFinal) {
                    currentSpeechAccumulator += " " + text;
                } else {
                    interim += text;
                }
            }

            const liveText = (currentSpeechAccumulator + " " + interim).trim();
            if (liveText) {
                el.micStateLabel.textContent = `Hearing: "${liveText}"`;
            }

            // Debounce: wait for user to pause (750ms) before sending to AI
            clearTimeout(speechDebounceTimer);
            speechDebounceTimer = setTimeout(async () => {
                const phrase = (currentSpeechAccumulator || interim).trim();
                if (phrase && !state.isProcessing) {
                    stopListening();
                    await processUserQuery(phrase);
                }
            }, 750);
        };

        state.recognition.onerror = (e) => {
            console.warn("Browser SpeechRecognition error:", e.error);
            if (!state.isProcessing) setListeningState(false);
        };

        state.recognition.onend = () => {
            if (!state.isProcessing) setListeningState(false);
        };
    }

    el.micToggleBtn.addEventListener("click", () => {
        if (state.isListening) {
            stopListening();
        } else {
            startListening();
        }
    });

    el.startListeningBtn.addEventListener("click", startListening);
    el.stopListeningBtn.addEventListener("click", stopListening);
}

async function startListening() {
    if (state.isListening || state.isProcessing) return;

    if (state.recognition) {
        state.recognition.lang = state.language === "hi" ? "hi-IN" : "en-US";
        try {
            state.recognition.start();
            return;
        } catch (e) {
            console.warn("Could not start Web Speech, falling back to MediaRecorder", e);
        }
    }

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        state.audioChunks = [];
        state.mediaRecorder = new MediaRecorder(stream);
        state.mediaRecorder.ondataavailable = (e) => state.audioChunks.push(e.data);
        state.mediaRecorder.onstop = async () => {
            const blob = new Blob(state.audioChunks, { type: "audio/wav" });
            stream.getTracks().forEach(t => t.stop());
            await sendAudioToWhisper(blob);
        };
        state.mediaRecorder.start();
        setListeningState(true);
    } catch (err) {
        alert("Microphone permission denied or microphone not found.");
        console.error(err);
    }
}

function stopListening() {
    clearTimeout(speechDebounceTimer);
    if (!state.isListening) return;

    if (state.recognition) {
        try { state.recognition.stop(); } catch (e) {}
    }
    if (state.mediaRecorder && state.mediaRecorder.state !== "inactive") {
        state.mediaRecorder.stop();
    }
    setListeningState(false);
}

function setListeningState(isListening) {
    state.isListening = isListening;
    if (isListening) {
        el.micOrbContainer.classList.add("listening");
        el.micStatusBadge.textContent = "Listening...";
        el.micStatusBadge.className = "badge badge-success";
        el.micStateLabel.textContent = "Listening... Speak in English or हिन्दी";
        el.startListeningBtn.disabled = true;
        el.stopListeningBtn.disabled = false;
    } else {
        el.micOrbContainer.classList.remove("listening");
        el.micStatusBadge.textContent = state.isProcessing ? "Thinking..." : "Ready";
        el.micStatusBadge.className = state.isProcessing ? "badge badge-info" : "badge";
        el.micStateLabel.textContent = state.isProcessing ? "Processing response..." : "Click to Start Listening";
        el.startListeningBtn.disabled = state.isProcessing;
        el.stopListeningBtn.disabled = true;
    }
}

async function sendAudioToWhisper(blob) {
    if (state.isProcessing) return;
    el.micStateLabel.textContent = "Transcribing with Faster-Whisper...";
    const formData = new FormData();
    formData.append("audio_file", blob, "speech.wav");

    try {
        const res = await fetch(`${API_BASE}/api/voice/transcribe`, {
            method: "POST",
            body: formData
        });
        const data = await res.json();
        if (data.text) {
            await processUserQuery(data.text);
        } else {
            el.micStateLabel.textContent = "No speech detected. Click to try again.";
        }
    } catch (err) {
        console.error("Whisper error:", err);
        el.micStateLabel.textContent = "Transcription error.";
    }
}

// ── User Query & AI Conversation Flow ──────────────────────────────────

async function handleManualTextSend() {
    const text = el.manualTextInput.value.trim();
    if (!text) return;
    el.manualTextInput.value = "";
    await processUserQuery(text);
}

async function processUserQuery(userText) {
    if (!userText || !userText.trim()) return;
    if (state.isProcessing) {
        console.warn("Already processing query, skipping:", userText);
        return;
    }
    state.isProcessing = true;
    stopListening();

    const empty = el.conversationStream.querySelector(".empty-state");
    if (empty) empty.remove();

    // 1. Append User Bubble
    appendChatBubble("user", userText);

    // 2. Show AI Thinking Bubble
    const thinkingId = "thinking_" + Date.now();
    appendChatBubble("ai", '<i class="fas fa-circle-notch fa-spin"></i> Thinking...', thinkingId);

    try {
        const res = await fetch(`${API_BASE}/api/ai/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                prompt: userText,
                provider: state.provider,
                model: state.model,
                language: state.language
            })
        });

        const thinkingBubble = document.getElementById(thinkingId);

        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            const errMsg = errData.detail || `Server returned HTTP ${res.status}`;
            if (thinkingBubble) {
                thinkingBubble.innerHTML = `<span style="color:#ef4444;"><i class="fas fa-triangle-exclamation"></i> Error: ${errMsg}</span>`;
            }
            return;
        }

        const data = await res.json();
        if (thinkingBubble) thinkingBubble.remove();

        // 3. Append Real AI Response
        appendChatBubble("ai", data.response, null, data.audio_base64, data.audio_format);

        // 4. Play Audio Response through laptop speakers
        if (data.audio_base64) {
            state.lastAudioBase64 = data.audio_base64;
            state.lastAudioFormat = data.audio_format || "wav";
            playBase64Audio(data.audio_base64, state.lastAudioFormat);
        }
    } catch (err) {
        console.error("AI chat error:", err);
        const thinkingBubble = document.getElementById(thinkingId);
        if (thinkingBubble) {
            thinkingBubble.innerHTML = `<span style="color:#ef4444;"><i class="fas fa-triangle-exclamation"></i> Connection Error: ${err.message || 'Could not connect to AI service. Please ensure Ollama is running.'}</span>`;
        }
    } finally {
        state.isProcessing = false;
        setListeningState(false);
    }
}

function appendChatBubble(role, content, id = null, audioB64 = null, audioFormat = "wav") {
    const bubble = document.createElement("div");
    bubble.className = `chat-bubble ${role}`;
    if (id) bubble.id = id;

    const roleName = role === "user" ? "You" : `VoiceAI (${state.provider.toUpperCase()} - ${state.model})`;
    const meta = document.createElement("div");
    meta.className = "chat-meta";
    meta.innerHTML = `<strong>${roleName}</strong> • ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
    bubble.appendChild(meta);

    const textDiv = document.createElement("div");
    textDiv.innerHTML = content;
    bubble.appendChild(textDiv);

    if (role === "ai" && audioB64) {
        const audioBtn = document.createElement("button");
        audioBtn.className = "play-bubble-audio-btn";
        audioBtn.innerHTML = '<i class="fas fa-volume-high"></i> Play';
        audioBtn.onclick = () => playBase64Audio(audioB64, audioFormat);
        bubble.appendChild(audioBtn);
    }

    el.conversationStream.appendChild(bubble);
    el.conversationStream.scrollTop = el.conversationStream.scrollHeight;
}

function playBase64Audio(base64Data, format = "wav") {
    try {
        const mime = format === "mp3" ? "audio/mp3" : "audio/wav";
        el.ttsAudioPlayer.src = `data:${mime};base64,${base64Data}`;
        el.ttsAudioPlayer.play().catch(e => console.warn("Auto-play blocked by browser policy:", e));
    } catch (e) {
        console.error("Audio playback error:", e);
    }
}

// ── Call Recording, File Storage & Summarization ──────────────────────

function initCallSummarizer() {
    el.startCallBtn.addEventListener("click", startCall);
    el.endCallBtn.addEventListener("click", endCall);
    el.generateSummaryBtn.addEventListener("click", generateSummary);

    // Save Transcript Button
    el.saveTranscriptBtn.addEventListener("click", async () => {
        const text = el.callTranscriptTextarea.value.trim();
        if (!text) {
            alert("Please type or record a transcript first.");
            return;
        }
        await saveCurrentTranscriptToFile(text);
    });

    // Character counter
    el.callTranscriptTextarea.addEventListener("input", updateCharCount);

    // Saved call selector
    el.savedCallsSelect.addEventListener("change", async (e) => {
        const callId = e.target.value;
        if (!callId) return;
        await loadSpecificCall(callId);
    });

    // Downloads
    el.downloadTranscriptBtn.addEventListener("click", () => {
        if (state.currentCallId) {
            window.open(`${API_BASE}/api/call/download/${state.currentCallId}/transcript`);
        } else {
            // Download directly from textarea
            downloadTextAsFile(el.callTranscriptTextarea.value, "call_transcript.txt");
        }
    });

    el.downloadSummaryBtn.addEventListener("click", () => {
        if (state.currentCallId) {
            window.open(`${API_BASE}/api/call/download/${state.currentCallId}/summary`);
        } else {
            downloadTextAsFile(el.callSummaryBody.textContent, "call_summary.txt");
        }
    });
}

function updateCharCount() {
    const len = el.callTranscriptTextarea.value.length;
    el.charCountDisplay.textContent = `${len} characters`;
}

async function startCall() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        state.callAudioChunks = [];
        state.callMediaRecorder = new MediaRecorder(stream);
        state.callMediaRecorder.ondataavailable = (e) => state.callAudioChunks.push(e.data);

        state.callMediaRecorder.start();
        state.isCallActive = true;
        state.callStartTime = Date.now();

        el.callActionCard.classList.add("recording");
        el.callRecStatusText.textContent = "Call in Progress (Recording Microphone)";
        el.startCallBtn.disabled = true;
        el.endCallBtn.disabled = false;

        // Reset summary display, but keep Generate Summary button visible!
        el.callTranscriptTextarea.value = "Recording live call audio from microphone... Speak now.";
        updateCharCount();

        el.callSummaryBody.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-clipboard-question"></i>
                <p>Summary will appear here <strong>only</strong> after you click <strong>Generate Summary</strong>.</p>
                <span>(1. Short Overview • 2. Discussion Points • 3. Decisions • 4. Action Items • 5. Follow-ups)</span>
            </div>
        `;
        el.downloadTranscriptBtn.disabled = true;
        el.downloadSummaryBtn.disabled = true;

        // Timer
        state.callTimerInterval = setInterval(() => {
            const elapsed = Math.floor((Date.now() - state.callStartTime) / 1000);
            const m = String(Math.floor(elapsed / 60)).padStart(2, "0");
            const s = String(elapsed % 60).padStart(2, "0");
            el.callTimerDisplay.textContent = `${m}:${s}`;
        }, 1000);

    } catch (err) {
        alert("Microphone permission required to record calls.");
        console.error(err);
    }
}

async function endCall() {
    if (!state.isCallActive) return;

    clearInterval(state.callTimerInterval);
    state.isCallActive = false;
    const durationSec = Math.floor((Date.now() - state.callStartTime) / 1000);

    el.callActionCard.classList.remove("recording");
    el.callRecStatusText.textContent = "Call Ended. Processing & saving transcript file...";
    el.startCallBtn.disabled = false;
    el.endCallBtn.disabled = true;

    state.callMediaRecorder.onstop = async () => {
        const blob = new Blob(state.callAudioChunks, { type: "audio/wav" });
        await finishCallProcessing(blob, durationSec);
    };
    state.callMediaRecorder.stop();
}

async function finishCallProcessing(audioBlob, durationSec) {
    el.callTranscriptTextarea.value = "Transcribing call with Faster-Whisper and saving file to disk...";
    updateCharCount();

    const formData = new FormData();
    formData.append("audio_file", audioBlob, "call_recording.wav");
    formData.append("duration", durationSec);
    formData.append("language", state.language);

    try {
        const res = await fetch(`${API_BASE}/api/call/end`, {
            method: "POST",
            body: formData
        });
        const data = await res.json();

        state.currentCallId = data.call_id;
        const transcriptText = data.transcript || "Call ended. (No audible speech detected).";

        // Automatically put the call data text into Call Summarization
        el.callTranscriptTextarea.value = transcriptText;
        updateCharCount();
        el.downloadTranscriptBtn.disabled = false;
        el.callRecStatusText.textContent = `Call saved to ${data.call_id}_transcript.txt. Click 'Generate Summary' when ready.`;

        // Reload the saved calls dropdown
        await loadSavedCallsList();
        el.savedCallsSelect.value = state.currentCallId;

    } catch (err) {
        console.error("Call end error:", err);
        el.callTranscriptTextarea.value = "Error processing call transcript. You can manually type or paste notes here.";
    }
}

async function saveCurrentTranscriptToFile(text) {
    el.saveTranscriptBtn.disabled = true;
    el.saveTranscriptBtn.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> Saving...';

    try {
        const res = await fetch(`${API_BASE}/api/call/save`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                transcript: text,
                language: state.language
            })
        });
        const data = await res.json();
        state.currentCallId = data.call_id;
        el.downloadTranscriptBtn.disabled = false;
        el.saveTranscriptBtn.innerHTML = '<i class="fas fa-check"></i> Saved!';
        await loadSavedCallsList();
        el.savedCallsSelect.value = data.call_id;
        setTimeout(() => {
            el.saveTranscriptBtn.disabled = false;
            el.saveTranscriptBtn.innerHTML = '<i class="fas fa-floppy-disk"></i> Save File';
        }, 2000);
    } catch (err) {
        console.error("Save error:", err);
        el.saveTranscriptBtn.disabled = false;
        el.saveTranscriptBtn.innerHTML = '<i class="fas fa-floppy-disk"></i> Save File';
        alert("Error saving transcript file to disk.");
    }
}

async function loadSavedCallsList() {
    try {
        const res = await fetch(`${API_BASE}/api/call/list`);
        if (res.ok) {
            const data = await res.json();
            const calls = data.calls || [];
            el.savedCallsSelect.innerHTML = '<option value="">-- Select a saved call text file --</option>';
            calls.forEach(c => {
                const opt = document.createElement("option");
                opt.value = c.call_id;
                opt.textContent = `${c.call_id} (${c.timestamp}) - ${c.preview}`;
                el.savedCallsSelect.appendChild(opt);
            });
        }
    } catch (e) {
        console.warn("Could not load saved calls list:", e);
    }
}

async function loadSpecificCall(callId) {
    try {
        const res = await fetch(`${API_BASE}/api/call/load/${callId}`);
        if (res.ok) {
            const data = await res.json();
            state.currentCallId = data.call_id;
            el.callTranscriptTextarea.value = data.transcript;
            updateCharCount();
            el.downloadTranscriptBtn.disabled = false;

            if (data.summary) {
                el.callSummaryBody.textContent = data.summary;
                el.downloadSummaryBtn.disabled = false;
            } else {
                el.callSummaryBody.innerHTML = `
                    <div class="empty-state">
                        <i class="fas fa-clipboard-question"></i>
                        <p>Summary not generated yet for this call. Click <strong>Generate Summary</strong> above.</p>
                    </div>
                `;
                el.downloadSummaryBtn.disabled = true;
            }
        }
    } catch (e) {
        console.error("Error loading call:", e);
    }
}

async function generateSummary() {
    const transcriptText = el.callTranscriptTextarea.value.trim();
    if (!transcriptText || transcriptText.startsWith("Recording live") || transcriptText.startsWith("Transcribing call")) {
        alert("Please ensure there is a valid call transcript before generating summary.");
        return;
    }

    el.generateSummaryBtn.disabled = true;
    el.generateSummaryBtn.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> Generating Summary...';
    el.callSummaryBody.innerHTML = `
        <div class="empty-state">
            <i class="fas fa-wand-magic-sparkles fa-spin"></i>
            <p>Analyzing discussion points, decisions, action items, and follow-ups...</p>
        </div>
    `;

    try {
        const res = await fetch(`${API_BASE}/api/call/summarize`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                call_id: state.currentCallId,
                transcript: transcriptText,
                provider: state.provider,
                model: state.model,
                language: state.language
            })
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || "Summary generation failed");
        }

        const data = await res.json();
        state.currentCallId = data.call_id;
        el.callSummaryBody.textContent = data.summary;
        el.downloadSummaryBtn.disabled = false;

        el.generateSummaryBtn.disabled = false;
        el.generateSummaryBtn.innerHTML = '<i class="fas fa-check"></i> Summary Generated';
        setTimeout(() => {
            el.generateSummaryBtn.innerHTML = '<i class="fas fa-wand-magic-sparkles"></i> Regenerate Summary';
        }, 3000);

        await loadSavedCallsList();
    } catch (err) {
        console.error("Summary error:", err);
        el.callSummaryBody.textContent = "Error generating call summary. " + err.message;
        el.generateSummaryBtn.disabled = false;
        el.generateSummaryBtn.innerHTML = '<i class="fas fa-wand-magic-sparkles"></i> Try Again';
    }
}

function downloadTextAsFile(content, filename) {
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}
