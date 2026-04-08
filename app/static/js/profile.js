// Obsługa modalu potwierdzenia usunięcia konta
document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('delete-modal');

    document.getElementById('open-delete-modal').addEventListener('click', function () {
        modal.style.display = 'flex';
    });

    document.getElementById('close-delete-modal').addEventListener('click', function () {
        modal.style.display = 'none';
    });
});