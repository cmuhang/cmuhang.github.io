(function () {
  const dataUrl =
    'https://raw.githubusercontent.com/cmuhang/cmuhang.github.io/main/_data/citations.json';

  async function refreshCitationCounts() {
    const badges = document.querySelectorAll('[data-citation-key]');
    if (!badges.length) return;

    try {
      const response = await fetch(dataUrl, { cache: 'no-store' });
      if (!response.ok) return;
      const data = await response.json();

      badges.forEach(function (badge) {
        const paper = data.papers && data.papers[badge.dataset.citationKey];
        if (!paper) return;
        const count = badge.querySelector('.citation-count');
        if (count) count.textContent = paper.indexed ? String(paper.count) : '—';
        if (paper.url) badge.href = paper.url;
        if (data.last_updated) {
          badge.title = 'Google Scholar citations · updated ' + data.last_updated;
        }
      });
    } catch (_) {
      // Keep the statically rendered counts when the network is unavailable.
    }
  }

  refreshCitationCounts();
})();
