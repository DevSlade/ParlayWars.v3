/**
 * ParlayWars v3 — Dashboard Module
 * Date: 2026-02-25
 *
 * Features:
 *   - Live / upcoming match cards with confidence tier glow
 *   - Engine vote cards with disagreement badge
 *   - Fade Risk + Value Bet badges
 *   - Streak tracker widget
 *   - Data freshness indicator
 *   - Quick Predict (any 2 players, autocomplete)
 *   - Bankroll mini-chart
 *   - Regression / Bounce-back alerts
 */

// Called by WebSocket on dashboard push
function onDashboardUpdate(data) {
  if (document.getElementById('dashboard-root')?.children.length > 0) {
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
    apiGet('/api/predictions?limit=30'),
    apiGet('/api/stats'),
    apiGet('/api/engines/accuracy').catch(() => ({})),
    apiGet('/api/stats/regression').catch(() => ({})),
  ]).then(([live, upcoming, preds, stats, accuracy, regression]) => {
    root.innerHTML = _buildDashboardHTML(live, upcoming, preds, stats, accuracy, regression);
    _renderBankrollMiniChart(stats);
    _initQuickPredictAutocomplete();
  }).catch(err => {
    root.innerHTML = `<div class="loading-overlay" style="color:var(--loss-color)">Error: ${err.message}</div>`;
  });
}

