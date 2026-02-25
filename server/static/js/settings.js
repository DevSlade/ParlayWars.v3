/**
 * ParlayWars v3 — Settings Module
 * Date: 2026-02-25
 *
 * Renders all config.yaml settings as editable form fields.
 * Save button writes updated config back to the server.
 */

let _currentConfig = {};

function renderSettings() {
  const root = document.getElementById('settings-root');
  if (!root) return;
  root.innerHTML = `<div class="loading-overlay"><div class="spinner"></div><span>Loading settings...</span></div>`;

  apiGet('/api/config').then(config => {
    _currentConfig = JSON.parse(JSON.stringify(config)); // deep copy
    _buildSettingsHTML(root, config);
  }).catch(err => {
    root.innerHTML = `<div class="loading-overlay" style="color:var(--loss-color)">Error: ${err.message}</div>`;
  });
}

function _buildSettingsHTML(root, config) {
  const sections = [
    {
      title: 'Server', key: 'server',
      fields: [
        { label: 'Host',      path: 'server.host',      type: 'text' },
        { label: 'Port',      path: 'server.port',      type: 'number' },
        { label: 'Log Level', path: 'server.log_level', type: 'text' },
      ],
    },
    {
      title: 'Simulation', key: 'simulation',
      fields: [
        { label: 'Starting Bankroll ($)', path: 'simulation.starting_bankroll', type: 'number' },
        { label: 'Kelly Fraction',        path: 'simulation.kelly_fraction',     type: 'number' },
        { label: 'Min Confidence',        path: 'simulation.min_confidence',     type: 'number' },
        { label: 'Max Parlay Legs',       path: 'simulation.max_parlay_legs',    type: 'number' },
        { label: 'Min Edge Per Leg',      path: 'simulation.min_edge_per_leg',   type: 'number' },
        { label: 'Flat Bet ($)',          path: 'simulation.flat_bet_amount',    type: 'number' },
      ],
    },
    {
      title: 'Scheduler', key: 'scheduler',
      fields: [
        { label: 'Live Poll Interval (s)',     path: 'scheduler.live_poll_interval_seconds',     type: 'number' },
        { label: 'Schedule Poll Interval (s)', path: 'scheduler.schedule_poll_interval_seconds', type: 'number' },
        { label: 'Retrain After N Matches',    path: 'scheduler.retrain_after_n_matches',        type: 'number' },
        { label: 'Daily Snapshot Hour (UTC)',  path: 'scheduler.daily_snapshot_hour',            type: 'number' },
      ],
    },
    {
      title: 'TITAN Engine', key: 'engines.titan',
      fields: [
        { label: 'Num Estimators',  path: 'engines.titan.n_estimators',  type: 'number' },
        { label: 'Learning Rate',   path: 'engines.titan.learning_rate', type: 'number' },
        { label: 'Max Depth',       path: 'engines.titan.max_depth',     type: 'number' },
        { label: 'Reg Alpha (L1)',  path: 'engines.titan.reg_alpha',     type: 'number' },
        { label: 'Reg Lambda (L2)', path: 'engines.titan.reg_lambda',    type: 'number' },
      ],
    },
    {
      title: 'APIs', key: 'apis',
      fields: [
        { label: 'Odds API Key',    path: 'apis.odds_api.key',     type: 'text' },
        { label: 'BetsAPI Token',   path: 'apis.betsapi.token',    type: 'text' },
        { label: 'BetsAPI Enabled', path: 'apis.betsapi.enabled',  type: 'checkbox' },
      ],
    },
  ];

  const sectionsHTML = sections.map(section => {
    const fieldsHTML = section.fields.map(field => {
      const value = _getNestedValue(config, field.path);
      const inputId = `cfg-${field.path.replace(/\./g, '-')}`;
      let inputHTML;
      if (field.type === 'checkbox') {
        inputHTML = `<input type="checkbox" id="${inputId}" ${value ? 'checked' : ''} style="width:auto"
          onchange="_updateConfig('${field.path}', this.checked)" />`;
      } else {
        inputHTML = `<input type="${field.type}" id="${inputId}" value="${value !== undefined ? value : ''}"
          oninput="_updateConfig('${field.path}', ${field.type === 'number' ? 'parseFloat(this.value)||this.value' : 'this.value'})" />`;
      }
      return `
        <div class="settings-row">
          <label class="form-label" for="${inputId}">${field.label}</label>
          ${inputHTML}
        </div>
      `;
    }).join('');

    return `
      <div class="settings-section">
        <div class="settings-section-header">${section.title}</div>
        ${fieldsHTML}
      </div>
    `;
  }).join('');

  root.innerHTML = `
    <div class="section-header">
      <div>
        <div class="section-title">⚙️ Settings</div>
        <div class="section-subtitle">Changes are saved to config.yaml immediately</div>
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn btn-secondary" onclick="renderSettings()">🔄 Reset</button>
        <button class="btn btn-primary" onclick="saveSettings()">💾 Save Settings</button>
      </div>
    </div>
    <div id="settings-save-status"></div>
    ${sectionsHTML}
  `;
}

