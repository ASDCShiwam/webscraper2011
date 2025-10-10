document.addEventListener('DOMContentLoaded', () => {
    const form = document.querySelector('[data-loading-form]');
    if (!form) {
        return;
    }

    const loadingIndicator = form.querySelector('[data-loading-indicator]');
    const submitButton = form.querySelector('[data-loading-button]');

    form.addEventListener('submit', () => {
        if (loadingIndicator) {
            loadingIndicator.hidden = false;
        }

        if (submitButton) {
            submitButton.disabled = true;
            submitButton.dataset.originalText = submitButton.textContent;
            submitButton.textContent = 'Scraping…';
        }
    });
});
