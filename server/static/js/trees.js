/**
 * ParlayWars v3 — D3.js Interactive Tree Visualisation
 * Date: 2026-02-25
 *
 * Renders decision tree/feature importance charts for each engine
 * using D3.js. Animated expand/collapse. Scrollable.
 */

let _treeData = {};
let _selectedEngine = 'TITAN';

function renderTrees() {
  const root = document.getElementById('trees-root');
  if (!root) return;

  root.innerHTML = `
    <div class="section-header">
      <div>
        <div class="section-title">🌳 Engine Trees</div>
        <div class="section-subtitle">Interactive decision tree visualisation for each engine</div>
      </div>
      <div style="display:flex;gap:8px">
        ${['TITAN','PHANTOM','SURGE','ORACLE'].map(name => `
          <button class="btn btn-secondary btn-sm" id="tree-btn-${name}"
            onclick="selectEngine('${name}')">${name}</button>
        `).join('')}
      </div>
    </div>
    <div id="tree-content">
      <div class="loading-overlay"><div class="spinner"></div><span>Loading engine data...</span></div>
    </div>
  `;

  apiGet('/api/engines').then(engines => {
    engines.forEach(e => { _treeData[e.name] = e.tree_data; });
    selectEngine('TITAN');
  }).catch(err => {
    document.getElementById('tree-content').innerHTML =
      `<div class="loading-overlay" style="color:var(--loss-color)">Error: ${err.message}</div>`;
  });
}

function selectEngine(name) {
  _selectedEngine = name;
  // Highlight active button
  ['TITAN','PHANTOM','SURGE','ORACLE'].forEach(n => {
    const btn = document.getElementById(`tree-btn-${n}`);
    if (btn) btn.className = `btn btn-${n === name ? 'primary' : 'secondary'} btn-sm`;
  });

  const data = _treeData[name];
  if (!data) {
    document.getElementById('tree-content').innerHTML =
      `<div class="loading-overlay">No data for ${name}</div>`;
    return;
  }
  _renderEngineTree(data);
}

function _renderEngineTree(data) {
  const container = document.getElementById('tree-content');
  if (!container) return;

  const trained = data.trained;
  const topFeatures = data.top_features || [];
  const nodes = data.nodes || [];

  const engineColors = { TITAN: '#4fc3f7', PHANTOM: '#ce93d8', SURGE: '#ffb74d', ORACLE: '#ffd54f' };
  const color = engineColors[data.engine] || '#4fc3f7';

  // Feature importance bars
  const maxImp = Math.max(...topFeatures.map(f => f.importance), 0.001);
  const featureBars = topFeatures.length ? `
    <div class="card" style="margin-bottom:var(--gap)">
      <div class="card-title" style="margin-bottom:12px">Top Feature Importances</div>
      ${topFeatures.map(f => `
        <div style="margin-bottom:8px">
          <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px">
            <span style="color:var(--text-secondary)">${f.feature}</span>
            <span style="color:${color}">${(f.importance*100).toFixed(1)}%</span>
          </div>
          <div style="height:6px;background:var(--bg-input);border-radius:3px;overflow:hidden">
            <div style="height:100%;width:${(f.importance/maxImp*100).toFixed(0)}%;background:${color};border-radius:3px;transition:width 0.5s"></div>
          </div>
        </div>
      `).join('')}
    </div>
  ` : '';

  // Status info
  const statusInfo = `
    <div class="card" style="margin-bottom:var(--gap)">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <div>
          <div class="card-title">${data.engine} Engine</div>
          <div style="font-size:12px;color:var(--text-muted);margin-top:4px">
            ${data.n_estimators ? `${data.n_estimators} trees` : ''}
            ${data.max_depth ? ` · max depth ${data.max_depth}` : ''}
            ${data.model_type ? ` · ${data.model_type}` : ''}
            ${data.architecture ? data.architecture : ''}
          </div>
        </div>
        <span class="tier-badge ${trained ? 'tier-HIGH' : 'tier-LOW'}">
          ${trained ? '✓ Trained' : '○ Not Trained'}
        </span>
      </div>
    </div>
  `;

  // D3 tree visualisation
  const treeViz = nodes.length > 1 ? `
    <div class="card">
      <div class="card-title" style="margin-bottom:12px">Decision Tree (first tree — click to expand)</div>
      <div id="tree-svg-container"></div>
    </div>
  ` : '';

  container.innerHTML = statusInfo + featureBars + treeViz;

  if (nodes.length > 1) {
    _buildD3Tree(nodes, color);
  }
}

