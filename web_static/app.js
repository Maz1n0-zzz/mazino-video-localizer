const ICONS = {
  video: '<path d="M15 10l4.55-2.27A1 1 0 0 1 21 8.6v6.8a1 1 0 0 1-1.45.87L15 14"/><rect x="3" y="6" width="12" height="12" rx="2"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
  trend: '<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 12 15 16 10"/>',
  download: '<path d="M8 17l4 4 4-4"/><path d="M12 12v9"/><path d="M20.88 18.09A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.29"/>',
  globe: '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
  headphones: '<path d="M3 18v-6a9 9 0 0 1 18 0v6"/><path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z"/>',
  gauge: '<path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z"/><path d="M12 12l4-4"/><circle cx="12" cy="12" r="1.5"/>',
  heart: '<path d="M20.8 4.6c-1.8-1.8-4.7-1.8-6.5 0L12 6.9l-2.3-2.3c-1.8-1.8-4.7-1.8-6.5 0-1.8 1.8-1.8 4.7 0 6.5L12 20.3l8.8-8.8c1.8-1.8 1.8-4.8 0-6.9z"/>',
  play: '<polygon points="5 3 19 12 5 21 5 3"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>',
  cloud: '<path d="M8 17l4 4 4-4"/><path d="M12 12v9"/><path d="M20.88 18.09A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.29"/>',
  clapper: '<path d="M20 6H4a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2z"/><path d="M2 8l3-4h3l-3 4M8 8l3-4h3l-3 4M14 8l3-4h3l-3 4"/>',
};

function svg(name, vb = "0 0 24 24") {
  return `<svg viewBox="${vb}">${ICONS[name]}</svg>`;
}

function setIcon(id, name) {
  document.getElementById(id).innerHTML = svg(name);
}

setIcon("icon-video-header", "video");
setIcon("icon-video-1", "video");
setIcon("icon-settings", "settings");
setIcon("icon-trend", "trend");
setIcon("icon-shield", "shield");
setIcon("icon-download", "download");
setIcon("icon-globe-1", "globe");
setIcon("icon-globe-2", "globe");
setIcon("icon-headphones", "headphones");
setIcon("icon-gauge", "gauge");
setIcon("icon-heart", "heart");
setIcon("icon-play", "play");
setIcon("icon-upload", "upload");
setIcon("icon-cloud", "cloud");
setIcon("icon-clapper", "clapper");

const els = {
  sourceLang: document.getElementById("source_lang"),
  targetLang: document.getElementById("target_lang"),
  voiceRole: document.getElementById("voice_role"),
  modelName: document.getElementById("model_name"),
  inpaintMode: document.getElementById("inpaint_mode"),
  fileInput: document.getElementById("file-input"),
  uploadBtn: document.getElementById("upload-btn"),
  dropzone: document.getElementById("dropzone"),
  dropzoneEmpty: document.getElementById("dropzone-empty"),
  previewVideo: document.getElementById("preview-video"),
  runBtn: document.getElementById("run-btn"),
  logBox: document.getElementById("log-box"),
  resultBox: document.getElementById("result-box"),
  resultVideo: document.getElementById("result-video"),
  downloadBox: document.getElementById("download-box"),
  downloadText: document.getElementById("download-text"),
  downloadLink: document.getElementById("download-link"),
  saveDefaultLink: document.getElementById("save-default-link"),
  cancelVideoBtn: document.getElementById("cancel-video-btn"),
};

let selectedFile = null;
let cfgCache = null;

function fillSelect(select, options, value) {
  select.innerHTML = "";
  options.forEach((opt) => {
    const [v, label] = Array.isArray(opt) ? opt : [opt, opt];
    const o = document.createElement("option");
    o.value = v;
    o.textContent = label;
    if (v === value) o.selected = true;
    select.appendChild(o);
  });
}

async function loadConfig() {
  const res = await fetch("/api/config");
  const data = await res.json();
  cfgCache = data.config;
  fillSelect(els.sourceLang, data.lang_choices, data.config.source_lang);
  fillSelect(els.targetLang, data.lang_choices, data.config.target_lang);
  fillSelect(els.modelName, data.model_choices, data.config.model_name);
  fillSelect(els.inpaintMode, data.inpaint_choices, data.config.inpaint_mode);
  fillSelect(els.voiceRole, data.voices, data.config.voice_role);
}
loadConfig();

