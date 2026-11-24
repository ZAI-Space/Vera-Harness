/**
 * VERA HARNESS - LANDING PAGE MAIN CONTROLLER
 * Keeps the landing, documentation and demo in one hash-addressable shell.
 * Section iframes retain their content and height synchronization across views.
 */

// Seamless Iframe Height Sync (Exact fit, no overflow gap)
function autoResize(iframe) {
  try {
    const doc = iframe.contentWindow.document;
    const body = doc.body;
    const html = doc.documentElement;
    iframe.style.height = 'auto';
    const height = Math.max(
      body ? body.scrollHeight : 0,
      body ? body.offsetHeight : 0,
      html ? html.clientHeight : 0,
      html ? html.scrollHeight : 0
    );
    if (height > 50) {
      iframe.style.height = height + 'px';
    }
  } catch (err) {
    iframe.style.minHeight = '750px';
  }
}

// Window Resize Observer for Responsive Iframes
window.addEventListener('resize', () => {
  document.querySelectorAll('.section-frame').forEach(autoResize);
});

// Handle Resize Notifications from Child Iframes
window.addEventListener('message', (e) => {
  if (e.data && e.data.type === 'RESIZE') {
    document.querySelectorAll('.section-frame').forEach(autoResize);
  }
});

// Dynamic Floating Pill Navbar on Scroll (Transforms to frosted pill upon scrolling)
function initNavbarScroll() {
  const navPill = document.getElementById('navbar-pill');
  const homeView = document.getElementById('view-home');
  if (!navPill || !homeView) return;

  function updateNavbarOnScroll() {
    if (document.body.dataset.view !== 'home' || homeView.scrollTop > 40) {
      navPill.classList.add('pill-scrolled');
    } else {
      navPill.classList.remove('pill-scrolled');
    }
  }

  homeView.addEventListener('scroll', updateNavbarOnScroll, { passive: true });
  window.addEventListener('viewchange', updateNavbarOnScroll);
  updateNavbarOnScroll();
}

// Nav Scroll Spy & Animation Trigger
function initScrollSpy() {
  const sectionIds = ['sec-01', 'sec-02', 'sec-03', 'sec-04', 'sec-05', 'sec-06', 'sec-07'];
  const dots = document.querySelectorAll('.nav-dot');

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        dots.forEach((dot) => {
          if (dot.getAttribute('data-section') === entry.target.id) {
            dot.classList.add('active');
          } else {
            dot.classList.remove('active');
          }
        });

        // Trigger Evolution Animation ONLY when user scrolls to Section 05
        if (entry.target.id === 'sec-05') {
          const evolutionIframe = document.querySelector('#sec-05 iframe');
          if (evolutionIframe && evolutionIframe.contentWindow) {
            try {
              if (typeof evolutionIframe.contentWindow.playEvolutionAnimation === 'function') {
                evolutionIframe.contentWindow.playEvolutionAnimation();
              } else {
                evolutionIframe.contentWindow.postMessage({ type: 'START_EVOLUTION_ANIM' }, '*');
              }
            } catch (err) {
              evolutionIframe.contentWindow.postMessage({ type: 'START_EVOLUTION_ANIM' }, '*');
            }
          }
        }
      }
    });
  }, { root: document.getElementById('view-home'), threshold: 0.3 });

  // Smooth Anchor Click Handler for Navigation Links
  document.querySelectorAll('a[href^="#sec-"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
      e.preventDefault();
      const targetId = this.getAttribute('href').substring(1);
      const targetEl = document.getElementById(targetId);
      if (targetEl) {
        const behavior = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
        targetEl.scrollIntoView({ behavior });
      }
    });
  });

  sectionIds.forEach((id) => {
    const el = document.getElementById(id);
    if (el) observer.observe(el);
  });
}

// Hash changes restore the active view without replacing the global navigation.
function initViews() {
  const names = ['home', 'docs', 'demo'];
  const track = document.getElementById('view-track');
  const docsFrame = document.getElementById('docs-frame');
  const docsBase = new URL('./docs/', window.location.href);
  let currentDocsPath = 'zh/';

  function docsURL(path) {
    const target = new URL(path, docsBase);
    return target.origin === docsBase.origin && target.pathname.startsWith(docsBase.pathname) ? target : new URL('zh/', docsBase);
  }

  function applyRoute() {
    const [route, query = ''] = window.location.hash.slice(1).split('?');
    const name = names.includes(route) ? route : 'home';
    document.body.dataset.view = name;
    track.style.transform = `translateX(-${names.indexOf(name) * 100}%)`;
    names.forEach((view) => {
      const panel = document.getElementById(`view-${view}`);
      const active = view === name;
      panel.inert = !active;
      panel.setAttribute('aria-hidden', String(!active));
      const link = document.getElementById(`nav-${view}`);
      if (active) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
    if (name === 'docs') {
      const path = new URLSearchParams(query).get('path') || currentDocsPath;
      const target = docsURL(path);
      let currentURL = '';
      try {
        currentURL = docsFrame.contentWindow.location.href;
      } catch {
        // An external link can leave the frame on another origin; restore docs.
      }
      if (currentURL !== target.href) docsFrame.src = target.href;
    }
    if (route.startsWith('sec-')) {
      document.getElementById(route)?.scrollIntoView();
    }
    window.dispatchEvent(new Event('viewchange'));
  }

  // Same-origin documentation pages report their current path, including anchors.
  // Replace the shell URL because iframe navigation already creates history entries.
  window.addEventListener('message', (event) => {
    if (event.origin !== window.location.origin || event.source !== docsFrame.contentWindow || event.data?.type !== 'VERA_DOCS_LOCATION') return;
    const target = docsURL(event.data.path);
    currentDocsPath = target.pathname.slice(docsBase.pathname.length) + target.search + target.hash;
    if (document.body.dataset.view === 'docs') {
      history.replaceState(null, '', `#docs?path=${encodeURIComponent(currentDocsPath)}`);
    }
  });
  window.addEventListener('hashchange', applyRoute);
  window.addEventListener('popstate', applyRoute);
  applyRoute();
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
  initNavbarScroll();
  initScrollSpy();
  initViews();
});
