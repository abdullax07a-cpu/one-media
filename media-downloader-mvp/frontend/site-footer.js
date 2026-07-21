(() => {
  "use strict";

  const footer = document.querySelector("[data-site-footer]");
  if (!footer) {
    return;
  }

  const root = footer.dataset.rootPath || ".";
  footer.innerHTML = `
    <div class="footer-glow" aria-hidden="true"></div>
    <div class="footer-shell">
      <div class="footer-identity">
        <img class="footer-product-logo" src="${root}/assets/one-media-logo.png" alt="" width="72" height="72" />
        <strong data-i18n="brand.name"></strong>
        <p><span data-i18n="footer.poweredBy"></span> <span data-i18n="brand.shexaTech"></span> - <span lang="ku" dir="rtl" data-i18n="brand.shexaKurdish"></span></p>
        <a class="support-link" href="${root}/support.html" data-i18n-aria-label="support.buttonAria">
          <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 13v-1a8 8 0 0 1 16 0v1M4 13a2 2 0 0 0-2 2v2a2 2 0 0 0 2 2h2v-6H4Zm16 0a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2h-2v-6h2ZM18 19c-1 2-3 2-5 2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" /></svg>
          <span data-i18n="support.button"></span>
        </a>
      </div>
      <nav class="footer-links" data-i18n-aria-label="footer.legalNavigation">
        <a href="${root}/privacy/" data-i18n="legal.privacy.title"></a>
        <a href="${root}/terms/" data-i18n="legal.terms.title"></a>
        <a href="${root}/copyright/" data-i18n="legal.copyright.title"></a>
        <a href="${root}/contact/" data-i18n="legal.contact.title"></a>
      </nav>
      <div class="footer-preferences">
        <div class="footer-control" role="group" data-i18n-aria-label="languages.select">
          <span data-i18n="languages.label"></span>
          <div><button type="button" data-set-language="ku" data-i18n="languages.ku"></button><button type="button" data-set-language="ar" data-i18n="languages.ar"></button><button type="button" data-set-language="en" data-i18n="languages.en"></button></div>
        </div>
        <div class="footer-control" role="group" data-i18n-aria-label="theme.select">
          <span data-i18n="theme.label"></span>
          <div><button type="button" data-set-theme="dark" data-i18n="theme.dark"></button><button type="button" data-set-theme="light" data-i18n="theme.light"></button><button type="button" data-set-theme="system" data-i18n="theme.system"></button></div>
        </div>
      </div>
    </div>
    <div class="footer-disclaimer">
      <p data-i18n="footer.permissionDisclaimer"></p>
      <p data-i18n="footer.affiliationDisclaimer"></p>
    </div>
    <div class="footer-rule"></div>
    <p class="copyright"><span data-i18n="footer.copyright"></span> <span data-i18n="footer.rights"></span></p>`;
})();
