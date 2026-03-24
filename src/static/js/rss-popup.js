function getRssToken() {
    return document.body.dataset.rssToken || '';
}

function toggleRssPopup(event, podcastId) {
    event.preventDefault();
    event.stopPropagation();

    var popup = document.getElementById('rss-popup');
    var button = event.currentTarget;
    var token = getRssToken();

    // If already open for this podcast, close it
    if (popup.classList.contains('visible') && popup.dataset.podcastId === String(podcastId)) {
        popup.classList.remove('visible');
        return;
    }

    // Build paths with token
    var rssPath = '/podcast/' + podcastId + '/rss' + (token ? '/' + token : '');

    // Update links
    popup.dataset.podcastId = podcastId;
    document.getElementById('rss-popup-rss-link').href = rssPath;

    // Setup copy button
    var copyRss = document.getElementById('rss-popup-copy-rss');

    copyRss.onclick = function (e) {
        e.stopPropagation();
        copyFeedUrl(copyRss, rssPath);
    };

    // Reset copy button text
    resetCopyButton(copyRss, 'RSS');

    // Position popup above the button
    var rect = button.getBoundingClientRect();
    popup.classList.add('visible');

    var popupRect = popup.getBoundingClientRect();
    var top = rect.top - popupRect.height - 8;

    // If not enough space above, show below
    if (top < 8) {
        top = rect.bottom + 8;
    }

    // Keep within viewport horizontally
    var left = rect.left;
    if (left + popupRect.width > window.innerWidth - 8) {
        left = window.innerWidth - popupRect.width - 8;
    }

    popup.style.left = left + 'px';
    popup.style.top = top + 'px';
}

function resetCopyButton(button, type) {
    button.querySelector('i').className = 'fas fa-copy';
    button.classList.remove('copied');
    // Clear old text nodes and set fresh
    var icon = button.querySelector('i');
    button.textContent = '';
    button.appendChild(icon);
    button.appendChild(document.createTextNode(' Copia link ' + type));
}

function copyFeedUrl(button, path) {
    var url = window.location.origin + path;
    navigator.clipboard.writeText(url).then(function () {
        var icon = button.querySelector('i');
        icon.className = 'fas fa-check';
        button.classList.add('copied');
        button.textContent = '';
        button.appendChild(icon);
        button.appendChild(document.createTextNode(' Copiato!'));
        setTimeout(function () {
            resetCopyButton(button, 'RSS');
        }, 2000);
    });
}

document.addEventListener('click', function (e) {
    if (!e.target.closest('.rss-button') && !e.target.closest('#rss-popup')) {
        var popup = document.getElementById('rss-popup');
        if (popup) popup.classList.remove('visible');
    }
});

window.addEventListener('scroll', function () {
    var popup = document.getElementById('rss-popup');
    if (popup) popup.classList.remove('visible');
}, { passive: true });
