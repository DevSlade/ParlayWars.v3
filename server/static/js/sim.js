/**
 * ParlayWars v3 — Simulator Module
 * Date: 2026-02-25
 *
 * Paper trading: bankroll chart, bet log, P/L by day, ROI tracker, parlay history.
 */

let _bankrollChart = null;

function renderSim() {
  const root = document.getElementById('sim-root');
  if (!root) return;
  root.innerHTML = `<div class="loading-overlay"><div class="spinner"></div><span>Loading simulator...</span></div>`;

  apiGet('/api/sim').then(sim => {
    _buildSimHTML(root, sim);
  }).catch(err => {
    root.innerHTML = `<div class="loading-overlay" style="color:var(--loss-color)">Error: ${err.message}</div>`;
  });
}

function _buildSimHTML(root, sim) {
  const s = sim.summary || {};
  const bankroll = sim.bankroll || 1000;
  const starting = sim.starting_bankroll || 1000;
  const pl = s.total_pl || 0;
  const plColor = pl >= 0 ? 'var(--win-color)' : 'var(--loss-color)';
  const plSign  = pl >= 0 ? '+' : '';

  const statCards = [
    { icon: '💰', label: 'Bankroll',   value: '$'+bankroll.toFixed(2) },
    { icon: '📈', label: 'Total P/L',  value: plSign+'$'+pl.toFixed(2), color: plColor },
    { icon: '🎯', label: 'Win Rate',   value: ((s.win_rate||0)*100).toFixed(1)+'%' },
    { icon: '🔥', label: 'Streak',     value: (s.current_streak||0) > 0 ? '+'+s.current_streak : s.current_streak || 0 },
    { icon: '📉', label: 'Max DD',     value: '$'+(s.max_drawdown||0).toFixed(2) },
    { icon: '📊', label: 'ROI',        value: (s.roi_pct||0).toFixed(2)+'%', color: pl >= 0 ? 'var(--win-color)' : 'var(--loss-color)' },
    { icon: '🎲', label: 'Total Bets', value: s.total_bets || 0 },
  ];

  const statsHTML = statCards.map(sc => `
    <div class="card" style="text-align:center">
      <div style="font-size:22px">${sc.icon}</div>
      <div class="stat-number" style="font-size:20px;${sc.color ? 'color:'+sc.color : ''}">${sc.value}</div>
      <div class="stat-label">${sc.label}</div>
    </div>
  `).join('');

  // Engine breakdown table
  const breakdown = sim.engine_breakdown || {};
  const breakdownHTML = Object.entries(breakdown).map(([eng, d]) => `
    <tr>
      <td><span class="engine-name" style="color:var(--${eng.toLowerCase()}-color,var(--accent))">${eng}</span></td>
      <td>${d.bets}</td>
      <td>${d.wins}</td>
      <td>${(d.win_rate*100).toFixed(1)}%</td>
      <td style="color:${d.pl>=0?'var(--win-color)':'var(--loss-color)'}">${d.pl>=0?'+':''}$${d.pl.toFixed(2)}</td>
    </tr>
  `).join('') || '<tr><td colspan="5" style="text-align:center;color:var(--text-muted)">No bets placed yet</td></tr>';

  // Recent bets
  const betsHTML = (sim.recent_bets || []).map(b => `
    <tr>
      <td style="font-size:11px;color:var(--text-muted)">${(b.placed_at||'').slice(0,16)}</td>
      <td>${b.predicted_winner||'?'}</td>
      <td>$${(b.stake||0).toFixed(2)}</td>
      <td>${b.odds_american > 0 ? '+' : ''}${b.odds_american||0}</td>
      <td>
        <span class="tier-badge ${
          b.status==='won' ? 'tier-HIGH' : b.status==='lost' ? 'tier-LOW' : 'tier-MEDIUM'
        }">${b.status||'pending'}</span>
      </td>
      <td style="color:${(b.profit_loss||0)>=0?'var(--win-color)':'var(--loss-color)'}">
        ${b.profit_loss != null ? ((b.profit_loss>=0?'+':'')+'$'+b.profit_loss.toFixed(2)) : '—'}
      </td>
    </tr>
  `).join('') || '<tr><td colspan="6" style="text-align:center;color:var(--text-muted)">No bets placed yet</td></tr>';

  root.innerHTML = `
    <div class="section-header">
      <div>
        <div class="section-title">💰 Paper Trading Simulator</div>
        <div class="section-subtitle">Quarter-Kelly sizing • Auto-bets on engine predictions • Settles on real results</div>
      </div>
      <button class="btn btn-secondary" onclick="renderSim()">🔄 Refresh</button>
    </div>

    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:var(--gap-sm);margin-bottom:var(--gap)">
      ${statsHTML}
    </div>

    <div class="grid-2" style="margin-bottom:var(--gap)">
      <!-- Bankroll chart -->
      <div class="card">
        <div class="card-title" style="margin-bottom:12px">📈 Bankroll Over Time</div>
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
          <thead><tr><th>Time</th><th>Pick</th><th>Stake</th><th>Odds</th><th>Status</th><th>P/L</th></tr></thead>
          <tbody>${betsHTML}</tbody>
        </table>
      </div>
    </div>
  `;

  // Render bankroll chart
  const canvas = document.getElementById('bankroll-main-chart');
  if (canvas && window.Chart) {
    const chartData = (sim.bankroll_chart || []).slice(-100);
    const labels = chartData.map((d,i) => i % 5 === 0 ? (d.ts||'').slice(11,16) : '');
    const values = chartData.map(d => d.balance);
    if (!values.length) { values.push(starting); labels.push('Start'); }

    if (_bankrollChart) _bankrollChart.destroy();
    _bankrollChart = new Chart(canvas, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: 'Bankroll',
          data: values,
          borderColor: values[values.length-1] >= starting ? '#69f0ae' : '#ff5252',
          backgroundColor: values[values.length-1] >= starting
            ? 'rgba(105,240,174,0.1)' : 'rgba(255,82,82,0.1)',
          borderWidth: 2,
          fill: true,
          tension: 0.4,
          pointRadius: 2,
        }],
      },
      options: {
        responsive: true,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => `$${ctx.parsed.y.toFixed(2)}`,
            },
          },
        },
        scales: {
          x: { display: false },
          y: {
            ticks: { color: '#8892b0', callback: v => '$'+v.toFixed(0) },
            grid: { color: 'rgba(42,58,92,0.5)' },
          },
        },
      },
    });
  }
}
