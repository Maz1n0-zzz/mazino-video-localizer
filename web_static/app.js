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
  caption: '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M7 12h4M7 15h2M14 12h3M14 15h3"/>',
  mic: '<path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/>',
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
setIcon("icon-caption", "caption");
setIcon("icon-mic", "mic");

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
  subtitleBottomPct: document.getElementById("subtitle_bottom_pct"),
  modeSubBtn: document.getElementById("mode-sub-btn"),
  modeLogoBtn: document.getElementById("mode-logo-btn"),
  ttsEngine: document.getElementById("tts_engine"),
  rowVoiceRole: document.getElementById("row-voice-role"),
  voiceRoleLabel: document.getElementById("voice-role-label"),
  clonePanel: document.getElementById("clone-panel"),
  elPanel: document.getElementById("el-panel"),
  elApiKey: document.getElementById("el-api-key"),
  elVoiceId: document.getElementById("el-voice-id"),
  elModel: document.getElementById("el-model"),
  addCloneBtn: document.getElementById("add-clone-btn"),
  delCloneBtn: document.getElementById("del-clone-btn"),
  addCloneForm: document.getElementById("add-clone-form"),
  newCloneName: document.getElementById("new-clone-name"),
  newCloneFileBtn: document.getElementById("new-clone-file-btn"),
  newCloneFile: document.getElementById("new-clone-file"),
  newCloneFileName: document.getElementById("new-clone-file-name"),
  saveCloneBtn: document.getElementById("save-clone-btn"),
  cloneSaveStatus: document.getElementById("clone-save-status"),
  regionPanel: document.getElementById("region-panel"),
  regionStartBtn: document.getElementById("region-start-btn"),
  regionCount: document.getElementById("region-count"),
  regionEditor: document.getElementById("region-editor"),
  regionCanvas: document.getElementById("region-canvas"),
  regionUndoBtn: document.getElementById("region-undo-btn"),
  regionClearBtn: document.getElementById("region-clear-btn"),
  regionDoneBtn: document.getElementById("region-done-btn"),
};

let selectedFile = null;
let cfgCache = null;
let cloneVoices = [];
let newCloneFileObj = null;
let edgeVoices = [];

// ---- Chuyển đổi Edge-TTS <-> Clone giọng ----
function updateTtsEngine() {
  const eng = els.ttsEngine.value;
  const isClone = eng === "f5clone";
  const isEl = eng === "elevenlabs";
  els.clonePanel.style.display = isClone ? "block" : "none";
  els.elPanel.style.display = isEl ? "block" : "none";
  els.rowVoiceRole.style.display = isEl ? "none" : "";  // EL dùng Voice ID, ẩn dropdown giọng
  els.voiceRoleLabel.textContent = isClone ? "Giọng clone (đã lưu)" : "Giọng đọc (Edge-TTS)";
  if (isEl) return;
  if (isClone) {
    if (cloneVoices.length) {
      fillSelect(els.voiceRole, cloneVoices, cloneVoices[0]);
    } else {
      els.voiceRole.innerHTML = '<option value="">(chưa có giọng — bấm "Thêm giọng clone mới")</option>';
    }
  } else {
    fillSelect(els.voiceRole, edgeVoices, edgeVoices[0]);
  }
}
els.ttsEngine.addEventListener("change", updateTtsEngine);

// Nhớ thông tin ElevenLabs trong trình duyệt (khỏi nhập lại mỗi lần)
["elApiKey", "elVoiceId", "elModel"].forEach((k) => {
  const el = els[k], sk = "mvl_" + k;
  const saved = localStorage.getItem(sk);
  if (saved != null) el.value = saved;
  const save = () => localStorage.setItem(sk, el.value);
  el.addEventListener("change", save);
  el.addEventListener("input", save);
});

els.addCloneBtn.addEventListener("click", () => {
  els.addCloneForm.style.display = els.addCloneForm.style.display === "none" ? "block" : "none";
});
els.newCloneFileBtn.addEventListener("click", () => els.newCloneFile.click());
els.newCloneFile.addEventListener("change", () => {
  newCloneFileObj = els.newCloneFile.files[0] || null;
  els.newCloneFileName.textContent = newCloneFileObj ? `✓ ${newCloneFileObj.name}` : "";
});
els.saveCloneBtn.addEventListener("click", async () => {
  const name = (els.newCloneName.value || "").trim();
  if (!name) { els.cloneSaveStatus.textContent = "Chưa đặt tên"; return; }
  if (!newCloneFileObj) { els.cloneSaveStatus.textContent = "Chưa chọn file"; return; }
  els.cloneSaveStatus.textContent = "Đang lưu + nhận diện lời thoại...";
  els.saveCloneBtn.disabled = true;
  try {
    const fd = new FormData();
    fd.append("name", name);
    fd.append("ref_audio", newCloneFileObj);
    const res = await fetch("/api/clone-voices", { method: "POST", body: fd });
    const data = await res.json();
    if (data.error) { els.cloneSaveStatus.textContent = data.error; }
    else {
      cloneVoices = data.clone_voices || [];
      els.cloneSaveStatus.textContent = "✓ Đã lưu";
      els.newCloneName.value = "";
      newCloneFileObj = null;
      els.newCloneFileName.textContent = "";
      els.addCloneForm.style.display = "none";
      fillSelect(els.voiceRole, cloneVoices, name);
    }
  } catch (e) {
    els.cloneSaveStatus.textContent = "Lỗi: " + e;
  } finally {
    els.saveCloneBtn.disabled = false;
  }
});
els.delCloneBtn.addEventListener("click", async () => {
  const name = els.voiceRole.value;
  if (!name || els.ttsEngine.value !== "f5clone") return;
  if (!confirm(`Xoá giọng "${name}"?`)) return;
  const res = await fetch(`/api/clone-voices/${encodeURIComponent(name)}`, { method: "DELETE" });
  const data = await res.json();
  cloneVoices = data.clone_voices || [];
  updateTtsEngine();
});

