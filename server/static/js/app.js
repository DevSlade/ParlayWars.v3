/**
 * ParlayWars v3 — Alpine.js App Root
 * Date: 2026-02-25
 *
 * Global state, tab routing, WebSocket management.
 */

function app() {
  return {
    // ── State ───────────────────────────────────────────────────────
    currentTab: 'dashboard',
    wsConnected: false,
    modal: { open: false, content: '' },
    stats: { bankroll: 1000.00, roi_pct: 0 },
    tabs: [
      { id: 'dashboard',   label: '📊 Dashboard' },
      { id: 'players',     label: '👥 Players' },
      { id: 'predictions', label: '🎯 Predictions' },
      { id: 'h2h',         label: '⚔️ H2H' },
      { id: 'trees',       label: '🌳 Trees' },
      { id: 'sim',         label: '💰 Simulator' },
      { id: 'console',     label: '🖥 Console' },
      { id: 'settings',    label: '⚙️ Settings' },
      { id: 'export',      label: '📥 Export' },
    ],
    _wsConsole: null,
    _wsDashboard: null,

    // ── Init ────────────────────────────────────────────────────────
    init() {
      this.loadStats();
      this.connectWebSockets();
      this.renderCurrentTab();
      setInterval(() => this.loadStats(), 30000);
    },

    // ── Tab switching ────────────────────────────────────────────────
    switchTab(tabId) {
      this.currentTab = tabId;
      this.$nextTick(() => this.renderCurrentTab());
    },

    renderCurrentTab() {
      switch (this.currentTab) {
        case 'dashboard':   renderDashboard(); break;
        case 'players':     renderPlayers(); break;
        case 'predictions': renderPredictions(); break;
        case 'h2h':         renderH2H(); break;
        case 'trees':       renderTrees(); break;
        case 'sim':         renderSim(); break;
        case 'console':     renderConsole(); break;
        case 'settings':    renderSettings(); break;
        case 'export':      renderExport(); break;
      }
    },

    // ── Stats ────────────────────────────────────────────────────────
    async loadStats() {
      try {
        const res = await fetch('/api/stats');
        if (res.ok) {
          this.stats = await res.json();
        }
      } catch (e) { /* silent fail */ }
    },

    // ── WebSocket connections ────────────────────────────────────────
    connectWebSockets() {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      const base  = `${proto}://${location.host}`;

      // Dashboard WS
      this._connectWS(`${base}/ws/dashboard`, (data) => {
        this.wsConnected = true;
        if (typeof onDashboardUpdate === 'function') {
          onDashboardUpdate(data);
        }
        if (data.bankroll) this.stats.bankroll = data.bankroll;
      });

      // Console WS
      this._connectWS(`${base}/ws/console`, (data) => {
        if (typeof onConsoleMessage === 'function') {
          onConsoleMessage(data);
        }
      });
    },

    _connectWS(url, onMessage) {
      let ws;
      const connect = () => {
        ws = new WebSocket(url);
        ws.onopen  = () => { this.wsConnected = true; };
        ws.onclose = () => {
          this.wsConnected = false;
          setTimeout(connect, 3000); // auto-reconnect
        };
        ws.onerror = () => { ws.close(); };
        ws.onmessage = (evt) => {
          try { onMessage(JSON.parse(evt.data)); } catch(e) {}
        };
      };
      connect();
      return ws;
    },

    // ── Modal helpers ────────────────────────────────────────────────
    openModal(html) {
      this.modal.content = html;
      this.modal.open = true;
    },

    closeModal() {
      this.modal.open = false;
    },
  };
}

// ── Shared API helper ────────────────────────────────────────────────
async function apiGet(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json();
}

async function apiPost(path, body) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json();
}

// ── Render Export tab (inline — simple enough) ────────────────────────
function renderExport() {
  const root = document.getElementById('export-root');
  if (!root) return;
  root.innerHTML = `
    <div class="section-header">
      <div>
        <div class="section-title">📥 Data Export</div>
        <div class="section-subtitle">Download your data in CSV or JSON format</div>
      </div>
    </div>
    <div style="display:grid;gap:12px;max-width:600px">
      ${[
        { label: '👥 Players',     path: 'players',     desc: 'All 166+ player profiles with stats and ratings' },
        { label: '🏀 Matches',     path: 'matches',     desc: 'Complete match history' },
        { label: '🎯 Predictions', path: 'predictions', desc: 'All engine predictions' },
        { label: '💰 Bets',        path: 'bets',        desc: 'Paper trading bet log' },
      ].map(e => `
        <div class="export-card">
          <div>
            <div style="font-weight:600;margin-bottom:4px">${e.label}</div>
            <div style="font-size:12px;color:var(--text-muted)">${e.desc}</div>
          </div>
          <div style="display:flex;gap:8px">
            <a href="/export/${e.path}?format=csv"  class="btn btn-secondary btn-sm">CSV</a>
            <a href="/export/${e.path}?format=json" class="btn btn-primary btn-sm">JSON</a>
          </div>
        </div>
      `).join('')}
    </div>
  `;
}

// ── Render Predictions tab ──────────────────────────────────────────────
function renderPredictions() {
  const root = document.getElementById('predictions-root');
  if (!root) return;
  root.innerHTML = `<div class="loading-overlay"><div class="spinner"></div><span>Loading predictions...</span></div>`;

  apiGet('/api/predictions?limit=50').then(preds => {
    if (!preds.length) {
      root.innerHTML = `<div class="loading-overlay">No predictions yet — matches will be analysed when detected.</div>`;
      return;
    }

    const engineColors = { TITAN: 'titan', PHANTOM: 'phantom', SURGE: 'surge', ORACLE: 'oracle' };
    const rows = preds.map(p => {
      const clr = engineColors[p.engine_name] || 'titan';
      return `
        <tr>
          <td><span class="engine-name" style="color:var(--${clr}-color)">${p.engine_name}</span></td>
          <td>${p.player_a || '—'}</td>
          <td>vs</td>
          <td>${p.player_b || '—'}</td>
          <td style="font-weight:700">${p.predicted_winner || '—'}</td>
          <td>${p.prob_a != null ? (p.prob_a*100).toFixed(1)+'%' : '—'}</td>
          <td><span class="tier-badge tier-${p.tier || 'LOW'}">${p.tier || 'LOW'}</span></td>
          <td style="font-size:11px;color:var(--text-muted);max-width:200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${p.explanation || '—'}</td>
          <td style="font-size:11px;color:var(--text-muted)">${(p.created_at||'').slice(0,16)}</td>
        </tr>
      `;
    }).join('');

    root.innerHTML = `
      <div class="section-header">
        <div class="section-title">🎯 Recent Predictions</div>
        <span style="color:var(--text-muted);font-size:13px">${preds.length} predictions</span>
      </div>
      <div class="card" style="overflow-x:auto">
        <table class="data-table">
          <thead><tr>
            <th>Engine</th><th>Player A</th><th></th><th>Player B</th>
            <th>Predicted Winner</th><th>Prob A</th><th>Tier</th><th>Explanation</th><th>Time</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }).catch(err => {
    root.innerHTML = `<div class="loading-overlay" style="color:var(--loss-color)">Error: ${err.message}</div>`;
  });
}
