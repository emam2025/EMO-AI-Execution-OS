// Minimal JS — HTMX event handlers + UI helpers only
document.addEventListener('htmx:afterSwap', function(evt) {
  if (evt.detail.target && evt.detail.target.id) {
    const el = evt.detail.target;
    try {
      const data = JSON.parse(el.innerText);
      if (Array.isArray(data)) {
        let html = '<ul class="space-y-1">';
        data.slice(0, 10).forEach(function(item) {
          if (typeof item === 'object') {
            html += '<li class="text-sm border-b pb-1">';
            for (const [k, v] of Object.entries(item)) {
              html += '<span class="text-xs text-gray-500">' + k + ':</span> ' + v + ' ';
            }
            html += '</li>';
          } else {
            html += '<li class="text-sm">' + item + '</li>';
          }
        });
        if (data.length > 10) html += '<li class="text-xs text-gray-400">… and ' + (data.length - 10) + ' more</li>';
        html += '</ul>';
        el.innerHTML = html;
      } else if (typeof data === 'object' && data.overall_status) {
        let html = '<div class="space-y-1 text-sm">';
        for (const [k, v] of Object.entries(data)) {
          html += '<div><span class="text-gray-500">' + k + ':</span> ' + v + '</div>';
        }
        html += '</div>';
        el.innerHTML = html;
      }
    } catch(e) {}
  }
});
