const api = window.OneMediaApi;
const form = document.querySelector("#inspect-form");
const urlInput = document.querySelector("#url");
const statusBox = document.querySelector("#status");
const result = document.querySelector("#result");
const title = document.querySelector("#title");
const thumbnail = document.querySelector("#thumbnail");
const meta = document.querySelector("#meta");
const mode = document.querySelector("#mode");
const format = document.querySelector("#format");
const submitButton = document.querySelector("#scan-button");
const downloadButton = document.querySelector("#download");
const scanLoading = document.querySelector("#scan-loading");
const platformBadge = document.querySelector("#platform-badge");
const resolutionBadge = document.querySelector("#resolution-badge");
const durationBadge = document.querySelector("#duration-badge");
const creator = document.querySelector("#creator");
const fileSize = document.querySelector("#file-size");
const i18n = window.I18n;

let requestActive = false;
let activeRequestType = "";
let inspectedUrl = "";
let inspectedFormats = [];
let inspectedData = null;
let statusKey = "";
let statusTone = "";
let statusVariables = {};

function t(key, variables = {}) {
  return i18n.t(key, variables);
}

function setStatus(key, tone = "", variables = {}) {
  statusKey = key || "";
  statusTone = tone;
  statusVariables = variables;
  statusBox.textContent = key ? t(key, variables) : "";
  statusBox.className = `status-message${tone ? ` ${tone}` : ""}`;
  statusBox.hidden = !key;
}

function setRequestActive(active, type = "") {
  requestActive = active;
  activeRequestType = active ? type : "";
  submitButton.disabled = active;
  downloadButton.disabled = active;
  submitButton.classList.toggle("is-loading", active && type === "scan");
  downloadButton.classList.toggle("is-loading", active && type === "download");
  scanLoading.hidden = !(active && type === "scan");
  scanLoading.setAttribute("aria-hidden", String(!(active && type === "scan")));
  form.setAttribute("aria-busy", String(active && type === "scan"));
  downloadButton.setAttribute("aria-busy", String(active && type === "download"));

  const downloadLabel = downloadButton.querySelector(".button-label");
  if (downloadLabel) {
    downloadLabel.textContent = t(active && type === "download" ? "result.preparingDownload" : "result.download");
  }
}

