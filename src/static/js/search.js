function calculateScore(text, searchTerm) {
    text = text.toLowerCase();
    searchTerm = searchTerm.toLowerCase();
    
    // Match esatto nel testo
    if (text.includes(searchTerm)) {
        return 3;
    }
    
    // Match parziale (parole che iniziano con il termine di ricerca)
    const words = text.split(/\s+/);
    for (let word of words) {
        if (word.startsWith(searchTerm)) {
            return 2;
        }
    }
    
    // Fuzzy match come fallback
    let searchIndex = 0;
    for (let i = 0; i < text.length && searchIndex < searchTerm.length; i++) {
        if (text[i] === searchTerm[searchIndex]) {
            searchIndex++;
        }
    }
    return searchIndex === searchTerm.length ? 1 : 0;
}

function searchPodcasts(searchTerm) {
    const podcastCards = document.querySelectorAll('.podcast-card');
    
    if (!searchTerm.trim()) {
        podcastCards.forEach(card => card.classList.remove('hidden'));
        return;
    }
    
    podcastCards.forEach(card => {
        const title = card.querySelector('h2').textContent;
        const author = card.querySelector('.author').textContent;
        const description = card.querySelector('.description').textContent;
        
        // Diamo più peso al titolo
        const titleScore = calculateScore(title, searchTerm) * 3;
        const authorScore = calculateScore(author, searchTerm) * 2;
        const descriptionScore = calculateScore(description, searchTerm);
        
        const totalScore = titleScore + authorScore + descriptionScore;
        
        if (totalScore > 0) {
            card.classList.remove('hidden');
            // Opzionalmente, possiamo usare il punteggio per ordinare i risultati
            card.style.order = -totalScore; // I punteggi più alti appaiono prima
        } else {
            card.classList.add('hidden');
        }
    });
}

document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.getElementById('podcast-search');
    const podcastGrid = document.querySelector('.podcast-grid');
    
    // Abilita il riordinamento dei risultati
    podcastGrid.style.display = 'grid';
    
    searchInput.addEventListener('input', function(e) {
        searchPodcasts(e.target.value);
    });
}); 