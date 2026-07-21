(() => {
  "use strict";

  const API = (window.ONE_MEDIA_API_BASE_URL || "").replace(/\/+$/, "");
  const HISTORY_KEY = "one-media-download-history";
  const HISTORY_LIMIT = 20;
  const queue = new Map();
  const streams = new Map();
  const queueElement = document.querySelector("#download-queue");
  const queueEmpty = document.querySelector("#queue-empty");
  const historyElement = document.querySelector("#download-history");
  const historyEmpty = document.querySelector("#history-empty");

  function t(key, variables = {}) {
    return window.I18n.t(key, variables);
  }

  function formatBytes(value, fallbackKey = "queue.unknownSize") {
    const bytes = Number(value);
    if (!Number.isFinite(bytes) || bytes <= 0) {
      return t(fallbackKey);
    }
    const units = ["units.byte", "units.kilobyte", "units.megabyte", "units.gigabyte"];
    const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    const amount = bytes / (1024 ** index);
    return `${new Intl.NumberFormat(window.I18n.language, {maximumFractionDigits: amount < 10 ? 1 : 0}).format(amount)} ${t(units[index])}`;
  }

  function formatEta(seconds) {
    if (!Number.isFinite(Number(seconds)) || Number(seconds) < 0) {
      return t("queue.calculating");
    }
    const value = Math.ceil(Number(seconds));
    if (value < 60) {
      return t("queue.secondsRemaining", {value});
    }
    return t("queue.minutesRemaining", {value: Math.ceil(value / 60)});
  }

  function platformId(value = "") {
    const platform = value.toLowerCase();
    return ["youtube", "tiktok", "instagram", "facebook", "snapchat", "pinterest", "reddit", "vimeo", "threads"]
      .find((name) => platform.includes(name)) || (platform.includes("twitter") ? "x" : "download");
  }

  function iconMarkup(platform) {
    return `<svg aria-hidden="true"><use href="#icon-${platformId(platform)}"></use></svg>`;
  }

  function readHistory() {
    try {
      const value = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
      return Array.isArray(value) ? value.slice(0, HISTORY_LIMIT) : [];
    } catch {
      return [];
    }
  }

  function writeHistory(items) {
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(items.slice(0, HISTORY_LIMIT)));
    } catch {
      return;
    }
  }

  function addHistory(item) {
    const items = readHistory().filter((entry) => entry.id !== item.id);
    items.unshift(item);
    writeHistory(items);
    renderHistory();
  }

  function removeHistory(id) {
    writeHistory(readHistory().filter((item) => item.id !== id));
    renderHistory();
  }

  function renderHistory() {
    if (!historyElement || !historyEmpty) {
      return;
    }
    const items = readHistory();
    historyEmpty.hidden = items.length > 0;
    historyElement.replaceChildren(...items.map((item) => {
      const card = document.createElement("article");
      card.className = "history-card";
      card.innerHTML = `
        <div class="history-thumb">${item.thumbnail ? `<img src="${escapeAttribute(item.thumbnail)}" alt="" />` : iconMarkup(item.platform)}</div>
        <div class="history-copy"><span class="history-platform">${escapeText(item.platform || t("result.publicMedia"))}</span><strong>${escapeText(item.title || t("result.untitled"))}</strong><time datetime="${new Date(item.completedAt).toISOString()}">${escapeText(new Intl.DateTimeFormat(window.I18n.language, {dateStyle: "medium", timeStyle: "short"}).format(item.completedAt))}</time></div>
        <div class="history-actions"><button type="button" class="history-download" data-history-download="${item.id}">${iconMarkup("download")}<span>${escapeText(t("history.downloadAgain"))}</span></button><button type="button" class="icon-action danger-action" data-history-remove="${item.id}" aria-label="${escapeAttribute(t("history.removeAria", {title: item.title || t("result.untitled")}))}"><svg aria-hidden="true"><use href="#icon-trash"></use></svg></button></div>`;
      return card;
    }));
  }

  function escapeText(value) {
    const node = document.createElement("span");
    node.textContent = String(value ?? "");
    return node.innerHTML;
  }

  function escapeAttribute(value) {
    return escapeText(value).replaceAll('"', "&quot;");
  }

  function renderQueueItem(item) {
    let card = queueElement?.querySelector(`[data-job-id="${item.jobId}"]`);
    if (!card) {
      card = document.createElement("article");
      card.className = "queue-card";
      card.dataset.jobId = item.jobId;
      queueElement?.prepend(card);
    }

    const percentage = Math.max(0, Math.min(100, Number(item.percentage) || 0));
    const terminal = ["completed", "failed", "canceled"].includes(item.status);
    card.dataset.status = item.status;
    card.innerHTML = `
      <div class="queue-thumbnail">${item.thumbnail ? `<img src="${escapeAttribute(item.thumbnail)}" alt="" />` : iconMarkup(item.platform)}<span class="queue-platform">${iconMarkup(item.platform)}</span></div>
      <div class="queue-content">
        <div class="queue-topline"><div><span class="queue-status">${escapeText(t(`queue.status.${item.status}`))}</span><h3>${escapeText(item.title || t("result.untitled"))}</h3></div><strong class="queue-percentage">${new Intl.NumberFormat(window.I18n.language, {maximumFractionDigits: 1}).format(percentage)}%</strong></div>
        <div class="queue-progress" role="progressbar" aria-label="${escapeAttribute(t("queue.progressAria", {title: item.title || t("result.untitled")}))}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${percentage}"><span style="--progress:${percentage}%"></span><i></i></div>
        <div class="queue-metrics"><span>${escapeText(formatBytes(item.downloadedBytes, "queue.zeroBytes"))} / ${escapeText(formatBytes(item.totalBytes))}</span><span>${escapeText(item.speed ? `${formatBytes(item.speed)}/${t("queue.secondShort")}` : t("queue.calculating"))}</span><span>${escapeText(formatEta(item.eta))}</span></div>
      </div>
      <div class="queue-actions">${!terminal ? `<button class="icon-action danger-action" type="button" data-cancel-job="${item.jobId}" aria-label="${escapeAttribute(t("queue.cancelAria", {title: item.title || t("result.untitled")}))}"><svg aria-hidden="true"><use href="#icon-x-circle"></use></svg></button>` : ""}${item.status === "failed" ? `<button class="queue-retry" type="button" data-retry-job="${item.jobId}"><svg aria-hidden="true"><use href="#icon-retry"></use></svg><span>${escapeText(t("queue.retry"))}</span></button>` : ""}</div>
      ${["queued", "preparing", "finishing"].includes(item.status) ? '<div class="queue-motion" aria-hidden="true"><i></i><i></i><i></i></div>' : ""}
      ${item.status === "completed" ? '<div class="queue-success" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="m6.5 12.5 3.5 3.5 7.5-8" /></svg></div>' : ""}`;
    queueEmpty.hidden = queue.size > 0;
  }

  function updateJob(jobId, progress) {
    const item = queue.get(jobId);
    if (!item) {
      return;
    }
    Object.assign(item, {
      status: progress.status,
      percentage: progress.percentage,
      downloadedBytes: progress.downloaded_bytes,
      totalBytes: progress.total_bytes,
      speed: progress.speed,
      eta: progress.eta,
      filename: progress.filename,
    });
    renderQueueItem(item);

    if (["completed", "failed", "canceled"].includes(item.status)) {
      streams.get(jobId)?.close();
      streams.delete(jobId);
    }
    if (item.status === "completed" && !item.retrieved) {
      item.retrieved = true;
      retrieveFile(item);
    }
  }

  function watch(jobId) {
    const stream = new EventSource(`${API}/api/downloads/${jobId}/events`);
    streams.set(jobId, stream);
    stream.onmessage = (event) => updateJob(jobId, JSON.parse(event.data));
    stream.onerror = async () => {
      if (!queue.has(jobId) || ["completed", "failed", "canceled"].includes(queue.get(jobId).status)) {
        stream.close();
        return;
      }
      try {
        const response = await fetch(`${API}/api/downloads/${jobId}`);
        if (response.ok) {
          updateJob(jobId, await response.json());
          return;
        }
      } catch (error) {
        console.error("[One Media] Download progress fallback request failed.", error);
        // The shared error event below provides the localized UI message.
      }
      console.error("[One Media] Download progress stream failed.", {jobId});
      stream.close();
      window.dispatchEvent(new CustomEvent("downloadmanagererror"));
    };
  }

  async function retrieveFile(item) {
    item.status = "finishing";
    renderQueueItem(item);
    try {
      const response = await fetch(`${API}/api/downloads/${item.jobId}/file`);
      if (!response.ok) {
        throw new Error("file retrieval failed");
      }
      const blob = await response.blob();
      if (!blob.size) {
        throw new Error("empty file");
      }
      const filename = getFilename(response.headers.get("content-disposition") || "", item.filename);
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = filename;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
      item.status = "completed";
      item.downloadedBytes = blob.size;
      item.totalBytes = blob.size;
      renderQueueItem(item);
      addHistory({id: crypto.randomUUID(), title: item.title, thumbnail: item.thumbnail, platform: item.platform, completedAt: Date.now(), request: item.request});
      window.dispatchEvent(new CustomEvent("downloadmanagercomplete"));
    } catch (error) {
      console.error("[One Media] Completed file request failed.", {jobId: item.jobId, error});
      item.status = "failed";
      renderQueueItem(item);
      window.dispatchEvent(new CustomEvent("downloadmanagererror"));
    }
  }

  function getFilename(disposition, fallback) {
    const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    if (encoded) {
      return decodeURIComponent(encoded[1]);
    }
    return disposition.match(/filename="?([^";]+)"?/i)?.[1] || fallback || t("download.fallbackFilename");
  }

  async function enqueue(request, media) {
    const response = await fetch(`${API}/api/downloads`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(request)});
    if (!response.ok) {
      const error = new Error("job creation failed");
      error.response = response;
      console.error("[One Media] Download job creation failed.", {status: response.status});
      throw error;
    }
    const created = await response.json();
    const item = {jobId: created.job_id, status: created.status, percentage: 0, downloadedBytes: 0, totalBytes: null, speed: null, eta: null, title: media.title, thumbnail: media.thumbnail, platform: media.platform, request};
    queue.set(item.jobId, item);
    renderQueueItem(item);
    watch(item.jobId);
    return item;
  }

  async function cancel(jobId) {
    try {
      const response = await fetch(`${API}/api/downloads/${jobId}`, {method: "DELETE"});
      if (response.ok) {
        updateJob(jobId, await response.json());
      } else {
        console.error("[One Media] Download cancellation failed.", {jobId, status: response.status});
      }
    } catch (error) {
      console.error("[One Media] Download cancellation request failed.", {jobId, error});
    }
  }

  async function retry(jobId) {
    const previous = queue.get(jobId);
    if (!previous) {
      return;
    }
    const response = await fetch(`${API}/api/downloads/${jobId}/retry`, {method: "POST"});
    if (!response.ok) {
      console.error("[One Media] Download retry failed.", {jobId, status: response.status});
      window.dispatchEvent(new CustomEvent("downloadmanagererror"));
      return;
    }
    const created = await response.json();
    const item = {...previous, jobId: created.job_id, status: created.status, percentage: 0, downloadedBytes: 0, totalBytes: null, speed: null, eta: null, retrieved: false};
    queue.set(item.jobId, item);
    renderQueueItem(item);
    watch(item.jobId);
  }

  document.addEventListener("click", (event) => {
    const cancelButton = event.target.closest("[data-cancel-job]");
    const retryButton = event.target.closest("[data-retry-job]");
    const historyDownload = event.target.closest("[data-history-download]");
    const historyRemove = event.target.closest("[data-history-remove]");
    if (cancelButton) cancel(cancelButton.dataset.cancelJob);
    if (retryButton) retry(retryButton.dataset.retryJob);
    if (historyRemove) removeHistory(historyRemove.dataset.historyRemove);
    if (historyDownload) {
      const item = readHistory().find((entry) => entry.id === historyDownload.dataset.historyDownload);
      if (item) enqueue(item.request, item).catch(() => window.dispatchEvent(new CustomEvent("downloadmanagererror")));
    }
  });

  window.addEventListener("languagechange", () => {
    queue.forEach(renderQueueItem);
    renderHistory();
  });
  window.oneMediaI18nReady?.then(renderHistory);
  window.OneMediaDownloads = {enqueue};
})();
