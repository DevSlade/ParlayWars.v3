/**
 * ParlayWars v3 — Simulator Module (rewritten 2026-02-25)
 *
 * Paper trading UI: bankroll + drawdown chart, bet grade pills, recovery mode
 * banner, compound growth projection card, engine breakdown table, recent bets.
 */

/** @type {Chart|null} */
let _bankrollChart = null;

/** Fetch sim data and build the entire UI. */
function renderSim() {
  const root = document.getElementById('sim-root');
  if (!root) return;
  root.innerHTML = `<div class="loading-overlay"><div class="spinner"></div><span>Loading simulator...</span></div>`;

  Promise.all([
    apiGet('/api/sim'),
    apiGet('/api/calibration').catch(() => ({ engines: {}, overall_status: 'UNKNOWN' })),
  ]).then(([sim, cal]) => {
    _buildSimHTML(root, sim, cal);
  }).catch(err => {
    root.innerHTML = `<div class="loading-overlay" style="color:var(--loss-color)">Error: ${err.message}</div>`;
  });
}

/**
 * Build the complete simulator HTML and charts.
 * @param {HTMLElement} root
 * @param {Object} sim  - /api/sim response
 * @param {Object} cal  - /api/calibration response
 */
function _buildSimHTML(root, sim, cal) {
  const s = sim.summary || {};
  const bankroll   = sim.bankroll || 1000;
  const starting   = sim.starting_bankroll || 1000;
  const pl         = s.total_pl || 0;
  const plColor    = pl >= 0 ? 'var(--win-color)' : 'var(--loss-color)';
  const plSign     = pl >= 0 ? '+' : '';
  const inRecovery = sim.recovery_mode === true;

  // ── Recovery mode banner ────────────────────────────────────────────────
  const recoveryBanner = inRecovery ? `
    <div style="background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.5);
      border-radius:var(--radius);padding:12px 16px;margin-bottom:var(--gap);
      display:flex;align-items:center;gap:10px">
      <span style="font-size:20px">⚠️</span>
      <div>
        <div style="font-weight:700;color:#ef4444">RECOVERY MODE ACTIVE</div>
        <div style="font-size:12px;color:var(--text-secondary)">
          Flat betting 2% per bet — LOCK picks only until bankroll recovers.
        </div>
      </div>
    </div>` : '';

  // ── Stat cards ────────────────────────────────────────────────────────
  const statCards = [
    { icon: '💰', label: 'Bankroll',   value: '$' + bankroll.toFixed(2) },
    { icon: '📈', label: 'Total P/L',  value: plSign + '$' + pl.toFixed(2), color: plColor },
    { icon: '🎯', label: 'Win Rate',   value: ((s.win_rate || 0) * 100).toFixed(1) + '%' },
    {
      icon: '🔥', label: 'Streak',
      value: (s.current_streak || 0) > 0 ? '+' + s.current_streak : (s.current_streak || 0),
    },
    { icon: '📉', label: 'Max DD',     value: '$' + (s.max_drawdown || 0).toFixed(2) },
    {
      icon: '📊', label: 'ROI',
      value: (s.roi_pct || 0).toFixed(2) + '%',
      color: pl >= 0 ? 'var(--win-color)' : 'var(--loss-color)',
    },
    { icon: '🎲', label: 'Total Bets', value: s.total_bets || 0 },
  ];

  const statsHTML = statCards.map(sc => `
    <div class="card" style="text-align:center">
      <div style="font-size:22px">${sc.icon}</div>
      <div class="stat-number" style="font-size:20px;${sc.color ? 'color:' + sc.color : ''}">${sc.value}</div>
      <div class="stat-label">${sc.label}</div>
    </div>
  `).join('');

  // ── Bet grade distribution ────────────────────────────────────────────
  const grades = sim.bet_grades || {};
  const gradeConfig = {
    'A+': { bg: 'rgba(16,185,129,0.2)', border: '#10b981', text: '#10b981' },
    'A':  { bg: 'rgba(105,240,174,0.2)', border: '#69f0ae', text: '#69f0ae' },
    'B':  { bg: 'rgba(59,130,246,0.2)', border: '#3b82f6', text: '#3b82f6' },
    'C':  { bg: 'rgba(245,158,11,0.2)', border: '#f59e0b', text: '#f59e0b' },
    'F':  { bg: 'rgba(239,68,68,0.2)', border: '#ef4444', text: '#ef4444' },
  };
  const gradesHTML = Object.entries(gradeConfig).map(([g, cfg]) => `
    <div style="display:flex;align-items:center;gap:6px;padding:6px 12px;
      background:${cfg.bg};border:1px solid ${cfg.border};border-radius:20px">
      <span style="font-weight:700;color:${cfg.text}">${g}</span>
      <span style="font-size:13px;color:var(--text-secondary)">${grades[g] || 0}</span>
    </div>
  `).join('');

  // ── Compound growth projection ────────────────────────────────────────
  const proj = sim.growth_projection || {};
  const projHTML = `
    <div class="card" style="margin-bottom:var(--gap)">
      <div class="card-title" style="margin-bottom:12px">📊 Growth Projection</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px">
        ${[
          ['Daily ROI', (proj.daily_roi_pct || 0).toFixed(3) + '%'],
          ['30d Est.',  '$' + (proj.projection_30d || bankroll).toFixed(2)],
          ['60d Est.',  '$' + (proj.projection_60d || bankroll).toFixed(2)],
          ['90d Est.',  '$' + (proj.projection_90d || bankroll).toFixed(2)],
          ['CAGR',      (proj.cagr_pct || 0).toFixed(1) + '%'],
        ].map(([label, val]) => `
          <div style="text-align:center;padding:10px;background:var(--bg-hover);border-radius:var(--radius-sm)">
            <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase">${label}</div>
            <div style="font-size:16px;font-weight:700;margin-top:4px">${val}</div>
          </div>
        `).join('')}
      </div>
    </div>`;

  // ── Engine breakdown table ────────────────────────────────────────────
  const breakdown = sim.engine_breakdown || {};
  const breakdownHTML = Object.entries(breakdown).map(([eng, d]) => `
    <tr>
      <td><span class="engine-name" style="color:var(--${eng.toLowerCase()}-color,var(--accent))">${eng}</span></td>
      <td>${d.bets}</td>
      <td>${d.wins}</td>
      <td>${(d.win_rate * 100).toFixed(1)}%</td>
      <td style="color:${d.pl >= 0 ? 'var(--win-color)' : 'var(--loss-color)'}">
        ${d.pl >= 0 ? '+' : ''}$${d.pl.toFixed(2)}
      </td>
    </tr>
  `).join('') || '<tr><td colspan="5" style="text-align:center;color:var(--text-muted)">No bets placed yet</td></tr>';

  // ── Recent bets table ─────────────────────────────────────────────────
  const betsHTML = (sim.recent_bets || []).map(b => {
    const gradeVal = b.grade || '';
    const gc = gradeConfig[gradeVal] || {};
    const gradePill = gradeVal
      ? `<span style="padding:1px 6px;border-radius:10px;font-size:10px;
           background:${gc.bg};color:${gc.text};border:1px solid ${gc.border}">${gradeVal}</span>`
      : '';
    return `
      <tr>
        <td style="font-size:11px;color:var(--text-muted)">${(b.placed_at || '').slice(0, 16)}</td>
        <td>${b.predicted_winner || '?'}</td>
        <td>$${(b.stake || 0).toFixed(2)}</td>
        <td>${b.odds_american > 0 ? '+' : ''}${b.odds_american || 0}</td>
        <td>
          <span class="tier-badge ${
            b.status === 'won' ? 'tier-HIGH' : b.status === 'lost' ? 'tier-LOW' : 'tier-MEDIUM'
          }">${b.status || 'pending'}</span>
        </td>
        <td style="color:${(b.profit_loss || 0) >= 0 ? 'var(--win-color)' : 'var(--loss-color)'}">
          ${b.profit_loss != null ? ((b.profit_loss >= 0 ? '+' : '') + '$' + b.profit_loss.toFixed(2)) : '—'}
        </td>
        <td>${gradePill}</td>
      </tr>
    `;
  }).join('') || '<tr><td colspan="7" style="text-align:center;color:var(--text-muted)">No bets placed yet</td></tr>';

  root.innerHTML = `
    <div class="section-header">
      <div>
        <div class="section-title">💰 Paper Trading Simulator</div>
        <div class="section-subtitle">Quarter-Kelly sizing • Auto-bets on engine predictions • Settles on real results</div>
      </div>
      <button class="btn btn-secondary" onclick="renderSim()">🔄 Refresh</button>
    </div>

    ${recoveryBanner}

    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:var(--gap-sm);margin-bottom:var(--gap)">
      ${statsHTML}
    </div>

    <!-- Bet grade distribution -->
    <div class="card" style="margin-bottom:var(--gap)">
      <div class="card-title" style="margin-bottom:10px">🏅 Bet Grade Distribution</div>
      <div style="display:flex;flex-wrap:wrap;gap:8px">${gradesHTML}</div>
    </div>

    ${projHTML}

    <div class="grid-2" style="margin-bottom:var(--gap)">
      <!-- Bankroll + drawdown chart -->
      <div class="card">
        <div class="card-title" style="margin-bottom:12px">📈 Bankroll & Drawdown</div>
        <canvas id="bankroll-main-chart" height="200"></canvas>
      </div>
      <!-- Engine breakdown -->
      <div class="card">
        <div class="card-title" style="margin-bottom:12px">⚙️ Engine Breakdown</div>
        <table class="data-table">
          <thead><tr><th>Engine</th><th>Bets</th><th>W</th><th>WR%</th><th>P/L</th></tr></thead>
          <tbody>${breakdownHTML}</tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <div class="card-title" style="margin-bottom:12px">📋 Recent Bets</div>
      <div style="overflow-x:auto">
        <table class="data-table">
          <thead><tr><th>Time</th><th>Pick</th><th>Stake</th><th>Odds</th><th>Status</th><th>P/L</th><th>Grade</th></tr></thead>
          <tbody>${betsHTML}</tbody>
        </table>
      </div>
    </div>
  `;

  // ── Render bankroll + drawdown chart ─────────────────────────────────
  const canvas = document.getElementById('bankroll-main-chart');
  if (canvas && window.Chart) {
    const chartData = (sim.bankroll_chart || []).slice(-100);
    const labels = chartData.map((d, i) => i % 10 === 0 ? (d.ts || '').slice(11, 16) : '');
    const balanceValues = chartData.map(d => d.balance);
    const peakValues    = chartData.map(d => d.peak || d.balance);
    const drawdownVals  = chartData.map(d => (d.peak || d.balance) - d.drawdown);

    if (!balanceValues.length) {
      balanceValues.push(starting);
      labels.push('Start');
      peakValues.push(starting);
      drawdownVals.push(starting);
    }

    const isProfit = balanceValues[balanceValues.length - 1] >= starting;

    if (_bankrollChart) _bankrollChart.destroy();
    _bankrollChart = new Chart(canvas, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: 'Bankroll',
            data: balanceValues,
            borderColor: isProfit ? '#69f0ae' : '#ff5252',
            backgroundColor: isProfit ? 'rgba(105,240,174,0.08)' : 'rgba(255,82,82,0.08)',
            borderWidth: 2,
            fill: false,
            tension: 0.4,
            pointRadius: 0,
            order: 1,
          },
          {
            label: 'Peak',
            data: peakValues,
            borderColor: 'rgba(139,92,246,0.5)',
            borderDash: [4, 4],
            borderWidth: 1,
            fill: false,
            tension: 0,
            pointRadius: 0,
            order: 2,
          },
          {
            label: 'Drawdown Floor',
            data: drawdownVals,
            borderColor: 'rgba(239,68,68,0)',
            backgroundColor: 'rgba(239,68,68,0.18)',
            borderWidth: 0,
            fill: '+1',           // fill between this dataset and the peak dataset
            tension: 0.4,
            pointRadius: 0,
            order: 3,
          },
        ],
      },
      options: {
        responsive: true,
        plugins: {
          legend: {
            display: true,
            labels: { color: '#8892b0', boxWidth: 12, font: { size: 10 } },
          },
          tooltip: {
            callbacks: {
              label: ctx => `${ctx.dataset.label}: $${ctx.parsed.y.toFixed(2)}`,
            },
          },
        },
        scales: {
          x: { display: false },
          y: {
            ticks: { color: '#8892b0', callback: v => '$' + v.toFixed(0) },
            grid: { color: 'rgba(42,58,92,0.5)' },
          },
        },
      },
    });
  }
}
