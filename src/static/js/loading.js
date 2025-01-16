class LoadingBar {
    constructor() {
        this.container = document.createElement('div');
        this.container.className = 'loading-container loading-hidden';
        this.bar = document.createElement('div');
        this.bar.className = 'loading-bar';
        this.container.appendChild(this.bar);
        document.body.appendChild(this.container);

        this.progress = 0;
        this.loadingItems = new Set();
        this.isVisible = false;
    }

    show() {
        if (!this.isVisible) {
            this.container.classList.remove('loading-hidden');
            document.querySelector('main').classList.add('content-loading');
            this.isVisible = true;
        }
    }

    hide() {
        if (this.isVisible) {
            this.container.classList.add('loading-hidden');
            document.querySelector('main').classList.remove('content-loading');
            this.isVisible = false;
            setTimeout(() => {
                this.progress = 0;
                this.bar.style.width = '0%';
            }, 300);
        }
    }

    addItem(id) {
        this.loadingItems.add(id);
        this.show();
        this.updateProgress();
    }

    removeItem(id) {
        this.loadingItems.delete(id);
        this.updateProgress();
        if (this.loadingItems.size === 0) {
            this.hide();
        }
    }

    updateProgress() {
        const totalItems = this.loadingItems.size;
        if (totalItems === 0) {
            this.progress = 100;
        } else {
            // Start with 30% progress when items are added
            this.progress = Math.max(30, 100 - (totalItems * 20));
        }
        this.bar.style.width = `${this.progress}%`;
    }
}

// Create global loading bar instance
const loadingBar = new LoadingBar();

// Intercept fetch requests to show loading bar
const originalFetch = window.fetch;
window.fetch = function(...args) {
    const requestId = Math.random().toString(36);
    loadingBar.addItem(requestId);

    return originalFetch.apply(this, args)
        .then(response => {
            loadingBar.removeItem(requestId);
            return response;
        })
        .catch(error => {
            loadingBar.removeItem(requestId);
            throw error;
        });
};