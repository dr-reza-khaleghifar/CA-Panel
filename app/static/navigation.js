/* Iran CA Center — accessible, responsive navigation with real section state. */
(function () {
  'use strict';
  const doc = document;
  const sidebar = doc.getElementById('sidebar');
  const toggle = doc.getElementById('menu-toggle');
  const closeButton = doc.getElementById('menu-close');
  const backdrop = doc.getElementById('nav-backdrop');
  const links = Array.from(doc.querySelectorAll('.side-nav a[href^="#"]'));
  if (!sidebar || !toggle || !closeButton || !backdrop || !links.length) return;

  const mobile = () => window.matchMedia('(max-width: 980px)').matches;
  const sections = links.map(link => ({link, target: doc.getElementById(link.getAttribute('href').slice(1))}))
    .filter(item => item.target);
  let opened = false;
  let scheduled = false;

  function setOpen(next, restoreFocus) {
    opened = Boolean(next) && mobile();
    doc.body.classList.toggle('nav-open', opened);
    backdrop.hidden = !opened;
    toggle.setAttribute('aria-expanded', String(opened));
    toggle.setAttribute('aria-label', opened ? 'بستن منوی ناوبری' : 'باز کردن منوی ناوبری');
    sidebar.setAttribute('aria-hidden', String(mobile() && !opened));
    if (opened) closeButton.focus();
    else if (restoreFocus && mobile()) toggle.focus();
  }

  function setActive(id) {
    for (const item of sections) {
      const active = item.target.id === id;
      item.link.classList.toggle('active', active);
      if (active) {
        item.link.setAttribute('aria-current', 'location');
        const breadcrumb = doc.getElementById('breadcrumb-current');
        const label = item.link.querySelector('span:not(.nav-end)');
        if (breadcrumb && label) breadcrumb.textContent = label.textContent;
      } else item.link.removeAttribute('aria-current');
    }
  }

  function updateFromScroll() {
    scheduled = false;
    let found = sections[0];
    // The last section whose heading passed the top navigation line is active.
    const limit = Math.min(210, Math.round(window.innerHeight * 0.33));
    for (const item of sections) {
      if (item.target.getBoundingClientRect().top <= limit) found = item;
    }
    if (found) setActive(found.target.id);
  }
  function scheduleUpdate() {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(updateFromScroll);
  }

  toggle.addEventListener('click', () => setOpen(!opened, false));
  closeButton.addEventListener('click', () => setOpen(false, true));
  backdrop.addEventListener('click', () => setOpen(false, true));

  for (const item of sections) {
    item.link.addEventListener('click', event => {
      event.preventDefault();
      setActive(item.target.id);
      setOpen(false, false);
      item.target.focus({preventScroll: true});
      const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      item.target.scrollIntoView({behavior: reduceMotion ? 'auto' : 'smooth', block: 'start'});
      if (window.history && window.history.pushState) {
        window.history.pushState(null, '', '#' + item.target.id);
      }
    });
  }
  const brand = doc.querySelector('.brand[href="#top"]');
  if (brand) brand.addEventListener('click', () => {setOpen(false, false);setActive('overview');});

  doc.addEventListener('keydown', event => {
    if (!opened) return;
    if (event.key === 'Escape') {
      setOpen(false, true);
      return;
    }
    if (event.key !== 'Tab') return;
    // An off-canvas menu should not let keyboard focus escape behind its backdrop.
    const focusables = Array.from(sidebar.querySelectorAll('a[href], button:not([disabled])'))
      .filter(element => element.getAttribute('tabindex') !== '-1');
    if (!focusables.length) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (event.shiftKey && doc.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && doc.activeElement === last) {
      event.preventDefault();
      first.focus();
    } else if (!sidebar.contains(doc.activeElement)) {
      event.preventDefault();
      first.focus();
    }
  });
  window.addEventListener('resize', () => {
    if (!mobile() && opened) setOpen(false, false);
    sidebar.setAttribute('aria-hidden', String(mobile() && !opened));
    scheduleUpdate();
  });
  window.addEventListener('scroll', scheduleUpdate, {passive: true});
  window.addEventListener('hashchange', scheduleUpdate);
  setOpen(false, false);
  scheduleUpdate();
})();