function isPublicHttpUrl(value) {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

function sanitizeMediaUrl(value) {
  return value.trim().replace(/^\/+(https?:\/\/)/i, "$1");
}

function getKnownErrorKey(detail) {
  const keys = ["errors.story", "errors.privateContent", "errors.snapchatPrivate", "errors.snapchatUnsupported"];
  return keys.find((key) => detail === i18n.getSource(key)) || "";
}

async function readError(response, fallbackKey, responseData = null) {
  try {
    const data = responseData || await response.json();
    const knownError = getKnownErrorKey(data.detail);
    if (knownError) {
      return knownError;
    }
    if (response.status === 403) {
      return "errors.privateContent";
    }
    if (Array.isArray(data.detail)) {
      return "errors.invalidUrl";
    }
    if (response.status === 400) {
      return "errors.invalidUrl";
    }
    if (response.status === 422) {
      return fallbackKey;
    }
    return fallbackKey;
  } catch {
    return fallbackKey;
  }
}

async function isBackendAvailable() {
  const requestUrl = api.url("/api/health");
  try {
    const response = await fetch(requestUrl, {cache: "no-store"});
    if (!response.ok) {
      await api.logHttpError("API health request failed.", requestUrl, response);
      return false;
    }
    const data = await response.json();
    return data?.status === "ok";
  } catch (error) {
    api.logNetworkError("API health request failed.", requestUrl, error);
    return false;
  }
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return t("result.calculatedOnDownload");
  }
  const units = ["units.byte", "units.kilobyte", "units.megabyte", "units.gigabyte"];
  const unitIndex = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const amount = bytes / (1024 ** unitIndex);
  const precision = amount >= 10 || unitIndex === 0 ? 0 : 1;
  const localizedAmount = new Intl.NumberFormat(i18n.language, {
    minimumFractionDigits: precision,
    maximumFractionDigits: precision,
  }).format(amount);
  return `${localizedAmount} ${t(units[unitIndex])}`;
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) {
    return "--";
  }
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainingSeconds = total % 60;
  return hours
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(remainingSeconds).padStart(2, "0")}`
    : `${minutes}:${String(remainingSeconds).padStart(2, "0")}`;
}

function getResolution(item) {
  if (!item) {
    return t("result.bestAvailable");
  }
  if (item.height) {
    return t("result.resolutionValue", {value: item.height});
  }
  return item.resolution || item.extension?.toUpperCase() || t("result.bestAvailable");
}

function getSelectedFormat() {
  return inspectedFormats.find((item) => String(item.format_id) === format.value) || null;
}

function updateSelectedFormatMeta() {
  if (mode.value === "audio") {
    resolutionBadge.textContent = t("result.audio");
    fileSize.textContent = t("result.calculatedOnDownload");
    return;
  }
  if (mode.value === "image") {
    resolutionBadge.textContent = t("result.originalImage");
    fileSize.textContent = t("result.calculatedOnDownload");
    return;
  }

  const selected = getSelectedFormat();
  resolutionBadge.textContent = getResolution(selected);
  fileSize.textContent = formatBytes(selected?.filesize);
}

function updateFormatControl() {
  const acceptsFormat = mode.value === "video";
  format.disabled = !acceptsFormat;
  if (!acceptsFormat) {
    format.value = "";
  }
  updateSelectedFormatMeta();
}

function renderFormatOptions() {
  const selectedFormat = format.value;
  format.replaceChildren();
  const automaticOption = document.createElement("option");
  automaticOption.value = "";
  automaticOption.textContent = t("result.bestAvailableQuality");
  format.append(automaticOption);

  for (const item of inspectedFormats) {
    const option = document.createElement("option");
    const size = item.filesize ? ` · ${formatBytes(item.filesize)}` : "";
    const audio = item.has_audio ? ` · ${t("result.withAudio")}` : "";
    option.value = item.format_id;
    option.textContent = `${getResolution(item)} · ${(item.extension || t("result.format")).toUpperCase()}${audio}${size}`;
    format.append(option);
  }

  if ([...format.options].some((option) => option.value === selectedFormat)) {
    format.value = selectedFormat;
  }
}

function renderResultTranslations() {
  if (!inspectedData) {
    return;
  }

  const displayTitle = inspectedData.title || t("result.untitled");
  const displayPlatform = inspectedData.platform || t("result.publicMedia");
  title.textContent = displayTitle;
  platformBadge.textContent = displayPlatform;
  creator.textContent = inspectedData.uploader || t("result.publicCreator");
  thumbnail.alt = inspectedData.thumbnail ? t("result.thumbnailAlt", {title: displayTitle}) : "";
  meta.textContent = `${displayPlatform} · ${formatDuration(inspectedData.duration)} · ${inspectedData.media_kind || t("result.media")}`;
  renderFormatOptions();
  updateSelectedFormatMeta();
}

function populateResult(data, requestedUrl) {
  inspectedData = data;
  if (data.thumbnail) {
    thumbnail.src = data.thumbnail;
  } else {
    thumbnail.removeAttribute("src");
  }
  thumbnail.hidden = !data.thumbnail;
  durationBadge.textContent = formatDuration(data.duration);

  inspectedFormats = Array.isArray(data.formats) ? data.formats : [];
  inspectedUrl = requestedUrl;
  mode.value = data.media_kind === "image" ? "image" : "video";
  renderResultTranslations();
  updateFormatControl();
  result.hidden = false;
}

function refreshLocalizedState() {
  if (statusKey) {
    setStatus(statusKey, statusTone, statusVariables);
  }
  if (requestActive) {
    setRequestActive(true, activeRequestType);
  }
  renderResultTranslations();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (requestActive) {
    return;
  }

  const requestedUrl = sanitizeMediaUrl(urlInput.value);
  if (urlInput.value !== requestedUrl) {
    urlInput.value = requestedUrl;
  }
  if (!isPublicHttpUrl(requestedUrl)) {
    setStatus("errors.invalidUrl", "error");
    urlInput.focus();
    return;
  }

  result.hidden = true;
  inspectedUrl = "";
  inspectedFormats = [];
  inspectedData = null;
  setStatus(null);
  setRequestActive(true, "scan");

  const requestUrl = api.url("/api/inspect");
  try {
    const response = await fetch(requestUrl, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({url: requestedUrl}),
    });

    const errorResponse = response.clone();
    const data = await response.json();
    if (data?.success !== true) {
      await api.logHttpError("Inspect request failed.", requestUrl, errorResponse);
      setStatus(await readError(response, "errors.unsupportedUrl", data), "error");
      return;
    }

    populateResult(data, requestedUrl);
    setStatus(null);
  } catch (error) {
    api.logNetworkError("Inspect API request could not be completed.", requestUrl, error);
    setStatus(await isBackendAvailable() ? "errors.unsupportedUrl" : "errors.backendUnavailable", "error");
  } finally {
    setRequestActive(false);
  }
});

downloadButton.addEventListener("click", async (event) => {
  event.preventDefault();
  if (requestActive) {
    return;
  }
  if (!inspectedUrl) {
    setStatus("errors.scanFirst", "error");
    return;
  }

  setStatus("status.preparingFile");
  setRequestActive(true, "download");

  try {
    await window.OneMediaDownloads.enqueue(
      {
        url: inspectedUrl,
        mode: mode.value,
        format_id: mode.value === "video" ? format.value || null : null,
      },
      inspectedData,
    );
    setStatus("status.addedToQueue", "success");
  } catch (error) {
    console.error("[One Media] Download job request failed.", error);
    if (error.response) {
      setStatus(await readError(error.response, "errors.downloadFailure"), "error");
    } else if (error instanceof TypeError && !await isBackendAvailable()) {
      setStatus("errors.backendUnavailable", "error");
    } else {
      setStatus("errors.downloadFailure", "error");
    }
  } finally {
    setRequestActive(false);
  }
});

mode.addEventListener("change", updateFormatControl);
format.addEventListener("change", updateSelectedFormatMeta);

thumbnail.addEventListener("error", () => {
  thumbnail.hidden = true;
});

urlInput.addEventListener("input", () => {
  if (inspectedUrl && sanitizeMediaUrl(urlInput.value) !== inspectedUrl) {
    inspectedUrl = "";
    inspectedFormats = [];
    inspectedData = null;
    result.hidden = true;
    setStatus(null);
  }
});

window.addEventListener("languagechange", refreshLocalizedState);
window.addEventListener("downloadmanagercomplete", () => setStatus("status.downloadReady", "success"));
window.addEventListener("downloadmanagererror", () => setStatus("errors.downloadFailure", "error"));
