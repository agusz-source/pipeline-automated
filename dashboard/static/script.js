// Binario CRM — Production Dashboard
'use strict';

// ── State ────────────────────────────────────────────────────
const state = {
  currentPage: 'dashboard',
  dashData: null,
  leads: [],
  leadsTotal: 0,
  leadsPage: 1,
  leadsPerPage: 50,
  leadsSort: { col: 'created_at', dir: 'desc' },
  leadsStageFilter: null,
  jobs: {},
  activeLogJobId: null,
  analyticsData: null,
  editingLeadId: null,
  editingTemplateId: null,
  editingMantLeadId: null,
  charts: {},
  config: {},
  genWebsCandidates: [],
  genWebsSelected: new Set(),
  genWebsQuery: '',
  dolarRate: null,
  pagoForceCreate: false,
  pagosMap: {},
  followupSelectedMsg: 0,
  followupCandidates: [],
  followupSelected: new Set(),
  followupQuery: '',
  _followupJobId: null,
};

// ── Dólar helpers ─────────────────────────────────────────────

async function fetchDolarRate() {
  const data = await api('/api/dolar');
  if (data && data.mid) {
    state.dolarRate = data.mid;
    const el = document.getElementById('dolar-value');
    if (el) el.textContent = '$' + Math.round(data.mid).toLocaleString('es-AR');
  }
}

function toUSD(amount, moneda) {
  if (!amount) return 0;
  if (moneda === 'USD') return amount;
  return state.dolarRate ? amount / state.dolarRate : 0;
}

function fmtUSD(usdAmount) {
  const n = usdAmount || 0;
  if (n >= 1000) return 'USD ' + (n / 1000).toFixed(1) + 'K';
  return 'USD ' + n.toFixed(0);
}

// ── Socket.IO ────────────────────────────────────────────────
const socket = io({ transports: ['websocket', 'polling'] });

socket.on('connect', () => setWsStatus(true));
socket.on('disconnect', () => setWsStatus(false));
socket.on('connected', () => setWsStatus(true));

socket.on('jobs_state', ({ jobs }) => {
  jobs.forEach(j => { state.jobs[j.job_id] = j; });
  updateActiveJobsIndicator();
  if (state.currentPage === 'pipeline') renderPipelineCards();
});

socket.on('job_update', ({ job }) => {
  state.jobs[job.job_id] = job;
  updateActiveJobsIndicator();
  if (state.currentPage === 'pipeline') renderPipelineCards();
  if (state.currentPage === 'pipeline') loadFlow();

  if (state._followupJobId && job.job_id === state._followupJobId && (job.status === 'done' || job.status === 'error')) {
    state._followupJobId = null;
    const btn = document.getElementById('followup-send-btn');
    if (btn) { btn.disabled = false; btn.textContent = 'Enviar seguimientos'; }
    if (state.currentPage === 'seguimientos') {
      loadSeguimientos();
      showToast(job.status === 'done' ? 'Seguimientos enviados y marcados' : 'Envío completado con errores', job.status === 'done' ? 'success' : 'warning');
    }
  }
});

socket.on('job_progress', ({ job_id, progress, processed, total }) => {
  if (state.jobs[job_id]) {
    state.jobs[job_id].progress = progress;
    state.jobs[job_id].processed_items = processed;
    state.jobs[job_id].total_items = total;
    renderPipelineCards();
  }
});

socket.on('job_log', ({ job_id, entry }) => {
  if (state.jobs[job_id]) {
    (state.jobs[job_id].logs = state.jobs[job_id].logs || []).push(entry);
  }
  if (state.activeLogJobId === job_id || !state.activeLogJobId) {
    state.activeLogJobId = job_id;
    appendLog(entry);
  }
});

socket.on('lead_update', ({ lead }) => {
  const idx = state.leads.findIndex(l => l.id === lead.id);
  if (idx >= 0) state.leads[idx] = lead;
  if (state.currentPage === 'leads') renderLeads();
  if (state.currentPage === 'seguimientos') loadSeguimientos();
});

socket.on('lead_deleted', ({ lead_id }) => {
  state.leads = state.leads.filter(l => l.id !== lead_id);
  if (state.currentPage === 'leads') renderLeads();
});

// ── Navigation ───────────────────────────────────────────────

const PAGE_TITLES = {
  dashboard:     'Dashboard',
  clientes:      'Clientes',
  leads:         'Leads',
  mantenimiento: 'Mantenimiento',
  seguimientos:  'Seguimientos',
  pipeline:      'Pipeline',
  websites:      'Websites',
  analytics:     'Analytics',
  finanzas:      'Finanzas',
  renovaciones:  'Renovaciones',
  templates:     'Templates',
  settings:      'Ajustes',
};

function navigate(page, el) {
  if (state.currentPage === page) return;

  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(a => a.classList.remove('active'));

  document.getElementById(`page-${page}`)?.classList.add('active');
  el?.classList.add('active');
  document.getElementById('header-title').textContent = PAGE_TITLES[page] || page;

  const cta = document.getElementById('header-cta');
  if (cta) cta.innerHTML = '';

  state.currentPage = page;
  localStorage.setItem('crm_page', page);
  loadPage(page);
}

function loadPage(page) {
  switch (page) {
    case 'dashboard':     loadDashboard(); break;
    case 'clientes':      loadClientes(); break;
    case 'leads':         loadLeads(); break;
    case 'mantenimiento': loadMantenimiento(); break;
    case 'seguimientos':  loadSeguimientos(); break;
    case 'pipeline':      loadPipeline(); break;
    case 'websites':      loadWebsites(); break;
    case 'analytics':     loadAnalytics(); break;
    case 'finanzas':      loadFinanzas(); break;
    case 'renovaciones':  loadRenovaciones(); break;
    case 'templates':     loadTemplates(); break;
    case 'settings':      loadSettings(); break;
  }
}

function refresh() { loadPage(state.currentPage); }

// ── Dashboard ────────────────────────────────────────────────

async function loadDashboard() {
  const dateEl = document.getElementById('dash-date');
  if (dateEl) dateEl.textContent = new Date().toLocaleDateString('es-AR', { weekday: 'long', day: 'numeric', month: 'long' });

  const data = await api('/api/dashboard/summary');
  if (!data) return;
  state.dashData = data;

  renderDashKPIs(data);
  renderTodayTasks(data.tasks);
  renderActivityFeed(data.activity);
  renderVerticalFunnel(data.funnel);
  renderDashStageCards(data.stage_cards);
  renderDashInsights(data.insights);
  renderDashCatTable(data.categorias);

  const badge = document.getElementById('renewal-badge');
  if (badge) {
    badge.textContent = data.renewal_count;
    badge.style.display = data.renewal_count > 0 ? 'flex' : 'none';
  }
}

function renderDashKPIs(data) {
  const grid = document.getElementById('kpi-grid');
  if (!grid) return;

  const fmtARS = n => n >= 1_000_000 ? `$${(n/1_000_000).toFixed(1)}M`
                    : n >= 1_000 ? `$${Math.round(n/1_000)}K`
                    : `$${Math.round(n).toLocaleString('es-AR')}`;

  const mrrARS = data.mrr_ars ?? data.mrr ?? 0;
  const mrrUSD = data.mrr_usd ?? 0;
  const mrrPrevARS = data.mrr_prev_ars ?? data.mrr_prev ?? 0;
  const mrrPrevUSD = data.mrr_prev_usd ?? 0;

  // Main display: ARS total (ARS payments + USD converted to ARS)
  const mrrTotalARS = mrrARS + (state.dolarRate ? mrrUSD * state.dolarRate : 0);
  const mrrPrevTotalARS = mrrPrevARS + (state.dolarRate ? mrrPrevUSD * state.dolarRate : 0);
  const delta = mrrTotalARS - mrrPrevTotalARS;
  const mrrTrend = delta > 0 ? 'up' : delta < 0 ? 'down' : 'neutral';
  const mrrDeltaStr = (delta > 0 ? '+' : '') + fmtARS(Math.abs(delta));

  // Secondary line: USD equivalent
  const mrrConv = state.dolarRate
    ? (mrrUSD > 0
        ? `USD ${mrrUSD.toFixed(0)} + ≈ USD ${Math.round(mrrARS / state.dolarRate)}`
        : `≈ USD ${Math.round(mrrARS / state.dolarRate)}`)
    : null;

  const hasMRR = mrrTotalARS > 0;
  const kpis = [
    {
      label: 'Ingresos este mes',
      main: hasMRR ? fmtARS(mrrTotalARS) : '—',
      conv: hasMRR ? mrrConv : null,
      trend: mrrPrevTotalARS > 0 ? { cls: mrrTrend, text: mrrDeltaStr } : null,
      ctx: hasMRR ? 'vs mes anterior' : 'sin pagos registrados',
    },
    {
      label: 'Clientes activos',
      main: data.clients_count,
      trend: data.clients_new > 0 ? { cls: 'up', text: `+${data.clients_new} este mes` } : null,
      ctx: 'sitios entregados',
    },
    {
      label: 'Seguimientos',
      main: data.follow_ups_count,
      trend: { cls: data.follow_ups_count > 0 ? 'amber' : 'up', text: data.follow_ups_count > 0 ? 'requieren accion' : 'al dia' },
      ctx: 'sin respuesta +3 dias',
    },
    {
      label: 'Renovaciones',
      main: data.renewals_soon,
      trend: data.renewals_overdue > 0 ? { cls: 'down', text: `${data.renewals_overdue} vencidas` } : null,
      ctx: 'proximos 7 dias',
    },
  ];

  grid.innerHTML = kpis.map(k => `
    <div class="kpi">
      <div class="kpi-label">${k.label}</div>
      <div class="kpi-main-num">${k.main}</div>
      ${k.conv ? `<div class="kpi-conv">${k.conv}</div>` : ''}
      <div class="kpi-footer">
        ${k.trend ? `<span class="kpi-trend ${k.trend.cls}">${k.trend.text}</span>` : ''}
        <span class="kpi-ctx">${k.ctx}</span>
      </div>
    </div>
  `).join('');
}

function renderTodayTasks(tasks) {
  const el = document.getElementById('today-tasks');
  const badge = document.getElementById('tasks-badge');
  if (!el) return;
  const active = tasks.filter(t => !t._done);
  if (badge) badge.textContent = active.length;

  if (!tasks.length) {
    el.innerHTML = '<div style="padding:24px 0;text-align:center;color:var(--text-3);font-size:13px">Sin tareas pendientes</div>';
    return;
  }

  const CHECK_SVG = `<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2.2" width="8" height="8"><polyline points="2 6 5 9 10 3"/></svg>`;
  el.innerHTML = tasks.map((t, i) => `
    <div class="task-item" id="task-${i}">
      <span class="task-dot ${t.priority || 'medium'}"></span>
      <div class="task-body">
        <div class="task-title">${esc(t.title)}</div>
        <div class="task-sub">${esc(t.sub || '')}</div>
      </div>
      <div class="task-check" onclick="event.stopPropagation();markTask(${i})" title="Completar">${CHECK_SVG}</div>
    </div>
  `).join('');
}

function markTask(i) {
  const el = document.getElementById(`task-${i}`);
  if (el) el.classList.toggle('done');
}

