/**
 * Offscreen document for audio processing.
 * 
 * MV3 service workers can't access MediaStream APIs directly.
 * This offscreen doc handles the actual audio capture + PCM conversion.
 */

const activeSessions = new Map(); // sessionId -> { stream, audioCtx, processor, interval }

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.action === "offscreen_startCapture") {
    handleStartCapture(msg);
  }
  if (msg.action === "offscreen_stopCapture") {
    handleStopCapture(msg.sessionId);
  }
});

async function handleStartCapture({ streamId, sessionId, tabUrl, tabTitle, perceptUrl, sampleRate, chunkMs }) {
  try {
    // Use the stream ID from tabCapture to get the actual MediaStream
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        mandatory: {
          chromeMediaSource: "tab",
          chromeMediaSourceId: streamId,
        },
      },
    });

    const audioCtx = new AudioContext({ sampleRate: sampleRate || 16000 });
    const source = audioCtx.createMediaStreamSource(stream);
    
    // ScriptProcessor for PCM access (AudioWorklet would be cleaner but more complex)
    const processor = audioCtx.createScriptProcessor(4096, 1, 1);
    
    let audioBuffer = [];
    let chunkStartTime = Date.now();
    const targetChunkMs = chunkMs || 3000;
    
    processor.onaudioprocess = (e) => {
      const input = e.inputBuffer.getChannelData(0);
      // Float32 -> Int16
      const pcm16 = new Int16Array(input.length);
      for (let i = 0; i < input.length; i++) {
        const s = Math.max(-1, Math.min(1, input[i]));
        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
      }
      audioBuffer.push(pcm16);
      
      if (Date.now() - chunkStartTime >= targetChunkMs) {
        sendChunk(audioBuffer, sessionId, tabUrl, tabTitle, perceptUrl, sampleRate);
        audioBuffer = [];
        chunkStartTime = Date.now();
      }
    };
    
    source.connect(processor);
    processor.connect(audioCtx.destination); // Required for ScriptProcessor to fire
    
    activeSessions.set(sessionId, {
      stream, audioCtx, source, processor,
    });
    
    console.log(`[Percept] Capturing audio: ${tabTitle} (${sessionId})`);
  } catch (err) {
    console.error(`[Percept] Capture failed:`, err);
  }
}

function handleStopCapture(sessionId) {
  const session = activeSessions.get(sessionId);
  if (!session) return;
  
  try {
    session.processor.disconnect();
    session.source.disconnect();
    session.audioCtx.close();
    session.stream.getTracks().forEach(t => t.stop());
  } catch (e) {
    console.error("[Percept] Cleanup error:", e);
  }
  
  activeSessions.delete(sessionId);
  console.log(`[Percept] Stopped: ${sessionId}`);
}

function sendChunk(buffers, sessionId, tabUrl, tabTitle, perceptUrl, sampleRate) {
  // Merge all PCM16 arrays
  const totalLength = buffers.reduce((acc, arr) => acc + arr.length, 0);
  if (totalLength === 0) return;
  
  const merged = new Int16Array(totalLength);
  let offset = 0;
  for (const arr of buffers) {
    merged.set(arr, offset);
    offset += arr.length;
  }
  
  // Convert to base64
  const bytes = new Uint8Array(merged.buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  const b64 = btoa(binary);
  
  // POST to Percept receiver
  fetch(`${perceptUrl}/audio`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      sessionId,
      audio: b64,
      sampleRate: sampleRate || 16000,
      format: "pcm16",
      source: "browser_extension",
      tabUrl,
      tabTitle,
    }),
  }).catch(err => console.error("[Percept] Send error:", err));
}
