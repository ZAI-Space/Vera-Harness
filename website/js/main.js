/**
 * VERA HARNESS - LANDING PAGE MAIN CONTROLLER
 * Handles responsive iframe scaling, floating island navbar, and scroll-spy interactions.
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
  if (!navPill) return;

  function updateNavbarOnScroll() {
    if (window.scrollY > 40) {
      navPill.classList.add('pill-scrolled');
    } else {
      navPill.classList.remove('pill-scrolled');
    }
  }

  window.addEventListener('scroll', updateNavbarOnScroll, { passive: true });
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
  }, { threshold: 0.3 });

  // Smooth Anchor Click Handler for Navigation Links
  document.querySelectorAll('a[href^="#sec-"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
      e.preventDefault();
      const targetId = this.getAttribute('href').substring(1);
      const targetEl = document.getElementById(targetId);
      if (targetEl) {
        targetEl.scrollIntoView({ behavior: 'smooth' });
      }
    });
  });

  sectionIds.forEach((id) => {
    const el = document.getElementById(id);
    if (el) observer.observe(el);
  });
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
  initNavbarScroll();
  initScrollSpy();
});