// ---- Khoanh vùng xoá sub/logo (toạ độ theo PIXEL GỐC của video) ----
let subAreas = [];       // [{xmin,ymin,xmax,ymax}]
let regionFrame = null;  // canvas offscreen giữ frame đã chụp để vẽ lại
let drawing = false;
let dragStart = null;
let dragCur = null;
let regionType = "sub";  // 'sub' = che sub + đặt sub mới; 'logo' = chỉ blur

function setRegionType(t) {
  regionType = t;
  els.modeSubBtn.classList.toggle("ghost", t !== "sub");
  els.modeLogoBtn.classList.toggle("ghost", t !== "logo");
}

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
  edgeVoices = data.voices || [];
  cloneVoices = data.clone_voices || [];
  els.subtitleBottomPct.value = data.subtitle_bottom_pct ?? data.config.subtitle_bottom_pct ?? 15;
  updateTtsEngine();  // populate dropdown giọng đúng theo engine đang chọn
}
loadConfig();

els.targetLang.addEventListener("change", async () => {
  const res = await fetch(`/api/voices?lang=${encodeURIComponent(els.targetLang.value)}`);
  const data = await res.json();
  edgeVoices = data.voices || [];
  if (els.ttsEngine.value !== "f5clone") fillSelect(els.voiceRole, edgeVoices, edgeVoices[0]);
});

function showPreview(file) {
  selectedFile = file;
  els.dropzoneEmpty.style.display = "none";
  els.previewVideo.style.display = "block";
  els.previewVideo.src = URL.createObjectURL(file);
  els.cancelVideoBtn.style.display = "flex";
  // reset vùng đã chọn cho video mới
  resetRegions();
  els.regionPanel.style.display = "block";
  els.regionEditor.style.display = "none";
  els.regionStartBtn.style.display = "inline-block";
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
  els.regionPanel.style.display = "none";
  els.regionEditor.style.display = "none";
  resetRegions();
}

// ---------- Region editor ----------
function resetRegions() {
  subAreas = [];
  drawing = false;
  dragStart = dragCur = null;
  regionFrame = null;
  updateRegionCount();
}

function updateRegionCount() {
  const n = subAreas.length;
  els.regionCount.textContent = n
    ? `Đã chọn ${n} vùng — sẽ xoá các vùng này`
    : "Chưa chọn vùng — sẽ bỏ qua bước xoá sub/logo";
}

function canvasPt(e) {
  const rect = els.regionCanvas.getBoundingClientRect();
  const sx = els.regionCanvas.width / rect.width;
  const sy = els.regionCanvas.height / rect.height;
  let x = (e.clientX - rect.left) * sx;
  let y = (e.clientY - rect.top) * sy;
  x = Math.max(0, Math.min(x, els.regionCanvas.width));
  y = Math.max(0, Math.min(y, els.regionCanvas.height));
  return { x, y };
}

function redrawRegions(preview) {
  if (!regionFrame) return;
  const cv = els.regionCanvas;
  const ctx = cv.getContext("2d");
  ctx.drawImage(regionFrame, 0, 0);
  const lw = Math.max(2, Math.round(cv.width * 0.004));
  const drawBox = (b, stroke, fill) => {
    const x = Math.min(b.xmin, b.xmax), y = Math.min(b.ymin, b.ymax);
    const w = Math.abs(b.xmax - b.xmin), h = Math.abs(b.ymax - b.ymin);
    ctx.fillStyle = fill; ctx.fillRect(x, y, w, h);
    ctx.lineWidth = lw; ctx.strokeStyle = stroke; ctx.strokeRect(x, y, w, h);
  };
  subAreas.forEach((b) => b.type === "logo"
    ? drawBox(b, "#f59e0b", "rgba(245,158,11,0.22)")
    : drawBox(b, "#38bdf8", "rgba(56,189,248,0.22)"));
  if (preview) drawBox(preview, regionType === "logo" ? "#f59e0b" : "#38bdf8",
                       regionType === "logo" ? "rgba(245,158,11,0.28)" : "rgba(56,189,248,0.28)");
}

