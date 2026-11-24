/** Embed docs in the shared website shell and observe the article scroll area. */
(function () {
  const config = JSON.parse(document.getElementById('__config').textContent);
  const docsBase = new URL(`${config.base}/`, window.location.href);
  const relativePath = () => window.location.pathname.slice(docsBase.pathname.length) + window.location.search + window.location.hash;

  // Direct documentation links open the same shell as the global documentation tab.
  if (window.parent === window) {
    const shell = new URL('../', docsBase);
    shell.hash = `docs?path=${encodeURIComponent(relativePath())}`;
    window.location.replace(shell.href);
    return;
  }

  function reportLocation() {
    window.parent.postMessage({ type: 'VERA_DOCS_LOCATION', path: relativePath() }, window.location.origin);
  }
  window.addEventListener('hashchange', reportLocation);
  reportLocation();

  document.querySelectorAll('.website-tools label[role="button"]').forEach((label) => {
    label.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      label.click();
    });
  });

  const article = document.querySelector('.md-content');
  const toc = document.querySelector('.md-sidebar--secondary');
  const toggle = document.querySelector('.website-toc-toggle');
  toggle?.addEventListener('click', () => {
    const open = document.body.toggleAttribute('data-toc-open');
    toggle.setAttribute('aria-expanded', String(open));
  });

  // Material observes the window; the embedded view reads only the middle column.
  const links = Array.from(toc?.querySelectorAll('a[href^="#"]') || []);
  const targets = links.map((link) => document.getElementById(decodeURIComponent(link.hash.slice(1))));
  function updateContents() {
    const top = article.getBoundingClientRect().top + 32;
    let active = 0;
    targets.forEach((target, index) => {
      if (target && target.getBoundingClientRect().top <= top) active = index;
    });
    links.forEach((link, index) => {
      link.classList.toggle('website-toc-active', index === active);
    });
  }
  links.forEach((link, index) => {
    link.addEventListener('click', (event) => {
      if (!targets[index]) return;
      event.preventDefault();
      article.scrollTo({
        top: article.scrollTop + targets[index].getBoundingClientRect().top - article.getBoundingClientRect().top,
        behavior: 'auto',
      });
      history.pushState(null, '', link.hash);
      document.getElementById('__drawer').checked = false;
      document.body.removeAttribute('data-toc-open');
      toggle?.setAttribute('aria-expanded', 'false');
      updateContents();
      reportLocation();
    });
  });
  article?.addEventListener('scroll', updateContents, { passive: true });
  if (article) updateContents();
})();