function _getNestedValue(obj, path) {
  return path.split('.').reduce((cur, key) => (cur && cur[key] !== undefined) ? cur[key] : '', obj);
}

function _setNestedValue(obj, path, value) {
  const keys = path.split('.');
  let cur = obj;
  for (let i = 0; i < keys.length - 1; i++) {
    if (!cur[keys[i]]) cur[keys[i]] = {};
    cur = cur[keys[i]];
  }
  cur[keys[keys.length - 1]] = value;
}

function _updateConfig(path, value) {
  _setNestedValue(_currentConfig, path, value);
}

async function saveSettings() {
  const statusEl = document.getElementById('settings-save-status');
  if (statusEl) statusEl.innerHTML = `<div style="color:var(--text-muted);margin-bottom:8px">Saving...</div>`;

  try {
    await fetch('/api/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ data: _currentConfig }),
    });
    if (statusEl) statusEl.innerHTML = `<div style="color:var(--win-color);margin-bottom:8px">✅ Settings saved successfully.</div>`;
    setTimeout(() => { if (statusEl) statusEl.innerHTML = ''; }, 3000);
  } catch (err) {
    if (statusEl) statusEl.innerHTML = `<div style="color:var(--loss-color);margin-bottom:8px">❌ Error: ${err.message}</div>`;
  }
}

// Console module (inline for simplicity)
function renderConsole() {
  const root = document.getElementById('console-root');
  if (!root) return;
  root.innerHTML = `
    <div class="section-header">
      <div>
        <div class="section-title">🖥 Console</div>
        <div class="section-subtitle">Live server log stream</div>
      </div>
      <div style="display:flex;gap:8px;align-items:center">
        <select id="log-filter" onchange="_filterLogs()" style="width:auto;padding:4px 8px;font-size:12px">
          <option value="">All levels</option>
          <option value="INFO">INFO</option>
          <option value="WARNING">WARNING</option>
          <option value="ERROR">ERROR</option>
          <option value="DEBUG">DEBUG</option>
        </select>
        <button class="btn btn-secondary btn-sm" onclick="_clearConsole()">🗑 Clear</button>
      </div>
    </div>
    <div class="console-container" id="console-log-box"></div>
  `;
}

let _allLogEntries = [];

function onConsoleMessage(data) {
  if (data.type === 'log_init') {
    _allLogEntries = data.entries || [];
  } else if (data.type === 'log_append') {
    _allLogEntries = _allLogEntries.concat(data.entries || []);
    // Keep last 500
    if (_allLogEntries.length > 500) _allLogEntries = _allLogEntries.slice(-500);
  }
  _renderLogs();
}

function _renderLogs() {
  const box = document.getElementById('console-log-box');
  if (!box) return;
  const filter = document.getElementById('log-filter')?.value || '';
  const filtered = filter ? _allLogEntries.filter(e => e.level === filter) : _allLogEntries;
  
  box.innerHTML = filtered.map(e => `
    <div class="log-entry ${e.level}">
      <span class="log-timestamp">${(e.ts||'').slice(11,23)}</span>
      <span class="log-level">${e.level}</span>
      <span>${_escapeHTML(e.msg||'')}</span>
    </div>
  `).join('');
  
  // Auto-scroll to bottom
  box.scrollTop = box.scrollHeight;
}

function _filterLogs() { _renderLogs(); }
function _clearConsole() { _allLogEntries = []; _renderLogs(); }

function _escapeHTML(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
