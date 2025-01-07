class PodcastPlayer {
    constructor() {
        this.player = document.getElementById('player');
        this.nowPlayingTitle = document.getElementById('now-playing-title');
        this.prevButton = document.getElementById('prev-episode');
        this.nextButton = document.getElementById('next-episode');
        this.currentEpisodeIndex = -1;
        this.currentPodcastId = null;
        this.episodes = [];
        
        // Ripristina lo stato del player
        this.restorePlayerState();
        
        // Salva lo stato periodicamente
        setInterval(() => this.savePlayerState(), 1000);
        
        // Salva lo stato quando il player viene messo in pausa o riparte
        this.player.addEventListener('play', () => this.savePlayerState());
        this.player.addEventListener('pause', () => this.savePlayerState());
        
        // Salva lo stato prima di lasciare la pagina
        window.addEventListener('beforeunload', () => this.savePlayerState());
        
        this.initializeControls();
        
        // Aggiungi il metodo per chiudere il player
        this.closePlayer = this.closePlayer.bind(this);
        window.closePlayer = () => this.closePlayer();
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
            isMinimized: document.getElementById('audio-player').classList.contains('minimized'),
            backgroundImage: document.getElementById('audio-player').style.getPropertyValue('--background-image'),
            coverImage: document.getElementById('podcast-cover').src
        };
        localStorage.setItem('playerState', JSON.stringify(state));
    }
    
    restorePlayerState() {
        const savedState = localStorage.getItem('playerState');
        if (savedState) {
            const state = JSON.parse(savedState);
            
            // Ripristina lo stato del player
            if (state.src) {
                this.player.src = state.src;
                this.player.currentTime = state.currentTime;
                this.nowPlayingTitle.textContent = state.title;
                this.currentPodcastId = state.podcastId;
                this.currentEpisodeIndex = state.episodeIndex;
                this.episodes = state.episodes;
                
                // Mostra il player
                const audioPlayer = document.getElementById('audio-player');
                audioPlayer.classList.add('visible');
                
                // Ripristina lo stato minimizzato
                if (state.isMinimized) {
                    audioPlayer.classList.add('minimized');
                    audioPlayer.querySelector('.player-toggle i').classList.add('fa-chevron-up');
                    audioPlayer.querySelector('.player-toggle i').classList.remove('fa-chevron-down');
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

                if (state.backgroundImage) {
                    this.setPlayerBackground(state.backgroundImage);
                }

                if (state.coverImage) {
                    document.getElementById('podcast-cover').src = state.coverImage;
                }
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
        const response = await fetch(`/api/podcast/${podcastId}/episodes`);
        const data = await response.json();
        this.episodes = data.episodes;
        return this.episodes;
    }
    
    async loadAndPlayLatestEpisode(podcastId) {
        this.currentPodcastId = podcastId;
        const episodes = await this.loadPodcastEpisodes(podcastId);
        if (episodes.length > 0) {
            // Otteniamo l'immagine dal data attribute del pulsante
            const button = document.querySelector(`.last-episode-button[href="/podcast/${podcastId}/last"]`);
            const podcastImage = button?.dataset.podcastImage;
            
            if (podcastImage) {
                this.setPlayerBackground(podcastImage);
            }
            this.playEpisode(episodes[0]);
        }
    }
    
    async loadAndPlayEpisode(podcastId, audioUrl, episodeTitle) {
        await this.loadPodcastEpisodes(podcastId);
        // Trova l'immagine del podcast
        const podcastImage = document.querySelector(`.podcast-card img[src*="${podcastId}"]`)?.src;
        if (podcastImage) {
            this.setPlayerBackground(podcastImage);
        }
        this.playEpisodeByUrl(audioUrl, episodeTitle);
    }
    
    playEpisodeByUrl(audioUrl, episodeTitle) {
        this.player.src = audioUrl;
        this.player.play();
        this.nowPlayingTitle.textContent = `In riproduzione: ${episodeTitle}`;
        document.getElementById('audio-player').classList.add('visible');
        
        if (this.episodes.length > 0) {
            this.currentEpisodeIndex = this.episodes.findIndex(e => e.episode_raw_url === audioUrl);
            this.updateControls();
        }
    }
    
    playEpisode(episode) {
        this.playEpisodeByUrl(episode.episode_raw_url, episode.title);
    }
    
    updateControls() {
        this.prevButton.disabled = this.currentEpisodeIndex >= this.episodes.length - 1;
        this.nextButton.disabled = this.currentEpisodeIndex <= 0;
        
        if (!this.prevButton.disabled) {
            this.prevButton.setAttribute('title', 
                `Episodio precedente: ${this.episodes[this.currentEpisodeIndex + 1].title}`);
        } else {
            this.prevButton.removeAttribute('title');
        }
        
        if (!this.nextButton.disabled) {
            this.nextButton.setAttribute('title', 
                `Episodio successivo: ${this.episodes[this.currentEpisodeIndex - 1].title}`);
        } else {
            this.nextButton.removeAttribute('title');
        }
    }
    
    playPrevious() {
        if (this.currentPodcastId && this.currentEpisodeIndex < this.episodes.length - 1) {
            this.playEpisode(this.episodes[this.currentEpisodeIndex + 1]);
        }
    }
    
    playNext() {
        if (this.currentPodcastId && this.currentEpisodeIndex > 0) {
            this.playEpisode(this.episodes[this.currentEpisodeIndex - 1]);
        }
    }

    setPlayerBackground(imageUrl) {
        if (!imageUrl) return;
        
        const audioPlayer = document.getElementById('audio-player');
        const podcastCover = document.getElementById('podcast-cover');
        
        // Impostiamo sia lo sfondo sfocato che la thumbnail
        audioPlayer.style.setProperty('--background-image', `url("${imageUrl}")`);
        podcastCover.src = imageUrl;
        podcastCover.alt = this.nowPlayingTitle.textContent;

        // Mostriamo la thumbnail
        document.querySelector('.podcast-thumbnail').style.display = 'block';
    }
    
    closePlayer() {
        // Ferma la riproduzione
        this.player.pause();
        this.player.currentTime = 0;
        
        // Nascondi il player
        const audioPlayer = document.getElementById('audio-player');
        audioPlayer.classList.remove('visible');
        audioPlayer.classList.remove('minimized');
        
        // Reset dello stato
        this.nowPlayingTitle.textContent = '';
        this.currentEpisodeIndex = -1;
        this.currentPodcastId = null;
        
        // Pulisci il localStorage
        localStorage.removeItem('playerState');
    }
}

// Inizializza il player quando il DOM è pronto
document.addEventListener('DOMContentLoaded', () => {
    new PodcastPlayer();
}); 