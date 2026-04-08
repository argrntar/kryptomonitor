/**
 * price_chart.js
 *
 * Renderuje interaktywny wykres historii cen z przyciskami zakresu.
 *
 * Strategia pobierania danych:
 *   - Strona ładuje się bez danych (chart_data=[])
 *   - Zaraz po załadowaniu JS wywołuje setRange("30d") → AJAX
 *   - Każdy zakres pobierany jest przez AJAX przy pierwszym kliknięciu
 *   - Cache w pamięci – kolejne kliknięcia tego samego zakresu = 0 zapytań
 *
 * Zakresy:
 *   24h  – ostatnie 24 godziny  (filtrowane lokalnie z cache 30d)
 *   7d   – ostatnie 7 dni       (filtrowane lokalnie z cache 30d)
 *   30d  – ostatnie 30 dni      (AJAX przy wejściu na stronę)
 */

/**
 * @typedef {{ ts: number, label: string, price: number }} HistoryPoint
 * Kształt pojedynczego punktu historii zwracanego przez API.
 * ts    – timestamp Unix w sekundach
 * label – sformatowana etykieta czasu do wyświetlenia na osi X
 * price – cena w USD
 */

const appData = document.getElementById("app-data");
const COIN_ID = appData ? parseInt(appData.dataset.coinId, 10) : null;

/** @type {import('chart.js').Chart | null} */
let chart = null;

/** @type {Object.<string, HistoryPoint[]>} */
const cache = {};

const RANGE_MS = {
    "24h": 24 * 60 * 60 * 1000,
    "7d": 7 * 24 * 60 * 60 * 1000,
    "30d": 30 * 24 * 60 * 60 * 1000,
};

/**
 * Filtruje dane 30d do mniejszego zakresu lokalnie – bez AJAX.
 * @param {HistoryPoint[]} data30d  pełne dane 30-dniowe z cache
 * @param {string} range            "24h" | "7d"
 * @returns {HistoryPoint[]}
 */
function filterFromCache(data30d, range) {
    const cutoff = Date.now() - RANGE_MS[range];
    return data30d.filter(d => d.ts * 1000 >= cutoff);  // ts w sekundach → ms
}


// ---------------------------------------------------------------------------
// Pobieranie danych
// ---------------------------------------------------------------------------

/**
 * Zwraca dane dla zakresu – z cache lub przez AJAX.
 * Jeśli cache["30d"] istnieje, mniejsze zakresy filtruje lokalnie.
 * @param {string} range  "24h" | "7d" | "30d"
 * @returns {Promise<HistoryPoint[]>}
 */
async function getData(range) {
    // Mamy 30d w cache – wylicz mniejszy zakres lokalnie, 0 zapytań do serwera
    if (range !== "30d" && cache["30d"]) {
        return filterFromCache(cache["30d"], range);
    }

    if (cache[range]) return cache[range];

    const response = await fetch(`/coins/${COIN_ID}/history?range=${range}`);
    if (!response.ok) {
        console.error(`Błąd pobierania historii ${range}: ${response.status}`);
        return [];
    }
    cache[range] = await response.json();
    return cache[range];
}


// ---------------------------------------------------------------------------
// Renderowanie wykresu
// ---------------------------------------------------------------------------

// Jedna instancja formatera – reużywana przy każdym ticku osi Y
const numFormat = new Intl.NumberFormat("en-US");

/**
 * Formatuje wartość ticku osi Y z prefiksem $.
 * @param {number} v
 * @returns {string}
 */
const formatYTick = v => {
    if (v >= 1000) return "$" + numFormat.format(v);
    if (v < 1) return "$" + v.toFixed(4);
    return "$" + v.toFixed(2);
};

/**
 * Tworzy lub aktualizuje wykres Chart.js.
 * Przy pierwszym wywołaniu tworzy instancję,
 * przy kolejnych aktualizuje dane bez przebudowy canvasu.
 * @param {HistoryPoint[]} data  lista punktów historii ceny
 */