function enterRegionMode() {
  const v = els.previewVideo;
  if (!v.videoWidth || !v.videoHeight || v.readyState < 2) {
    appendLog("Video chưa nạp xong khung hình — đợi 1-2 giây rồi bấm lại.");
    return;
  }
  const cw = v.videoWidth, ch = v.videoHeight;
  regionFrame = document.createElement("canvas");
  regionFrame.width = cw; regionFrame.height = ch;
  regionFrame.getContext("2d").drawImage(v, 0, 0, cw, ch);
  els.regionCanvas.width = cw;
  els.regionCanvas.height = ch;
  redrawRegions();
  els.regionEditor.style.display = "block";
  els.regionStartBtn.style.display = "none";
  els.previewVideo.style.display = "none";
}

function exitRegionMode() {
  els.regionEditor.style.display = "none";
  els.previewVideo.style.display = "block";
  els.regionStartBtn.style.display = "inline-block";
  els.regionStartBtn.textContent = subAreas.length
    ? `✏️ Sửa vùng xoá (${subAreas.length})`
    : "✏️ Khoanh vùng xoá sub/logo cũ";
}

els.modeSubBtn.addEventListener("click", () => setRegionType("sub"));
els.modeLogoBtn.addEventListener("click", () => setRegionType("logo"));
els.regionStartBtn.addEventListener("click", enterRegionMode);
els.regionDoneBtn.addEventListener("click", exitRegionMode);
els.regionUndoBtn.addEventListener("click", () => { subAreas.pop(); redrawRegions(); updateRegionCount(); });
els.regionClearBtn.addEventListener("click", () => { subAreas = []; redrawRegions(); updateRegionCount(); });

els.regionCanvas.addEventListener("pointerdown", (e) => {
  e.preventDefault();
  drawing = true;
  try { els.regionCanvas.setPointerCapture(e.pointerId); } catch (_) {}
  dragStart = dragCur = canvasPt(e);
});
els.regionCanvas.addEventListener("pointermove", (e) => {
  if (!drawing) return;
  dragCur = canvasPt(e);
  redrawRegions({ xmin: dragStart.x, ymin: dragStart.y, xmax: dragCur.x, ymax: dragCur.y });
});
els.regionCanvas.addEventListener("pointerup", () => {
  if (!drawing) return;
  drawing = false;
  const b = {
    xmin: Math.round(Math.min(dragStart.x, dragCur.x)),
    ymin: Math.round(Math.min(dragStart.y, dragCur.y)),
    xmax: Math.round(Math.max(dragStart.x, dragCur.x)),
    ymax: Math.round(Math.max(dragStart.y, dragCur.y)),
  };
  if (b.xmax - b.xmin >= 4 && b.ymax - b.ymin >= 4) { b.type = regionType; subAreas.push(b); }
  dragStart = dragCur = null;
  redrawRegions();
  updateRegionCount();
});

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
  form.append("subtitle_bottom_pct", els.subtitleBottomPct.value || "15");
  // Khối CHE SUB to nhất (nếu có) -> nơi đặt sub mới. Các khối còn lại chỉ blur.
  const subBoxes = subAreas.filter((b) => b.type !== "logo");
  if (subBoxes.length) {
    const sb = subBoxes.reduce((a, b) =>
      (b.xmax - b.xmin) * (b.ymax - b.ymin) > (a.xmax - a.xmin) * (a.ymax - a.ymin) ? b : a);
    form.append("sub_box", JSON.stringify({ ymin: sb.ymin, ymax: sb.ymax, xmin: sb.xmin, xmax: sb.xmax }));
  }
  form.append("tts_engine", els.ttsEngine.value);
  if (els.ttsEngine.value === "f5clone" && !els.voiceRole.value) {
    appendLog('Bạn chọn Clone giọng nhưng chưa có giọng nào. Bấm "Thêm giọng clone mới" để tạo trước.');
    setRunning(false);
    return;
  }
  if (els.ttsEngine.value === "elevenlabs") {
    if (!els.elApiKey.value.trim() || !els.elVoiceId.value.trim()) {
      appendLog("Bạn chọn ElevenLabs nhưng chưa nhập API key hoặc Voice ID.");
      setRunning(false);
      return;
    }
    form.append("el_api_key", els.elApiKey.value.trim());
    form.append("el_voice_id", els.elVoiceId.value.trim());
    form.append("el_model", els.elModel.value);
  }
  // VSR nhận theo thứ tự ymin,ymax,xmin,xmax
  form.append("sub_areas", JSON.stringify(subAreas.map((b) => ({
    ymin: b.ymin, ymax: b.ymax, xmin: b.xmin, xmax: b.xmax,
  }))));
  if (!subAreas.length) {
    appendLog("(Chưa khoanh vùng xoá sub/logo — bước xoá sẽ được bỏ qua, giữ nguyên video gốc.)");
  }

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
    subtitle_bottom_pct: parseInt(els.subtitleBottomPct.value || "15", 10),
  };
  await fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  appendLog(`✓ Đã lưu làm mặc định: ${payload.source_lang} → ${payload.target_lang}, model=${payload.model_name}, voice=${payload.voice_role}, inpaint=${payload.inpaint_mode}, sub cách đáy=${payload.subtitle_bottom_pct}%`);
});