function _buildDashboardHTML(live, upcoming, preds, stats, accuracy, regression) {
  const streak   = accuracy.current_streak || 0;
  const best     = accuracy.best_streak    || 0;
  const worst    = accuracy.worst_streak   || 0;

  const liveSection = live.length ? `
    <div style="margin-bottom:var(--gap)">
      <div class="card-title" style="margin-bottom:8px">🔴 Live Now</div>
      <div style="display:grid;gap:8px">${live.map(m => _matchCard(m, preds)).join('')}</div>
    </div>
  ` : '';

  const upcomingSection = upcoming.length ? `
    <div style="margin-bottom:var(--gap)">
      <div class="card-title" style="margin-bottom:8px">📅 Upcoming</div>
      <div style="display:grid;gap:8px">${upcoming.slice(0,8).map(m => _matchCard(m, preds)).join('')}</div>
    </div>
  ` : `<div class="card" style="text-align:center;padding:32px;color:var(--text-muted)">No scheduled matches — data refreshes every 30s.</div>`;

  // Engine accuracy cards
  const byEngine = accuracy.by_engine || {};
  const engNames = ['TITAN','PHANTOM','SURGE','ORACLE'];
  const accCards = engNames.map(eng => {
    const d = byEngine[eng];
    const pct = d?.accuracy ?? '—';
    const total = d?.total ?? 0;
    const colors = { TITAN:'var(--titan-color)', PHANTOM:'var(--phantom-color)', SURGE:'var(--surge-color)', ORACLE:'var(--oracle-color)' };
    return `
      <div class="accuracy-card">
        <div class="acc-engine-name" style="color:${colors[eng]}">${eng}</div>
        <div class="acc-pct" style="color:${colors[eng]}">${pct}${typeof pct==='number'?'%':''}</div>
        <div class="acc-total">${total} settled</div>
      </div>`;
  }).join('');

  // Regression alerts
  const regCandidates = (regression.regression_candidates || []).slice(0,3);
  const bbCandidates  = (regression.bounce_back_candidates || []).slice(0,3);
  const alertsHtml = (regCandidates.length || bbCandidates.length) ? `
    <div class="card" style="margin-bottom:var(--gap)">
      <div class="card-title" style="margin-bottom:8px">📉 Market Alerts</div>
      ${regCandidates.map(p => `
        <div class="regression-alert">⚠️ <b>${p.name}</b> — REGRESSION CANDIDATE: recent ${p.recent_wr}% vs career ${p.career_wr}% (+${p.gap}%)</div>
      `).join('')}
      ${bbCandidates.map(p => `
        <div class="bounceback-alert">🔄 <b>${p.name}</b> — BOUNCE-BACK CANDIDATE: recent ${p.recent_wr}% vs career ${p.career_wr}% (${p.gap}%)</div>
      `).join('')}
    </div>
  ` : '';

  return `
    <div class="section-header">
      <div>
        <div class="section-title">📊 Dashboard</div>
        <div class="section-subtitle">Live 2K eBasketball AI Predictions</div>
      </div>
      <button class="btn btn-secondary" onclick="renderDashboard()">🔄 Refresh</button>
    </div>

    <!-- Stats row -->
    <div class="grid-4" style="margin-bottom:var(--gap)">
      ${_statCard('👥','Players', stats.players||0)}
      ${_statCard('🏀','Matches', stats.matches||0)}
      ${_statCard('🎯','Predictions', stats.predictions||0)}
      ${_statCard('💰','Bankroll','$'+(stats.bankroll||1000).toFixed(2))}
    </div>

    <!-- Engine accuracy row -->
    <div class="card" style="margin-bottom:var(--gap)">
      <div class="card-title" style="margin-bottom:0">🧠 Engine Accuracy</div>
      <div class="accuracy-grid">${accCards}</div>
    </div>

    <!-- Streak + alerts row -->
    ${alertsHtml}

    <div class="grid-2" style="margin-bottom:var(--gap)">
      <!-- Left: matches -->
      <div>
        ${liveSection}
        ${upcomingSection}
      </div>

      <!-- Right: bankroll + streak + quick predict -->
      <div style="display:flex;flex-direction:column;gap:var(--gap)">

        <!-- Streak widget -->
        <div class="card">
          <div class="card-title" style="margin-bottom:10px">🔥 Sim Streak</div>
          <div style="display:flex;gap:10px;flex-wrap:wrap">
            ${_streakWidget('Current', streak)}
            ${_streakStatMini('Best', best, true)}
            ${_streakStatMini('Worst', worst, false)}
          </div>
        </div>

        <!-- Bankroll mini-chart -->
        <div class="card">
          <div class="card-title" style="margin-bottom:8px">💰 Bankroll</div>
          <canvas id="bankroll-mini-chart" height="100"></canvas>
          <div style="display:flex;justify-content:space-between;margin-top:8px;font-size:12px;color:var(--text-muted)">
            <span>Start: $${(stats.starting_bankroll||1000).toFixed(2)}</span>
            <span style="color:${(stats.roi_pct||0)>=0?'var(--win-color)':'var(--loss-color)'}">
              ROI: ${(stats.roi_pct||0)>=0?'+':''}${(stats.roi_pct||0).toFixed(2)}%
            </span>
          </div>
        </div>

        <!-- Quick Predict -->
        <div class="card">
          <div class="card-title" style="margin-bottom:12px">⚡ Quick Predict</div>
          <div class="form-group">
            <label class="form-label">Player A</label>
            <input type="text" id="qp-player-a" placeholder="e.g. TAAPZ" autocomplete="off" oninput="_qpSuggest('a',this.value)" />
            <div id="qp-suggest-a" class="search-results" style="display:none"></div>
          </div>
          <div class="form-group">
            <label class="form-label">Player B</label>
            <input type="text" id="qp-player-b" placeholder="e.g. LANES" autocomplete="off" oninput="_qpSuggest('b',this.value)" />
            <div id="qp-suggest-b" class="search-results" style="display:none"></div>
          </div>
          <button class="btn btn-primary" style="width:100%" onclick="quickPredict()">🎯 Predict</button>
          <div id="quick-predict-result" style="margin-top:12px"></div>
        </div>
      </div>
    </div>
  `;
}

function _streakWidget(label, streak) {
  const isWin = streak >= 0;
  const icon  = isWin ? (streak >= 3 ? '🔥' : '✅') : (streak <= -3 ? '❄️' : '❌');
  const cls   = isWin ? 'streak-win' : 'streak-loss';
  const val   = isWin ? `W${streak}` : `L${Math.abs(streak)}`;
  return `
    <div class="streak-widget" style="flex:1;min-width:90px">
      <span class="${isWin ? 'streak-fire' : 'streak-cold'}">${icon}</span>
      <div>
        <div class="streak-value ${cls}">${val}</div>
        <div style="font-size:11px;color:var(--text-muted)">${label}</div>
      </div>
    </div>`;
}

function _streakStatMini(label, val, isWin) {
  const disp = isWin ? `W${val}` : `L${Math.abs(val)}`;
  const cls  = isWin ? 'streak-win' : 'streak-loss';
  return `
    <div style="text-align:center;background:var(--bg-elevated);border-radius:8px;padding:8px 12px;flex:1;min-width:70px">
      <div style="font-size:16px;font-weight:700" class="${cls}">${disp}</div>
      <div style="font-size:10px;color:var(--text-muted)">${label}</div>
    </div>`;
}

