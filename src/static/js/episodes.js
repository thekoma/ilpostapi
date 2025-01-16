// Funzione per il refresh dell'episodio
async function refreshEpisode(podcastId, episodeId, button) {
    try {
        button.disabled = true;
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

        const response = await fetch(`/api/podcast/${podcastId}/episode/${episodeId}/refresh`, {
            method: 'POST'
        });

        if (!response.ok) throw new Error('Errore nel refresh dell\'episodio');

        // Ricarica la pagina per mostrare i dati aggiornati
        window.location.reload();

    } catch (error) {
        console.error('Errore:', error);
        alert('Errore nell\'aggiornamento dell\'episodio');
    } finally {
        button.disabled = false;
        button.innerHTML = '<i class="fas fa-sync-alt"></i>';
    }
}

// Funzione per espandere/contrarre la descrizione
async function toggleDescription(button) {
    const row = button.closest('.episode-title-row');
    const descriptionDiv = row.nextElementSibling;
    const episodeId = row.querySelector('.episode-title').getAttribute('data-episode-id');
    const podcastId = document.body.getAttribute('data-podcast-id');

    button.classList.toggle('expanded');

    // Se la descrizione è già caricata, la mostriamo/nascondiamo
    if (descriptionDiv.innerHTML.trim()) {
        descriptionDiv.style.display = descriptionDiv.style.display === 'none' ? 'block' : 'none';
        return;
    }

    try {
        button.disabled = true;
        showLoading();

        const response = await fetch(`/api/podcast/${podcastId}/episode/${episodeId}/description`);
        if (!response.ok) throw new Error('Errore nel caricamento della descrizione');

        const data = await response.json();
        descriptionDiv.innerHTML = data.content_html;
        descriptionDiv.style.display = 'block';

        // Controlla se ci sono immagini o se il testo è lungo
        const hasImages = descriptionDiv.querySelector('img') !== null;
        const textLength = descriptionDiv.textContent.length;

        if (hasImages || textLength >= 1000) {
            descriptionDiv.classList.add('truncated');
            const showMore = document.createElement('span');
            showMore.className = 'show-more';
            showMore.textContent = 'Mostra tutto';
            showMore.onclick = function(e) {
                e.stopPropagation();
                descriptionDiv.classList.toggle('expanded');
                descriptionDiv.classList.toggle('truncated');
                showMore.textContent = descriptionDiv.classList.contains('expanded') ? 'Mostra meno' : 'Mostra tutto';
            };
            descriptionDiv.parentNode.insertBefore(showMore, descriptionDiv.nextSibling);
        }
    } catch (error) {
        console.error('Errore:', error);
        descriptionDiv.innerHTML = '<em>Errore nel caricamento della descrizione</em>';
        descriptionDiv.style.display = 'block';
    } finally {
        button.disabled = false;
        hideLoading();
    }
}

// Funzione per cambiare il numero di elementi per pagina
function changePerPage(value) {
    showLoading();
    window.location.href = `?page=1&per_page=${value}`;
}

// Funzioni di utilità per il loading
function showLoading() {
    const loadingContainer = document.querySelector('.loading-container');
    const loadingBar = document.querySelector('.loading-bar');
    const loadingText = document.querySelector('.loading-text');

    loadingContainer.classList.remove('loading-hidden');
    loadingText.classList.remove('hidden');
    loadingContainer.style.display = 'block';
    loadingBar.style.width = '0%';

    setTimeout(() => {
        loadingBar.style.width = '90%';
    }, 50);
}

function hideLoading() {
    const loadingContainer = document.querySelector('.loading-container');
    const loadingBar = document.querySelector('.loading-bar');
    const loadingText = document.querySelector('.loading-text');

    loadingBar.style.width = '100%';
    setTimeout(() => {
        loadingText.classList.add('hidden');
        setTimeout(() => {
            loadingContainer.classList.add('loading-hidden');
        }, 500);
    }, 200);
}

async function updateEpisodesInBackground() {
    try {
        showLoading();
        const podcastId = document.body.getAttribute('data-podcast-id');

        const response = await fetch(`/api/podcast/${podcastId}/update`, {
            method: 'POST'
        });

        if (!response.ok) {
            throw new Error('Errore nell\'aggiornamento degli episodi');
        }

        const data = await response.json();
        if (data.success) {
            window.location.reload();
        }
    } catch (error) {
        console.error('Errore nell\'aggiornamento degli episodi:', error);
        hideLoading();
    }
}

// Funzione per mostrare/nascondere il selettore delle pagine
function showPageSelector(button) {
    const selector = button.querySelector('.page-selector');
    const allSelectors = document.querySelectorAll('.page-selector');

    // Nascondi tutti gli altri selettori
    allSelectors.forEach(s => {
        if (s !== selector) {
            s.classList.remove('visible');
        }
    });

    // Mostra/nascondi il selettore corrente
    selector.classList.toggle('visible');

    // Aggiungi event listener per chiudere il selettore quando si clicca fuori
    const closeSelector = (e) => {
        if (!selector.contains(e.target) && !button.contains(e.target)) {
            selector.classList.remove('visible');
            document.removeEventListener('click', closeSelector);
        }
    };

    // Aggiungi l'event listener solo se il selettore è visibile
    if (selector.classList.contains('visible')) {
        // Usiamo setTimeout per evitare che l'event listener venga triggerato immediatamente
        setTimeout(() => {
            document.addEventListener('click', closeSelector);
        }, 0);
    }
}

// Inizializzazione quando il DOM è pronto
document.addEventListener('DOMContentLoaded', function() {
    // Gestione dello scroll del selettore delle pagine
    const pageSelectors = document.querySelectorAll('.page-selector');
    pageSelectors.forEach(selector => {
        selector.addEventListener('wheel', function(e) {
            e.preventDefault(); // Previene lo scroll della pagina
            this.scrollTop += e.deltaY; // Scrolla il selettore
        });
    });

    // Verifica se è necessario aggiornare gli episodi
    const needsUpdate = document.body.getAttribute('data-needs-update') === 'true';
    if (needsUpdate) {
        updateEpisodesInBackground();
    }
});