function renderActivityFeed(events) {
  const el = document.getElementById('activity-feed');
  if (!el) return;

  const ICONS = {
    deployed: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="12" height="12"><polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>`,
    reply:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="12" height="12"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`,
    sent:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="12" height="12"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>`,
    created:  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="12" height="12"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><line x1="19" y1="8" x2="19" y2="14"/><line x1="22" y1="11" x2="16" y2="11"/></svg>`,
  };

  if (!events.length) {
    el.innerHTML = '<div style="padding:24px 0;text-align:center;color:var(--text-3);font-size:13px">Sin actividad reciente</div>';
    return;
  }

  el.innerHTML = events.map(e => `
    <div class="activity-item">
      <div class="act-icon ${e.color || 'blue'}">${ICONS[e.type] || ICONS.created}</div>
      <div class="act-body">
        <div class="act-label">${esc(e.label)}</div>
        <div class="act-client">${esc(e.client)}</div>
      </div>
      <div class="act-time">${timeAgo(e.time)}</div>
    </div>
  `).join('');
}

function renderVerticalFunnel(steps) {
  const el = document.getElementById('dash-funnel-v');
  if (!el || !steps?.length) return;
  const max = steps[0]?.value || 1;

  el.innerHTML = steps.map((s, i) => `
    ${i > 0 ? `
      <div class="fv-connector${s.biggest_drop ? ' big-drop' : ''}">
        ${s.pct}% pasan${s.biggest_drop ? ' — mayor caida' : ''}
      </div>
    ` : ''}
    <div class="fv-step">
      <div class="fv-label">${esc(s.label)}</div>
      <div class="fv-bar-wrap">
        <div class="fv-bar${s.biggest_drop ? ' drop' : ''}" style="width:${Math.max(2, Math.round((s.value / max) * 100))}%"></div>
      </div>
      <div class="fv-count">${s.value}</div>
    </div>
  `).join('');
}

const STAGE_COLORS = {
  discovered: '#676767', pending_send: '#4a90e2', sent: '#e8a020',
  waiting: '#f0722a', generating: '#1abc9c', ready_deploy: '#10a37f',
  deployed: '#9b59b6', link_sent: '#e91e8c', completed: '#27ae60', error: '#e74c3c',
};

function renderDashStageCards(stages) {
  const el = document.getElementById('dash-stage-cards');
  if (!el) return;
  el.innerHTML = stages.map(s => `
    <div class="stage-h-card" onclick="navigate('leads', document.querySelector('[data-page=leads]')); setTimeout(()=>filterLeadsByStage('${s.key}'), 150)">
      <div class="stage-h-dot" style="background:${STAGE_COLORS[s.key] || '#676767'}"></div>
      <div class="stage-h-name">${esc(s.label)}</div>
      <div class="stage-h-count">${s.count}</div>
      <div class="stage-h-pct">${s.pct}%</div>
    </div>
  `).join('');
}

function renderDashInsights(insights) {
  const el = document.getElementById('dash-insights');
  if (!el) return;
  if (!insights?.length) {
    el.innerHTML = '<div style="padding:24px 0;text-align:center;color:var(--text-3);font-size:13px">Sin datos suficientes</div>';
    return;
  }
  el.innerHTML = insights.map(ins => `
    <div class="insight-item">
      <div class="insight-dot ${ins.type}"></div>
      <div class="insight-text">${esc(ins.text)}</div>
    </div>
  `).join('');
}

let _catData = [], _catSort = { col: 'total', dir: 'desc' };

function renderDashCatTable(cats) {
  _catData = cats || [];
  _renderCatRows();
}

function sortCatTable(col) {
  if (_catSort.col === col) _catSort.dir = _catSort.dir === 'desc' ? 'asc' : 'desc';
  else { _catSort.col = col; _catSort.dir = 'desc'; }
  _renderCatRows();
}

function _renderCatRows() {
  const body = document.getElementById('cat-analytics-body');
  if (!body) return;
  const sorted = [..._catData].sort((a, b) => {
    const av = a[_catSort.col] ?? 0, bv = b[_catSort.col] ?? 0;
    const cmp = typeof av === 'string' ? av.localeCompare(bv) : av - bv;
    return _catSort.dir === 'desc' ? -cmp : cmp;
  });
  body.innerHTML = sorted.map(c => `
    <tr>
      <td style="font-weight:500">${esc(c.nombre)}</td>
      <td>${c.total}</td>
      <td>${c.enviados}</td>
      <td>${c.respondieron || 0}</td>
      <td>${c.interesados}</td>
      <td>${c.convertidos}</td>
      <td><span style="color:${c.tasa_interes > 20 ? 'var(--green)' : c.tasa_interes > 8 ? 'var(--amber)' : 'var(--text-3)'};font-weight:500">${c.tasa_interes}%</span></td>
      <td style="color:${c.revenue > 0 ? 'var(--text)' : 'var(--text-4)'}">${c.revenue > 0 ? '$' + c.revenue.toLocaleString() : '—'}</td>
    </tr>
  `).join('');
}

function setDashFilter(el, filter) {
  document.querySelectorAll('.dfp').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
  // Re-load with filter context — currently informational only
  loadDashboard();
}

function filterLeadsByStage(stage) {
  state.leadsStageFilter = stage;
  const pills = document.getElementById('stage-pills');
  if (pills) {
    pills.querySelectorAll('.pill').forEach(p => {
      p.classList.toggle('active', p.dataset.stage === stage);
    });
  }
  loadLeads();
}

function timeAgo(iso) {
  if (!iso) return '';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return 'ahora';
  if (diff < 3600) return `hace ${Math.floor(diff / 60)}min`;
  if (diff < 86400) return `hace ${Math.floor(diff / 3600)}h`;
  if (diff < 604800) return `hace ${Math.floor(diff / 86400)}d`;
  return fmtDate(iso);
}

// Legacy renderKPIs kept for analytics page compatibility
function renderKPIs(stats) {
  // analytics page uses its own kpi grid, no-op on dashboard
}

function renderFunnelBars(containerId, stats) {
  const c = document.getElementById(containerId);
  if (!c) return;
  const max = stats.total || 1;
  const rows = [
    { label: 'Total',         value: stats.total },
    { label: 'Enviados',      value: stats.enviados },
    { label: 'Respondieron',  value: stats.respondieron },
    { label: 'Interesados',   value: stats.interesados },
    { label: 'Webs generadas',value: stats.con_web },
    { label: 'Sitios live',   value: stats.con_link },
    { label: 'Links enviados',value: stats.links_enviados },
    { label: 'Clientes',      value: stats.clientes },
  ];
  c.innerHTML = rows.map(r => `
    <div class="funnel-bar-row">
      <div class="funnel-bar-label">${r.label}</div>
      <div class="funnel-bar-track">
        <div class="funnel-bar-fill" style="width:${Math.round((r.value||0)/max*100)}%"></div>
      </div>
      <div class="funnel-bar-val">${r.value||0}</div>
    </div>
  `).join('');
}

