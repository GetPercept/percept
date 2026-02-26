/**
 * Percept Audio Capture — Background Service Worker (MV3)
 * 
 * Uses chrome.tabCapture to grab tab audio, processes to PCM16 via
 * an offscreen document, and streams to the Percept receiver.
 */

const PERCEPT_URL = "http://127.0.0.1:8900";
const SAMPLE_RATE = 16000;
const CHUNK_MS = 3000;

let activeCaptures = new Map(); // tabId -> { streamId, sessionId }

// Listen for messages from popup
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === "startCapture") {
    startCapture(msg.tabId).then(sendResponse);
    return true; // async
  }
  if (msg.action === "stopCapture") {
    stopCapture(msg.tabId).then(sendResponse);
    return true;
  }
  if (msg.action === "getStatus") {
    sendResponse({
      active: Array.from(activeCaptures.entries()).map(([tabId, info]) => ({
        tabId,
        sessionId: info.sessionId,
      })),
    });
    return false;
  }
});

async function startCapture(tabId) {
  if (activeCaptures.has(tabId)) {
    return { status: "already_capturing", sessionId: activeCaptures.get(tabId).sessionId };
  }

  try {
    // Get a MediaStream ID for this tab
    const streamId = await new Promise((resolve, reject) => {
      chrome.tabCapture.getMediaStreamId({ targetTabId: tabId }, (id) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
        } else {
          resolve(id);
        }
      });
    });

    const sessionId = `browser_${Date.now()}_${tabId}`;

    // Get tab info for metadata
    const tab = await chrome.tabs.get(tabId);

    // Ensure offscreen document exists for audio processing
    await ensureOffscreen();

    // Send to offscreen doc for MediaRecorder processing
    chrome.runtime.sendMessage({
      action: "offscreen_startCapture",
      streamId,
      sessionId,
      tabUrl: tab.url || "",
      tabTitle: tab.title || "",
      perceptUrl: PERCEPT_URL,
      sampleRate: SAMPLE_RATE,
      chunkMs: CHUNK_MS,
    });

    activeCaptures.set(tabId, { streamId, sessionId });

    // Update badge
    chrome.action.setBadgeText({ text: "🎙️" });
    chrome.action.setBadgeBackgroundColor({ color: "#e74c3c" });

    return { status: "capturing", sessionId, tabTitle: tab.title };
  } catch (err) {
    return { status: "error", error: err.message };
  }
}

async function stopCapture(tabId) {
  const info = activeCaptures.get(tabId);
  if (!info) {
    return { status: "not_capturing" };
  }

  chrome.runtime.sendMessage({
    action: "offscreen_stopCapture",
    sessionId: info.sessionId,
  });

  activeCaptures.delete(tabId);

  if (activeCaptures.size === 0) {
    chrome.action.setBadgeText({ text: "" });
  }

  return { status: "stopped", sessionId: info.sessionId };
}

async function ensureOffscreen() {
  const existing = await chrome.offscreen.hasDocument();
  if (!existing) {
    await chrome.offscreen.createDocument({
      url: "offscreen.html",
      reasons: ["USER_MEDIA"],
      justification: "Audio processing for tab capture",
    });
  }
}

// Clean up when tabs close
chrome.tabs.onRemoved.addListener((tabId) => {
  if (activeCaptures.has(tabId)) {
    stopCapture(tabId);
  }
});
