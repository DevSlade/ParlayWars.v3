/**
 * ParlayWars v3 — Alpine.js App Root
 * Date: 2026-02-25
 *
 * Global state, tab routing, WebSocket, live mode, theme toggle,
 * global search, toast notifications, data freshness indicator.
 */

function app() {
  return {
    // ── State ───────────────────────────────────────────────────────
    currentTab: 'dashboard',
    wsConnected: false,
    liveMode: true,            // auto-refresh via WebSocket when ON
    theme: 'dark',
    mobileMenuOpen: false,
    modal: { open: false, content: '' },
    stats: { bankroll: 1000.00, roi_pct: 0 },
    searchQuery: '',
    searchResults: [],
    _searchDebounce: null,
    _allPlayers: [],           // cached for search
    // Freshness
    freshnessClass: 'freshness-unknown',
    freshnessLabel: '● Syncing',
    freshnessTitle: 'Checking API sync status...',
    _freshnessTimer: null,

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

    // ── Init ────────────────────────────────────────────────────────
    init() {
      // Restore saved theme
      const savedTheme = localStorage.getItem('pw_theme') || 'dark';
      this.theme = savedTheme;
      document.documentElement.setAttribute('data-theme', savedTheme);

      // Restore live mode pref
      const savedLive = localStorage.getItem('pw_livemode');
      this.liveMode = savedLive !== 'false';

      this.loadStats();
      this.connectWebSockets();
      this.renderCurrentTab();
      this._cachePlayersForSearch();

      // Keyboard shortcut: / focuses global search
      document.addEventListener('keydown', (e) => {
        if (e.key === '/' && document.activeElement.tagName !== 'INPUT' &&
            document.activeElement.tagName !== 'TEXTAREA') {
          e.preventDefault();
          document.getElementById('global-search')?.focus();
        }
      });

      // Stats refresh
      setInterval(() => this.loadStats(), 30000);
      // Freshness refresh
      this._freshnessTimer = setInterval(() => this._updateFreshness(), 15000);
      this._updateFreshness();
    },

    // ── Tab switching ────────────────────────────────────────────────
    switchTab(tabId) {
      this.currentTab = tabId;
      this.mobileMenuOpen = false;
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

    // ── Live Mode ────────────────────────────────────────────────────
    toggleLiveMode() {
      this.liveMode = !this.liveMode;
      localStorage.setItem('pw_livemode', this.liveMode);
      showToast(this.liveMode ? '🔴 Live Mode ON' : '⬜ Live Mode OFF',
                this.liveMode ? 'info' : 'info');
    },

    // ── Theme Toggle ────────────────────────────────────────────────
    toggleTheme() {
      this.theme = this.theme === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', this.theme);
      localStorage.setItem('pw_theme', this.theme);
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

    // ── Data freshness ────────────────────────────────────────────────
    async _updateFreshness() {
      try {
        const res = await fetch('/api/freshness');
        if (!res.ok) { this._setFreshnessUnknown(); return; }
        const data = await res.json();
        const ts = data.hudstats;
        if (!ts) { this._setFreshnessUnknown(); return; }
        const ageMs = Date.now() - new Date(ts).getTime();
        const ageSec = Math.floor(ageMs / 1000);
        if (ageSec < 90) {
          this.freshnessClass = 'freshness-ok';
          this.freshnessLabel = `● ${ageSec}s ago`;
          this.freshnessTitle = `Last HudStats sync: ${ageSec}s ago`;
        } else if (ageSec < 600) {
          const m = Math.floor(ageSec / 60);
          this.freshnessClass = 'freshness-warn';
          this.freshnessLabel = `⚠️ ${m}m ago`;
          this.freshnessTitle = `Data stale — last sync ${m} min ago`;
        } else {
          const m = Math.floor(ageSec / 60);
          this.freshnessClass = 'freshness-stale';
          this.freshnessLabel = `🔴 ${m}m ago`;
          this.freshnessTitle = `⚠️ API unreachable — last sync ${m} min ago`;
        }
      } catch (e) { this._setFreshnessUnknown(); }
    },
    _setFreshnessUnknown() {
      this.freshnessClass = 'freshness-unknown';
      this.freshnessLabel = '● --';
      this.freshnessTitle = 'Sync status unknown';
    },

    // ── Global Search ────────────────────────────────────────────────
    async _cachePlayersForSearch() {
      try {
        const players = await apiGet('/api/players?limit=300');
        this._allPlayers = players;
      } catch (e) {}
    },

    onGlobalSearch(q) {
      clearTimeout(this._searchDebounce);
      if (!q || q.length < 2) { this.searchResults = []; return; }
      this._searchDebounce = setTimeout(() => {
        const lower = q.toLowerCase();
        const results = [];
        // Search players
        for (const p of this._allPlayers) {
          if ((p.name || '').toLowerCase().includes(lower)) {
            results.push({ id: `p:${p.name}`, label: `👥 ${p.name}`, type: 'player', name: p.name });
          }
          if (results.length >= 8) break;
        }
        this.searchResults = results;
      }, 150);
    },

    handleSearchResult(r) {
      this.searchQuery = '';
      this.searchResults = [];
      if (r.type === 'player') {
        this.switchTab('players');
        this.$nextTick(() => {
          if (typeof showPlayerProfile === 'function') showPlayerProfile(r.name);
        });
      }
    },

    closeSearch() {
      this.searchResults = [];
    },

    // ── WebSocket connections ────────────────────────────────────────
    connectWebSockets() {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      const base  = `${proto}://${location.host}`;

      this._connectWS(`${base}/ws/dashboard`, (data) => {
        this.wsConnected = true;
        if (!this.liveMode) return;  // respect live mode toggle
        if (typeof onDashboardUpdate === 'function') onDashboardUpdate(data);
        if (data.bankroll) this.stats.bankroll = data.bankroll;
        // Toast for bet settlement
        if (data.bet_settled) {
          const b = data.bet_settled;
          const won = b.profit_loss > 0;
          const icon = won ? '✅' : '❌';
          const msg = won
            ? `${icon} ${b.predicted_winner} won — $${b.profit_loss?.toFixed(2)} profit`
            : `${icon} Lost $${Math.abs(b.profit_loss||0).toFixed(2)} on ${b.predicted_winner}`;
          showToast(msg, won ? 'win' : 'loss');
        }
        // Toast for LOCK pick
        if (data.new_lock) {
          const l = data.new_lock;
          showToast(
            `🔒 LOCK: ${l.player_a} vs ${l.player_b} — ${((l.confidence||0)*100).toFixed(0)}% confidence`,
            'lock'
          );
          _playAlertSound('lock');
        }
        // Toast for engine retrain
        if (data.retrained) {
          showToast(`🧠 ${data.retrained.engine} retrained — accuracy: ${data.retrained.accuracy?.toFixed(1)}%`, 'retrain');
        }
      });

      this._connectWS(`${base}/ws/console`, (data) => {
        if (typeof onConsoleMessage === 'function') onConsoleMessage(data);
      });
    },

    _connectWS(url, onMessage) {
      let ws;
      const connect = () => {
        ws = new WebSocket(url);
        ws.onopen  = () => { this.wsConnected = true; };
        ws.onclose = () => {
          this.wsConnected = false;
          setTimeout(connect, 3000);
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
    openModal(html) { this.modal.content = html; this.modal.open = true; },
    closeModal()    { this.modal.open = false; },
  };
}

// ── Toast notification system ─────────────────────────────────────────────
/**
 * Show a toast notification in the bottom-right corner.
 * @param {string} message - HTML message to display
 * @param {string} type    - 'win'|'loss'|'info'|'lock'|'retrain'
 * @param {number} ttl     - milliseconds before auto-dismiss (default 5000)
 */
function showToast(message, type = 'info', ttl = 5000) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <span class="toast-msg">${message}</span>
    <button class="toast-close" onclick="this.parentElement.remove()">✕</button>
  `;
  container.appendChild(toast);
  setTimeout(() => {
    toast.classList.add('toast-dismiss');
    toast.addEventListener('animationend', () => toast.remove());
  }, ttl);
}

// ── Audio alert (browser notification sound) ─────────────────────────────
function _playAlertSound(type) {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.value = type === 'lock' ? 880 : 660;
    osc.type = 'sine';
    gain.gain.setValueAtTime(0.3, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
    osc.start();
    osc.stop(ctx.currentTime + 0.4);
  } catch (e) { /* audio not available */ }
}

// ── Shared API helpers ────────────────────────────────────────────────────
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

// ── Tier helper ───────────────────────────────────────────────────────────
function tierLabel(tier) {
  const icons = { LOCK: '🔒', STRONG: '💪', LEAN: '🎯', SKIP: '⬜',
                  HIGH: '🔒', MEDIUM: '💪', LOW: '⬜' };
  return icons[tier] || '';
}

// ── Render Export tab ─────────────────────────────────────────────────────
function renderExport() {
  const root = document.getElementById('export-root');
  if (!root) return;
  root.innerHTML = `
    <div class="section-header">
      <div>
        <div class="section-title">📥 Data Export</div>
        <div class="section-subtitle">Filter and download your data in CSV or JSON</div>
      </div>
    </div>

    <!-- Export Filters -->
    <div class="export-filters">
      <div>
        <label>Date from</label>
        <input type="date" id="exp-from">
      </div>
      <div>
        <label>Date to</label>
        <input type="date" id="exp-to">
      </div>
      <div>
        <label>Player name</label>
        <input type="text" id="exp-player" placeholder="e.g. TAAPZ">
      </div>
      <div>
        <label>Engine</label>
        <select id="exp-engine">
          <option value="">All engines</option>
          <option>TITAN</option><option>PHANTOM</option>
          <option>SURGE</option><option>ORACLE</option>
        </select>
      </div>
      <div>
        <label>Confidence tier</label>
        <select id="exp-tier">
          <option value="">All tiers</option>
          <option>LOCK</option><option>STRONG</option>
          <option>LEAN</option><option>SKIP</option>
        </select>
      </div>
      <div>
        <label>Bet result</label>
        <select id="exp-result">
          <option value="">All</option>
          <option value="won">Won</option>
          <option value="lost">Lost</option>
          <option value="pending">Pending</option>
        </select>
      </div>
    </div>

    <div style="display:grid;gap:12px;max-width:600px">
      ${[
        { label: '👥 Players',     path: 'players',     desc: 'All player profiles with stats and ratings' },
        { label: '🏀 Matches',     path: 'matches',     desc: 'Complete match history' },
        { label: '🎯 Predictions', path: 'predictions', desc: 'All engine predictions (with tier filter)' },
        { label: '💰 Bets',        path: 'bets',        desc: 'Paper trading bet log (with all filters)' },
      ].map(e => `
        <div class="export-card">
          <div>
            <div style="font-weight:600;margin-bottom:4px">${e.label}</div>
            <div style="font-size:12px;color:var(--text-muted)">${e.desc}</div>
          </div>
          <div style="display:flex;gap:8px">
            <button onclick="_doExport('${e.path}','csv')"  class="btn btn-secondary btn-sm">CSV</button>
            <button onclick="_doExport('${e.path}','json')" class="btn btn-primary btn-sm">JSON</button>
          </div>
        </div>
      `).join('')}
    </div>
  `;
}

function _buildExportParams(format) {
  const params = new URLSearchParams({ format });
  const from   = document.getElementById('exp-from')?.value;
  const to     = document.getElementById('exp-to')?.value;
  const player = document.getElementById('exp-player')?.value?.trim();
  const engine = document.getElementById('exp-engine')?.value;
  const tier   = document.getElementById('exp-tier')?.value;
  const result = document.getElementById('exp-result')?.value;
  if (from)   params.set('date_from', from);
  if (to)     params.set('date_to', to);
  if (player) params.set('player', player);
  if (engine) params.set('engine', engine);
  if (tier)   params.set('tier', tier);
  if (result) params.set('status', result);
  return params.toString();
}

function _doExport(dataset, format) {
  const qs = _buildExportParams(format);
  window.open(`/export/${dataset}?${qs}`, '_blank');
}

// ── Render Predictions tab ─────────────────────────────────────────────────
function renderPredictions() {
  const root = document.getElementById('predictions-root');
  if (!root) return;
  root.innerHTML = `<div class="loading-overlay"><div class="spinner"></div><span>Loading predictions...</span></div>`;

  apiGet('/api/predictions?limit=50').then(preds => {
    if (!preds.length) {
      root.innerHTML = `<div class="loading-overlay">No predictions yet — matches will be analysed automatically.</div>`;
      return;
    }
    const engineColors = { TITAN: 'titan', PHANTOM: 'phantom', SURGE: 'surge', ORACLE: 'oracle' };
    const rows = preds.map(p => {
      const clr = engineColors[p.engine_name] || 'titan';
      return `
        <tr>
          <td><span class="engine-name" style="color:var(--${clr}-color)">${p.engine_name}</span></td>
          <td>${p.player_a || '—'}</td><td>vs</td><td>${p.player_b || '—'}</td>
          <td style="font-weight:700">${p.predicted_winner || '—'}</td>
          <td>${p.prob_a != null ? (p.prob_a*100).toFixed(1)+'%' : '—'}</td>
          <td><span class="tier-badge tier-${p.tier || 'SKIP'}">${tierLabel(p.tier)} ${p.tier || 'SKIP'}</span></td>
          <td style="font-size:11px;color:var(--text-muted);max-width:200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${p.explanation || '—'}</td>
          <td style="font-size:11px;color:var(--text-muted)">${(p.created_at||'').slice(0,16)}</td>
        </tr>`;
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
            <th>Pick</th><th>Prob A</th><th>Tier</th><th>Explanation</th><th>Time</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }).catch(err => {
    root.innerHTML = `<div class="loading-overlay" style="color:var(--loss-color)">Error: ${err.message}</div>`;
  });
}

// ── Render Console tab ─────────────────────────────────────────────────────
function renderConsole() {
  const root = document.getElementById('console-root');
  if (!root) return;
  root.innerHTML = `
    <div class="section-header">
      <div class="section-title">🖥 Console</div>
      <div style="display:flex;gap:8px">
        <select id="console-level-filter" onchange="filterConsoleLogs()" style="padding:4px 8px;border-radius:6px;background:var(--input-bg);border:1px solid var(--border-color);color:var(--text-primary);font-size:12px">
          <option value="">All levels</option>
          <option value="INFO">INFO</option>
          <option value="WARN">WARN</option>
          <option value="ERROR">ERROR</option>
        </select>
        <button class="btn btn-secondary btn-sm" onclick="clearConsole()">Clear</button>
      </div>
    </div>
    <div class="card console-log-box" id="console-log" style="font-family:monospace;font-size:12px;min-height:400px;overflow-y:auto;max-height:70vh;padding:12px;line-height:1.6"></div>
  `;
  apiGet('/api/stats').then(() => {}).catch(() => {});
}

let _consoleLogs = [];
function onConsoleMessage(data) {
  _consoleLogs.push(data);
  if (_consoleLogs.length > 500) _consoleLogs.shift();
  filterConsoleLogs();
}
function filterConsoleLogs() {
  const box = document.getElementById('console-log');
  if (!box) return;
  const level = document.getElementById('console-level-filter')?.value || '';
  const filtered = level ? _consoleLogs.filter(l => (l.level || '').includes(level)) : _consoleLogs;
  const colors = { ERROR: 'var(--loss-color)', WARN: '#ffc107', INFO: 'var(--text-primary)', DEBUG: 'var(--text-muted)' };
  box.innerHTML = filtered.map(l => {
    const lvl = (l.level || 'INFO').toUpperCase();
    const color = colors[lvl] || 'var(--text-primary)';
    return `<div style="color:${color}">[${l.time || ''}] ${lvl} — ${l.msg || ''}</div>`;
  }).join('');
  box.scrollTop = box.scrollHeight;
}
function clearConsole() {
  _consoleLogs = [];
  const box = document.getElementById('console-log');
  if (box) box.innerHTML = '';
}