let stageChart = null;
function renderStageChart(stages) {
  const ctx = document.getElementById('stage-chart');
  if (!ctx) return;
  const LABELS = {
    discovered:'Descubierto', pending_send:'Pendiente',
    sent:'Enviado', waiting:'Esperando', generating:'Generando',
    ready_deploy:'Listo deploy', deployed:'Desplegado',
    link_sent:'Link enviado', completed:'Completado', error:'Error',
  };
  const labels = Object.keys(stages).map(k => LABELS[k] || k);
  const values = Object.values(stages);
  const colors = ['#676767','#4a90e2','#e8a020','#e8a020','#1abc9c','#10a37f','#9b59b6','#e91e8c','#27ae60','#e74c3c'];
  if (stageChart) stageChart.destroy();
  stageChart = new Chart(ctx, {
    type: 'doughnut',
    data: { labels, datasets: [{ data: values, backgroundColor: colors, borderWidth: 0 }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ${ctx.parsed}` } },
      },
      cutout: '72%',
    },
  });
}

function renderCatTable(cats) {
  const body = document.getElementById('cat-table-body');
  if (!body) return;
  if (!cats?.length) {
    body.innerHTML = '<tr><td colspan="6" style="padding:20px;text-align:center;color:var(--text-3)">Sin datos</td></tr>';
    return;
  }
  body.innerHTML = cats.map(c => `
    <tr>
      <td>${esc(c.nombre)}</td>
      <td>${c.total}</td>
      <td>${c.enviados}</td>
      <td>${c.interesados}</td>
      <td>${c.convertidos}</td>
      <td>${c.tasa_interes}%</td>
    </tr>
  `).join('');
}

// ── Clientes ─────────────────────────────────────────────────

async function loadClientes() {
  const data = await api('/api/clientes');
  if (!data) return;
  const grid = document.getElementById('clientes-grid');
  const countEl = document.getElementById('clientes-count');
  const clientes = data.clientes || [];
  if (countEl) countEl.textContent = `${clientes.length} cliente${clientes.length !== 1 ? 's' : ''}`;

  if (!clientes.length) {
    grid.innerHTML = '<div class="empty"><div class="empty-msg">Sin clientes registrados aun</div></div>';
    return;
  }

  grid.innerHTML = clientes.map(c => {
    const dias = c.fecha_renovacion_web
      ? Math.round((new Date(c.fecha_renovacion_web) - new Date()) / 86400000)
      : null;
    const renewClass = dias === null ? '' : dias < 30 ? 'renew-urgent' : dias < 90 ? 'renew-soon' : 'renew-ok';
    const services = [];
    if (c.fecha_renovacion_web) services.push('Web');
    if (c.fecha_renovacion_hosting) services.push('Hosting');
    if (c.fecha_renovacion_mantenimiento) services.push('Mant.');

    return `
      <div class="client-card" onclick="openLead(${c.id})">
        <div class="client-card-header">
          <div class="client-avatar">${c.nombre.charAt(0).toUpperCase()}</div>
          <div style="flex:1;min-width:0">
            <div class="client-name">${esc(c.nombre)}</div>
            <div class="client-cat">${esc(c.categoria || 'Cliente')}</div>
          </div>
          ${c.live_url ? `<a href="${esc(c.live_url)}" target="_blank" class="btn btn-ghost btn-sm" onclick="event.stopPropagation()" style="flex-shrink:0">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="11" height="11"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
            Ver sitio
          </a>` : ''}
        </div>
        <div class="client-meta">
          <span>Tel: ${esc(c.telefono || '-')}</span>
          <span>Entrega: ${fmtDate(c.fecha_entrega)}</span>
        </div>
        <div class="client-services">
          ${services.map(s => `<span class="service-tag">${s}</span>`).join('')}
          ${dias !== null ? `<span class="service-tag ${renewClass}">Web vence en ${dias}d</span>` : ''}
        </div>
        ${c.notas ? `<div class="client-notas">${esc(c.notas)}</div>` : ''}
      </div>
    `;
  }).join('');
}

// ── Servicios (Mantenimiento + Renovaciones unificado) ────────

function advanceMonthly(dateStr) {
  if (!dateStr) return null;
  let d = new Date(dateStr + 'T00:00:00');
  if (isNaN(d)) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  while (d <= today) {
    const m = d.getMonth();
    d = new Date(m === 11 ? d.getFullYear() + 1 : d.getFullYear(), m === 11 ? 0 : m + 1, d.getDate());
  }
  return d.toISOString().slice(0, 10);
}

async function loadMantenimiento() {
  const data = await api('/api/clientes');
  if (!data) return;
  const list    = document.getElementById('mantenimiento-list');
  const summary = document.getElementById('serv-summary');
  const clientes = data.clientes || [];

  if (!clientes.length) {
    list.innerHTML = '<div class="empty"><div class="empty-msg">Sin clientes para gestionar</div></div>';
    return;
  }

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  function diasHasta(fecha) {
    if (!fecha) return null;
    return Math.round((new Date(fecha + 'T00:00:00') - today) / 86400000);
  }
  function diasClass(d) {
    if (d === null) return 'service-none';
    if (d < 0)  return 'service-expired';
    if (d < 8)  return 'service-urgent';
    if (d < 31) return 'service-soon';
    return 'service-ok';
  }
  function diasLabel(d, fecha, noServTxt = 'Sin servicio') {
    if (d === null) return `<span class="service-none-text">${noServTxt}</span>`;
    if (d < 0)  return `<span class="service-expired-text">Vencido hace ${Math.abs(d)}d</span>`;
    if (d === 0) return `<span class="service-urgent-text">Hoy · ${fmtDate(fecha)}</span>`;
    return `<span class="${diasClass(d) + '-text'}">${fmtDate(fecha)}<br><small>en ${d}d</small></span>`;
  }

  const rows = clientes.map(c => {
    const mantFecha = advanceMonthly(c.fecha_renovacion_mantenimiento);
    const dWeb  = diasHasta(c.fecha_renovacion_web);
    const dHost = diasHasta(c.fecha_renovacion_hosting);
    const dMant = diasHasta(mantFecha);
    const vals  = [dWeb, dHost, dMant].filter(d => d !== null);
    const urgency = vals.length ? Math.min(...vals) : 9999;
    return { c, mantFecha, dWeb, dHost, dMant, urgency };
  });

  rows.sort((a, b) => a.urgency - b.urgency);

  const nUrgent = rows.filter(r => r.urgency < 8   && r.urgency !== 9999).length;
  const nSoon   = rows.filter(r => r.urgency >= 8  && r.urgency < 31).length;
  const nOk     = rows.filter(r => r.urgency >= 31).length;

  if (summary) {
    summary.innerHTML = `
      <span class="serv-pill serv-urgent">${nUrgent} urgente${nUrgent !== 1 ? 's' : ''}</span>
      <span class="serv-pill serv-soon">${nSoon} próximo${nSoon !== 1 ? 's' : ''}</span>
      <span class="serv-pill serv-ok">${nOk} al día</span>
    `;
  }

  list.innerHTML = `
    <div class="table-wrap">
      <table>
        <thead><tr>
          <th>Cliente</th>
          <th>Mantenimiento mensual</th>
          <th>Web (anual)</th>
          <th>Hosting (anual)</th>
          <th>Sitio</th>
          <th></th>
        </tr></thead>
        <tbody>
          ${rows.map(({ c, mantFecha, dWeb, dHost, dMant }) => `
            <tr>
              <td>
                <div style="font-weight:500">${esc(c.nombre)}</div>
                <div style="font-size:11px;color:var(--text-3)">${esc(c.categoria || '')}</div>
              </td>
              <td class="mant-cell ${diasClass(dMant)}">${diasLabel(dMant, mantFecha, '—')}</td>
              <td class="mant-cell ${diasClass(dWeb)}">${diasLabel(dWeb, c.fecha_renovacion_web)}</td>
              <td class="mant-cell ${diasClass(dHost)}">${diasLabel(dHost, c.fecha_renovacion_hosting)}</td>
              <td>
                ${c.live_url
                  ? `<a href="${esc(c.live_url)}" target="_blank" style="font-size:11px;color:var(--accent);font-family:var(--mono);text-decoration:none">${c.live_url.replace(/^https?:\/\//,'').slice(0,28)}</a>`
                  : '<span style="color:var(--text-3);font-size:11px">Sin URL</span>'
                }
              </td>
              <td style="white-space:nowrap;display:flex;gap:6px;align-items:center">
                <button class="btn btn-ghost btn-sm" onclick="openMantModal(${c.id})">Editar</button>
                <button class="btn btn-primary btn-sm" onclick="openRegistrarPago(${c.id},'${esc(c.nombre).replace(/'/g,"\\'")}','${(c.telefono||'').replace(/'/g,"\\'")}')">+ Pago</button>
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;
}

function openMantModal(leadId) {
  state.editingMantLeadId = leadId;
  const lead = null;
  api(`/api/leads/${leadId}`).then(data => {
    if (!data) return;
    document.getElementById('mant-modal-title').textContent = data.nombre;
    document.getElementById('mant-renov-web').value = data.fecha_renovacion_web || '';
    document.getElementById('mant-renov-hosting').value = data.fecha_renovacion_hosting || '';
    document.getElementById('mant-renov-mant').value = data.fecha_renovacion_mantenimiento || '';
    document.getElementById('mant-live-url').value = data.live_url || '';
    document.getElementById('mant-notas').value = data.notas || '';
    openModal('mant-modal');
  });
}

async function saveMantModal() {
  const id = state.editingMantLeadId;
  if (!id) return;
  const r = await api(`/api/leads/${id}`, 'PUT', {
    fecha_renovacion_web: val('mant-renov-web') || null,
    fecha_renovacion_hosting: val('mant-renov-hosting') || null,
    fecha_renovacion_mantenimiento: val('mant-renov-mant') || null,
    live_url: val('mant-live-url') || null,
    notas: val('mant-notas'),
  });
  if (r) {
    showToast('Servicios actualizados', 'success');
    closeModal('mant-modal');
    loadMantenimiento();
  }
}

// ── Pipeline ─────────────────────────────────────────────────

const STAGE_ICONS = {
  scrape:        `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>`,
  discover:      `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>`,
  send:          `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>`,
  generate_webs: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>`,
  deploy:        `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><polyline points="16 3 21 3 21 8"/><line x1="4" y1="20" x2="21" y2="3"/><polyline points="21 16 21 21 16 21"/><line x1="15" y1="15" x2="21" y2="21"/></svg>`,
  send_links:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>`,
};

const STAGE_META = {
  scrape:        { label: 'Scraper Apify',   color: '#4a90e2' },
  discover:      { label: 'Importar leads',  color: '#9b59b6' },
  send:          { label: 'Enviar mensajes', color: '#e8a020' },
  generate_webs: { label: 'Generar webs',    color: '#1abc9c' },
  deploy:        { label: 'Deploy Vercel',   color: '#10a37f' },
  send_links:    { label: 'Enviar links',    color: '#e91e8c' },
};

let stageInfoCache = {};

async function loadPipeline() {
  const data = await api('/api/pipeline/stages');
  if (data) {
    stageInfoCache = {};
    data.stages.forEach(s => { stageInfoCache[s.key] = s; });
  }
  renderPipelineCards();
  loadFlow();
}

function renderPipelineCards() {
  const grid = document.getElementById('pipeline-stage-cards');
  if (!grid || state.currentPage !== 'pipeline') return;

  grid.innerHTML = Object.keys(STAGE_META).map(stage => {
    const meta = STAGE_META[stage];
    const job = Object.values(state.jobs).find(j => j.stage === stage && j.status !== 'cancelled');
    const info = stageInfoCache[stage];
    const status = job?.status || 'idle';
    const progress = job?.progress || 0;
    const isRunning = status === 'running';
    const isPaused = status === 'paused';
    const isDone = status === 'completed' || status === 'failed';
    const processed = job?.processed_items || 0;
    const total = job?.total_items || 0;
    const count = info?.count ?? '-';

    let elapsed = '';
    if (job?.started_at) {
      const secs = Math.round((Date.now() - new Date(job.started_at)) / 1000);
      elapsed = secs < 60 ? `${secs}s` : `${Math.floor(secs/60)}m${secs%60}s`;
    }

    const lastLog = job?.logs?.length ? job.logs[job.logs.length - 1]?.msg : '';
    const truncLog = lastLog ? (lastLog.length > 52 ? lastLog.slice(0,52) + '...' : lastLog) : '';

    return `
      <div class="stage-card ${status}" id="stage-card-${stage}">
        <div class="stage-header">
          <div class="stage-name">
            <div class="stage-icon" style="background:${meta.color}20;color:${meta.color}">
              ${STAGE_ICONS[stage] || ''}
            </div>
            ${meta.label}
          </div>
          <span class="stage-status-badge status-${status}">${statusLabel(status)}</span>
        </div>
        <div class="stage-count-row">
          <div class="stage-count">${count}</div>
          <div style="font-size:12px;color:var(--text-3)">leads</div>
          ${elapsed ? `<div style="font-size:12px;color:var(--text-3);margin-left:auto;font-variant-numeric:tabular-nums">${elapsed}</div>` : ''}
        </div>
        ${(isRunning || isPaused || isDone) ? `
          <div class="stage-progress">
            <div class="progress-bar">
              <div class="progress-fill ${isPaused?'paused':status==='failed'?'failed':''}"
                   style="width:${progress}%"></div>
            </div>
            <div class="progress-text">
              <span>${total > 0 ? `${processed} / ${total}` : 'Procesando...'}</span>
              <span>${progress}%</span>
            </div>
          </div>
          ${truncLog ? `<div style="font-size:11px;color:var(--text-3);font-family:var(--mono);overflow:hidden;white-space:nowrap;text-overflow:ellipsis">${esc(truncLog)}</div>` : ''}
        ` : ''}
        ${job?.error ? `<div style="color:var(--red);font-size:11.5px;margin-top:2px">${esc(job.error.slice(0,80))}</div>` : ''}
        <div class="stage-actions">
          ${isRunning ? `
            <button class="btn btn-ghost btn-sm" onclick="pauseJob('${job.job_id}')">Pausar</button>
            <button class="btn btn-danger btn-sm" onclick="stopJob('${job.job_id}')">Detener</button>
          ` : isPaused ? `
            <button class="btn btn-primary btn-sm" onclick="resumeJob('${job.job_id}')">Continuar</button>
            <button class="btn btn-danger btn-sm" onclick="stopJob('${job.job_id}')">Cancelar</button>
          ` : `
            ${stage === 'generate_webs'
              ? `<button class="btn btn-primary btn-sm" onclick="openGenerateWebsModal()">Iniciar</button>`
              : stage === 'scrape'
              ? `<button class="btn btn-primary btn-sm" onclick="openScrapeModal()">Iniciar</button>`
              : stage === 'send_links'
              ? `<button class="btn btn-primary btn-sm" onclick="openSendLinksModal()">Iniciar</button>`
              : `<button class="btn btn-primary btn-sm" onclick="startStage('${stage}')">Iniciar</button>`
            }
          `}
          ${job?.logs?.length ? `
            <button class="btn btn-ghost btn-sm" onclick="showJobLogs('${job.job_id}')">Ver logs</button>
          ` : ''}
        </div>
      </div>
    `;
  }).join('');
}

function statusLabel(s) {
  return {
    idle:'Inactivo', running:'Activo', paused:'Pausado',
    completed:'Completado', failed:'Error', cancelled:'Cancelado', queued:'En cola'
  }[s] || s;
}

async function startStage(stage) {
  const r = await api(`/api/pipeline/start/${stage}`, 'POST', {});
  if (r) {
    state.jobs[r.job_id] = {
      job_id: r.job_id, stage, status: 'running',
      progress: 0, logs: [], started_at: new Date().toISOString()
    };
    state.activeLogJobId = r.job_id;
    clearLogEntries();
    renderPipelineCards();
    showToast(`Iniciando ${STAGE_META[stage]?.label || stage}...`, 'success');
  }
}

async function stopJob(jobId) {
  await api(`/api/pipeline/stop/${jobId}`, 'POST');
  if (state.jobs[jobId]) state.jobs[jobId].status = 'cancelled';
  renderPipelineCards();
}

async function pauseJob(jobId) {
  await api(`/api/pipeline/pause/${jobId}`, 'POST');
  if (state.jobs[jobId]) state.jobs[jobId].status = 'paused';
  renderPipelineCards();
}

async function resumeJob(jobId) {
  await api(`/api/pipeline/resume/${jobId}`, 'POST');
  if (state.jobs[jobId]) state.jobs[jobId].status = 'running';
  renderPipelineCards();
}

function showJobLogs(jobId) {
  state.activeLogJobId = jobId;
  const job = state.jobs[jobId];
  if (!job) return;
  clearLogEntries();
  (job.logs || []).forEach(appendLog);
  const label = document.getElementById('log-job-label');
  if (label) label.textContent = `· ${STAGE_META[job.stage]?.label || job.stage}`;
}

function appendLog(entry) {
  const container = document.getElementById('log-entries');
  if (!container) return;
  const empty = container.querySelector('.empty');
  if (empty) empty.remove();

  const isError = entry.level === 'error';
  const isWarn  = entry.level === 'warning';
  const isSucc  = entry.msg?.includes('completado') || entry.msg?.includes('completada') || entry.msg?.includes('nuevos resultados');

  const ts  = entry.ts ? new Date(entry.ts).toLocaleTimeString('es-AR', { hour12: false }) : '';
  const cls = isError ? 'error' : isWarn ? 'warning' : isSucc ? 'success' : 'info';

  const el = document.createElement('div');
  el.className = 'log-entry';
  el.innerHTML = `<span class="log-ts">${ts}</span><span class="log-msg ${cls}">${esc(entry.msg)}</span>`;
  container.appendChild(el);

  const autoscroll = document.getElementById('log-autoscroll');
  if (autoscroll?.checked) container.scrollTop = container.scrollHeight;
  while (container.children.length > 500) container.firstChild.remove();
}

function clearLogs() {
  clearLogEntries();
  state.activeLogJobId = null;
  const label = document.getElementById('log-job-label');
  if (label) label.textContent = '';
}

function clearLogEntries() {
  const c = document.getElementById('log-entries');
  if (c) c.innerHTML = '<div class="empty"><div class="empty-msg" style="color:var(--text-4)">Sin logs</div></div>';
}

function updateActiveJobsIndicator() {
  const el = document.getElementById('active-jobs-indicator');
  if (!el) return;
  const running = Object.values(state.jobs).filter(j => j.status === 'running');
  if (running.length) {
    el.innerHTML = `<div class="job-indicator"><div class="job-indicator-dot"></div>${running.length} activo${running.length > 1 ? 's' : ''}</div>`;
  } else {
    el.innerHTML = '';
  }
}

// ── Scrape Niche Modal ────────────────────────────────────────

const state_scrape = { niches: {}, selected: new Set(), account: 'both' };

function setScrapeAccount(acct, el) {
  state_scrape.account = acct;
  document.querySelectorAll('.scrape-acct-btn').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
}

async function openScrapeModal() {
  const data = await api('/api/niches');
  if (!data) return;
  state_scrape.niches = data.niches;
  state_scrape.selected = new Set(Object.keys(data.niches));
  state_scrape.account = 'both';
  document.querySelectorAll('.scrape-acct-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.acct === 'both')
  );

  const list = document.getElementById('scrape-niche-list');
  if (list) {
    list.innerHTML = Object.entries(data.niches).map(([key, niche]) => `
      <label class="candidate-item" style="align-items:center">
        <input type="checkbox" class="niche-chk" value="${key}" checked
          onchange="toggleNiche('${key}', this.checked)">
        <div style="flex:1">
          <div style="font-size:13px;font-weight:500;color:var(--text)">${esc(niche.label)}</div>
          <div style="font-size:11px;color:var(--text-3)">${niche.queries.length} queries</div>
        </div>
      </label>
    `).join('');
  }

  updateScrapePreview();
  openModal('scrape-modal');
}

function toggleNiche(key, checked) {
  if (checked) state_scrape.selected.add(key);
  else state_scrape.selected.delete(key);
  updateScrapePreview();
}

function updateScrapePreview() {
  const preview = document.getElementById('scrape-queries-preview');
  if (!preview) return;
  const queries = [];
  Object.entries(state_scrape.niches).forEach(([key, niche]) => {
    if (state_scrape.selected.has(key)) queries.push(...niche.queries);
  });
  const customQ = val('scrape-custom-query');
  if (customQ) queries.push(customQ);
  preview.innerHTML = queries.length
    ? queries.map(q => `<span>&mdash; ${esc(q)}</span>`).join('')
    : '<span style="color:var(--text-4)">Ninguna query seleccionada</span>';
}

async function startScrapeWithConfig() {
  const queries = [];
  Object.entries(state_scrape.niches).forEach(([key, niche]) => {
    if (state_scrape.selected.has(key)) queries.push(...niche.queries);
  });
  const customQ = val('scrape-custom-query');
  if (customQ) queries.push(customQ);
  if (!queries.length) { showToast('Selecciona al menos un nicho', 'error'); return; }

  const r = await api('/api/pipeline/start/scrape', 'POST', { queries, account: state_scrape.account });
  if (r) {
    state.jobs[r.job_id] = {
      job_id: r.job_id, stage: 'scrape', status: 'running',
      progress: 0, logs: [], started_at: new Date().toISOString()
    };
    state.activeLogJobId = r.job_id;
    clearLogEntries();
    closeModal('scrape-modal');
    renderPipelineCards();
    const acctLabel = state_scrape.account === 'both' ? 'ambas cuentas' : `cuenta ${state_scrape.account}`;
    showToast(`Scraping iniciado — ${queries.length} queries (${acctLabel})`, 'success');
  }
}

// ── Generate Webs Modal ───────────────────────────────────────

async function openGenerateWebsModal() {
  state.genWebsSelected = new Set();
  state.genWebsQuery = '';
  const data = await api('/api/generate-webs/candidates');
  if (!data) return;
  state.genWebsCandidates = data.candidates || [];
  const searchEl = document.getElementById('gen-webs-search');
  if (searchEl) searchEl.value = '';
  renderGenWebsCandidates(state.genWebsCandidates);
  openModal('gen-webs-modal');
}

function filterGenWebsCandidates(q) {
  state.genWebsQuery = q.trim().toLowerCase();
  const filtered = state.genWebsQuery
    ? state.genWebsCandidates.filter(c =>
        (c.nombre || '').toLowerCase().includes(state.genWebsQuery) ||
        (c.telefono || '').includes(state.genWebsQuery)
      )
    : state.genWebsCandidates;
  renderGenWebsCandidates(filtered);
}

function renderGenWebsCandidates(candidates) {
  const container = document.getElementById('gen-webs-candidates');
  if (!candidates.length) {
    container.innerHTML = '<div class="empty"><div class="empty-msg">Sin resultados</div></div>';
    return;
  }
  container.innerHTML = candidates.map(c => `
    <label class="candidate-item">
      <input type="checkbox" class="candidate-chk" value="${c.id}"
        ${state.genWebsSelected.has(c.id) ? 'checked' : ''}
        onchange="toggleCandidate(${c.id}, this.checked)">
      <div class="candidate-info">
        <div class="candidate-name">${esc(c.nombre)}</div>
        <div class="candidate-meta">
          ${esc(c.telefono || '')}
          ${c.categoria ? ' · ' + esc(c.categoria) : ''}
          ${c.fecha_envio ? ' · Enviado ' + fmtDate(c.fecha_envio) : ''}
          ${c.project_path ? ' · <span style="color:var(--green)">Web generada</span>' : ''}
          ${c.estado_respuesta ? ` · <span style="color:var(--amber)">${esc(c.estado_respuesta)}</span>` : ''}
        </div>
      </div>
    </label>
  `).join('');
  updateGenWebsCount();
}

function toggleCandidate(id, checked) {
  if (checked) state.genWebsSelected.add(id);
  else state.genWebsSelected.delete(id);
  updateGenWebsCount();
}

function selectAllCandidates(checked) {
  const visible = state.genWebsQuery
    ? state.genWebsCandidates.filter(c =>
        (c.nombre || '').toLowerCase().includes(state.genWebsQuery) ||
        (c.telefono || '').includes(state.genWebsQuery)
      )
    : state.genWebsCandidates;
  visible.forEach(c => {
    if (checked) state.genWebsSelected.add(c.id);
    else state.genWebsSelected.delete(c.id);
  });
  document.querySelectorAll('.candidate-chk').forEach(el => { el.checked = checked; });
  updateGenWebsCount();
}

function updateGenWebsCount() {
  const el = document.getElementById('gen-webs-sel-count');
  if (el) el.textContent = `${state.genWebsSelected.size} seleccionados`;
}

async function startGenerateWebs() {
  const leadIds = Array.from(state.genWebsSelected);
  if (!leadIds.length) {
    showToast('Selecciona al menos un lead', 'error');
    return;
  }

  const active = Object.values(state.jobs).find(j => j.stage === 'generate_webs' && ['running','paused'].includes(j.status));
  if (active) {
    showToast('Ya hay una generacion en curso', 'error');
    closeModal('gen-webs-modal');
    return;
  }

  const r = await api('/api/pipeline/start/generate_webs', 'POST', { lead_ids: leadIds });
  if (r) {
    state.jobs[r.job_id] = {
      job_id: r.job_id, stage: 'generate_webs', status: 'running',
      progress: 0, logs: [], started_at: new Date().toISOString()
    };
    state.activeLogJobId = r.job_id;
    clearLogEntries();
    closeModal('gen-webs-modal');
    renderPipelineCards();
    showToast(`Generando ${leadIds.length} sitio${leadIds.length !== 1 ? 's' : ''}...`, 'success');
  }
}

// ── Send links modal ─────────────────────────────────────────

async function openSendLinksModal() {
  state.sendLinksSelected = new Set();
  state.sendLinksQuery = '';
  const data = await api('/api/send-links/candidates');
  if (!data) return;
  state.sendLinksCandidates = data.candidates || [];
  const searchEl = document.getElementById('send-links-search');
  if (searchEl) searchEl.value = '';
  renderSendLinksCandidates(state.sendLinksCandidates);
  openModal('send-links-modal');
}

function filterSendLinksCandidates(q) {
  state.sendLinksQuery = q.trim().toLowerCase();
  const filtered = state.sendLinksQuery
    ? state.sendLinksCandidates.filter(c =>
        (c.nombre || '').toLowerCase().includes(state.sendLinksQuery) ||
        (c.telefono || '').includes(state.sendLinksQuery)
      )
    : state.sendLinksCandidates;
  renderSendLinksCandidates(filtered);
}

function renderSendLinksCandidates(candidates) {
  const container = document.getElementById('send-links-candidates');
  if (!candidates.length) {
    container.innerHTML = '<div class="empty"><div class="empty-msg">Sin resultados</div></div>';
    return;
  }
  container.innerHTML = candidates.map(c => `
    <label class="candidate-item">
      <input type="checkbox" class="send-links-chk" value="${c.id}"
        ${state.sendLinksSelected.has(c.id) ? 'checked' : ''}
        onchange="toggleSendLinksCandidate(${c.id}, this.checked)">
      <div class="candidate-info">
        <div class="candidate-name">${esc(c.nombre)}</div>
        <div class="candidate-meta">
          ${esc(c.telefono || '')}
          ${c.categoria ? ' · ' + esc(c.categoria) : ''}
          ${c.live_url ? ` · <span style="color:var(--green)">✓ URL lista</span>` : ''}
          ${c.enviado_links ? ` · <span style="color:var(--amber)">Ya enviado</span>` : ''}
        </div>
      </div>
    </label>
  `).join('');
  updateSendLinksCount();
}

function toggleSendLinksCandidate(id, checked) {
  if (checked) state.sendLinksSelected.add(id);
  else state.sendLinksSelected.delete(id);
  updateSendLinksCount();
}

function selectAllSendLinks(checked) {
  const visible = state.sendLinksQuery
    ? state.sendLinksCandidates.filter(c =>
        (c.nombre || '').toLowerCase().includes(state.sendLinksQuery) ||
        (c.telefono || '').includes(state.sendLinksQuery)
      )
    : state.sendLinksCandidates;
  visible.forEach(c => {
    if (checked) state.sendLinksSelected.add(c.id);
    else state.sendLinksSelected.delete(c.id);
  });
  document.querySelectorAll('.send-links-chk').forEach(el => { el.checked = checked; });
  updateSendLinksCount();
}

function updateSendLinksCount() {
  const el = document.getElementById('send-links-sel-count');
  if (el) el.textContent = `${state.sendLinksSelected.size} seleccionados`;
}

async function startSendLinks() {
  const leadIds = Array.from(state.sendLinksSelected);
  if (!leadIds.length) {
    showToast('Seleccioná al menos un lead', 'error');
    return;
  }
  const r = await api('/api/pipeline/start/send_links', 'POST', { lead_ids: leadIds });
  if (r) {
    state.jobs[r.job_id] = {
      job_id: r.job_id, stage: 'send_links', status: 'running',
      progress: 0, logs: [], started_at: new Date().toISOString()
    };
    state.activeLogJobId = r.job_id;
    clearLogEntries();
    closeModal('send-links-modal');
    renderPipelineCards();
    showToast(`Enviando links a ${leadIds.length} negocio${leadIds.length !== 1 ? 's' : ''}...`, 'success');
  }
}

// ── Flujo de nodos ───────────────────────────────────────────

const FLOW_NODES = [
  { id: 'scrape',        label: 'Scraper',       sub: 'Google Maps / Apify',  col: 0, row: 0 },
  { id: 'discover',      label: 'Importar',       sub: 'dataset.json → DB',    col: 1, row: 0 },
  { id: 'send',          label: 'Outreach',       sub: 'WhatsApp masivo',      col: 2, row: 0 },
  { id: 'generate_webs', label: 'Generar web',    sub: 'Claude + templates',   col: 3, row: 0 },
  { id: 'deploy',        label: 'Deploy',         sub: 'Vercel / GitHub',      col: 4, row: 0 },
  { id: 'send_links',    label: 'Enviar links',   sub: 'Notificacion final',   col: 5, row: 0 },
];

const FLOW_EDGES = [
  ['scrape', 'discover'],
  ['discover', 'send'],
  ['send', 'generate_webs'],
  ['generate_webs', 'deploy'],
  ['deploy', 'send_links'],
];

const NODE_W = 148;
const NODE_H = 80;
const NODE_GAP_X = 70;
const NODE_GAP_Y = 110;
const CANVAS_PAD = 40;

let flowAnimFrame = null;
let flowOffset = { x: 0, y: 0 };
let flowDragging = false;
let flowDragStart = null;

async function loadFlow() {
  const stagesData = await api('/api/pipeline/stages');
  const counts = {};
  if (stagesData) stagesData.stages.forEach(s => { counts[s.key] = s.count; });

  const canvas = document.getElementById('flujo-canvas');
  const nodesEl = document.getElementById('flujo-nodes');
  const edgesEl = document.getElementById('flujo-edges');
  if (!canvas || !nodesEl || !edgesEl) return;

  const totalW = FLOW_NODES.length * (NODE_W + NODE_GAP_X) - NODE_GAP_X + CANVAS_PAD * 2;
  const totalH = NODE_H + CANVAS_PAD * 2;

  nodesEl.innerHTML = '';
  edgesEl.innerHTML = '';

  const positions = {};

  FLOW_NODES.forEach((node, i) => {
    const x = CANVAS_PAD + i * (NODE_W + NODE_GAP_X);
    const y = CANVAS_PAD;
    positions[node.id] = { x, y };

    const job = Object.values(state.jobs).find(j => j.stage === node.id && j.status !== 'cancelled');
    const status = job?.status || 'idle';
    const progress = job?.progress || 0;
    const count = counts[node.id] ?? 0;

    const el = document.createElement('div');
    el.className = `flow-node flow-node-${status}`;
    el.id = `flow-node-${node.id}`;
    el.style.left = x + 'px';
    el.style.top = y + 'px';
    el.style.width = NODE_W + 'px';
    el.style.height = NODE_H + 'px';
    el.innerHTML = `
      <div class="flow-node-header">
        <div class="flow-node-status-dot dot-${status}"></div>
        <div class="flow-node-label">${esc(node.label)}</div>
        <div class="flow-node-count">${count}</div>
      </div>
      <div class="flow-node-sub">${esc(node.sub)}</div>
      ${status === 'running' ? `
        <div class="flow-node-progress">
          <div class="flow-node-progress-fill" style="width:${progress}%"></div>
        </div>
      ` : ''}
    `;
    el.addEventListener('click', () => {
      navigate('pipeline', document.querySelector('[data-page="pipeline"]'));
    });
    nodesEl.appendChild(el);
  });

  edgesEl.setAttribute('width', totalW);
  edgesEl.setAttribute('height', totalH);
  edgesEl.style.width = totalW + 'px';
  edgesEl.style.height = totalH + 'px';

  FLOW_EDGES.forEach(([fromId, toId]) => {
    const from = positions[fromId];
    const to   = positions[toId];
    if (!from || !to) return;

    const x1 = from.x + NODE_W;
    const y1 = from.y + NODE_H / 2;
    const x2 = to.x;
    const y2 = to.y + NODE_H / 2;
    const cx1 = x1 + (x2 - x1) * 0.5;
    const cx2 = x2 - (x2 - x1) * 0.5;

    const fromJob = Object.values(state.jobs).find(j => j.stage === fromId && j.status !== 'cancelled');
    const toJob   = Object.values(state.jobs).find(j => j.stage === toId   && j.status !== 'cancelled');
    const isActive = (fromJob?.status === 'running' || fromJob?.status === 'completed') &&
                     (toJob?.status === 'running' || !toJob);

    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', `M${x1},${y1} C${cx1},${y1} ${cx2},${y2} ${x2},${y2}`);
    path.setAttribute('class', `flow-edge${isActive ? ' flow-edge-active' : ''}`);

    if (isActive) {
      const dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      dot.setAttribute('r', '4');
      dot.setAttribute('class', 'flow-edge-dot');
      const anim = document.createElementNS('http://www.w3.org/2000/svg', 'animateMotion');
      anim.setAttribute('dur', '1.8s');
      anim.setAttribute('repeatCount', 'indefinite');
      const mp = document.createElementNS('http://www.w3.org/2000/svg', 'mpath');
      const pathId = `edge-path-${fromId}-${toId}`;
      path.setAttribute('id', pathId);
      mp.setAttributeNS('http://www.w3.org/1999/xlink', 'xlink:href', `#${pathId}`);
      anim.appendChild(mp);
      dot.appendChild(anim);
      edgesEl.appendChild(path);
      edgesEl.appendChild(dot);
    } else {
      edgesEl.appendChild(path);
    }
  });

  canvas.style.width = totalW + 'px';
  canvas.style.height = totalH + 'px';
}

// ── Kanban ───────────────────────────────────────────────────

const KANBAN_STAGES = [
  'discovered','pending_send','sent','waiting',
  'generating','ready_deploy','deployed','link_sent','completed','error',
];
const KANBAN_LABELS = {
  discovered:'Descubierto', pending_send:'Pendiente',
  sent:'Enviado', waiting:'Esperando respuesta',
  generating:'Generando web', ready_deploy:'Listo deploy',
  deployed:'Desplegado', link_sent:'Link enviado',
  completed:'Completado', error:'Error',
};

async function loadKanban() {
  const data = await api('/api/leads/kanban');
  if (!data) return;
  renderKanban(data.board, data.counts);
}

function renderKanban(board, counts) {
  const container = document.getElementById('kanban-board');
  if (!container) return;
  container.innerHTML = KANBAN_STAGES.map(stage => `
    <div class="kanban-col" id="kanban-col-${stage}">
      <div class="kanban-col-header">
        <div class="kanban-col-title">${KANBAN_LABELS[stage]}</div>
        <span class="kanban-count">${counts[stage] || 0}</span>
      </div>
      <div class="kanban-cards" id="kanban-cards-${stage}">
        ${(board[stage] || []).map(lead => renderKanbanCard(lead)).join('')}
        ${!(board[stage]?.length) ? '<div style="padding:12px;text-align:center;font-size:11px;color:var(--text-3)">Vacio</div>' : ''}
      </div>
    </div>
  `).join('');

  container.querySelectorAll('.kanban-cards').forEach(el => enableDrop(el));
  container.querySelectorAll('.kanban-card').forEach(card => {
    card.draggable = true;
    card.addEventListener('dragstart', e => {
      e.dataTransfer.setData('lead_id', card.dataset.leadId);
      card.style.opacity = '0.5';
    });
    card.addEventListener('dragend', () => card.style.opacity = '1');
  });
}

function renderKanbanCard(lead) {
  const urlShort = lead.live_url ? lead.live_url.replace(/^https?:\/\//, '').slice(0, 30) : '';
  return `
    <div class="kanban-card" data-lead-id="${lead.id}" data-stage="${lead.stage}" onclick="openLead(${lead.id})">
      <div class="kanban-card-name">${esc(lead.nombre)}</div>
      <div class="kanban-card-meta">
        <span class="priority-dot p${lead.prioridad || 3}"></span>
        <span>${esc(lead.categoria || '')}${lead.score ? ` · ${lead.score}pts` : ''}</span>
      </div>
      ${lead.live_url ? `
      <div class="kanban-card-url" onclick="event.stopPropagation()">
        <span class="kanban-url-text">${urlShort}</span>
        <button class="kanban-preview-btn" onclick="openSitePreview('${esc(lead.live_url)}')" title="Preview">&#9654;</button>
        <a href="${esc(lead.live_url)}" target="_blank" class="kanban-ext-btn" title="Abrir">&#8599;</a>
      </div>` : ''}
    </div>
  `;
}

function openSitePreview(url) {
  document.getElementById('site-preview-iframe').src = url;
  document.getElementById('site-preview-link').href = url;
  document.getElementById('site-preview-link').textContent = url;
  openModal('site-preview-modal');
}

function enableDrop(el) {
  el.addEventListener('dragover', e => { e.preventDefault(); el.style.background = 'rgba(16,185,129,0.05)'; });
  el.addEventListener('dragleave', () => { el.style.background = ''; });
  el.addEventListener('drop', async e => {
    e.preventDefault();
    el.style.background = '';
    const leadId = e.dataTransfer.getData('lead_id');
    const newStage = el.id.replace('kanban-cards-', '');
    if (!leadId || !newStage) return;
    await api(`/api/leads/${leadId}/stage`, 'PUT', { stage: newStage });
    loadKanban();
  });
}

// ── Leads ────────────────────────────────────────────────────

const STAGE_BADGE = {
  discovered:   ['badge-discovered','Descubierto'],
  pending_send: ['badge-sent','Pendiente'],
  sent:         ['badge-sent','Enviado'],
  waiting:      ['badge-waiting','Esperando'],
  generating:   ['badge-generating','Generando web'],
  ready_deploy: ['badge-generating','Listo deploy'],
  deployed:     ['badge-deployed','Desplegado'],
  link_sent:    ['badge-link-sent','Link enviado'],
  completed:    ['badge-completed','Completado'],
  error:        ['badge-error','Error'],
};
const RESPONSE_BADGE = {
  interest:        ['badge-interest','Interesado'],
  positive_intent: ['badge-interest','Positivo'],
  price_request:   ['badge-interest','Pidio precio'],
  info_request:    ['badge-neutral','Pidio info'],
  follow_up:       ['badge-neutral','Follow-up'],
  rejection:       ['badge-rejected','Rechazo'],
  neutral:         ['badge-neutral','Neutral'],
};

async function loadLeads() {
  const q = document.getElementById('leads-search')?.value || '';
  const params = new URLSearchParams({
    page: state.leadsPage,
    per_page: state.leadsPerPage,
    sort: state.leadsSort.col,
    dir: state.leadsSort.dir,
  });
  if (q) params.set('q', q);
  if (state.leadsStageFilter) params.set('stage', state.leadsStageFilter);

  const data = await api(`/api/leads?${params}`);
  if (!data) return;
  state.leads = data.leads;
  state.leadsTotal = data.total;
  renderLeads();
  renderLeadsPagination(data.total, data.page, data.pages);
  renderStagePills();
}

function renderStagePills() {
  const c = document.getElementById('stage-pills');
  if (!c) return;
  const stages = [
    { key: null, label: 'Todos' },
    ...KANBAN_STAGES.map(k => ({ key: k, label: KANBAN_LABELS[k] })),
  ];
  c.innerHTML = stages.map(s => `
    <button class="pill${state.leadsStageFilter === s.key ? ' active' : ''}"
      onclick="setStageFilter(${s.key === null ? 'null' : `'${s.key}'`})">${s.label}</button>
  `).join('');
}

function setStageFilter(stage) {
  state.leadsStageFilter = stage;
  state.leadsPage = 1;
  loadLeads();
}

function sortLeads(col) {
  if (state.leadsSort.col === col) {
    state.leadsSort.dir = state.leadsSort.dir === 'desc' ? 'asc' : 'desc';
  } else {
    state.leadsSort = { col, dir: 'desc' };
  }
  loadLeads();
}

function renderLeads() {
  const body = document.getElementById('leads-body');
  if (!body) return;
  const count = document.getElementById('leads-count');
  if (count) count.textContent = `${state.leadsTotal} leads`;
  if (!state.leads.length) {
    body.innerHTML = '<tr><td colspan="8" style="padding:24px;text-align:center;color:var(--text-3)">Sin leads</td></tr>';
    return;
  }
  body.innerHTML = state.leads.map(l => {
    const [sCls, sLabel] = STAGE_BADGE[l.stage] || ['badge-neutral', l.stage];
    const [rCls, rLabel] = RESPONSE_BADGE[l.estado_respuesta] || ['',''];
    return `
      <tr onclick="openLead(${l.id})">
        <td><strong>${esc(l.nombre)}</strong></td>
        <td class="muted">${esc(l.categoria || '-')}</td>
        <td class="muted" style="font-family:var(--mono);font-size:12px">${esc(l.telefono || '-')}</td>
        <td>${l.score || '-'}</td>
        <td><span class="badge ${sCls}">${sLabel}</span></td>
        <td>${rLabel ? `<span class="badge ${rCls}">${rLabel}</span>` : '-'}</td>
        <td class="muted">${fmtDate(l.created_at)}</td>
        <td onclick="event.stopPropagation()">
          <button class="btn btn-ghost btn-sm" onclick="openLead(${l.id})">Ver</button>
        </td>
      </tr>
    `;
  }).join('');
}

function renderLeadsPagination(total, page, pages) {
  const c = document.getElementById('leads-pagination');
  if (!c || pages <= 1) { if (c) c.innerHTML = ''; return; }
  const btns = [];
  if (page > 1) btns.push(`<button class="btn btn-ghost btn-sm" onclick="goLeadsPage(${page-1})">←</button>`);
  for (let p = Math.max(1,page-2); p <= Math.min(pages,page+2); p++) {
    btns.push(`<button class="btn ${p===page?'btn-primary':'btn-ghost'} btn-sm" onclick="goLeadsPage(${p})">${p}</button>`);
  }
  if (page < pages) btns.push(`<button class="btn btn-ghost btn-sm" onclick="goLeadsPage(${page+1})">→</button>`);
  c.innerHTML = btns.join('');
}

function goLeadsPage(p) {
  state.leadsPage = p;
  loadLeads();
}

// ── Lead Modal ───────────────────────────────────────────────

async function openLead(id) {
  const lead = await api(`/api/leads/${id}`);
  if (!lead) return;
  state.editingLeadId = id;
  document.getElementById('lead-modal-title').textContent = lead.nombre;

  const STAGES = KANBAN_STAGES.map(s => `<option value="${s}"${lead.stage===s?' selected':''}>${KANBAN_LABELS[s]}</option>`).join('');
  const RESPONSES = [
    ['','Sin respuesta'],['interest','Interesado'],['positive_intent','Positivo'],
    ['price_request','Pidio precio'],['info_request','Pidio info'],
    ['follow_up','Follow-up'],['rejection','Rechazo'],['neutral','Neutral'],
  ].map(([v,l]) => `<option value="${v}"${lead.estado_respuesta===v?' selected':''}>${l}</option>`).join('');

  document.getElementById('lead-modal-body').innerHTML = `
    <div class="form-row">
      <div class="field"><label>Nombre</label><input type="text" id="lm-nombre" value="${esc(lead.nombre)}"></div>
      <div class="field"><label>Telefono</label><input type="text" id="lm-telefono" value="${esc(lead.telefono||'')}"></div>
    </div>
    <div class="form-row">
      <div class="field"><label>Categoria</label><input type="text" id="lm-categoria" value="${esc(lead.categoria||'')}"></div>
      <div class="field"><label>Ciudad</label><input type="text" id="lm-ciudad" value="${esc(lead.ciudad||'Rosario')}"></div>
    </div>
    <div class="form-row full">
      <div class="field"><label>Direccion</label><input type="text" id="lm-direccion" value="${esc(lead.direccion||'')}"></div>
    </div>
    <div class="form-row">
      <div class="field"><label>Etapa</label><select id="lm-stage">${STAGES}</select></div>
      <div class="field"><label>Respuesta</label><select id="lm-estado-respuesta">${RESPONSES}</select></div>
    </div>
    <div class="form-row">
      <div class="field"><label>Prioridad (1=alta)</label>
        <select id="lm-prioridad">
          ${[1,2,3,4,5].map(n=>`<option value="${n}"${lead.prioridad===n?' selected':''}>${n}</option>`).join('')}
        </select>
      </div>
      <div class="field"><label>Responsable</label><input type="text" id="lm-responsable" value="${esc(lead.responsable||'')}"></div>
    </div>
    <div class="form-row">
      <div class="field"><label>Fecha entrega</label><input type="date" id="lm-fecha-entrega" value="${lead.fecha_entrega||''}"></div>
      <div class="field"><label>URL del sitio</label><input type="text" id="lm-live-url" value="${esc(lead.live_url||'')}"></div>
    </div>
    <div class="form-row">
      <div class="field"><label>Renov. web</label><input type="date" id="lm-renov-web" value="${lead.fecha_renovacion_web||''}"></div>
      <div class="field"><label>Renov. hosting</label><input type="date" id="lm-renov-hosting" value="${lead.fecha_renovacion_hosting||''}"></div>
    </div>
    <div class="form-row full">
      <div class="field"><label>Mantenimiento mensual (proximo cobro)</label><input type="date" id="lm-renov-mant" value="${lead.fecha_renovacion_mantenimiento||''}"></div>
    </div>
    <div class="form-row full">
      <div class="field"><label>Notas</label><textarea id="lm-notas" rows="3">${esc(lead.notas||'')}</textarea></div>
    </div>
    ${lead.live_url ? `<div style="margin-top:8px"><a href="${esc(lead.live_url)}" target="_blank" class="btn btn-ghost btn-sm">Ver sitio live</a></div>` : ''}
    ${lead.project_path ? `
      <div style="margin-top:8px;font-size:12px;color:var(--text-3)">
        Proyecto: <code style="font-family:var(--mono)">${esc(lead.project_path)}</code>
        <button class="btn btn-ghost btn-sm" style="margin-left:8px" onclick="regenerateWebsite(${lead.id})">Regenerar</button>
      </div>
    ` : ''}
    ${lead.conversacion?.length ? `
      <div class="divider"></div>
      <div class="card-title">Conversacion</div>
      <div style="max-height:200px;overflow-y:auto;background:var(--bg);border-radius:8px;padding:10px">
        ${lead.conversacion.map(m => `
          <div style="margin-bottom:8px">
            <span style="color:var(--text-3);font-size:11px">${m.from||''} · ${fmtDate(m.timestamp)}</span>
            <div style="font-size:13px;color:var(--text);margin-top:2px">${esc(m.body||'')}</div>
          </div>
        `).join('')}
      </div>
    ` : ''}
  `;
  openModal('lead-modal');
}

async function saveLead() {
  const id = state.editingLeadId;
  if (!id) return;
  const r = await api(`/api/leads/${id}`, 'PUT', {
    nombre: val('lm-nombre'),
    telefono: val('lm-telefono'),
    categoria: val('lm-categoria'),
    ciudad: val('lm-ciudad'),
    direccion: val('lm-direccion'),
    stage: val('lm-stage'),
    estado_respuesta: val('lm-estado-respuesta'),
    prioridad: parseInt(val('lm-prioridad')),
    responsable: val('lm-responsable'),
    notas: val('lm-notas'),
    live_url: val('lm-live-url') || null,
    fecha_entrega: val('lm-fecha-entrega') || null,
    fecha_renovacion_web: val('lm-renov-web') || null,
    fecha_renovacion_hosting: val('lm-renov-hosting') || null,
    fecha_renovacion_mantenimiento: val('lm-renov-mant') || null,
  });
  if (r) {
    showToast('Lead actualizado', 'success');
    closeModal('lead-modal');
    loadPage(state.currentPage);
  }
}

async function openNewLeadModal() {
  openModal('new-lead-modal');
}

async function createLead() {
  const nombre = val('nl-nombre');
  const telefono = val('nl-telefono');
  if (!nombre || !telefono) { showToast('Nombre y telefono son requeridos', 'error'); return; }

  const fechaEntrega = val('nl-fecha-entrega');
  const r = await api('/api/leads', 'POST', {
    nombre,
    telefono,
    categoria: val('nl-categoria'),
    ciudad: val('nl-ciudad'),
    direccion: val('nl-direccion'),
    notas: val('nl-notas'),
    live_url: val('nl-live-url') || null,
    stage: fechaEntrega ? 'completed' : 'discovered',
    fecha_entrega: fechaEntrega || null,
  });
  if (r) {
    showToast('Lead creado', 'success');
    closeModal('new-lead-modal');
    loadPage(state.currentPage);
  }
}

async function regenerateWebsite(leadId) {
  const r = await api(`/api/websites/${leadId}/regenerate`, 'POST');
  if (r) {
    showToast('Regeneracion iniciada', 'success');
    state.activeLogJobId = r.job_id;
    navigate('pipeline', document.querySelector('[data-page="pipeline"]'));
  }
}

// ── Websites ─────────────────────────────────────────────────

async function loadWebsites() {
  const data = await api('/api/websites');
  if (!data) return;
  const grid = document.getElementById('websites-grid');
  if (!grid) return;
  if (!data.websites.length) {
    grid.innerHTML = '<div class="empty"><div class="empty-msg">Sin sitios generados aun</div></div>';
    return;
  }
  grid.innerHTML = data.websites.map(w => `
    <div class="website-card">
      <div class="website-preview">
        ${w.live_url
          ? `<div style="font-size:11px;color:var(--accent);font-family:var(--mono);padding:8px">${w.live_url}</div>`
          : `<div style="font-size:11px;color:var(--text-3)">Local · sin deploy</div>`
        }
      </div>
      <div class="website-info">
        <div class="website-name">${esc(w.nombre)}</div>
        ${w.live_url ? `<div class="website-url">${w.live_url}</div>` : '<div class="website-url" style="color:var(--text-3)">Sin URL</div>'}
        <div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap">
          ${w.live_url ? `<a href="${w.live_url}" target="_blank" class="btn btn-ghost btn-sm">Abrir</a>` : ''}
          <button class="btn btn-ghost btn-sm" onclick="regenerateWebsite(${w.lead_id})">Regenerar</button>
        </div>
      </div>
    </div>
  `).join('');
}

// ── Analytics ────────────────────────────────────────────────

let responsesChart = null;
let timelineChart = null;

async function loadAnalytics() {
  const data = await api('/api/analytics');
  if (!data) return;
  state.analyticsData = data;

  const grid = document.getElementById('analytics-kpi-grid');
  if (grid) {
    const s = data.stats;
    const kpis = [
      { label: 'Total leads',    value: s.total },
      { label: 'Tasa de envio',  value: `${s.tasa_envio}%` },
      { label: 'Tasa de interes',value: `${s.tasa_interes}%` },
      { label: 'Tasa de deploy', value: `${s.tasa_deploy}%` },
    ];
    grid.innerHTML = kpis.map(k => `
      <div class="kpi">
        <div class="kpi-label">${k.label}</div>
        <div class="kpi-value">${k.value}</div>
      </div>
    `).join('');
  }

  renderFunnelBars('analytics-funnel', data.stats);
  renderResponsesChart(data.responses);
  renderTimelineChart(data.timeline);
}

function renderResponsesChart(responses) {
  const ctx = document.getElementById('responses-chart');
  if (!ctx) return;
  const LABELS = {
    interest:'Interesado', positive_intent:'Positivo',
    price_request:'Precio', info_request:'Info',
    follow_up:'Follow-up', rejection:'Rechazo', neutral:'Neutral',
  };
  if (responsesChart) responsesChart.destroy();
  responsesChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: Object.keys(responses).map(k => LABELS[k] || k),
      datasets: [{
        data: Object.values(responses),
        backgroundColor: ['#10a37f','#27ae60','#1abc9c','#4a90e2','#e8a020','#e74c3c','#676767'],
        borderRadius: 4,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#666', font: { size: 11 } } },
        y: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#666', font: { size: 11 } } },
      },
    },
  });
}

function renderTimelineChart(timeline) {
  const ctx = document.getElementById('timeline-chart');
  if (!ctx) return;
  if (timelineChart) timelineChart.destroy();
  timelineChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: timeline.map(t => t.date.slice(5)),
      datasets: [{
        data: timeline.map(t => t.count),
        borderColor: '#10b981',
        backgroundColor: 'rgba(16,185,129,0.08)',
        fill: true,
        tension: 0.3,
        pointRadius: 0,
        borderWidth: 2,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { color: '#555', font: { size: 10 }, maxTicksLimit: 10 } },
        y: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#555', font: { size: 10 } } },
      },
    },
  });
}

// ── Finanzas ─────────────────────────────────────────────────

async function loadFinanzas() {
  if (!state.dolarRate) await fetchDolarRate();
  const data = await api('/api/finanzas');
  if (!data) return;

  const grid = document.getElementById('fin-kpi-grid');
  if (grid) {
    const s = data.stats;
    const totalUSD    = toUSD(s.total_ars || 0, 'ARS') + (s.total_usd || 0);
    const pendienteUSD = toUSD(s.pendiente_ars || 0, 'ARS') + (s.pendiente_usd || 0);
    grid.innerHTML = [
      { label: 'Clientes totales', value: s.total_clientes },
      { label: 'Pagados',          value: s.clientes_pagados },
      { label: 'Total cobrado',    value: state.dolarRate ? fmtUSD(totalUSD) : '...' },
      { label: 'Pendiente',        value: state.dolarRate ? fmtUSD(pendienteUSD) : '...' },
    ].map(k => `
      <div class="kpi">
        <div class="kpi-label">${k.label}</div>
        <div class="kpi-value">${k.value}</div>
      </div>
    `).join('');
  }

  // Store in map so openEditPago(id) can look it up safely (avoids JSON.stringify quoting issues)
  state.pagosMap = {};
  data.pagos.forEach(p => { state.pagosMap[p.id] = p; });

  const body = document.getElementById('fin-table-body');
  if (body) {
    body.innerHTML = data.pagos.map(p => {
      const estadoBadge = p.estado === 'pagado'
        ? 'badge-interest'
        : p.estado === 'parcial'
          ? 'badge-neutral'
          : 'badge-waiting';
      const isPending = p.estado !== 'pagado';
      const monto = p.monto || 0;
      let montoDisplay, montoSecondary;
      if (p.moneda === 'USD') {
        montoDisplay = `USD ${monto % 1 === 0 ? monto : monto.toFixed(2)}`;
        montoSecondary = state.dolarRate
          ? `<div style="font-size:10px;color:var(--text-3);font-family:var(--mono)">≈ $${Math.round(monto * state.dolarRate).toLocaleString('es-AR')}</div>`
          : '';
      } else {
        montoDisplay = `$${monto.toLocaleString('es-AR')}`;
        montoSecondary = state.dolarRate
          ? `<div style="font-size:10px;color:var(--text-3);font-family:var(--mono)">≈ USD ${Math.round(monto / state.dolarRate)}</div>`
          : '';
      }
      return `
      <tr>
        <td><strong>${esc(p.nombre)}</strong></td>
        <td class="muted">${esc(p.servicio||'-')}</td>
        <td style="font-weight:${isPending?'400':'600'}">${montoDisplay}${montoSecondary}</td>
        <td><span class="badge ${estadoBadge}">${p.estado}</span></td>
        <td class="muted">${fmtDate(p.fecha)}</td>
        <td class="muted" style="max-width:120px;overflow:hidden;text-overflow:ellipsis">${esc(p.notas||'-')}</td>
        <td>
          ${isPending
            ? `<button class="btn btn-primary btn-sm" onclick="openCobrarPago(${p.id})" style="margin-right:4px">Cobrar</button>`
            : ''}
          <button class="btn btn-ghost btn-sm" onclick="openEditPago(${p.id})">Editar</button>
          <button class="btn btn-danger btn-sm" onclick="deletePago(${p.id})" style="margin-left:4px">X</button>
        </td>
      </tr>`;
    }).join('') || '<tr><td colspan="7" style="padding:24px;text-align:center;color:var(--text-3)">Sin pagos registrados</td></tr>';
  }
}

function openPaymentModal() {
  state.pagoForceCreate = false;
  document.getElementById('p-fecha').value = new Date().toISOString().slice(0,10);
  openModal('payment-modal');
}

function openRegistrarPago(leadId, nombre, telefono) {
  state.pagoForceCreate = true;
  document.getElementById('p-nombre').value = nombre;
  document.getElementById('p-telefono').value = telefono;
  document.getElementById('p-servicio').value = 'Mantenimiento mensual';
  document.getElementById('p-estado').value = 'pagado';
  document.getElementById('p-fecha').value = new Date().toISOString().slice(0,10);
  document.getElementById('p-monto').value = '';
  document.getElementById('p-notas').value = '';
  openModal('payment-modal');
  setTimeout(() => document.getElementById('p-monto').focus(), 120);
}

async function savePayment() {
  const r = await api('/api/finanzas/pago', 'POST', {
    nombre: val('p-nombre'),
    telefono: val('p-telefono'),
    monto: parseFloat(val('p-monto') || '0'),
    moneda: val('p-moneda'),
    estado: val('p-estado'),
    fecha: val('p-fecha'),
    servicio: val('p-servicio'),
    notas: val('p-notas'),
    force_create: state.pagoForceCreate || false,
  });
  if (r) {
    state.pagoForceCreate = false;
    showToast('Pago guardado', 'success');
    closeModal('payment-modal');
    loadFinanzas();
  }
}

function openEditPago(id) {
  const p = state.pagosMap && state.pagosMap[id];
  if (!p) return;
  document.getElementById('ep-id').value = p.id;
  document.getElementById('edit-pago-title').textContent = `Editar — ${p.nombre}`;
  document.getElementById('ep-monto').value = p.monto || '';
  document.getElementById('ep-moneda').value = p.moneda || 'ARS';
  document.getElementById('ep-estado').value = p.estado || 'pendiente';
  document.getElementById('ep-fecha').value = (p.fecha || '').slice(0, 10);
  document.getElementById('ep-notas').value = p.notas || '';
  document.getElementById('ep-monto-label').textContent = 'Monto cobrado';
  openModal('edit-pago-modal');
  setTimeout(() => document.getElementById('ep-monto').focus(), 120);
}

function openCobrarPago(id) {
  const p = state.pagosMap && state.pagosMap[id];
  if (!p) return;
  document.getElementById('ep-id').value = p.id;
  document.getElementById('edit-pago-title').textContent = `¿Cuánto te pagó ${p.nombre}?`;
  document.getElementById('ep-monto').value = '';
  document.getElementById('ep-moneda').value = p.moneda || 'ARS';
  document.getElementById('ep-estado').value = 'parcial';
  document.getElementById('ep-fecha').value = new Date().toISOString().slice(0, 10);
  document.getElementById('ep-notas').value = p.notas || '';
  document.getElementById('ep-monto-label').textContent = 'Monto recibido';
  openModal('edit-pago-modal');
  setTimeout(() => document.getElementById('ep-monto').focus(), 120);
}

async function saveEditPago() {
  const id = document.getElementById('ep-id').value;
  const r = await api(`/api/finanzas/pago/${id}`, 'PUT', {
    monto: parseFloat(val('ep-monto') || '0'),
    moneda: val('ep-moneda'),
    estado: val('ep-estado'),
    fecha: val('ep-fecha'),
    notas: val('ep-notas'),
  });
  if (r) {
    showToast('Pago actualizado', 'success');
    closeModal('edit-pago-modal');
    loadFinanzas();
  }
}

async function deletePago(id) {
  if (!confirm('Eliminar este pago?')) return;
  const r = await api(`/api/finanzas/pago/${id}`, 'DELETE');
  if (r) { showToast('Pago eliminado', 'success'); loadFinanzas(); }
}

// ── Renovaciones → redirige a Servicios ──────────────────────

async function loadRenovaciones() {
  navigate('mantenimiento', document.querySelector('[data-page=mantenimiento]'));
}

// ── Templates ────────────────────────────────────────────────

async function loadTemplates() {
  const data = await api('/api/templates');
  if (!data) return;
  const c = document.getElementById('templates-list');
  if (!c) return;
  c.innerHTML = data.templates.map(t => `
    <div class="card" style="margin-bottom:10px">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">
        <div style="font-size:13px;font-weight:600">${esc(t.nombre)}</div>
        <span class="badge badge-neutral">${t.tipo}</span>
        ${!t.activo ? '<span class="badge badge-rejected">Inactivo</span>' : ''}
        <div style="margin-left:auto;display:flex;gap:8px">
          <button class="btn btn-ghost btn-sm" onclick="editTemplate(${t.id})">Editar</button>
          <button class="btn btn-danger btn-sm" onclick="deleteTemplate(${t.id})">Eliminar</button>
        </div>
      </div>
      <div style="font-family:var(--mono);font-size:12px;color:var(--text-2);background:var(--bg);border-radius:6px;padding:10px;white-space:pre-wrap">${esc(t.contenido)}</div>
    </div>
  `).join('') || '<div class="empty"><div class="empty-msg">Sin templates</div></div>';
}

function openTemplateModal(templateData) {
  state.editingTemplateId = templateData?.id || null;
  document.getElementById('template-modal-title').textContent = templateData ? 'Editar template' : 'Nuevo template';
  document.getElementById('t-nombre').value = templateData?.nombre || '';
  document.getElementById('t-tipo').value = templateData?.tipo || 'outreach';
  document.getElementById('t-activo').value = String(templateData?.activo !== false);
  document.getElementById('t-contenido').value = templateData?.contenido || '';
  openModal('template-modal');
}

async function editTemplate(id) {
  const data = await api('/api/templates');
  const t = data?.templates?.find(t => t.id === id);
  if (t) openTemplateModal(t);
}

async function saveTemplate() {
  const body = {
    nombre: val('t-nombre'),
    tipo: val('t-tipo'),
    activo: val('t-activo') === 'true',
    contenido: val('t-contenido'),
  };
  const id = state.editingTemplateId;
  const r = await api(id ? `/api/templates/${id}` : '/api/templates', id ? 'PUT' : 'POST', body);
  if (r) {
    showToast('Template guardado', 'success');
    closeModal('template-modal');
    loadTemplates();
  }
}

async function deleteTemplate(id) {
  if (!confirm('Eliminar este template?')) return;
  const r = await api(`/api/templates/${id}`, 'DELETE');
  if (r) { showToast('Template eliminado', 'success'); loadTemplates(); }
}

// ── Settings ─────────────────────────────────────────────────

async function loadSettings() {
  loadDatasetStatus();
  const data = await api('/api/config');
  if (!data) return;
  state.config = data.config || {};
  const c = document.getElementById('config-fields');
  if (!c) return;
  const FIELDS = [
    { key: 'MAX_MENSAJES_POR_DIA', label: 'Mensajes por dia', desc: 'Limite de envios diarios' },
    { key: 'INTERVALO_SEGUNDOS', label: 'Intervalo entre mensajes (seg)', desc: '' },
    { key: 'SCORE_MIN_TO_CONTACT', label: 'Score minimo para contactar', desc: '' },
    { key: 'GITHUB_USERNAME', label: 'GitHub username', desc: '' },
    { key: 'WA_BRIDGE_PORT', label: 'Puerto WhatsApp bridge', desc: '' },
  ];
  c.innerHTML = FIELDS.map(f => `
    <div class="settings-row">
      <div>
        <div class="settings-label">${f.label}</div>
        ${f.desc ? `<div class="settings-desc">${f.desc}</div>` : ''}
      </div>
      <div class="settings-control">
        <input type="text" id="cfg-${f.key}" value="${esc(state.config[f.key] || '')}">
      </div>
    </div>
  `).join('');
}

async function loadDatasetStatus() {
  const data = await api('/api/dataset/status');
  const el = document.getElementById('dataset-status-text');
  if (!el) return;
  if (!data) { el.textContent = 'Error al verificar'; return; }
  if (!data.exists) { el.textContent = 'dataset.json no encontrado'; return; }
  el.textContent = `${data.count} registros · ${data.size_kb}KB · ${fmtDate(data.modified)}`;
}

async function saveConfig() {
  const KEYS = ['MAX_MENSAJES_POR_DIA','INTERVALO_SEGUNDOS','SCORE_MIN_TO_CONTACT','GITHUB_USERNAME','WA_BRIDGE_PORT'];
  const body = {};
  KEYS.forEach(k => { body[k] = document.getElementById(`cfg-${k}`)?.value || ''; });
  const r = await api('/api/config', 'PUT', body);
  if (r) showToast('Configuracion guardada', 'success');
}

async function runMigration() {
  const r = await api('/api/migrate', 'POST');
  if (r) showToast(r.message || `${r.imported} leads importados`, 'success');
}

// ── Modal helpers ─────────────────────────────────────────────

function openModal(id) { document.getElementById(id)?.classList.add('open'); }
function closeModal(id) { document.getElementById(id)?.classList.remove('open'); }

document.addEventListener('click', e => {
  if (e.target.classList.contains('modal-backdrop')) {
    e.target.classList.remove('open');
  }
});

// ── API helper ───────────────────────────────────────────────

async function api(url, method = 'GET', body = null) {
  try {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body !== null) opts.body = JSON.stringify(body);
    const r = await fetch(url, opts);
    const data = await r.json();
    if (!r.ok) { showToast(data.error || `Error ${r.status}`, 'error'); return null; }
    return data;
  } catch (e) {
    showToast(`Error de red: ${e.message}`, 'error');
    return null;
  }
}

