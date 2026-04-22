const app = document.querySelector('#searchApp');

if (app) {
  const input = app.querySelector('#searchInput');
  const status = app.querySelector('#searchStatus');
  const help = app.querySelector('#searchHelp');
  const resultsEl = app.querySelector('#searchResults');
  const modeButtons = Array.from(app.querySelectorAll('[data-mode]'));
  const rootPath = app.dataset.rootPath || '.';
  const bundles = {
    general: app.dataset.generalBundle,
    transcripts: app.dataset.transcriptBundle,
  };
  const helpText = {
    general: 'Default mode prioritizes meeting titles, summaries, people, tags, votes, and roll call without indexing transcript bodies.',
    transcripts: 'Transcript mode searches across all ingested meeting transcripts, including meetings that have not been fully annotated yet.',
  };

  let activeMode = 'general';
  let searchToken = 0;
  const loadedModules = new Map();

  const escapeHtml = (value) => String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

  const normalizeUrl = (url) => {
    if (!url) return '#';
    if (/^(https?:)?\/\//.test(url)) return url;
    if (url.startsWith('#') || url.startsWith('../') || url.startsWith('./')) return url;
    if (url.startsWith('/')) return `${rootPath}/${url.replace(/^\//, '')}`;
    return `${rootPath}/${url}`;
  };

  const loadPagefind = async (mode) => {
    if (loadedModules.has(mode)) {
      return loadedModules.get(mode);
    }
    const bundlePath = bundles[mode];
    const pagefind = await import(`${bundlePath}pagefind.js`);
    if (typeof pagefind.options === 'function') {
      await pagefind.options({ bundlePath });
    }
    if (typeof pagefind.init === 'function') {
      await pagefind.init();
    }
    loadedModules.set(mode, pagefind);
    return pagefind;
  };

  const renderResults = async (mode, search) => {
    const page = await Promise.all(search.results.slice(0, 12).map((result) => result.data()));
    if (!page.length) {
      resultsEl.innerHTML = '<p class="muted">No results.</p>';
      return;
    }

    resultsEl.innerHTML = page.map((result) => {
      const meta = result.meta || {};
      const title = meta.title || result.url;
      const href = normalizeUrl(mode === 'transcripts' ? (meta.target_url || result.url) : result.url);
      const metaLine = [];

      if (mode === 'transcripts') {
        if (meta.meeting_title) metaLine.push(escapeHtml(meta.meeting_title));
        if (meta.date) metaLine.push(escapeHtml(meta.date));
        if (meta.timestamp) metaLine.push(escapeHtml(meta.timestamp));
      } else {
        if (meta.type) metaLine.push(escapeHtml(meta.type));
        if (meta.date) metaLine.push(escapeHtml(meta.date));
      }

      return `
        <article class="search-result panel">
          <h3><a href="${href}">${escapeHtml(title)}</a></h3>
          ${metaLine.length ? `<p class="muted">${metaLine.join(' | ')}</p>` : ''}
          ${result.excerpt ? `<p>${result.excerpt}</p>` : ''}
        </article>
      `;
    }).join('');
  };

  const runSearch = async () => {
    const term = input.value.trim();
    const currentToken = ++searchToken;
    resultsEl.innerHTML = '';

    if (!term) {
      status.textContent = 'Type to search.';
      return;
    }

    status.textContent = 'Searching...';

    try {
      const pagefind = await loadPagefind(activeMode);
      if (typeof pagefind.preload === 'function') {
        pagefind.preload(term);
      }
      const search = await pagefind.debouncedSearch(term);
      if (search === null || currentToken !== searchToken) {
        return;
      }
      status.textContent = `${search.results.length} result${search.results.length === 1 ? '' : 's'}.`;
      await renderResults(activeMode, search);
    } catch (error) {
      console.error(error);
      status.textContent = 'Search index is not available yet for this build.';
      resultsEl.innerHTML = '<p class="muted">Search assets were not found. If you are building locally, make sure Pagefind ran after the site build.</p>';
    }
  };

  modeButtons.forEach((button) => {
    button.addEventListener('click', () => {
      activeMode = button.dataset.mode;
      modeButtons.forEach((candidate) => {
        const isActive = candidate === button;
        candidate.classList.toggle('is-active', isActive);
        candidate.setAttribute('aria-pressed', isActive ? 'true' : 'false');
      });
      help.textContent = helpText[activeMode];
      runSearch();
    });
  });

  let debounceHandle;
  input.addEventListener('input', () => {
    window.clearTimeout(debounceHandle);
    debounceHandle = window.setTimeout(runSearch, 120);
  });
}
