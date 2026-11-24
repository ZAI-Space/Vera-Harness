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

// Silent demo playback keeps only transport, seeking and fullscreen controls.
function initDemoPlayer() {
  const video = document.getElementById('demo-video');
  const player = document.getElementById('demo-player');
  const play = document.getElementById('demo-play');
  const progress = document.getElementById('demo-progress');
  const time = document.getElementById('demo-time');
  const fullscreen = document.getElementById('demo-fullscreen');
  const error = document.getElementById('demo-error');
  if (!video || !player || !play || !progress || !time || !fullscreen || !error) return;
  let dragging = false;

  function formatTime(value) {
    const seconds = Number.isFinite(value) ? Math.max(0, Math.floor(value)) : 0;
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
  }

  function showError(message) {
    error.textContent = message;
    error.hidden = false;
  }

  function syncProgress() {
    const duration = Number.isFinite(video.duration) ? video.duration : 0;
    progress.disabled = duration <= 0;
    progress.max = String(duration);
    if (!dragging) progress.value = String(video.currentTime);
    progress.setAttribute('aria-valuetext', `${formatTime(video.currentTime)} / ${formatTime(duration)}`);
    time.textContent = `${formatTime(video.currentTime)} / ${formatTime(duration)}`;
  }

  function togglePlayback() {
    if (!video.paused) {
      video.pause();
      return;
    }
    error.hidden = true;
    void video.play().catch(() => showError('视频暂时无法播放，请刷新页面后重试。'));
  }

  function syncPlayback() {
    play.dataset.playing = String(!video.paused);
    play.setAttribute('aria-label', video.paused ? '播放视频' : '暂停视频');
  }

  play.addEventListener('click', togglePlayback);
  video.addEventListener('click', togglePlayback);
  video.addEventListener('keydown', (event) => {
    if (event.code === 'Space' || event.key.toLowerCase() === 'k') {
      event.preventDefault();
      togglePlayback();
    } else if (['ArrowLeft', 'ArrowRight'].includes(event.key) && Number.isFinite(video.duration)) {
      event.preventDefault();
      const offset = event.key === 'ArrowRight' ? 5 : -5;
      video.currentTime = Math.max(0, Math.min(video.duration, video.currentTime + offset));
    }
  });
  for (const name of ['play', 'pause', 'ended']) video.addEventListener(name, syncPlayback);
  for (const name of ['loadedmetadata', 'durationchange', 'timeupdate']) video.addEventListener(name, syncProgress);
  video.addEventListener('error', () => showError('视频加载失败，请刷新页面后重试。'));
  progress.addEventListener('pointerdown', () => { dragging = true; });
  function finishDragging() {
    dragging = false;
    syncProgress();
  }
  window.addEventListener('pointerup', finishDragging);
  window.addEventListener('pointercancel', finishDragging);
  progress.addEventListener('input', () => {
    if (Number.isFinite(video.duration) && video.duration > 0) {
      video.currentTime = Math.max(0, Math.min(video.duration, Number(progress.value)));
      syncProgress();
    }
  });
  fullscreen.hidden = !document.fullscreenEnabled;
  fullscreen.addEventListener('click', async () => {
    try {
      if (document.fullscreenElement === player) await document.exitFullscreen();
      else await player.requestFullscreen();
    } catch {
      showError('暂时无法进入全屏，请稍后重试。');
    }
  });
  document.addEventListener('fullscreenchange', () => {
    fullscreen.setAttribute('aria-label', document.fullscreenElement === player ? '退出全屏' : '全屏播放');
  });
  syncProgress();
  syncPlayback();
}

// Hash changes restore the active view without replacing the global navigation.
function initViews() {
  const names = ['home', 'docs', 'demo'];
  const track = document.getElementById('view-track');
  const docsFrame = document.getElementById('docs-frame');
  const demoVideo = document.getElementById('demo-video');
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
    // Fetch video metadata on demand and stop playback when leaving the demo.
    if (demoVideo) {
      if (name === 'demo' && demoVideo.preload === 'none') {
        demoVideo.preload = 'metadata';
        demoVideo.load();
      } else if (name !== 'demo') {
        demoVideo.pause();
      }
    }
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
  initDemoPlayer();
  initViews();
});
