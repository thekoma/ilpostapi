/**
 * Pjax-style navigation: intercepts internal link clicks, fetches the new page
 * via AJAX, and swaps only #app-content while keeping the audio player alive.
 */
(function () {
    function isInternalLink(a) {
        if (!a || !a.href) return false;
        if (a.target && a.target !== '_self') return false;
        if (a.hasAttribute('download')) return false;
        if (a.href.startsWith('javascript:')) return false;
        try {
            const url = new URL(a.href, location.origin);
            if (url.origin !== location.origin) return false;
            // Skip RSS/RDF feed links and API endpoints
            if (url.pathname.endsWith('/rss') || url.pathname.endsWith('/rdf')) return false;
            if (url.pathname.endsWith('/last') || url.pathname.endsWith('/lastepisode')) return false;
            return true;
        } catch {
            return false;
        }
    }

    function extractContent(html) {
        const doc = new DOMParser().parseFromString(html, 'text/html');
        return {
            appContent: doc.getElementById('app-content'),
            title: doc.title,
            bodyClass: doc.body.className,
            bodyDataAttrs: Array.from(doc.body.attributes).filter(
                a => a.name.startsWith('data-')
            ),
            // Collect inline <style> in <head> (for podcast cover CSS vars)
            headStyles: Array.from(doc.head.querySelectorAll('style')).map(s => s.textContent),
            // Check which page-specific CSS/JS are needed
            hasEpisodesCss: !!doc.querySelector('link[href*="episodes.css"]'),
            inlineScripts: Array.from(
                doc.querySelectorAll('#app-content ~ script, script[data-pjax]')
            ).map(s => s.textContent),
            // Grab inline scripts that are inside the body (page-specific init)
            bodyInlineScripts: Array.from(doc.body.querySelectorAll('script:not([src])')).map(
                s => s.textContent
            ),
        };
    }

    function ensureCss(href) {
        if (document.querySelector(`link[href*="${href}"]`)) return;
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = `/static/css/${href}`;
        document.head.appendChild(link);
    }

    function updateHeadStyles(styles) {
        // Remove old dynamic styles
        document.querySelectorAll('style[data-pjax]').forEach(s => s.remove());
        styles.forEach(css => {
            const style = document.createElement('style');
            style.setAttribute('data-pjax', '');
            style.textContent = css;
            document.head.appendChild(style);
        });
    }

    function reinitPageScripts(extracted) {
        // Re-bind play buttons for the player
        if (window.podcastPlayer) {
            window.podcastPlayer.initializeControls();
        }

        // Re-init search if on directory page
        const searchInput = document.getElementById('podcast-search');
        const podcastGrid = document.querySelector('.podcast-grid');
        if (searchInput && podcastGrid) {
            podcastGrid.style.display = 'grid';
            searchInput.addEventListener('input', function (e) {
                searchPodcasts(e.target.value);
            });
        }

        // Re-init episodes page-specific logic
        const pageSelectors = document.querySelectorAll('.page-selector');
        pageSelectors.forEach(selector => {
            selector.addEventListener('wheel', function (e) {
                e.preventDefault();
                this.scrollTop += e.deltaY;
            });
        });

        // Check if episodes need background update
        const needsUpdate = document.body.getAttribute('data-needs-update') === 'true';
        if (needsUpdate && typeof updateEpisodesInBackground === 'function') {
            updateEpisodesInBackground();
        }

        // Re-init theme selector
        const savedTheme = getCookie('theme') || 'macchiato';
        document.documentElement.setAttribute('data-theme', savedTheme);
        const themeSelect = document.getElementById('theme-select');
        if (themeSelect) {
            themeSelect.value = savedTheme;
        }

        // Handle directory loading animation
        const loadingContainer = document.querySelector('.loading-container');
        const podcastGridEl = document.querySelector('.podcast-grid');
        if (loadingContainer && podcastGridEl) {
            // If we're on directory page and needs_update, trigger background update
            // Otherwise just show content
            podcastGridEl.style.opacity = '1';
            loadingContainer.classList.add('loading-hidden');
        }
    }

    async function navigateTo(url) {
        try {
            // Show a subtle loading indicator
            document.body.classList.add('pjax-loading');

            const response = await window._originalFetch(url);
            if (!response.ok) {
                // Fall back to normal navigation on error
                location.href = url;
                return;
            }

            const html = await response.text();
            const extracted = extractContent(html);

            if (!extracted.appContent) {
                // Page doesn't have #app-content, fall back
                location.href = url;
                return;
            }

            // Swap content
            const currentContent = document.getElementById('app-content');
            currentContent.replaceWith(extracted.appContent);

            // Update title
            document.title = extracted.title;

            // Update body class and data attributes
            document.body.className = extracted.bodyClass;
            // Remove old data attrs
            Array.from(document.body.attributes)
                .filter(a => a.name.startsWith('data-'))
                .forEach(a => document.body.removeAttribute(a.name));
            // Set new data attrs
            extracted.bodyDataAttrs.forEach(a =>
                document.body.setAttribute(a.name, a.value)
            );

            // Update head styles (podcast cover CSS vars)
            updateHeadStyles(extracted.headStyles);

            // Ensure episodes CSS is loaded if needed
            if (extracted.hasEpisodesCss) {
                ensureCss('episodes.css');
            }

            // Update URL
            history.pushState({ pjax: true }, '', url);

            // Scroll to top
            window.scrollTo(0, 0);

            // Re-initialize page scripts
            reinitPageScripts(extracted);

            // Execute inline scripts from the new page
            extracted.bodyInlineScripts.forEach(code => {
                // Skip DOMContentLoaded wrappers since we're already loaded
                // Extract the callback content if wrapped in DOMContentLoaded
                const unwrapped = code.replace(
                    /document\.addEventListener\s*\(\s*['"]DOMContentLoaded['"]\s*,\s*function\s*\(\s*\)\s*\{/,
                    '(function(){'
                );
                try {
                    new Function(unwrapped)();
                } catch (e) {
                    console.warn('Error running inline script after navigation:', e);
                }
            });
        } catch (e) {
            console.error('Pjax navigation failed, falling back:', e);
            location.href = url;
        } finally {
            document.body.classList.remove('pjax-loading');
        }
    }

    // Intercept clicks on internal links
    document.addEventListener('click', function (e) {
        // Find the closest <a> element
        const a = e.target.closest('a');
        if (!a) return;
        if (!isInternalLink(a)) return;

        // Don't intercept if modifier keys are held
        if (e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;

        e.preventDefault();
        navigateTo(a.href);
    });

    // Handle browser back/forward
    window.addEventListener('popstate', function (e) {
        if (e.state && e.state.pjax) {
            navigateTo(location.href);
        } else {
            // For non-pjax states, just reload
            navigateTo(location.href);
        }
    });

    // Store initial state
    history.replaceState({ pjax: true }, '', location.href);

    // Store original fetch before loading.js wraps it
    // (loading.js intercepts fetch which would cause loading bar on navigation)
    window._originalFetch = window._originalFetch || window.fetch;

    // Expose navigateTo globally so other scripts can use pjax navigation
    // instead of window.location.reload() or window.location.href = ...
    window.pjaxNavigate = navigateTo;
    window.pjaxReload = function () {
        return navigateTo(location.href);
    };
})();