function renderChart(data) {
    const labels = data.map(d => d.label);
    const prices = data.map(d => d.price);

    // Aktualizuj licznik punktów – String() bo textContent wymaga stringa
    const counter = document.getElementById("history-count");
    if (counter) counter.textContent = String(data.length);

    const canvas = document.getElementById("priceChart");
    if (!canvas) return;

    const isUp = prices.length >= 2 ? prices[prices.length - 1] >= prices[0] : true;
    const color = isUp ? "#00c896" : "#ff4d4d";
    const colorFade = isUp ? "rgba(0,200,150,0.12)" : "rgba(255,77,77,0.12)";

    // Aktualizuj istniejący wykres bez destroy – płynniejsza zmiana zakresu
    if (chart) {
        chart.data.labels = labels;
        chart.data.datasets[0].data = prices;
        chart.data.datasets[0].borderColor = color;
        chart.update();   // bez argumentu – Chart.js aktualizuje z domyślną animacją
        return;
    }

    // Pierwsze renderowanie – utwórz instancję Chart
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const gradientFn = (/** @type {{ chart: { ctx: CanvasRenderingContext2D }}} */ context) => {
        const g = context.chart.ctx.createLinearGradient(0, 0, 0, 300);
        g.addColorStop(0, colorFade);
        g.addColorStop(1, "transparent");
        return g;
    };

    chart = new Chart(ctx, {
        type: "line",
        data: {
            labels,
            datasets: [{
                label: "Cena (USD)",
                data: prices,
                borderColor: color,
                borderWidth: 2,
                pointRadius: 0,
                pointHoverRadius: 0,
                fill: true,
                backgroundColor: gradientFn,
                tension: 0.3,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {mode: "index", intersect: false},
            plugins: {
                legend: {display: false},
                tooltip: {
                    callbacks: {
                        label: tooltipCtx => {
                            const v = tooltipCtx.parsed.y;
                            return " $" + (v < 1
                                    ? v.toFixed(6)
                                    : v.toLocaleString("en-US", {
                                        minimumFractionDigits: 2,
                                        maximumFractionDigits: 2,
                                    })
                            );
                        },
                    },
                },
            },
            scales: {
                x: {
                    ticks: {
                        maxTicksLimit: 8,
                        maxRotation: 0,
                        color: "#888",
                        font: {size: 11},
                    },
                    grid: {color: "rgba(255,255,255,0.05)"},
                },
                y: {
                    position: "right",
                    ticks: {
                        color: "#888",
                        font: {size: 11},
                        callback: formatYTick,
                    },
                    grid: {color: "rgba(255,255,255,0.05)"},
                },
            },
        },
    });
}


// ---------------------------------------------------------------------------
// Obsługa przycisków zakresu
// ---------------------------------------------------------------------------

/**
 * Przełącza aktywny zakres – pobiera dane (cache lub AJAX) i aktualizuje wykres.
 * @param {string} range  "24h" | "7d" | "30d"
 * @returns {Promise<void>}
 */
async function setRange(range) {
    document.querySelectorAll(".range-btn").forEach(btn => {
        btn.classList.toggle("active", btn.dataset.range === range);
    });

    if (!cache[range]) {
        const counter = document.getElementById("history-count");
        if (counter) counter.textContent = "…";
    }

    const data = await getData(range);
    renderChart(data);
}


// ---------------------------------------------------------------------------
// Inicjalizacja – odpala się gdy skrypt się załaduje (po DOM)
// ---------------------------------------------------------------------------

document.querySelectorAll(".range-btn").forEach(btn => {
    btn.addEventListener("click", () => {
        setRange(btn.dataset.range).catch(err =>
            console.error("Błąd zmiany zakresu:", err)
        );
    });
});

// Domyślny zakres 30d – pobiera wszystkie dane, mniejsze zakresy filtrowane lokalnie
setRange("30d").catch(err => console.error("Błąd inicjalizacji wykresu:", err));
