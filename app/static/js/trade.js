document.addEventListener('DOMContentLoaded', function () {
    const price = parseFloat(document.getElementById("trade-data").dataset.price);
    const buyInput = document.getElementById("buy-amount");
    const buyPreview = document.getElementById("buy-cost-preview");
    const sellInput = document.getElementById("sell-amount");
    const sellPreview = document.getElementById("sell-value-preview");

    buyInput.addEventListener("input", () => {
        const amt = parseFloat(buyInput.value.replace(",", "."));
        if (!isNaN(amt) && amt > 0) {
            const cost = amt * price;
            buyPreview.textContent = `≈ $${cost.toLocaleString("en-US", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            })}`;
        } else {
            buyPreview.textContent = "";
        }
    });

    sellInput.addEventListener("input", () => {
        const amt = parseFloat(sellInput.value.replace(",", "."));
        if (!isNaN(amt) && amt > 0) {
            const value = amt * price;
            sellPreview.textContent = `≈ $${value.toLocaleString("en-US", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            })}`;
        } else {
            sellPreview.textContent = "";
        }
    });
});