// ── Toast ─────────────────────────────────────────────────────

function showToast(msg, type = 'info') {
  const c = document.getElementById('toast-container');
  if (!c) return;
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  c.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

// ── Utilities ─────────────────────────────────────────────────

function esc(s) {
  if (!s) return '';
  return String(s).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c])
  );
}

function val(id) {
  return document.getElementById(id)?.value?.trim() || '';
}

function fmtDate(s) {
  if (!s) return '-';
  try {
    const d = new Date(s);
    if (isNaN(d)) return s.slice(0,10);
    return d.toLocaleDateString('es-AR', { day:'2-digit', month:'short', year:'numeric' });
  } catch { return '-'; }
}

function fmtMoney(amount, moneda = 'ARS') {
  const n = amount || 0;
  const pfx = moneda === 'USD' ? 'USD ' : '$';
  if (n >= 1_000_000) return pfx + (n/1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return pfx + (n/1_000).toFixed(0) + 'K';
  return pfx + n.toLocaleString('es-AR');
}

function animateCount(el, from, to, duration = 600) {
  if (from === to) { el.textContent = to; return; }
  const step = (to - from) / (duration / 16);
  let cur = from;
  const t = setInterval(() => {
    cur += step;
    const done = step > 0 ? cur >= to : cur <= to;
    if (done) { cur = to; clearInterval(t); }
    el.textContent = Math.floor(cur);
  }, 16);
}

function setWsStatus(connected) {
  const dot = document.getElementById('ws-dot');
  const label = document.getElementById('ws-label');
  if (dot) dot.className = `status-dot ${connected ? 'online' : 'error'}`;
  if (label) label.textContent = connected ? 'Conectado' : 'Sin conexion';
}

function globalSearch(q) {
  if (state.currentPage === 'leads') debounce(loadLeads, 300)();
}

function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

// ── Seguimientos ─────────────────────────────────────────────

const FOLLOWUP_LABELS = [
  'Hola, pudieron ver el mensaje?',
  'Hola, pudieron ver la pagina web?',
  'Hola, buenas tardes, pudieron decidirse? Si les gusto la pagina web la podemos publicar ya esta semana.',
];

const FOLLOWUP_TAGS = ['Seg. 1', 'Seg. 2', 'Seg. 3'];

async function loadSeguimientos() {
  renderFollowupMsgCards();
  const data = await api('/api/followup/candidates');
  if (!data) return;
  state.followupCandidates = data.candidates || [];
  renderFollowupTable(state.followupCandidates);
}

function renderFollowupMsgCards() {
  const container = document.getElementById('followup-msg-cards');
  if (!container) return;
  container.innerHTML = FOLLOWUP_LABELS.map((msg, i) => `
    <label class="followup-msg-card ${state.followupSelectedMsg === i ? 'selected' : ''}" onclick="setFollowupMsg(${i})">
      <input type="radio" name="followup-msg" value="${i}" ${state.followupSelectedMsg === i ? 'checked' : ''} style="display:none">
      <div class="followup-msg-num">Mensaje ${i + 1}</div>
      <div class="followup-msg-text">${esc(msg)}</div>
    </label>
  `).join('');
}

function setFollowupMsg(idx) {
  state.followupSelectedMsg = idx;
  renderFollowupMsgCards();
}

function filterFollowupCandidates(q) {
  state.followupQuery = q.trim().toLowerCase();
  const filtered = state.followupQuery
    ? state.followupCandidates.filter(c =>
        (c.nombre || '').toLowerCase().includes(state.followupQuery) ||
        (c.telefono || '').includes(state.followupQuery)
      )
    : state.followupCandidates;
  renderFollowupTable(filtered);
}

function renderFollowupTable(list) {
  const tbody = document.getElementById('followup-table-body');
  if (!tbody) return;
  if (!list || list.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text-3);padding:24px">Sin leads contactados</td></tr>';
    updateFollowupSelCount();
    return;
  }
  tbody.innerHTML = list.map(c => {
    const fechaEnv = c.fecha_envio ? new Date(c.fecha_envio).toLocaleDateString('es-AR') : '—';
    const resp = c.estado_respuesta ? `<span class="badge badge-${c.estado_respuesta}">${c.estado_respuesta}</span>` : '<span style="color:var(--text-4)">—</span>';
    const url = c.live_url
      ? `<a href="${esc(c.live_url)}" target="_blank" style="color:var(--accent);font-size:11px;font-family:var(--mono)" onclick="event.stopPropagation()">${esc(c.live_url.replace(/^https?:\/\//, '').slice(0, 28))}</a>`
      : '<span style="color:var(--text-4)">—</span>';
    const tag = c.followup_stage > 0
      ? `<span class="badge followup-tag-${c.followup_stage}">${FOLLOWUP_TAGS[c.followup_stage - 1] || 'Seg.'}</span>`
      : '<span style="color:var(--text-4)">—</span>';
    return `
      <tr>
        <td><input type="checkbox" ${state.followupSelected.has(c.id) ? 'checked' : ''} onchange="toggleFollowup(${c.id}, this.checked)"></td>
        <td>${esc(c.nombre || '')}</td>
        <td style="font-family:var(--mono);font-size:12px">${esc(c.telefono || '')}</td>
        <td style="font-size:12px">${esc(c.categoria || '')}</td>
        <td style="font-size:12px">${fechaEnv}</td>
        <td>${resp}</td>
        <td>${url}</td>
        <td>${tag}</td>
      </tr>`;
  }).join('');
  updateFollowupSelCount();
}

