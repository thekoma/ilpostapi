class LoadingStatus {
    constructor() {
        this.overlay = document.createElement('div');
        this.overlay.className = 'loading-status-overlay';
        this.overlay.innerHTML = `
            <div class="loading-status-title">Caricamento in corso...</div>
            <div class="loading-status-message"></div>
            <div class="loading-status-progress">
                <div class="loading-status-bar"></div>
            </div>
            <div class="loading-status-details"></div>
            <div class="loading-status-error" style="display: none;"></div>
        `;
        document.body.appendChild(this.overlay);

        this.title = this.overlay.querySelector('.loading-status-title');
        this.message = this.overlay.querySelector('.loading-status-message');
        this.progressBar = this.overlay.querySelector('.loading-status-bar');
        this.details = this.overlay.querySelector('.loading-status-details');
        this.error = this.overlay.querySelector('.loading-status-error');

        this.currentPhase = '';
        this.totalEpisodes = 0;
        this.loadedEpisodes = 0;
        this.loadedDescriptions = 0;
        this.errors = 0;
    }

    show() {
        this.overlay.classList.add('visible');
    }

    hide() {
        this.overlay.classList.remove('visible');
        setTimeout(() => {
            this.reset();
        }, 300);
    }

    reset() {
        this.currentPhase = '';
        this.totalEpisodes = 0;
        this.loadedEpisodes = 0;
        this.loadedDescriptions = 0;
        this.errors = 0;
        this.progressBar.style.width = '0%';
        this.error.style.display = 'none';
        this.error.textContent = '';
    }

    startEpisodesFetch(total) {
        this.reset();
        this.show();
        this.currentPhase = 'episodes';
        this.totalEpisodes = total;
        this.updateStatus();
    }

    updateEpisodesFetch(loaded) {
        this.loadedEpisodes = loaded;
        this.updateStatus();
    }

    startDescriptionsFetch(total) {
        this.currentPhase = 'descriptions';
        this.totalEpisodes = total;
        this.updateStatus();
    }

    updateDescriptionsFetch(loaded) {
        this.loadedDescriptions = loaded;
        this.updateStatus();
    }

    addError(message) {
        this.errors++;
        this.error.textContent = message;
        this.error.style.display = 'block';
        this.updateStatus();
    }

    updateStatus() {
        let progress = 0;
        let message = '';
        let details = '';

        if (this.currentPhase === 'episodes') {
            progress = (this.loadedEpisodes / this.totalEpisodes) * 100;
            message = `Recupero degli episodi in corso...`;
            details = `Recuperati ${this.loadedEpisodes} di ${this.totalEpisodes} episodi`;
        } else if (this.currentPhase === 'descriptions') {
            progress = (this.loadedDescriptions / this.totalEpisodes) * 100;
            message = `Recupero delle descrizioni in corso...`;
            details = `Caricate ${this.loadedDescriptions} di ${this.totalEpisodes} descrizioni`;
        }

        if (this.errors > 0) {
            details += `\nErrori: ${this.errors}`;
        }

        this.progressBar.style.width = `${progress}%`;
        this.message.textContent = message;
        this.details.textContent = details;

        if (progress >= 100) {
            setTimeout(() => this.hide(), 1000);
        }
    }
}

// Create global loading status instance
const loadingStatus = new LoadingStatus();

// Modify the loadDescription function to update loading status
async function loadDescription(podcastId, episodeId, button) {
    const descriptionDiv = button.parentElement.querySelector('.episode-description');

    if (descriptionDiv.innerHTML.trim()) {
        descriptionDiv.style.display = descriptionDiv.style.display === 'none' ? 'block' : 'none';
        return;
    }

    try {
        button.disabled = true;
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

        loadingStatus.startDescriptionsFetch(1);
        const response = await fetch(`/api/podcast/${podcastId}/episode/${episodeId}/description`);
        if (!response.ok) throw new Error('Errore nel caricamento della descrizione');

        const data = await response.json();
        descriptionDiv.innerHTML = data.content_html;
        descriptionDiv.style.display = 'block';
        loadingStatus.updateDescriptionsFetch(1);

        if (descriptionDiv.scrollHeight > descriptionDiv.clientHeight) {
            const showMore = document.createElement('span');
            showMore.className = 'show-more';
            showMore.textContent = 'Mostra tutto';
            showMore.onclick = function() {
                descriptionDiv.classList.toggle('expanded');
                showMore.textContent = descriptionDiv.classList.contains('expanded') ? 'Mostra meno' : 'Mostra tutto';
            };
            descriptionDiv.parentNode.insertBefore(showMore, descriptionDiv.nextSibling);
        }
    } catch (error) {
        console.error('Errore:', error);
        descriptionDiv.innerHTML = '<em>Errore nel caricamento della descrizione</em>';
        descriptionDiv.style.display = 'block';
        loadingStatus.addError('Errore nel caricamento della descrizione');
    } finally {
        button.disabled = false;
        button.innerHTML = '<i class="fas fa-info-circle"></i>';
    }
}