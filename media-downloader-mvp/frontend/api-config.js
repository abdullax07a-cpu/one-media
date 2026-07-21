(() => {
  "use strict";

  const isLocalDevelopment = ["localhost", "127.0.0.1", "[::1]"].includes(window.location.hostname);
  const requestedBase = isLocalDevelopment ? String(window.ONE_MEDIA_API_BASE_URL || "") : "";
  const configuredBase = window.location.protocol === "https:" && requestedBase.startsWith("http:") ? "" : requestedBase;
  const baseUrl = configuredBase.replace(/\/+$/, "");

  function url(path) {
    return `${baseUrl}${path.startsWith("/") ? path : `/${path}`}`;
  }

  async function logHttpError(label, requestUrl, response) {
    let responseBody = "";
    try {
      responseBody = (await response.clone().text()).slice(0, 2000);
    } catch {
      responseBody = "<unavailable>";
    }
    console.error(`[One Media] ${label}`, {
      url: requestUrl,
      status: response.status,
      responseBody,
    });
  }

  function logNetworkError(label, requestUrl, error) {
    console.error(`[One Media] ${label}`, {url: requestUrl, status: null, responseBody: null, error});
  }

  window.OneMediaApi = {url, logHttpError, logNetworkError};
})();
