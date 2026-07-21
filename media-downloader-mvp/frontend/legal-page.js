(() => {
  "use strict";

  const page = document.body.dataset.legalPage;
  const sectionKeys = {
    privacy: ["collected", "cookies", "files", "analytics", "security", "retention"],
    terms: ["responsibility", "permission", "prohibited", "refusal", "availability"],
    copyright: ["ownership", "permission", "public", "respect"],
  };

  const socialLinks = [
    ["facebook", "platforms.facebook", "https://www.facebook.com/share/161XiUzpw1C/"],
    ["instagram", "platforms.instagram", "https://www.instagram.com/shexa_tech?igsh=MTlnbGtyNGZwMXVmcg=="],
    ["tiktok", "platforms.tiktok", "https://www.tiktok.com/@shexatech?_r=1&_t=ZS-98BXX9DeJdJ"],
    ["whatsapp", "support.whatsapp", "https://wa.me/qr/4UQV2EPY5EIGE1"],
  ];

  function socialIcon(name) {
    const paths = {
      facebook: '<path d="M13.6 22v-9h3l.45-3.5H13.6V7.27c0-1.01.28-1.7 1.73-1.7h1.85V2.45a25 25 0 0 0-2.7-.14c-2.67 0-4.5 1.63-4.5 4.63V9.5H7v3.5h2.98v9h3.62Z" />',
      instagram: '<rect x="2.5" y="2.5" width="19" height="19" rx="5" fill="none" stroke="currentColor" stroke-width="2" /><circle cx="12" cy="12" r="4.25" fill="none" stroke="currentColor" stroke-width="2" /><circle cx="17.6" cy="6.5" r="1.25" />',
      tiktok: '<path d="M19.59 6.69a4.83 4.83 0 0 1-3.77-4.15V2h-3.38v13.67a2.83 2.83 0 1 1-2-2.7V9.53a6.23 6.23 0 1 0 5.38 6.17V8.77a8.16 8.16 0 0 0 4.77 1.53V6.91c-.34 0-.67-.08-1-.22Z" />',
      whatsapp: '<path d="M20.5 11.7a8.5 8.5 0 0 1-12.55 7.47L3 20.5l1.31-4.79A8.5 8.5 0 1 1 20.5 11.7Z" fill="none" stroke="currentColor" stroke-width="1.8" /><path d="M8.4 7.3c.7 3.8 3.2 6.3 7 7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />',
    };
    return `<svg aria-hidden="true" viewBox="0 0 24 24">${paths[name]}</svg>`;
  }

  function contactContent() {
    const cards = socialLinks.map(([name, label, href]) => `<a class="legal-social ${name}" href="${href.replaceAll("&", "&amp;")}" target="_blank" rel="noopener noreferrer">${socialIcon(name)}<span data-i18n="${label}"></span><svg class="legal-external" aria-hidden="true" viewBox="0 0 24 24"><path d="M14 4h6v6M20 4l-9 9M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5" fill="none" stroke="currentColor" stroke-width="1.8" /></svg></a>`).join("");
    return `<section class="legal-contact-block"><h2 data-i18n="legal.contact.emailLabel"></h2><a class="legal-email" href="mailto:shexatechinfo@gmail.com">shexatechinfo@gmail.com</a><h2 data-i18n="legal.contact.socialTitle"></h2><div class="legal-social-grid">${cards}</div><a class="support-link legal-support-link" href="../support.html"><span data-i18n="legal.contact.openSupport"></span></a></section>`;
  }

  const sections = (sectionKeys[page] || []).map((key) => `<section class="legal-card"><h2 data-i18n="legal.${page}.${key}Title"></h2><p data-i18n="legal.${page}.${key}Body"></p></section>`).join("");
  document.body.innerHTML = `
    <div class="ambient-bg" aria-hidden="true"><span class="ambient-blob ambient-blob-one"></span><span class="ambient-blob ambient-blob-two"></span><span class="ambient-grid"></span></div>
    <header class="site-header"><div class="nav-shell legal-nav"><a class="brand" href="../index.html"><img src="../assets/one-media-logo.png" alt="" width="48" height="48" /><span data-i18n="brand.name"></span></a><a class="back-link" href="../index.html"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M19 12H5m0 0 6-6m-6 6 6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" /></svg><span data-i18n="legal.back"></span></a></div></header>
    <main class="legal-main"><div class="legal-hero"><span class="section-label" data-i18n="brand.name"></span><h1 data-i18n="legal.${page}.title"></h1><p data-i18n="legal.${page}.intro"></p></div><div class="legal-grid">${page === "contact" ? contactContent() : sections}</div></main>
    <footer class="site-footer" data-site-footer data-root-path=".."></footer>`;
})();