function _buildD3Tree(nodes, color) {
  const svgContainer = document.getElementById('tree-svg-container');
  if (!svgContainer || !window.d3) return;

  const W = svgContainer.clientWidth || 800;
  const H = 450;
  const margin = { top: 30, right: 20, bottom: 20, left: 20 };

  // Build hierarchy from nodes list
  const nodeMap = {};
  nodes.forEach(n => { nodeMap[n.id] = { ...n, children: [] }; });

  let rootNode = null;
  nodes.forEach(n => {
    if (n.yes && nodeMap[n.yes]) nodeMap[n.id].children.push(nodeMap[n.yes]);
    if (n.no  && nodeMap[n.no])  nodeMap[n.id].children.push(nodeMap[n.no]);
    // Left / Right (sklearn trees)
    if (n.left  && nodeMap[n.left])  nodeMap[n.id].children.push(nodeMap[n.left]);
    if (n.right && nodeMap[n.right]) nodeMap[n.id].children.push(nodeMap[n.right]);
  });

  // Find root (node not referenced as a child)
  const childIds = new Set();
  nodes.forEach(n => {
    if (n.yes) childIds.add(n.yes);
    if (n.no)  childIds.add(n.no);
    if (n.left)  childIds.add(n.left);
    if (n.right) childIds.add(n.right);
  });
  const rootId = nodes.find(n => !childIds.has(n.id))?.id;
  rootNode = rootId ? nodeMap[rootId] : Object.values(nodeMap)[0];

  if (!rootNode) return;

  svgContainer.innerHTML = '';
  const svg = d3.select(svgContainer)
    .append('svg')
    .attr('width', W)
    .attr('height', H)
    .style('background', 'var(--bg-input)');

  const g = svg.append('g')
    .attr('transform', `translate(${margin.left},${margin.top})`);

  const treeLayout = d3.tree().size([W - margin.left - margin.right, H - margin.top - margin.bottom]);
  const root = d3.hierarchy(rootNode, d => d.children && d.children.length > 0 ? d.children : null);
  treeLayout(root);

  // Links
  g.selectAll('.tree-link')
    .data(root.links())
    .enter().append('path')
    .attr('class', 'tree-link')
    .attr('d', d3.linkVertical().x(d => d.x).y(d => d.y));

  // Nodes
  const node = g.selectAll('.tree-node')
    .data(root.descendants())
    .enter().append('g')
    .attr('class', 'tree-node')
    .attr('transform', d => `translate(${d.x},${d.y})`)
    .style('cursor', 'pointer')
    .on('click', (evt, d) => { _toggleNode(d, g, root, treeLayout, color); });

  node.append('circle')
    .attr('r', 12)
    .attr('fill', d => d.data.feature === 'Leaf' ? color : 'var(--bg-card)')
    .attr('stroke', color)
    .attr('stroke-width', 2);

  node.append('text')
    .attr('dy', 25)
    .attr('text-anchor', 'middle')
    .attr('font-size', 8)
    .attr('fill', 'var(--text-secondary)')
    .text(d => {
      if (d.data.feature === 'Leaf') return `P=${(d.data.prob||0).toFixed(2)}`;
      const feat = d.data.feature || '';
      return feat.length > 14 ? feat.slice(0,12)+'…' : feat;
    });
}

function _toggleNode(d, g, root, layout, color) {
  if (d.children) {
    d._children = d.children;
    d.children = null;
  } else {
    d.children = d._children;
    d._children = null;
  }
  layout(root);
  // Animate updated positions
  g.selectAll('.tree-node')
    .transition().duration(300)
    .attr('transform', nd => `translate(${nd.x},${nd.y})`);
  g.selectAll('.tree-link')
    .transition().duration(300)
    .attr('d', d3.linkVertical().x(nd => nd.x).y(nd => nd.y));
}
