(() => {
  "use strict";

  const supportedLanguages = ["ku", "ar", "en"];
  const rtlLanguages = new Set(["ku", "ar"]);
  const storageKey = "one-media-language";
  const catalogBase = new URL("./", document.currentScript.src);
  const catalogs = new Map();

  let currentLanguage = "ku";
  let switcher;
  let trigger;
  let menu;
  let backdrop;

  function readSavedLanguage() {
    try {
      const saved = localStorage.getItem(storageKey);
      return supportedLanguages.includes(saved) ? saved : "ku";
    } catch {
      return "ku";
    }
  }

  function saveLanguage(language) {
    try {
      localStorage.setItem(storageKey, language);
    } catch {
      return;
    }
  }

  async function loadCatalog(language) {
    if (catalogs.has(language)) {
      return catalogs.get(language);
    }

    const response = await fetch(new URL(`${language}.json`, catalogBase), {cache: "no-cache"});
    if (!response.ok) {
      throw new Error(`i18n:${language}:${response.status}`);
    }
    const catalog = await response.json();
    catalogs.set(language, catalog);
    return catalog;
  }

  function findValue(catalog, key) {
    return key.split(".").reduce((value, part) => value?.[part], catalog);
  }

  function interpolate(value, variables = {}) {
    return String(value).replace(/\{\{(\w+)\}\}/g, (_, name) => variables[name] ?? "");
  }

  function translate(key, variables = {}, language = currentLanguage) {
    const value = findValue(catalogs.get(language), key)
      ?? findValue(catalogs.get("en"), key)
      ?? key;
    return interpolate(value, variables);
  }

  function applyTranslations() {
    document.querySelectorAll("[data-i18n]").forEach((element) => {
      element.textContent = translate(element.dataset.i18n);
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
      element.placeholder = translate(element.dataset.i18nPlaceholder);
    });
    document.querySelectorAll("[data-i18n-aria-label]").forEach((element) => {
      element.setAttribute("aria-label", translate(element.dataset.i18nAriaLabel));
    });
    document.querySelectorAll("[data-i18n-title]").forEach((element) => {
      element.title = translate(element.dataset.i18nTitle);
    });
    document.querySelectorAll("[data-i18n-content]").forEach((element) => {
      element.setAttribute("content", translate(element.dataset.i18nContent));
    });

    document.title = translate(document.documentElement.dataset.pageTitleKey || "page.title");
    document.documentElement.lang = currentLanguage;
    document.documentElement.dir = rtlLanguages.has(currentLanguage) ? "rtl" : "ltr";

    if (trigger) {
      trigger.querySelector("[data-current-language]").textContent = translate(`languages.${currentLanguage}`);
      trigger.setAttribute("aria-label", translate("languages.select"));
    }
    if (menu) {
      menu.querySelectorAll("[data-language]").forEach((option) => {
        const selected = option.dataset.language === currentLanguage;
        option.setAttribute("aria-selected", String(selected));
        option.classList.toggle("is-selected", selected);
      });
    }
    document.querySelectorAll("[data-set-language]").forEach((option) => {
      option.setAttribute("aria-pressed", String(option.dataset.setLanguage === currentLanguage));
    });
  }

  function closeMenu({restoreFocus = false} = {}) {
    if (!switcher || !trigger || !menu || !backdrop) {
      return;
    }
    switcher.classList.remove("is-open");
    trigger.setAttribute("aria-expanded", "false");
    menu.hidden = true;
    backdrop.hidden = true;
    document.body.classList.remove("language-menu-open");
    if (restoreFocus) {
      trigger.focus();
    }
  }

  function openMenu() {
    switcher.classList.add("is-open");
    trigger.setAttribute("aria-expanded", "true");
    menu.hidden = false;
    backdrop.hidden = false;
    document.body.classList.add("language-menu-open");
    const selected = menu.querySelector('[aria-selected="true"]') || menu.querySelector("[data-language]");
    requestAnimationFrame(() => selected?.focus());
  }

  async function setLanguage(language, {initial = false} = {}) {
    if (!supportedLanguages.includes(language)) {
      return;
    }

    await Promise.all([loadCatalog("en"), loadCatalog(language)]);
    if (!initial) {
      document.documentElement.classList.add("language-changing");
      await new Promise((resolve) => setTimeout(resolve, 110));
    }

    currentLanguage = language;
    saveLanguage(language);
    applyTranslations();
    document.documentElement.classList.remove("i18n-pending");

    requestAnimationFrame(() => {
      document.documentElement.classList.remove("language-changing");
    });

    window.dispatchEvent(new CustomEvent("languagechange", {detail: {language}}));
  }

  function setupSwitcher() {
    switcher = document.querySelector("#language-switcher");
    trigger = document.querySelector("#language-trigger");
    menu = document.querySelector("#language-menu");
    backdrop = document.querySelector("#language-backdrop");

    if (!switcher || !trigger || !menu || !backdrop) {
      return;
    }

    trigger.addEventListener("click", () => {
      if (menu.hidden) {
        openMenu();
      } else {
        closeMenu();
      }
    });

    menu.addEventListener("click", async (event) => {
      const option = event.target.closest("[data-language]");
      if (!option) {
        return;
      }
      closeMenu();
      await setLanguage(option.dataset.language);
      trigger.focus();
    });

    menu.addEventListener("keydown", (event) => {
      const options = [...menu.querySelectorAll("[data-language]")];
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
  }

  function setupShortcutControls() {
    document.addEventListener("click", async (event) => {
      const option = event.target.closest("[data-set-language]");
      if (option) {
        await setLanguage(option.dataset.setLanguage);
      }
    });
  }

  const api = {
    get language() {
      return currentLanguage;
    },
    t: translate,
    setLanguage,
    getSource(key) {
      return findValue(catalogs.get("en"), key);
    }
  };

  window.I18n = api;
  window.oneMediaI18nReady = (async () => {
    setupSwitcher();
    setupShortcutControls();
    await setLanguage(readSavedLanguage(), {initial: true});
  })().catch((error) => {
    document.documentElement.classList.remove("i18n-pending");
    console.error(error);
  });
})();