function _statCard(icon, label, value) {
  return `
    <div class="card" style="text-align:center">
      <div style="font-size:24px;margin-bottom:4px">${icon}</div>
      <div class="stat-number">${value}</div>
      <div class="stat-label">${label}</div>
    </div>`;
}

function _matchCard(match, preds) {
  const status = match.status || 'scheduled';
  const matchPreds = preds.filter(p =>
    (p.match_id && p.match_id === match.id) ||
    (p.player_a === match.player_a && p.player_b === match.player_b)
  );

  // Consensus: how many engines agree
  const votes = matchPreds.filter(p => p.predicted_winner).map(p => p.predicted_winner);
  const countA = votes.filter(v => v === match.player_a).length;
  const countB = votes.filter(v => v === match.player_b).length;
  const total  = votes.length;

  let consensusBadge = '';
  let cardClass = `match-card ${status === 'live' ? 'live' : ''}`;
  if (total >= 3) {
    const majority = Math.max(countA, countB);
    if (majority === total) {
      consensusBadge = `<span class="consensus-badge consensus-unanimous">✅ ${total}/${total} Unanimous</span>`;
      cardClass += ' lock-pick';
    } else if (majority >= total - 1) {
      consensusBadge = `<span class="consensus-badge consensus-majority">🟠 ${majority}/${total} Majority</span>`;
      cardClass += ' strong-pick';
    } else {
      consensusBadge = `<span class="consensus-badge consensus-split">⚠️ ${majority}/${total} Split</span>`;
    }
  }

  // Fade risk — check if any engine flagged fade
  const topConf = matchPreds.reduce((mx, p) => Math.max(mx, p.confidence||0), 0);
  const tier = matchPreds.find(p => p.tier)?.tier || 'SKIP';
  const fadeBadge = matchPreds.some(p => p.explanation?.toLowerCase().includes('fade'))
    ? `<span class="fade-badge">⚠️ FADE RISK</span>` : '';

  // Value bet: PHANTOM disagrees with others
  const phantomPred  = matchPreds.find(p => p.engine_name === 'PHANTOM');
  const otherPreds   = matchPreds.filter(p => p.engine_name !== 'PHANTOM');
  const isValueBet   = phantomPred && otherPreds.length >= 2 &&
    otherPreds.every(p => p.predicted_winner !== phantomPred.predicted_winner);
  const valueBadge   = isValueBet
    ? `<span class="value-bet-badge">💎 VALUE BET</span>` : '';

  const scoreDisplay = (match.score_a != null && match.score_b != null)
    ? `<span class="score-display">${match.score_a} – ${match.score_b}</span>` : '';

  const engineVotes = ['TITAN','PHANTOM','SURGE','ORACLE'].map(eng => {
    const pred = matchPreds.find(p => p.engine_name === eng);
    if (!pred) return `<div class="engine-card ${eng.toLowerCase()}" style="flex:1;min-width:90px">
      <div class="engine-name">${eng}</div>
      <div class="engine-pick" style="color:var(--text-muted)">—</div>
    </div>`;
    const tierCls = `tier-${pred.tier || 'SKIP'}`;
    return `<div class="engine-card ${eng.toLowerCase()}" style="flex:1;min-width:90px">
      <div class="engine-name">${eng}</div>
      <div class="engine-pick">${pred.predicted_winner || '—'}</div>
      <div class="engine-prob">
        ${((pred.confidence||0.5)*100).toFixed(0)}%
        <span class="tier-badge ${tierCls}" style="font-size:9px;margin-left:2px">${tierLabel(pred.tier||'SKIP')} ${pred.tier||'SKIP'}</span>
      </div>
    </div>`;
  }).join('');

  return `
    <div class="${cardClass}">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap">
        <span class="match-status-badge ${status}">${status.toUpperCase()}</span>
        <div class="match-players">
          <span>${match.player_a||'TBD'}</span>
          <span class="match-vs">vs</span>
          <span>${match.player_b||'TBD'}</span>
        </div>
        ${scoreDisplay}
        ${consensusBadge}
        ${fadeBadge}
        ${valueBadge}
      </div>
      <div style="display:flex;gap:6px;flex-wrap:wrap">${engineVotes}</div>
    </div>`;
}

