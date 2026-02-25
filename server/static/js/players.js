/**
 * ParlayWars v3 — Players Module
 * Date: 2026-02-25
 *
 * Searchable player table, click-to-profile with stats, ELO, PWR, form sparkline.
 */

let _allPlayers = [];

function renderPlayers() {
  const root = document.getElementById('players-root');
  if (!root) return;
  root.innerHTML = `<div class="loading-overlay"><div class="spinner"></div><span>Loading players...</span></div>`;

  apiGet('/api/players?limit=200').then(players => {
    _allPlayers = players;
    _renderPlayerTable(root, players);
  }).catch(err => {
    root.innerHTML = `<div class="loading-overlay" style="color:var(--loss-color)">Error: ${err.message}</div>`;
  });
}

function _renderPlayerTable(root, players) {
  const rows = players.map(p => {
    const form = (p.form || []).slice(0,10).map(r =>
      `<span class="form-dot ${r}" title="${r}"></span>`
    ).join('');
    const elo = (p.elo || 1500).toFixed(0);
    const pwr = (p.pwr_rating || 50).toFixed(1);
    const wp  = (p.win_pct || 50).toFixed(1);
    const rwp = (p.recent_win_pct || 50).toFixed(1);
    return `
      <tr onclick="showPlayerProfile('${p.name}')">
        <td>${p.rank || '—'}</td>
        <td style="font-weight:600">${p.name}</td>
        <td>${wp}%</td>
        <td>${rwp}%</td>
        <td>${p.total_games || 0}</td>
        <td><span class="elo-badge">${elo}</span></td>
        <td><span class="pwr-badge">${pwr}</span></td>
        <td><div style="display:flex;gap:2px">${form}</div></td>
        <td>${(p.clutch_index||50).toFixed(0)}</td>
        <td>${(p.consistency_score||50).toFixed(0)}</td>
      </tr>
    `;
  }).join('');

  root.innerHTML = `
    <div class="section-header">
      <div>
        <div class="section-title">👥 Players</div>
        <div class="section-subtitle">${players.length} players — click any row for full profile</div>
      </div>
    </div>
    <div class="search-bar">
      <input type="text" placeholder="Search players by name..." id="player-search"
        oninput="_filterPlayers(this.value)" />
    </div>
    <div class="card" style="overflow-x:auto">
      <table class="data-table" id="players-table">
        <thead><tr>
          <th>Rank</th><th>Name</th><th>Win%</th><th>Recent%</th>
          <th>Games</th><th>ELO</th><th>PWR</th>
          <th>Form (L10)</th><th>Clutch</th><th>Consistency</th>
        </tr></thead>
        <tbody id="players-tbody">${rows}</tbody>
      </table>
    </div>
  `;
}

function _filterPlayers(query) {
  const q = query.toUpperCase().trim();
  const filtered = q ? _allPlayers.filter(p => p.name.includes(q)) : _allPlayers;
  const tbody = document.getElementById('players-tbody');
  if (!tbody) return;
  tbody.innerHTML = filtered.map(p => {
    const form = (p.form || []).slice(0,10).map(r =>
      `<span class="form-dot ${r}" title="${r}"></span>`
    ).join('');
    return `
      <tr onclick="showPlayerProfile('${p.name}')">
        <td>${p.rank || '—'}</td>
        <td style="font-weight:600">${p.name}</td>
        <td>${(p.win_pct||50).toFixed(1)}%</td>
        <td>${(p.recent_win_pct||50).toFixed(1)}%</td>
        <td>${p.total_games || 0}</td>
        <td><span class="elo-badge">${(p.elo||1500).toFixed(0)}</span></td>
        <td><span class="pwr-badge">${(p.pwr_rating||50).toFixed(1)}</span></td>
        <td><div style="display:flex;gap:2px">${form}</div></td>
        <td>${(p.clutch_index||50).toFixed(0)}</td>
        <td>${(p.consistency_score||50).toFixed(0)}</td>
      </tr>
    `;
  }).join('');
}

async function showPlayerProfile(name) {
  // Get Alpine app instance for modal
  const appEl = document.querySelector('[x-data]');
  const alpine = appEl && appEl._x_dataStack && appEl._x_dataStack[0];

  try {
    const [player, h2hData] = await Promise.all([
      apiGet(`/api/players/${encodeURIComponent(name)}`),
      apiGet(`/api/predictions?limit=50`).then(preds =>
        preds.filter(p => p.player_a === name || p.player_b === name).slice(0, 5)
      ),
    ]);

    const form = (player.form || []).map(r =>
      `<span class="form-dot ${r}" style="width:16px;height:16px"></span>`
    ).join('');

    const stats = [
      ['Win %',       (player.win_pct||50).toFixed(1)+'%'],
      ['Recent Win%', (player.recent_win_pct||50).toFixed(1)+'%'],
      ['Total Games', player.total_games || 0],
      ['Wins',        player.wins || 0],
      ['Losses',      player.losses || 0],
      ['ELO',         (player.elo||1500).toFixed(0)],
      ['PWR',         (player.pwr_rating||50).toFixed(1)],
      ['Clutch',      (player.clutch_index||50).toFixed(1)],
      ['Consistency', (player.consistency_score||50).toFixed(1)],
      ['Upset Res.',  (player.upset_resistance||50).toFixed(1)],
      ['Form Vel.',   (player.form_velocity||0).toFixed(3)],
      ['OQR',         (player.oqr||50).toFixed(1)],
      ['Bounce Back', ((player.bounce_back_rate||0.5)*100).toFixed(0)+'%'],
      ['Avg Points',  (player.avg_points||45).toFixed(1)],
      ['Avg FG%',     ((player.avg_fg_pct||0.45)*100).toFixed(1)+'%'],
    ];

    const statsHTML = stats.map(([label, val]) => `
      <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border)">
        <span style="color:var(--text-secondary)">${label}</span>
        <span style="font-weight:600">${val}</span>
      </div>
    `).join('');

    const html = `
      <div class="player-header">
        <div class="player-avatar">${name.charAt(0)}</div>
        <div>
          <div class="player-name">${name}</div>
          <div class="player-rank">Rank #${player.rank || '?'} • ${player.sport || 'ebasketball'}</div>
          <div style="display:flex;gap:8px;margin-top:8px">
            <span class="elo-badge">⚡ ELO ${(player.elo||1500).toFixed(0)}</span>
            <span class="pwr-badge">★ PWR ${(player.pwr_rating||50).toFixed(1)}</span>
          </div>
        </div>
      </div>
      <div style="margin-bottom:16px">
        <div style="font-size:12px;color:var(--text-muted);margin-bottom:6px">FORM (last 10 — newest left)</div>
        <div style="display:flex;gap:4px">${form}</div>
      </div>
      <div style="font-size:12px">${statsHTML}</div>
    `;

    if (alpine) {
      alpine.openModal(html);
    } else {
      document.querySelector('[x-data]').__x.$data.openModal(html);
    }
  } catch(err) {
    console.error('Player profile error:', err);
  }
}
