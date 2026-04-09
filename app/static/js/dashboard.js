document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('confirm-modal');
    const closeAllForm = document.getElementById('close-all-form');

    const openBtn = document.querySelector('[data-action="open-confirm"]');
    const cancelBtn = document.querySelector('[data-action="cancel-confirm"]');
    const submitBtn = document.querySelector('[data-action="submit-confirm"]');

    if (openBtn) openBtn.addEventListener('click', () => modal.style.display = 'flex');
    if (cancelBtn) cancelBtn.addEventListener('click', () => modal.style.display = 'none');
    if (submitBtn) submitBtn.addEventListener('click', () => closeAllForm.submit());
});