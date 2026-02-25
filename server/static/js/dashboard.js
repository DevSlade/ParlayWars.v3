/**
 * ParlayWars v3 — Dashboard Module
 * Date: 2026-02-25
 *
 * Renders live + upcoming matches, engine vote cards, bankroll mini-chart,
 * and quick predict form.
 */

// Called by WebSocket on dashboard update
function onDashboardUpdate(data) {
  if (document.getElementById('dashboard-root') &&
      document.getElementById('dashboard-root').children.length > 0) {
    _updateDashboardLive(data);
  }
}

function renderDashboard() {
  const root = document.getElementById('dashboard-root');
  if (!root) return;
  root.innerHTML = `<div class="loading-overlay"><div class="spinner"></div><span>Loading dashboard...</span></div>`;

  Promise.all([
    apiGet('/api/matches?status=live&limit=10'),
    apiGet('/api/matches?status=scheduled&limit=10'),
    apiGet('/api/predictions?limit=20'),
    apiGet('/api/stats'),
  ]).then(([live, upcoming, preds, stats]) => {
    root.innerHTML = _buildDashboardHTML(live, upcoming, preds, stats);
    _renderBankrollMiniChart(stats);
  }).catch(err => {
    root.innerHTML = `<div class="loading-overlay" style="color:var(--loss-color)">Error: ${err.message}</div>`;
  });
}

function _buildDashboardHTML(live, upcoming, preds, stats) {
  const liveSection = live.length ? `
    <div style="margin-bottom:var(--gap)">
      <div class="card-title" style="margin-bottom:8px">🔴 Live Now</div>
      <div style="display:grid;gap:8px">
        ${live.map(m => _matchCard(m, preds)).join('')}
      </div>
    </div>
  ` : '';

  const upcomingSection = upcoming.length ? `
    <div style="margin-bottom:var(--gap)">
      <div class="card-title" style="margin-bottom:8px">📅 Upcoming</div>
      <div style="display:grid;gap:8px">
        ${upcoming.slice(0,8).map(m => _matchCard(m, preds)).join('')}
      </div>
    </div>
  ` : `<div class="card" style="text-align:center;padding:32px;color:var(--text-muted)">No scheduled matches found — data refreshes every 2 minutes.</div>`;

  return `
    <div class="section-header">
      <div>
        <div class="section-title">📊 Dashboard</div>
        <div class="section-subtitle">Live updates every 5 seconds via WebSocket</div>
      </div>
      <button class="btn btn-secondary" onclick="renderDashboard()">🔄 Refresh</button>
    </div>

    <!-- Stats row -->
    <div class="grid-4" style="margin-bottom:var(--gap)">
      ${_statCard('👥', 'Players', stats.players || 0)}
      ${_statCard('🏀', 'Matches', stats.matches || 0)}
      ${_statCard('🎯', 'Predictions', stats.predictions || 0)}
      ${_statCard('💰', 'Bankroll', '$'+(stats.bankroll||1000).toFixed(2))}
    </div>

    <div class="grid-2" style="margin-bottom:var(--gap)">
      <!-- Left: matches -->
      <div>
        ${liveSection}
        ${upcomingSection}
      </div>
      <!-- Right: bankroll chart + quick predict -->
      <div style="display:flex;flex-direction:column;gap:var(--gap)">
        <div class="card">
          <div class="card-title" style="margin-bottom:8px">💰 Bankroll</div>
          <canvas id="bankroll-mini-chart" height="120"></canvas>
          <div style="display:flex;justify-content:space-between;margin-top:8px;font-size:12px;color:var(--text-muted)">
            <span>Start: $${(stats.starting_bankroll||1000).toFixed(2)}</span>
            <span style="color:${(stats.roi_pct||0)>=0?'var(--win-color)':'var(--loss-color)'}">
              ROI: ${(stats.roi_pct||0)>=0?'+':''}${(stats.roi_pct||0).toFixed(2)}%
            </span>
          </div>
        </div>
        <div class="card">
          <div class="card-title" style="margin-bottom:12px">⚡ Quick Predict</div>
          <div id="quick-predict-form">
            <div class="form-group">
              <label class="form-label">Player A</label>
              <input type="text" id="qp-player-a" placeholder="e.g. TAAPZ" />
            </div>
            <div class="form-group">
              <label class="form-label">Player B</label>
              <input type="text" id="qp-player-b" placeholder="e.g. LANES" />
            </div>
            <button class="btn btn-primary" style="width:100%" onclick="quickPredict()">🎯 Predict</button>
          </div>
          <div id="quick-predict-result" style="margin-top:12px"></div>
        </div>
      </div>
    </div>
  `;
}

