(() => {
  "use strict";

  const modes = ["dark", "light", "system"];
  const storageKey = "one-media-theme";
  const systemPreference = window.matchMedia("(prefers-color-scheme: dark)");

  let currentMode = readSavedMode();
  let switcher;
  let trigger;
  let menu;
  let backdrop;

  function readSavedMode() {
    try {
      const saved = localStorage.getItem(storageKey);
      return modes.includes(saved) ? saved : "dark";
    } catch {
      return "dark";
    }
  }

  function saveMode(mode) {
    try {
      localStorage.setItem(storageKey, mode);
    } catch {
      return;
    }
  }

  function resolveMode(mode) {
    return mode === "system" ? (systemPreference.matches ? "dark" : "light") : mode;
  }

  function updateThemeColor(resolvedMode) {
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.content = resolvedMode === "dark" ? "#07111f" : "#f3f6fb";
    }
  }

  function updateControl() {
    if (trigger && menu) {
      const translatedLabel = window.I18n?.t(`theme.${currentMode}`);
      trigger.querySelector("[data-current-theme]").textContent = translatedLabel || "";
      trigger.setAttribute("aria-label", window.I18n?.t("theme.select") || "");
      const iconUse = trigger.querySelector("[data-theme-icon] use");
      iconUse?.setAttribute("href", `#icon-theme-${currentMode}`);

      menu.querySelectorAll("[data-theme-mode]").forEach((option) => {
        const selected = option.dataset.themeMode === currentMode;
        option.setAttribute("aria-selected", String(selected));
        option.classList.toggle("is-selected", selected);
      });
    }
    document.querySelectorAll("[data-set-theme]").forEach((option) => {
      option.setAttribute("aria-pressed", String(option.dataset.setTheme === currentMode));
    });
  }

  function applyMode(mode, {persist = true} = {}) {
    if (!modes.includes(mode)) {
      return;
    }
    currentMode = mode;
    const resolvedMode = resolveMode(mode);
    document.documentElement.dataset.themeMode = mode;
    document.documentElement.dataset.theme = resolvedMode;
    updateThemeColor(resolvedMode);
    if (persist) {
      saveMode(mode);
    }
    updateControl();
    window.dispatchEvent(new CustomEvent("themechange", {detail: {mode, resolvedMode}}));
  }

  function closeMenu({restoreFocus = false} = {}) {
    if (!switcher || !trigger || !menu || !backdrop) {
      return;
    }
    switcher.classList.remove("is-open");
    trigger.setAttribute("aria-expanded", "false");
    menu.hidden = true;
    backdrop.hidden = true;
    document.body.classList.remove("theme-menu-open");
    if (restoreFocus) {
      trigger.focus();
    }
  }

  function openMenu() {
    switcher.classList.add("is-open");
    trigger.setAttribute("aria-expanded", "true");
    menu.hidden = false;
    backdrop.hidden = false;
    document.body.classList.add("theme-menu-open");
    const selected = menu.querySelector('[aria-selected="true"]') || menu.querySelector("[data-theme-mode]");
    requestAnimationFrame(() => selected?.focus());
  }

  function setupSwitcher() {
    switcher = document.querySelector("#theme-switcher");
    trigger = document.querySelector("#theme-trigger");
    menu = document.querySelector("#theme-menu");
    backdrop = document.querySelector("#theme-backdrop");
    if (!switcher || !trigger || !menu || !backdrop) {
      updateControl();
      return;
    }

    trigger.addEventListener("click", () => menu.hidden ? openMenu() : closeMenu());
    menu.addEventListener("click", (event) => {
      const option = event.target.closest("[data-theme-mode]");
      if (!option) {
        return;
      }
      applyMode(option.dataset.themeMode);
      closeMenu();
      trigger.focus();
    });
    menu.addEventListener("keydown", (event) => {
      const options = [...menu.querySelectorAll("[data-theme-mode]")];
      const index = options.indexOf(document.activeElement);
      if (event.key === "Escape") {
        event.preventDefault();
        closeMenu({restoreFocus: true});
        return;
      }
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") {
        return;
      }
      event.preventDefault();
      const direction = event.key === "ArrowDown" ? 1 : -1;
      options[(index + direction + options.length) % options.length]?.focus();
    });
    backdrop.addEventListener("click", () => closeMenu({restoreFocus: true}));
    document.addEventListener("click", (event) => {
      if (!menu.hidden && !switcher.contains(event.target)) {
        closeMenu();
      }
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !menu.hidden) {
        closeMenu({restoreFocus: true});
      }
    });
    updateControl();
  }

  function setupShortcutControls() {
    document.addEventListener("click", (event) => {
      const option = event.target.closest("[data-set-theme]");
      if (option) {
        applyMode(option.dataset.setTheme);
      }
    });
  }

  systemPreference.addEventListener("change", () => {
    if (currentMode === "system") {
      applyMode("system", {persist: false});
    }
  });
  window.addEventListener("languagechange", updateControl);
  document.addEventListener("DOMContentLoaded", () => {
    setupSwitcher();
    setupShortcutControls();
  });

  applyMode(currentMode, {persist: false});
  window.Theme = {
    get mode() {
      return currentMode;
    },
    get resolvedMode() {
      return resolveMode(currentMode);
    },
    setMode: applyMode,
  };
})();