els.targetLang.addEventListener("change", async () => {
  const res = await fetch(`/api/voices?lang=${encodeURIComponent(els.targetLang.value)}`);
  const data = await res.json();
  fillSelect(els.voiceRole, data.voices, data.voices[0]);
});

function showPreview(file) {
  selectedFile = file;
  els.dropzoneEmpty.style.display = "none";
  els.previewVideo.style.display = "block";
  els.previewVideo.src = URL.createObjectURL(file);
  els.cancelVideoBtn.style.display = "flex";
}

function clearPreview() {
  selectedFile = null;
  els.fileInput.value = "";
  if (els.previewVideo.src) URL.revokeObjectURL(els.previewVideo.src);
  els.previewVideo.pause();
  els.previewVideo.removeAttribute("src");
  els.previewVideo.load();
  els.previewVideo.style.display = "none";
  els.cancelVideoBtn.style.display = "none";
  els.dropzoneEmpty.style.display = "block";
}

els.uploadBtn.addEventListener("click", () => els.fileInput.click());
els.fileInput.addEventListener("change", () => {
  if (els.fileInput.files[0]) showPreview(els.fileInput.files[0]);
});
els.cancelVideoBtn.addEventListener("click", (e) => {
  e.preventDefault();
  e.stopPropagation();
  clearPreview();
});
els.dropzone.addEventListener("dragover", (e) => { e.preventDefault(); els.dropzone.classList.add("drag-over"); });
els.dropzone.addEventListener("dragleave", () => els.dropzone.classList.remove("drag-over"));
els.dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  els.dropzone.classList.remove("drag-over");
  if (e.dataTransfer.files[0]) showPreview(e.dataTransfer.files[0]);
});

function appendLog(line) {
  if (els.logBox.textContent.startsWith("Chưa chạy")) els.logBox.textContent = "";
  els.logBox.textContent += (els.logBox.textContent ? "\n" : "") + line;
  els.logBox.scrollTop = els.logBox.scrollHeight;
}

function setRunning(isRunning) {
  els.runBtn.disabled = isRunning;
  els.cancelVideoBtn.disabled = isRunning;
}

els.runBtn.addEventListener("click", async () => {
  if (!selectedFile) {
    appendLog("Chưa chọn video đầu vào.");
    return;
  }
  setRunning(true);
  els.logBox.textContent = "";
  appendLog("Đang tải video lên...");

  const form = new FormData();
  form.append("video", selectedFile);
  form.append("source_lang", els.sourceLang.value);
  form.append("target_lang", els.targetLang.value);
  form.append("model_name", els.modelName.value);
  form.append("voice_role", els.voiceRole.value);
  form.append("inpaint_mode", els.inpaintMode.value);

  try {
    const res = await fetch("/api/run", { method: "POST", body: form });
    const { job_id } = await res.json();
    const es = new EventSource(`/api/progress/${job_id}`);
    es.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.log) appendLog(data.log);
    };
    es.addEventListener("done", (e) => {
      const data = JSON.parse(e.data);
      setRunning(false);
      if (data.result) {
        els.resultBox.style.display = "none";
        els.resultVideo.style.display = "block";
        els.resultVideo.src = `/outputs/${data.result}`;
        els.downloadText.style.display = "none";
        els.downloadLink.style.display = "inline-block";
        els.downloadLink.href = `/outputs/${data.result}`;
        els.downloadLink.download = data.result;
      }
      es.close();
    });
    es.addEventListener("error", () => {
      setRunning(false);
      es.close();
    });
  } catch (err) {
    appendLog(`[LỖI] ${err}`);
    setRunning(false);
  }
});

els.saveDefaultLink.addEventListener("click", async (e) => {
  e.preventDefault();
  const payload = {
    source_lang: els.sourceLang.value,
    target_lang: els.targetLang.value,
    model_name: els.modelName.value,
    voice_role: els.voiceRole.value,
    inpaint_mode: els.inpaintMode.value,
  };
  await fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  appendLog(`✓ Đã lưu làm mặc định: ${payload.source_lang} → ${payload.target_lang}, model=${payload.model_name}, voice=${payload.voice_role}, inpaint=${payload.inpaint_mode}`);
});
