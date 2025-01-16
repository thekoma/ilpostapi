// Service Worker per il player audio
self.addEventListener('install', (event) => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(clients.claim());
});

// Gestione dei messaggi dal player
self.addEventListener('message', (event) => {
    if (event.data.type === 'PLAYER_STATE') {
        // Broadcast dello stato del player a tutti i client
        self.clients.matchAll().then(clients => {
            clients.forEach(client => {
                if (client.id !== event.source.id) {
                    client.postMessage({
                        type: 'PLAYER_STATE_UPDATE',
                        state: event.data.state
                    });
                }
            });
        });
    }
});