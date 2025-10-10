document.addEventListener('DOMContentLoaded', function () {
    const form = document.querySelector('form');
    const loadingIndicator = document.querySelector('[data-loading]');

    form.addEventListener('submit', function (e) {
        // Show loading spinner when the form is submitted
        loadingIndicator.style.display = 'block';
    });
});