function _statCard(icon, label, value) {
  return `
    <div class="card" style="text-align:center">
      <div style="font-size:24px;margin-bottom:4px">${icon}</div>
      <div class="stat-number">${value}</div>
      <div class="stat-label">${label}</div>
    </div>
  `;
}

function _matchCard(match, preds) {
  const status = match.status || 'scheduled';
  const matchPreds = preds.filter(p => p.match_id === match.id || 
    (p.player_a === match.player_a && p.player_b === match.player_b));
  
  const scoreDisplay = (match.score_a != null && match.score_b != null)
    ? `<span class="score-display">${match.score_a} - ${match.score_b}</span>`
    : '';

  const engineVotes = ['TITAN','PHANTOM','SURGE','ORACLE'].map(eng => {
    const pred = matchPreds.find(p => p.engine_name === eng);
    if (!pred) return `<div class="engine-card ${eng}" style="flex:1;min-width:100px">
      <div class="engine-name">${eng}</div>
      <div class="engine-pick" style="color:var(--text-muted)">—</div>
    </div>`;
    return `<div class="engine-card ${eng}" style="flex:1;min-width:100px">
      <div class="engine-name">${eng}</div>
      <div class="engine-pick">${pred.predicted_winner||'—'}</div>
      <div class="engine-prob">${((pred.confidence||0.5)*100).toFixed(0)}% conf</div>
    </div>`;
  }).join('');

  return `
    <div class="match-card ${status === 'live' ? 'live' : ''}">
      <div style="flex:1">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
          <span class="match-status-badge ${status}">${status}</span>
          <div class="match-players">
            <span>${match.player_a||'TBD'}</span>
            <span class="match-vs">vs</span>
            <span>${match.player_b||'TBD'}</span>
          </div>
          ${scoreDisplay}
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap">
          ${engineVotes}
        </div>
      </div>
    </div>
  `;
}

function _updateDashboardLive(data) {
  // Update stats without full re-render
  const bankroll = document.querySelector('.bankroll-badge span');
  if (bankroll && data.bankroll) bankroll.textContent = data.bankroll.toFixed(2);
}

function _renderBankrollMiniChart(stats) {
  const canvas = document.getElementById('bankroll-mini-chart');
  if (!canvas || !window.Chart) return;

  // Fetch bankroll history
  apiGet('/api/sim').then(sim => {
    const chartData = (sim.bankroll_chart || []).slice(-30);
    const labels = chartData.map(d => d.ts ? d.ts.slice(11,16) : '');
    const values = chartData.map(d => d.balance);
    
    if (!labels.length) {
      labels.push('Start');
      values.push(stats.starting_bankroll || 1000);
    }

    if (canvas._chart) canvas._chart.destroy();
    canvas._chart = new Chart(canvas, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          data: values,
          borderColor: values[values.length-1] >= values[0] ? '#69f0ae' : '#ff5252',
          borderWidth: 2,
          fill: true,
          backgroundColor: values[values.length-1] >= values[0]
            ? 'rgba(105,240,174,0.08)' : 'rgba(255,82,82,0.08)',
          tension: 0.4,
          pointRadius: 0,
        }],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
          x: { display: false },
          y: { display: false },
        },
      },
    });
  }).catch(() => {});
}

async function quickPredict() {
  const pa = document.getElementById('qp-player-a')?.value?.trim().toUpperCase();
  const pb = document.getElementById('qp-player-b')?.value?.trim().toUpperCase();
  const resultDiv = document.getElementById('quick-predict-result');
  if (!pa || !pb) {
    if (resultDiv) resultDiv.innerHTML = `<div style="color:var(--loss-color)">Please enter both player names.</div>`;
    return;
  }
  if (resultDiv) resultDiv.innerHTML = `<div class="spinner" style="margin:0 auto"></div>`;

  try {
    const result = await apiPost('/api/predict', { player_a: pa, player_b: pb });
    const html = result.engines.map(e => `
      <div class="engine-card ${e.engine_name}" style="margin-bottom:6px">
        <div class="engine-name">${e.engine_name}</div>
        <div class="engine-pick">${e.predicted_winner||'?'}</div>
        <div class="engine-prob">
          A: ${((e.prob_a||0.5)*100).toFixed(1)}% | B: ${((e.prob_b||0.5)*100).toFixed(1)}%
          <span class="tier-badge tier-${e.tier||'LOW'}" style="margin-left:4px">${e.tier||'LOW'}</span>
        </div>
      </div>
    `).join('');
    if (resultDiv) resultDiv.innerHTML = html;
  } catch(err) {
    if (resultDiv) resultDiv.innerHTML = `<div style="color:var(--loss-color)">Error: ${err.message}</div>`;
  }
}