function toggleFollowup(id, checked) {
  if (checked) state.followupSelected.add(id);
  else state.followupSelected.delete(id);
  updateFollowupSelCount();
}

function selectAllFollowup(checked) {
  const visible = state.followupQuery
    ? state.followupCandidates.filter(c =>
        (c.nombre || '').toLowerCase().includes(state.followupQuery) ||
        (c.telefono || '').includes(state.followupQuery)
      )
    : state.followupCandidates;
  visible.forEach(c => {
    if (checked) state.followupSelected.add(c.id);
    else state.followupSelected.delete(c.id);
  });
  renderFollowupTable(visible.length < state.followupCandidates.length ? visible : state.followupCandidates);
  const allCheck = document.getElementById('followup-check-all');
  if (allCheck) allCheck.checked = checked;
}

function updateFollowupSelCount() {
  const el = document.getElementById('followup-sel-count');
  if (el) el.textContent = `${state.followupSelected.size} seleccionados`;
}

async function startFollowup() {
  const leadIds = Array.from(state.followupSelected);
  if (!leadIds.length) { showToast('Selecciona al menos un lead', 'warning'); return; }
  const msgIdx = state.followupSelectedMsg;

  const btn = document.getElementById('followup-send-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Enviando…'; }

  const res = await api('/api/pipeline/start/followup', 'POST', { lead_ids: leadIds, message_index: msgIdx });

  if (res?.ok && res?.job_id) {
    showToast(`Enviando seguimiento #${msgIdx + 1} a ${leadIds.length} leads`, 'success');
    state.followupSelected = new Set();
    state._followupJobId = res.job_id;
    // btn will be re-enabled when job_update fires with done/error status
  } else {
    showToast('Error al iniciar envío', 'error');
    if (btn) { btn.disabled = false; btn.textContent = 'Enviar seguimientos'; }
  }
}

// ── Init ──────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  fetchDolarRate();

  const savedPage = localStorage.getItem('crm_page') || 'dashboard';
  const validPages = Object.keys(PAGE_TITLES);
  const page = validPages.includes(savedPage) ? savedPage : 'dashboard';
  const navEl = document.querySelector(`[data-page="${page}"]`);

  if (page === 'dashboard' || !navEl) {
    loadDashboard();
  } else {
    navigate(page, navEl);
  }
});
