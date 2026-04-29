function renderCard(cardStr) {
    const rank = cardStr[0];
    const suit = cardStr[1];
    const isRed = suit === 'h' || suit === 'd';
    const className = isRed ? 'card-pill red' : 'card-pill black';
    return `<span class="${className}">${cardStr}</span>`;
}

function renderHand(cards) {
    return `<div class="hand-pills">${cards.map(renderCard).join('')}</div>`;
}

function renderDisparityBar(disparity) {
    const isPositiveEdge = disparity < 0;
    const barClass = isPositiveEdge ? 'positive-edge' : 'negative-edge';
    const valueClass = isPositiveEdge ? 'positive-edge' : 'negative-edge';
    const badgeClass = isPositiveEdge ? '' : 'negative';
    const badge = isPositiveEdge ? '+EV' : '-EV';

    // Scale bar width (max 100px)
    const maxWidth = 100;
    const width = Math.min(Math.abs(disparity) * 2, maxWidth);

    return `
        <div class="disparity-cell">
            <div class="disparity-bar ${barClass}" style="width: ${width}px;"></div>
            <span class="disparity-value ${valueClass}">${disparity.toFixed(2)}</span>
            <span class="ev-badge ${badgeClass}">${badge}</span>
        </div>
    `;
}

async function runAnalysis() {
    const input = document.getElementById('handsInput').value;
    const runButton = document.getElementById('runButton');
    const errorMessage = document.getElementById('errorMessage');
    const loadingState = document.getElementById('loadingState');
    const statusStrip = document.getElementById('statusStrip');
    const resultsTable = document.getElementById('resultsTable');
    const bottomCards = document.getElementById('bottomCards');

    // Reset UI
    errorMessage.classList.add('hidden');
    statusStrip.classList.add('hidden');
    resultsTable.classList.add('hidden');
    bottomCards.classList.add('hidden');
    loadingState.classList.remove('hidden');
    runButton.disabled = true;

    try {
        const response = await fetch('/api/equity/analyze', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ text: input })
        });

        const data = await response.json();

        if (!data.ok) {
            throw new Error(data.error || 'Analysis failed');
        }

        // Update status strip
        document.getElementById('statusValue').textContent = data.status;
        document.getElementById('streetValue').textContent = data.street;
        document.getElementById('pairCountValue').textContent = data.pair_count;
        document.getElementById('cpuCoresValue').textContent = data.cpu_cores;
        document.getElementById('runtimeValue').textContent = `${data.runtime_seconds}s`;
        statusStrip.classList.remove('hidden');

        // Render results table
        const tbody = document.getElementById('resultsBody');
        tbody.innerHTML = '';

        data.rows.forEach(row => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${row.rank}</td>
                <td>${row.pair_no}</td>
                <td>
                    ${renderHand(row.buy_hand)}
                    <span class="player-name">${row.buy_player}</span>
                </td>
                <td>
                    ${renderHand(row.reverse_hand)}
                    <span class="player-name">${row.reverse_player}</span>
                </td>
                <td>${row.price.toFixed(2)}%</td>
                <td>${row.rev_buy_hit.toFixed(2)}%</td>
                <td>${renderDisparityBar(row.disparity)}</td>
                <td>${row.rev_price.toFixed(2)}%</td>
                <td>${row.hitrate.toFixed(2)}%</td>
            `;
            tbody.appendChild(tr);
        });

        resultsTable.classList.remove('hidden');

        // Render bottom cards
        if (data.best_buy) {
            document.getElementById('bestBuyDetails').innerHTML = `
                <div class="result-detail">
                    <span class="result-detail-label">Pair #</span>
                    <span class="result-detail-value">${data.best_buy.pair_no}</span>
                </div>
                <div class="result-detail">
                    <span class="result-detail-label">Buy</span>
                    <span class="result-detail-value">${renderHand(data.best_buy.buy_hand)} ${data.best_buy.buy_player}</span>
                </div>
                <div class="result-detail">
                    <span class="result-detail-label">vs</span>
                    <span class="result-detail-value">${renderHand(data.best_buy.reverse_hand)} ${data.best_buy.reverse_player}</span>
                </div>
                <div class="result-detail">
                    <span class="result-detail-label">Disparity</span>
                    <span class="result-detail-value" style="color: #10b981;">${data.best_buy.disparity.toFixed(2)}</span>
                </div>
            `;
        }

        if (data.worst_buy) {
            document.getElementById('worstBuyDetails').innerHTML = `
                <div class="result-detail">
                    <span class="result-detail-label">Pair #</span>
                    <span class="result-detail-value">${data.worst_buy.pair_no}</span>
                </div>
                <div class="result-detail">
                    <span class="result-detail-label">Buy</span>
                    <span class="result-detail-value">${renderHand(data.worst_buy.buy_hand)} ${data.worst_buy.buy_player}</span>
                </div>
                <div class="result-detail">
                    <span class="result-detail-label">vs</span>
                    <span class="result-detail-value">${renderHand(data.worst_buy.reverse_hand)} ${data.worst_buy.reverse_player}</span>
                </div>
                <div class="result-detail">
                    <span class="result-detail-label">Disparity</span>
                    <span class="result-detail-value" style="color: #ef4444;">${data.worst_buy.disparity.toFixed(2)}</span>
                </div>
            `;
        }

        bottomCards.classList.remove('hidden');

    } catch (error) {
        errorMessage.textContent = `Error: ${error.message}`;
        errorMessage.classList.remove('hidden');
    } finally {
        loadingState.classList.add('hidden');
        runButton.disabled = false;
    }
}
