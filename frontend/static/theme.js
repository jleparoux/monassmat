(function () {
  var KEY = 'monassmat-theme';
  var CYCLE = ['auto', 'light', 'dark'];
  var mq = window.matchMedia('(prefers-color-scheme: dark)');

  function stored() {
    return localStorage.getItem(KEY) || 'auto';
  }

  function resolve(pref) {
    return (pref === 'dark' || (pref === 'auto' && mq.matches)) ? 'dark' : 'light';
  }

  function applyToDOM(pref) {
    document.documentElement.setAttribute('data-theme', resolve(pref));
    var btn = document.getElementById('theme-toggle');
    if (!btn) return;
    var icons  = { auto: '◐', light: '☀︎', dark: '☽' };
    var labels = { auto: 'Thème auto (système)', light: 'Thème clair', dark: 'Thème sombre' };
    btn.textContent = icons[pref];
    btn.title = labels[pref];
    btn.setAttribute('aria-label', labels[pref]);
    btn.setAttribute('data-mode', pref);
  }

  // Apply immediately (synchronous, before first paint) to prevent FOUC
  document.documentElement.setAttribute('data-theme', resolve(stored()));

  // Re-apply when OS preference changes (only relevant in auto mode)
  mq.addEventListener('change', function () {
    applyToDOM(stored());
  });

  document.addEventListener('DOMContentLoaded', function () {
    applyToDOM(stored());
    var btn = document.getElementById('theme-toggle');
    if (!btn) return;
    btn.addEventListener('click', function () {
      var current = stored();
      var next = CYCLE[(CYCLE.indexOf(current) + 1) % CYCLE.length];
      localStorage.setItem(KEY, next);
      applyToDOM(next);
    });
  });
})();