// ── Bankroll mini-chart ─────────────────────────────────────────────────────
function _renderBankrollMiniChart(stats) {
  const canvas = document.getElementById('bankroll-mini-chart');
  if (!canvas || !window.Chart) return;
  apiGet('/api/sim').then(sim => {
    const chartData = (sim.bankroll_chart || []).slice(-30);
    const labels  = chartData.map(d => d.ts ? d.ts.slice(11,16) : '');
    const values  = chartData.map(d => d.balance);
    if (!values.length) { labels.push('Start'); values.push(stats.starting_bankroll || 1000); }
    const isGreen = values[values.length-1] >= values[0];
    if (canvas._chart) canvas._chart.destroy();
    canvas._chart = new Chart(canvas, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          data: values,
          borderColor: isGreen ? '#69f0ae' : '#ff5252',
          borderWidth: 2, fill: true, tension: 0.4, pointRadius: 0,
          backgroundColor: isGreen ? 'rgba(105,240,174,0.08)' : 'rgba(255,82,82,0.08)',
        }],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: { x: { display: false }, y: { display: false } },
      },
    });
  }).catch(() => {});
}

// ── Quick Predict autocomplete ───────────────────────────────────────────────
let _qpPlayers = [];
async function _initQuickPredictAutocomplete() {
  try { _qpPlayers = await apiGet('/api/players?limit=300'); } catch(e) {}
}
function _qpSuggest(slot, query) {
  const box = document.getElementById(`qp-suggest-${slot}`);
  if (!box) return;
  if (!query || query.length < 2) { box.style.display = 'none'; return; }
  const lower = query.toLowerCase();
  const matches = _qpPlayers.filter(p => (p.name||'').toLowerCase().includes(lower)).slice(0,6);
  if (!matches.length) { box.style.display = 'none'; return; }
  box.innerHTML = matches.map(p =>
    `<div class="search-result-item" onclick="_qpSelect('${slot}','${p.name}')">${p.name}</div>`
  ).join('');
  box.style.display = 'block';
}
function _qpSelect(slot, name) {
  const inp = document.getElementById(`qp-player-${slot}`);
  if (inp) inp.value = name;
  const box = document.getElementById(`qp-suggest-${slot}`);
  if (box) box.style.display = 'none';
}

// ── Quick Predict submission ─────────────────────────────────────────────────
async function quickPredict() {
  const pa = document.getElementById('qp-player-a')?.value?.trim().toUpperCase();
  const pb = document.getElementById('qp-player-b')?.value?.trim().toUpperCase();
  const resultDiv = document.getElementById('quick-predict-result');
  if (!pa || !pb) {
    if (resultDiv) resultDiv.innerHTML = `<div style="color:var(--loss-color)">Enter both player names.</div>`;
    return;
  }
  if (resultDiv) resultDiv.innerHTML = `<div class="spinner" style="margin:0 auto"></div>`;
  try {
    const result = await apiPost('/api/predict', { player_a: pa, player_b: pb });
    const html = result.engines.map(e => {
      const tierCls = `tier-${e.tier||'SKIP'}`;
      const engCls  = (e.engine_name||'').toLowerCase();
      return `
        <div class="engine-card ${engCls}" style="margin-bottom:6px;padding:8px">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <div class="engine-name">${e.engine_name}</div>
            <span class="tier-badge ${tierCls}">${tierLabel(e.tier)} ${e.tier||'SKIP'}</span>
          </div>
          <div class="engine-pick" style="margin:4px 0">${e.predicted_winner||'?'}</div>
          <div class="engine-prob" style="font-size:11px">
            ${pa}: ${((e.prob_a||0.5)*100).toFixed(1)}% | ${pb}: ${((e.prob_b||0.5)*100).toFixed(1)}%
          </div>
        </div>`;
    }).join('');
    if (resultDiv) resultDiv.innerHTML = html;
  } catch(err) {
    if (resultDiv) resultDiv.innerHTML = `<div style="color:var(--loss-color)">Error: ${err.message}</div>`;
  }
}

function _updateDashboardLive(data) {
  const bankroll = document.querySelector('.bankroll-badge span');
  if (bankroll && data.bankroll) bankroll.textContent = data.bankroll.toFixed(2);
}
