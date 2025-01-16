class PodcastPlayer {
    constructor() {
        // Inizializza le proprietà
        this.audioPlayer = document.getElementById('audio-player');
        this.player = document.getElementById('player');
        this.nowPlayingTitle = document.getElementById('now-playing-title');
        this.prevButton = document.getElementById('prev-episode');
        this.nextButton = document.getElementById('next-episode');
        this.currentEpisodeIndex = -1;
        this.currentPodcastId = null;
        this.episodes = [];
        this.descriptionContainer = document.getElementById('episode-description-player');

        // Se non troviamo gli elementi necessari, non inizializzare il player
        if (!this.audioPlayer || !this.player) {
            console.warn('Player elements not found in the page');
            return;
        }

        // Nascondi il player all'avvio
        this.audioPlayer.style.display = 'none';
        this.audioPlayer.classList.remove('visible', 'minimized');

        // Inizializza i controlli e gli event listener
        this.initializeControls();

        // Registra il Service Worker
        this.registerServiceWorker();

        // Gestisci gli aggiornamenti di stato da altre pagine
        navigator.serviceWorker.addEventListener('message', (event) => {
            if (event.data.type === 'PLAYER_STATE_UPDATE') {
                this.handleStateUpdate(event.data.state);
            }
        });

        // Salva lo stato periodicamente
        setInterval(() => this.savePlayerState(), 1000);

        // Salva lo stato quando il player viene messo in pausa o riparte
        this.player.addEventListener('play', () => this.savePlayerState());
        this.player.addEventListener('pause', () => this.savePlayerState());

        // Salva lo stato prima di lasciare la pagina
        window.addEventListener('beforeunload', () => this.savePlayerState());

        // Aggiungi il metodo per chiudere il player
        this.closePlayer = this.closePlayer.bind(this);
        window.closePlayer = () => this.closePlayer();
    }

    async registerServiceWorker() {
        if ('serviceWorker' in navigator) {
            try {
                const registration = await navigator.serviceWorker.register('/static/js/player-sw.js');
                console.log('Service Worker registrato:', registration);
            } catch (error) {
                console.error('Errore nella registrazione del Service Worker:', error);
            }
        }
    }

    handleStateUpdate(state) {
        // Aggiorna lo stato del player solo se non è già attivo
        if (!this.audioPlayer.classList.contains('visible')) {
            this.restorePlayerState(state);
        }
    }

    savePlayerState() {
        const state = {
            currentTime: this.player.currentTime,
            src: this.player.src,
            title: this.nowPlayingTitle.textContent,
            podcastId: this.currentPodcastId,
            episodeIndex: this.currentEpisodeIndex,
            episodes: this.episodes,
            isPlaying: !this.player.paused,
            isMinimized: this.audioPlayer.classList.contains('minimized'),
            coverImage: document.getElementById('podcast-cover')?.src,
            description: this.descriptionContainer?.innerHTML
        };

        // Salva lo stato nel localStorage
        localStorage.setItem('playerState', JSON.stringify(state));

        // Invia lo stato al Service Worker
        if (navigator.serviceWorker.controller) {
            navigator.serviceWorker.controller.postMessage({
                type: 'PLAYER_STATE',
                state: state
            });
        }
    }

    restorePlayerState(state = null) {
        // Se non viene fornito uno stato, prova a recuperarlo dal localStorage
        if (!state) {
            const savedState = localStorage.getItem('playerState');
            if (savedState) {
                state = JSON.parse(savedState);
            }
        }

        if (state && state.src) {
            this.player.src = state.src;
            this.player.currentTime = state.currentTime;
            this.nowPlayingTitle.textContent = state.title;
            this.currentPodcastId = state.podcastId;
            this.currentEpisodeIndex = state.episodeIndex;
            this.episodes = state.episodes;

            // Mostra il player
            this.audioPlayer.style.display = 'block';
            this.audioPlayer.classList.add('visible');

            // Ripristina lo stato minimizzato
            if (state.isMinimized) {
                this.audioPlayer.classList.add('minimized');
                const playerToggle = this.audioPlayer.querySelector('.player-toggle i');
                playerToggle.classList.remove('fa-chevron-down');
                playerToggle.classList.add('fa-chevron-up');
            }

            this.updateControls();

            // Riprendi la riproduzione se era in corso
            if (state.isPlaying) {
                const playPromise = this.player.play();
                if (playPromise !== undefined) {
                    playPromise.catch(error => {
                        console.log("Autoplay prevented:", error);
                    });
                }
            }

            if (state.coverImage) {
                document.getElementById('podcast-cover').src = state.coverImage;
            }

            // Ripristina la descrizione
            if (state.description && this.descriptionContainer) {
                this.descriptionContainer.innerHTML = state.description;
            }
        }
    }

    initializeControls() {
        // Gestione prev/next
        this.prevButton.addEventListener('click', () => this.playPrevious());
        this.nextButton.addEventListener('click', () => this.playNext());

        // Gestione click sui pulsanti play nella tabella
        document.querySelectorAll('.play-button').forEach(button => {
            button.addEventListener('click', (e) => {
                const audioUrl = e.currentTarget.dataset.audio;
                const episodeTitle = e.currentTarget.closest('tr')?.querySelector('.episode-title')?.textContent;
                const podcastId = e.currentTarget.dataset.podcastId;
                const podcastImage = e.currentTarget.dataset.podcastImage;

                if (podcastId) {
                    this.currentPodcastId = podcastId;
                    if (podcastImage) {
                        this.setPlayerBackground(podcastImage);
                    }
                    this.loadAndPlayEpisode(podcastId, audioUrl, episodeTitle);
                } else {
                    this.playEpisodeByUrl(audioUrl, episodeTitle);
                }
            });
        });

        // Gestione click sul pulsante "Ultimo Episodio"
        document.querySelectorAll('.last-episode-button').forEach(button => {
            button.addEventListener('click', async (e) => {
                e.preventDefault();
                const podcastId = e.currentTarget.getAttribute('href').split('/')[2];
                await this.loadAndPlayLatestEpisode(podcastId);
            });
        });
    }

    async loadPodcastEpisodes(podcastId) {
        try {
            console.debug('Fetching episodes for podcast:', podcastId);
            const response = await fetch(`/api/podcast/${podcastId}/episodes`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();

            // Debug dettagliato della risposta
            console.debug('API Response:', data);

            // Verifica il formato della risposta
            if (!data) {
                throw new Error('Empty response');
            }

            // La risposta ha gli episodi in data.data
            let episodes = data.data || [];
            console.debug('Raw episodes:', episodes);

            if (!Array.isArray(episodes)) {
                console.debug('Episodes is not an array, trying to convert');
                episodes = Object.values(episodes).filter(item => {
                    const isValid = item &&
                                  typeof item === 'object' &&
                                  item.title &&
                                  (item.episode_raw_url || item.audio_url);
                    if (isValid) {
                        console.debug('Found valid episode:', item);
                    }
                    return isValid;
                });
            }

            // Verifica che ci siano episodi validi
            if (episodes.length === 0) {
                console.warn('No episodes found in response');
                this.episodes = [];
                return [];
            }

            // Normalizza il formato degli episodi e ordina per data
            this.episodes = episodes
                .map(episode => ({
                    ...episode,
                    episode_raw_url: episode.episode_raw_url || episode.audio_url,
                    date: new Date(episode.date)
                }))
                .sort((a, b) => b.date - a.date); // Ordina dal più recente al più vecchio

            console.debug('Processed episodes:', this.episodes);
            console.debug('Total episodes:', this.episodes.length);
            return this.episodes;
        } catch (error) {
            console.error('Error loading episodes:', error);
            console.error('For podcast ID:', podcastId);
            this.episodes = [];
            return [];
        }
    }

    async loadAndPlayLatestEpisode(podcastId) {
        try {
            this.currentPodcastId = podcastId;

            // Prima cerchiamo le informazioni nella pagina della directory
            const podcastCard = document.querySelector(`.podcast-card a[href="/podcast/${podcastId}/episodes"]`)?.closest('.podcast-card');
            if (podcastCard) {
                console.debug('Found podcast card in directory page');
                const lastEpisodeTitle = podcastCard.querySelector('.last-episode-title')?.textContent.replace('', '').trim();

                // Invece di chiamare /last, prendiamo il primo episodio dalla lista
                const episodes = await this.loadPodcastEpisodes(podcastId);
                if (episodes.length > 0) {
                    // Otteniamo l'immagine dal data attribute del pulsante
                    const button = document.querySelector(`.last-episode-button[href="/podcast/${podcastId}/last"]`);
                    const podcastImage = button?.dataset.podcastImage;

                    if (podcastImage) {
                        this.setPlayerBackground(podcastImage);
                    }

                    // Riproduci il primo episodio (l'ultimo in ordine cronologico)
                    this.playEpisode(episodes[0]);
                    return;
                }
            }

            // Se non troviamo le informazioni nella pagina, proviamo con l'API
            console.debug('Falling back to API call');
            const episodes = await this.loadPodcastEpisodes(podcastId);

            if (!Array.isArray(episodes) || episodes.length === 0) {
                console.warn('No episodes found for podcast:', podcastId);
                return;
            }

            this.playEpisode(episodes[0]);
        } catch (error) {
            console.error('Error playing latest episode:', error);
            alert('Errore nel caricamento dell\'ultimo episodio. Riprova più tardi.');
        }
    }

    async getLastEpisodeUrl(podcastId) {
        try {
            const response = await fetch(`/api/podcast/${podcastId}/last`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            return data.episode_raw_url || data.audio_url;
        } catch (error) {
            console.error('Error fetching last episode URL:', error);
            return null;
        }
    }

    async loadAndPlayEpisode(podcastId, audioUrl, episodeTitle) {
        try {
            this.currentPodcastId = podcastId;
            const episodes = await this.loadPodcastEpisodes(podcastId);

            console.debug('Loaded episodes:', episodes.length);
            console.debug('Looking for episode with URL:', audioUrl);

            if (episodes.length > 0) {
                // Trova l'indice dell'episodio corrente
                this.currentEpisodeIndex = episodes.findIndex(ep => {
                    const matches = (ep.episode_raw_url === audioUrl || ep.audio_url === audioUrl);
                    console.debug(`Comparing episode ${ep.title}:`, {
                        episode_raw_url: ep.episode_raw_url,
                        audio_url: ep.audio_url,
                        matches: matches
                    });
                    return matches;
                });

                console.debug('Found episode at index:', this.currentEpisodeIndex);

                if (this.currentEpisodeIndex === -1) {
                    console.warn('Episode not found in list, playing as standalone');
                    this.playEpisodeByUrl(audioUrl, episodeTitle);
                } else {
                    this.playEpisode(episodes[this.currentEpisodeIndex]);
                }

                // Aggiorna i controlli dopo aver impostato l'indice
                this.updateControls();

                // Debug per verificare lo stato
                console.debug('Player state:', {
                    currentIndex: this.currentEpisodeIndex,
                    totalEpisodes: episodes.length,
                    hasPrevious: this.currentEpisodeIndex > 0,
                    hasNext: this.currentEpisodeIndex < episodes.length - 1,
                    prevButtonDisabled: this.prevButton.disabled,
                    nextButtonDisabled: this.nextButton.disabled
                });
            } else {
                console.warn('No episodes available, playing as standalone');
                this.playEpisodeByUrl(audioUrl, episodeTitle);
            }
        } catch (error) {
            console.error('Error loading and playing episode:', error);
            this.playEpisodeByUrl(audioUrl, episodeTitle);
        }
    }

    playEpisodeByUrl(url, title) {
        if (!url) {
            console.error('No URL provided for playEpisodeByUrl');
            return;
        }

        this.player.src = url;
        this.nowPlayingTitle.textContent = title || 'Episodio sconosciuto';
        this.audioPlayer.style.display = 'block';

        setTimeout(() => {
            this.audioPlayer.classList.add('visible');
            const playPromise = this.player.play();
            if (playPromise !== undefined) {
                playPromise.catch(error => {
                    console.log("Autoplay prevented:", error);
                });
            }
        }, 10);

        this.updateControls();
    }

    async loadEpisodeDescription(episodeId) {
        if (!episodeId) {
            console.warn('No episode ID provided for description loading');
            return null;
        }

        try {
            const response = await fetch(`/api/podcast/${this.currentPodcastId}/episode/${episodeId}/description`);
            if (!response.ok) {
                throw new Error('Error loading episode description');
            }
            const data = await response.json();
            return data.content_html || null;
        } catch (error) {
            console.error('Error loading episode description:', error);
            return null;
        }
    }

    async playEpisode(episode) {
        if (!episode) {
            console.error('No episode provided for playEpisode');
            return;
        }

        const url = episode.episode_raw_url || episode.audio_url;
        if (!url) {
            console.error('No URL found in episode:', episode);
            return;
        }

        // Riproduci l'episodio
        this.playEpisodeByUrl(url, episode.title);

        // Carica la descrizione se disponibile
        if (episode.ilpost_id) {
            const description = await this.loadEpisodeDescription(episode.ilpost_id);
            if (description && this.descriptionContainer) {
                this.descriptionContainer.innerHTML = description;
            } else {
                this.descriptionContainer.innerHTML = '<em>Nessuna descrizione disponibile</em>';
            }
        }
    }

    updateControls() {
        console.debug('Updating controls:', {
            episodesLength: this.episodes.length,
            currentIndex: this.currentEpisodeIndex
        });

        const hasEpisodes = this.episodes.length > 0;
        const isValidIndex = this.currentEpisodeIndex !== -1;
        const hasPrevious = hasEpisodes && isValidIndex && this.currentEpisodeIndex > 0;
        const hasNext = hasEpisodes && isValidIndex && this.currentEpisodeIndex < this.episodes.length - 1;

        console.debug('Navigation state:', {
            hasEpisodes,
            isValidIndex,
            hasPrevious,
            hasNext
        });

        // Abilita/disabilita i pulsanti
        this.prevButton.disabled = !hasPrevious;
        this.nextButton.disabled = !hasNext;

        // Aggiorna i tooltip e le classi dei pulsanti
        if (hasPrevious) {
            const prevEpisode = this.episodes[this.currentEpisodeIndex - 1];
            this.prevButton.title = `Episodio precedente: ${prevEpisode.title}`;
            this.prevButton.classList.remove('disabled');
        } else {
            this.prevButton.title = 'Nessun episodio precedente';
            this.prevButton.classList.add('disabled');
        }

        if (hasNext) {
            const nextEpisode = this.episodes[this.currentEpisodeIndex + 1];
            this.nextButton.title = `Episodio successivo: ${nextEpisode.title}`;
            this.nextButton.classList.remove('disabled');
        } else {
            this.nextButton.title = 'Nessun episodio successivo';
            this.nextButton.classList.add('disabled');
        }

        console.debug('Button state after update:', {
            prevDisabled: this.prevButton.disabled,
            nextDisabled: this.nextButton.disabled,
            prevTitle: this.prevButton.title,
            nextTitle: this.nextButton.title
        });
    }

    playPrevious() {
        if (this.currentEpisodeIndex > 0 && this.episodes.length > 0) {
            console.debug('Playing previous episode, current index:', this.currentEpisodeIndex);
            this.currentEpisodeIndex--;
            console.debug('New index:', this.currentEpisodeIndex);
            this.playEpisode(this.episodes[this.currentEpisodeIndex]);
        }
    }

    playNext() {
        if (this.currentEpisodeIndex < this.episodes.length - 1) {
            console.debug('Playing next episode, current index:', this.currentEpisodeIndex);
            this.currentEpisodeIndex++;
            console.debug('New index:', this.currentEpisodeIndex);
            this.playEpisode(this.episodes[this.currentEpisodeIndex]);
        }
    }

    setPlayerBackground(imageUrl) {
        if (imageUrl) {
            document.getElementById('podcast-cover').src = imageUrl;
        }
    }

    closePlayer() {
        this.player.pause();
        this.audioPlayer.classList.remove('visible');
        setTimeout(() => {
            this.audioPlayer.style.display = 'none';
            this.player.src = '';
            this.nowPlayingTitle.textContent = '';
            if (this.descriptionContainer) {
                this.descriptionContainer.innerHTML = '';
            }
            this.currentEpisodeIndex = -1;
            this.episodes = [];
            localStorage.removeItem('playerState');
        }, 300);
    }

    togglePlayer() {
        const playerToggle = this.audioPlayer.querySelector('.player-toggle i');
        this.audioPlayer.classList.toggle('minimized');

        if (this.audioPlayer.classList.contains('minimized')) {
            playerToggle.classList.remove('fa-chevron-down');
            playerToggle.classList.add('fa-chevron-up');
        } else {
            playerToggle.classList.remove('fa-chevron-up');
            playerToggle.classList.add('fa-chevron-down');
        }

        // Salva lo stato dopo il toggle
        this.savePlayerState();
    }
}

// Inizializza il player quando il DOM è pronto
document.addEventListener('DOMContentLoaded', () => {
    window.podcastPlayer = new PodcastPlayer();
    window.podcastPlayer.restorePlayerState();

    // Esponi le funzioni necessarie globalmente
    window.closePlayer = () => window.podcastPlayer.closePlayer();
    window.togglePlayer = () => window.podcastPlayer.togglePlayer();
});