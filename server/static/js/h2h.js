/**
 * ParlayWars v3 — H2H Comparison Module
 * Date: 2026-02-25
 *
 * Select two players → full stat comparison + all engine predictions.
 */

function renderH2H() {
  const root = document.getElementById('h2h-root');
  if (!root) return;

  root.innerHTML = `
    <div class="section-header">
      <div>
        <div class="section-title">⚔️ Head-to-Head</div>
        <div class="section-subtitle">Compare two players with full engine analysis</div>
      </div>
    </div>
    <div class="card" style="margin-bottom:var(--gap)">
      <div class="grid-2" style="gap:var(--gap)">
        <div class="form-group">
          <label class="form-label">Player A</label>
          <input type="text" id="h2h-player-a" placeholder="e.g. TAAPZ" />
        </div>
        <div class="form-group">
          <label class="form-label">Player B</label>
          <input type="text" id="h2h-player-b" placeholder="e.g. LANES" />
        </div>
      </div>
      <button class="btn btn-primary" style="margin-top:8px" onclick="loadH2H()">⚔️ Compare</button>
    </div>
    <div id="h2h-results"></div>
  `;
}

async function loadH2H() {
  const pa = document.getElementById('h2h-player-a')?.value?.trim().toUpperCase();
  const pb = document.getElementById('h2h-player-b')?.value?.trim().toUpperCase();
  const results = document.getElementById('h2h-results');
  if (!pa || !pb || !results) return;

  results.innerHTML = `<div class="loading-overlay"><div class="spinner"></div></div>`;

  try {
    const [h2hData, predData] = await Promise.all([
      apiGet(`/api/h2h/${encodeURIComponent(pa)}/${encodeURIComponent(pb)}`),
      apiPost('/api/predict', { player_a: pa, player_b: pb }),
    ]);

    const pA = h2hData.player_a || {};
    const pB = h2hData.player_b || {};
    const h2h = h2hData.h2h || {};

    const total = h2h.total || 0;
    const aWins = h2h.a_wins || 0;
    const bWins = h2h.b_wins || 0;
    const pctA = total > 0 ? aWins / total : 0.5;

    const statRows = [
      ['Rank',         pA.rank || '?',                  pB.rank || '?'],
      ['ELO',          (pA.elo||1500).toFixed(0),        (pB.elo||1500).toFixed(0)],
      ['PWR',          (pA.pwr_rating||50).toFixed(1),   (pB.pwr_rating||50).toFixed(1)],
      ['Win %',        (pA.win_pct||50).toFixed(1)+'%',  (pB.win_pct||50).toFixed(1)+'%'],
      ['Recent Win%',  (pA.recent_win_pct||50).toFixed(1)+'%', (pB.recent_win_pct||50).toFixed(1)+'%'],
      ['Games',        pA.total_games||0,                pB.total_games||0],
      ['Clutch',       (pA.clutch_index||50).toFixed(1), (pB.clutch_index||50).toFixed(1)],
      ['Consistency',  (pA.consistency_score||50).toFixed(1), (pB.consistency_score||50).toFixed(1)],
      ['Form Vel.',    (pA.form_velocity||0).toFixed(3),  (pB.form_velocity||0).toFixed(3)],
      ['OQR',          (pA.oqr||50).toFixed(1),           (pB.oqr||50).toFixed(1)],
    ];

    const tableRows = statRows.map(([label, va, vb]) => `
      <tr>
        <td style="text-align:right;font-weight:600;color:var(--titan-color)">${va}</td>
        <td style="text-align:center;color:var(--text-muted);font-size:11px">${label}</td>
        <td style="text-align:left;font-weight:600;color:var(--surge-color)">${vb}</td>
      </tr>
    `).join('');

    // Engine predictions
    const engineVotes = (predData.engines || []).map(e => `
      <div class="engine-card ${e.engine_name}">
        <div class="engine-name">${e.engine_name}</div>
        <div class="engine-pick">${e.predicted_winner || '?'}</div>
        <div class="engine-prob">
          ${pa}: ${((e.prob_a||0.5)*100).toFixed(1)}% &nbsp;|&nbsp;
          ${pb}: ${((e.prob_b||0.5)*100).toFixed(1)}%
          <span class="tier-badge tier-${e.tier||'LOW'}" style="margin-left:4px">${e.tier}</span>
        </div>
        ${e.explanation ? `<div style="font-size:10px;color:var(--text-muted);margin-top:4px">${e.explanation}</div>` : ''}
      </div>
    `).join('');

    results.innerHTML = `
      <!-- H2H record bar -->
      <div class="card" style="margin-bottom:var(--gap)">
        <div style="display:flex;justify-content:space-between;margin-bottom:8px;font-weight:600">
          <span style="color:var(--titan-color)">${pa} (${aWins})</span>
          <span style="color:var(--text-muted)">H2H — ${total} matches</span>
          <span style="color:var(--surge-color)">(${bWins}) ${pb}</span>
        </div>
        <div class="h2h-bar">
          <div class="h2h-bar-a" style="width:${(pctA*100).toFixed(0)}%"></div>
          <div class="h2h-bar-b" style="width:${((1-pctA)*100).toFixed(0)}%"></div>
        </div>
        <div style="display:flex;justify-content:space-between;margin-top:4px;font-size:12px;color:var(--text-muted)">
          <span>${(pctA*100).toFixed(0)}%</span>
          <span>Avg margin: ${(h2h.avg_margin||0).toFixed(1)} pts</span>
          <span>${((1-pctA)*100).toFixed(0)}%</span>
        </div>
      </div>

      <!-- Stat comparison -->
      <div class="card" style="margin-bottom:var(--gap)">
        <div class="card-title" style="margin-bottom:12px">📊 Stat Comparison</div>
        <div style="display:flex;justify-content:space-between;margin-bottom:8px">
          <span style="font-size:14px;font-weight:700;color:var(--titan-color)">${pa}</span>
          <span style="font-size:14px;font-weight:700;color:var(--surge-color)">${pb}</span>
        </div>
        <table class="data-table"><tbody>${tableRows}</tbody></table>
      </div>

      <!-- Engine predictions -->
      <div class="card">
        <div class="card-title" style="margin-bottom:12px">🤖 Engine Predictions</div>
        <div style="display:grid;gap:8px">${engineVotes}</div>
        ${predData.consensus ? `
          <div style="margin-top:12px;padding:12px;background:var(--bg-hover);border-radius:var(--radius-sm)">
            <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px">Consensus</div>
            <div style="font-size:18px;font-weight:700;margin-top:4px">${predData.consensus.predicted_winner}</div>
            <div style="font-size:13px;color:var(--text-secondary)">
              ${(predData.consensus.confidence*100).toFixed(1)}% confidence &nbsp;
              <span class="tier-badge tier-${predData.consensus.tier}">${predData.consensus.tier}</span>
            </div>
          </div>
        ` : ''}
      </div>
    `;
  } catch (err) {
    results.innerHTML = `<div class="loading-overlay" style="color:var(--loss-color)">Error: ${err.message}</div>`;
  }
}
