// Binario Websites — Production Dashboard

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
  charts: {},
  config: {},
};

// ── Socket.IO ────────────────────────────────────────────────
const socket = io({ transports: ['websocket', 'polling'] });

socket.on('connect', () => {
  setWsStatus(true);
});

socket.on('disconnect', () => {
  setWsStatus(false);
});

socket.on('connected', () => {
  setWsStatus(true);
});

socket.on('jobs_state', ({ jobs }) => {
  jobs.forEach(j => { state.jobs[j.job_id] = j; });
  renderPipelineCards();
  updateActiveJobsIndicator();
});

socket.on('job_update', ({ job }) => {
  state.jobs[job.job_id] = job;
  renderPipelineCards();
  updateActiveJobsIndicator();
  if (state.currentPage === 'pipeline') {
    renderPipelineCards();
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
  if (state.currentPage === 'kanban') loadKanban();
});

socket.on('lead_deleted', ({ lead_id }) => {
  state.leads = state.leads.filter(l => l.id !== lead_id);
  if (state.currentPage === 'leads') renderLeads();
});

// ── Navigation ───────────────────────────────────────────────

const PAGE_TITLES = {
  dashboard: 'Dashboard',
  pipeline: 'Pipeline',
  kanban: 'Kanban',
  leads: 'Leads',
  websites: 'Websites',
  analytics: 'Analytics',
  finanzas: 'Finanzas',
  renovaciones: 'Renovaciones',
  templates: 'Templates',
  settings: 'Ajustes',
};

function navigate(page, el) {
  if (state.currentPage === page) return;

  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(a => a.classList.remove('active'));

  document.getElementById(`page-${page}`)?.classList.add('active');
  el?.classList.add('active');

  document.getElementById('header-title').textContent = PAGE_TITLES[page] || page;

  const search = document.getElementById('global-search');
  if (search) search.style.display = page === 'leads' ? 'flex' : 'none';

  const cta = document.getElementById('header-cta');
  if (cta) cta.innerHTML = '';

  state.currentPage = page;
  loadPage(page);
}

function loadPage(page) {
  switch (page) {
    case 'dashboard':    loadDashboard(); break;
    case 'pipeline':     loadPipeline(); break;
    case 'kanban':       loadKanban(); break;
    case 'leads':        loadLeads(); break;
    case 'websites':     loadWebsites(); break;
    case 'analytics':    loadAnalytics(); break;
    case 'finanzas':     loadFinanzas(); break;
    case 'renovaciones': loadRenovaciones(); break;
    case 'templates':    loadTemplates(); break;
    case 'settings':     loadSettings(); break;
  }
}

function refresh() {
  loadPage(state.currentPage);
}

// ── Dashboard ────────────────────────────────────────────────

async function loadDashboard() {
  const data = await api('/api/dashboard');
  if (!data) return;
  state.dashData = data;

  renderKPIs(data.stats);
  renderFunnelBars('funnel-bars', data.stats);
  renderStageChart(data.stages);
  renderCatTable(data.categorias);

  const badge = document.getElementById('renewal-badge');
  if (badge) {
    badge.textContent = data.renewal_count;
    badge.style.display = data.renewal_count > 0 ? 'flex' : 'none';
  }
}

function renderKPIs(stats) {
  const grid = document.getElementById('kpi-grid');
  const items = [
    { label: 'Leads en CRM',    value: stats.total,       sub: 'registros totales' },
    { label: 'Enviados',        value: stats.enviados,    sub: `${stats.tasa_envio}% del total` },
    { label: 'Interesados',     value: stats.interesados, sub: `${stats.tasa_interes}% de respuestas` },
    { label: 'Sitios live',     value: stats.con_link,    sub: `${stats.tasa_deploy}% de webs` },
  ];
  grid.innerHTML = items.map(k => `
    <div class="kpi">
      <div class="kpi-label">${k.label}</div>
      <div class="kpi-value" data-target="${k.value}">0</div>
      <div class="kpi-sub">${k.sub}</div>
    </div>
  `).join('');
  grid.querySelectorAll('[data-target]').forEach(el => {
    animateCount(el, 0, parseInt(el.dataset.target));
  });
}

function renderFunnelBars(containerId, stats) {
  const c = document.getElementById(containerId);
  if (!c) return;
  const max = stats.total || 1;
  const rows = [
    { label: 'Total', value: stats.total },
    { label: 'Enviados', value: stats.enviados },
    { label: 'Respondieron', value: stats.respondieron },
    { label: 'Interesados', value: stats.interesados },
    { label: 'Webs generadas', value: stats.con_web },
    { label: 'Sitios live', value: stats.con_link },
    { label: 'Links enviados', value: stats.links_enviados },
    { label: 'Clientes', value: stats.clientes },
  ];
  c.innerHTML = rows.map(r => `
    <div class="funnel-bar-row">
      <div class="funnel-bar-label">${r.label}</div>
      <div class="funnel-bar-track">
        <div class="funnel-bar-fill" style="width:${Math.round((r.value || 0)/max*100)}%"></div>
      </div>
      <div class="funnel-bar-val">${r.value || 0}</div>
    </div>
  `).join('');
}

let stageChart = null;
function renderStageChart(stages) {
  const ctx = document.getElementById('stage-chart');
  if (!ctx) return;
  const STAGE_LABELS = {
    discovered: 'Descubierto', pending_send: 'Pendiente',
    sent: 'Enviado', waiting: 'Esperando', generating: 'Generando',
    ready_deploy: 'Listo deploy', deployed: 'Desplegado',
    link_sent: 'Link enviado', completed: 'Completado', error: 'Error',
  };
  const labels = Object.keys(stages).map(k => STAGE_LABELS[k] || k);
  const values = Object.values(stages);
  const colors = ['#8f8f8f','#3b82f6','#8b5cf6','#f59e0b','#06b6d4','#ec4899','#10b981','#10b981','#22c55e','#ef4444'];

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
  if (!cats || !cats.length) {
    body.innerHTML = '<tr><td colspan="6" class="text-muted" style="padding:20px;text-align:center">Sin datos</td></tr>';
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

// ── Pipeline ─────────────────────────────────────────────────

const STAGE_META = {
  scrape:        { label: 'Scraper',       icon: '⊕', color: '#3b82f6' },
  discover:      { label: 'Discover',      icon: '◎', color: '#8b5cf6' },
  send:          { label: 'Enviar mensajes',icon: '▷', color: '#f59e0b' },
  generate_webs: { label: 'Generar webs',  icon: '⬡', color: '#06b6d4' },
  deploy:        { label: 'Deploy',        icon: '⚡', color: '#10b981' },
  send_links:    { label: 'Enviar links',  icon: '↗', color: '#ec4899' },
};

async function loadPipeline() {
  const data = await api('/api/pipeline/stages');
  if (data) renderPipelineStagesInfo(data.stages);
  renderPipelineCards();
}

let stageInfoCache = {};
function renderPipelineStagesInfo(stages) {
  stageInfoCache = {};
  stages.forEach(s => { stageInfoCache[s.key] = s; });
}

function renderPipelineCards() {
  const grid = document.getElementById('pipeline-stage-cards');
  if (!grid || state.currentPage !== 'pipeline') return;

  const stages = Object.keys(STAGE_META);
  grid.innerHTML = stages.map(stage => {
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
    const count = info?.count ?? '—';

    let elapsed = '';
    if (job?.started_at) {
      const secs = Math.round((Date.now() - new Date(job.started_at)) / 1000);
      elapsed = secs < 60 ? `${secs}s` : `${Math.floor(secs/60)}m${secs%60}s`;
    }

    return `
      <div class="stage-card ${status}" id="stage-card-${stage}">
        <div class="stage-header">
          <div class="stage-name">
            <div class="stage-icon" style="background:${meta.color}22;color:${meta.color}">${meta.icon}</div>
            ${meta.label}
          </div>
          <span class="stage-status-badge status-${status}">${statusLabel(status)}</span>
        </div>

        <div style="display:flex;align-items:baseline;gap:8px">
          <div class="stage-count">${count}</div>
          <div class="text-sm text-muted">leads</div>
          ${elapsed ? `<div class="text-sm text-muted ml-auto">⏱ ${elapsed}</div>` : ''}
        </div>

        ${(isRunning || isPaused || isDone) ? `
          <div class="stage-progress">
            <div class="progress-bar">
              <div class="progress-fill ${isPaused ? 'paused' : status === 'failed' ? 'failed' : ''}"
                   style="width:${progress}%"></div>
            </div>
            <div class="progress-text">
              <span>${processed}/${total}</span>
              <span>${progress}%</span>
            </div>
          </div>
        ` : ''}

        ${job?.error ? `<div class="text-sm" style="color:var(--red);margin-top:4px">${esc(job.error.slice(0,80))}</div>` : ''}

        <div class="stage-actions">
          ${isRunning ? `
            <button class="btn btn-ghost btn-sm" onclick="pauseJob('${job.job_id}')">⏸ Pausar</button>
            <button class="btn btn-danger btn-sm" onclick="stopJob('${job.job_id}')">⬜ Detener</button>
          ` : isPaused ? `
            <button class="btn btn-primary btn-sm" onclick="resumeJob('${job.job_id}')">▷ Continuar</button>
            <button class="btn btn-danger btn-sm" onclick="stopJob('${job.job_id}')">⬜ Cancelar</button>
          ` : `
            <button class="btn btn-primary btn-sm" onclick="startStage('${stage}')">▷ Iniciar</button>
          `}
          ${(isRunning || isPaused || job?.logs?.length) ? `
            <button class="btn btn-ghost btn-sm" onclick="showJobLogs('${job.job_id}')">Logs</button>
          ` : ''}
        </div>
      </div>
    `;
  }).join('');
}

function statusLabel(s) {
  return {idle:'Inactivo',running:'Activo',paused:'Pausado',completed:'Completado',failed:'Error',cancelled:'Cancelado',queued:'En cola'}[s] || s;
}

async function startStage(stage) {
  const r = await api(`/api/pipeline/start/${stage}`, 'POST', {});
  if (r) {
    state.jobs[r.job_id] = { job_id: r.job_id, stage, status: 'running', progress: 0, logs: [], started_at: new Date().toISOString() };
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
  const isWarn = entry.level === 'warning';
  const isSuccess = entry.msg?.startsWith('✅');

  const ts = entry.ts ? new Date(entry.ts).toLocaleTimeString('es-AR', { hour12: false }) : '';
  const cls = isError ? 'error' : isWarn ? 'warning' : isSuccess ? 'success' : 'info';

  const el = document.createElement('div');
  el.className = 'log-entry';
  el.innerHTML = `<span class="log-ts">${ts}</span><span class="log-msg ${cls}">${esc(entry.msg)}</span>`;
  container.appendChild(el);

  const autoscroll = document.getElementById('log-autoscroll');
  if (autoscroll?.checked) container.scrollTop = container.scrollHeight;
}

function clearLogs() {
  clearLogEntries();
  state.activeLogJobId = null;
  const label = document.getElementById('log-job-label');
  if (label) label.textContent = '';
}

function clearLogEntries() {
  const c = document.getElementById('log-entries');
  if (c) c.innerHTML = '<div class="empty"><div class="empty-icon">⬝</div><div class="empty-msg">Logs en tiempo real</div></div>';
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

// ── Kanban ───────────────────────────────────────────────────

const KANBAN_STAGES = [
  'discovered', 'pending_send', 'sent', 'waiting',
  'generating', 'ready_deploy', 'deployed', 'link_sent', 'completed', 'error',
];

const KANBAN_LABELS = {
  discovered: 'Descubierto', pending_send: 'Pendiente',
  sent: 'Enviado', waiting: 'Esperando respuesta',
  generating: 'Generando web', ready_deploy: 'Listo deploy',
  deployed: 'Desplegado', link_sent: 'Link enviado',
  completed: 'Completado', error: 'Error',
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
        ${!(board[stage]?.length) ? '<div style="padding:12px;text-align:center;font-size:11px;color:var(--text-3)">Vacío</div>' : ''}
      </div>
    </div>
  `).join('');

  // Drag & Drop
  container.querySelectorAll('.kanban-col-header').forEach(header => {
    const col = header.closest('.kanban-col');
    const cards = col.querySelector('.kanban-cards');
    enableDrop(cards);
  });

  container.querySelectorAll('.kanban-card').forEach(card => {
    card.draggable = true;
    card.addEventListener('dragstart', e => {
      e.dataTransfer.setData('lead_id', card.dataset.leadId);
      e.dataTransfer.setData('from_stage', card.dataset.stage);
      card.style.opacity = '0.5';
    });
    card.addEventListener('dragend', () => card.style.opacity = '1');
  });
}

function renderKanbanCard(lead) {
  const pClass = `p${lead.prioridad || 3}`;
  return `
    <div class="kanban-card" data-lead-id="${lead.id}" data-stage="${lead.stage}" onclick="openLead(${lead.id})">
      <div class="kanban-card-name">${esc(lead.nombre)}</div>
      <div class="kanban-card-meta">
        <span class="priority-dot ${pClass}"></span>
        <span>${esc(lead.categoria || '')}${lead.score ? ` · ${lead.score}pts` : ''}</span>
        ${lead.live_url ? `<span style="color:var(--accent)">live</span>` : ''}
      </div>
    </div>
  `;
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
  discovered: ['badge-discovered', 'Descubierto'],
  pending_send: ['badge-sent', 'Pendiente'],
  sent: ['badge-sent', 'Enviado'],
  waiting: ['badge-waiting', 'Esperando'],
  generating: ['badge-generating', 'Generando web'],
  ready_deploy: ['badge-generating', 'Listo deploy'],
  deployed: ['badge-deployed', 'Desplegado'],
  link_sent: ['badge-link-sent', 'Link enviado'],
  completed: ['badge-completed', 'Completado'],
  error: ['badge-error', 'Error'],
};

const RESPONSE_BADGE = {
  interest: ['badge-interest', 'Interesado'],
  positive_intent: ['badge-interest', 'Positivo'],
  price_request: ['badge-interest', 'Pidió precio'],
  info_request: ['badge-neutral', 'Pidió info'],
  follow_up: ['badge-neutral', 'Follow-up'],
  rejection: ['badge-rejected', 'Rechazo'],
  neutral: ['badge-neutral', 'Neutral'],
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
    body.innerHTML = '<tr><td colspan="8" class="text-muted" style="padding:24px;text-align:center">Sin leads</td></tr>';
    return;
  }

  body.innerHTML = state.leads.map(l => {
    const [sCls, sLabel] = STAGE_BADGE[l.stage] || ['badge-neutral', l.stage];
    const [rCls, rLabel] = RESPONSE_BADGE[l.estado_respuesta] || ['', ''];
    return `
      <tr onclick="openLead(${l.id})">
        <td><strong>${esc(l.nombre)}</strong></td>
        <td class="muted">${esc(l.categoria || '—')}</td>
        <td class="muted font-mono">${esc(l.telefono || '—')}</td>
        <td>${l.score || '—'}</td>
        <td><span class="badge ${sCls}">${sLabel}</span></td>
        <td>${rLabel ? `<span class="badge ${rCls}">${rLabel}</span>` : '—'}</td>
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
  for (let p = Math.max(1, page-2); p <= Math.min(pages, page+2); p++) {
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
    ['price_request','Pidió precio'],['info_request','Pidió info'],
    ['follow_up','Follow-up'],['rejection','Rechazo'],['neutral','Neutral'],
  ].map(([v,l]) => `<option value="${v}"${lead.estado_respuesta===v?' selected':''}>${l}</option>`).join('');

  document.getElementById('lead-modal-body').innerHTML = `
    <div class="form-row">
      <div class="field"><label>Nombre</label><input type="text" id="lm-nombre" value="${esc(lead.nombre)}"></div>
      <div class="field"><label>Teléfono</label><input type="text" id="lm-telefono" value="${esc(lead.telefono||'')}"></div>
    </div>
    <div class="form-row">
      <div class="field"><label>Categoría</label><input type="text" id="lm-categoria" value="${esc(lead.categoria||'')}"></div>
      <div class="field"><label>Ciudad</label><input type="text" id="lm-ciudad" value="${esc(lead.ciudad||'Rosario')}"></div>
    </div>
    <div class="form-row full">
      <div class="field"><label>Dirección</label><input type="text" id="lm-direccion" value="${esc(lead.direccion||'')}"></div>
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
      <div class="field"><label>Renovación web</label><input type="date" id="lm-renov-web" value="${lead.fecha_renovacion_web||''}"></div>
    </div>
    <div class="form-row">
      <div class="field"><label>Renov. hosting</label><input type="date" id="lm-renov-hosting" value="${lead.fecha_renovacion_hosting||''}"></div>
      <div class="field"><label>Renov. mantenimiento</label><input type="date" id="lm-renov-mant" value="${lead.fecha_renovacion_mantenimiento||''}"></div>
    </div>
    <div class="form-row full">
      <div class="field"><label>Notas</label><textarea id="lm-notas" rows="3">${esc(lead.notas||'')}</textarea></div>
    </div>
    ${lead.live_url ? `<div style="margin-top:8px"><a href="${lead.live_url}" target="_blank" class="btn btn-ghost btn-sm">🌐 Ver sitio live</a></div>` : ''}
    ${lead.project_path ? `
      <div style="margin-top:8px;font-size:12px;color:var(--text-3)">
        Proyecto: <code style="font-family:var(--mono)">${esc(lead.project_path)}</code>
        <button class="btn btn-ghost btn-sm" style="margin-left:8px" onclick="regenerateWebsite(${lead.id})">↻ Regenerar</button>
      </div>
    ` : ''}
    ${lead.conversacion?.length ? `
      <div class="divider"></div>
      <div class="card-title">Conversación</div>
      <div style="max-height:200px;overflow-y:auto;background:var(--bg);border-radius:8px;padding:10px">
        ${lead.conversacion.map(m => `
          <div style="margin-bottom:8px">
            <span style="color:var(--text-3);font-size:11px">${m.from || ''} · ${fmtDate(m.timestamp)}</span>
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

  const body = {
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
    fecha_entrega: val('lm-fecha-entrega') || null,
    fecha_renovacion_web: val('lm-renov-web') || null,
    fecha_renovacion_hosting: val('lm-renov-hosting') || null,
    fecha_renovacion_mantenimiento: val('lm-renov-mant') || null,
  };

  const r = await api(`/api/leads/${id}`, 'PUT', body);
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
  if (!nombre || !telefono) { showToast('Nombre y teléfono son requeridos', 'error'); return; }

  const r = await api('/api/leads', 'POST', {
    nombre, telefono,
    categoria: val('nl-categoria'),
    ciudad: val('nl-ciudad'),
    direccion: val('nl-direccion'),
    notas: val('nl-notas'),
  });
  if (r) {
    showToast('Lead creado', 'success');
    closeModal('new-lead-modal');
    loadLeads();
  }
}

async function regenerateWebsite(leadId) {
  const r = await api(`/api/websites/${leadId}/regenerate`, 'POST');
  if (r) {
    showToast('Regeneración iniciada', 'success');
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
    grid.innerHTML = '<div class="empty"><div class="empty-icon">⬡</div><div class="empty-msg">Sin sitios generados aún</div></div>';
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
          ${w.live_url ? `<a href="${w.live_url}" target="_blank" class="btn btn-ghost btn-sm">↗ Abrir</a>` : ''}
          <button class="btn btn-ghost btn-sm" onclick="regenerateWebsite(${w.lead_id})">↻ Regenerar</button>
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

  // KPIs
  const grid = document.getElementById('analytics-kpi-grid');
  if (grid) {
    const s = data.stats;
    const kpis = [
      { label: 'Total leads', value: s.total },
      { label: 'Tasa de envío', value: `${s.tasa_envio}%` },
      { label: 'Tasa de interés', value: `${s.tasa_interes}%` },
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
    interest: 'Interesado', positive_intent: 'Positivo',
    price_request: 'Precio', info_request: 'Info',
    follow_up: 'Follow-up', rejection: 'Rechazo', neutral: 'Neutral',
  };
  const labels = Object.keys(responses).map(k => LABELS[k] || k);
  const values = Object.values(responses);
  const colors = ['#10b981','#22c55e','#06b6d4','#3b82f6','#f59e0b','#ef4444','#8f8f8f'];

  if (responsesChart) responsesChart.destroy();
  responsesChart = new Chart(ctx, {
    type: 'bar',
    data: { labels, datasets: [{ data: values, backgroundColor: colors, borderRadius: 4 }] },
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
  const labels = timeline.map(t => t.date.slice(5));
  const values = timeline.map(t => t.count);

  if (timelineChart) timelineChart.destroy();
  timelineChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        data: values,
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
  const data = await api('/api/finanzas');
  if (!data) return;

  const grid = document.getElementById('fin-kpi-grid');
  if (grid) {
    const s = data.stats;
    grid.innerHTML = [
      { label: 'Clientes totales', value: s.total_clientes },
      { label: 'Pagados', value: s.clientes_pagados },
      { label: 'Total ARS', value: fmtMoney(s.total_ars, 'ARS') },
      { label: 'Total USD', value: fmtMoney(s.total_usd, 'USD') },
    ].map(k => `
      <div class="kpi">
        <div class="kpi-label">${k.label}</div>
        <div class="kpi-value">${k.value}</div>
      </div>
    `).join('');
  }

  const body = document.getElementById('fin-table-body');
  if (body) {
    body.innerHTML = data.pagos.map(p => `
      <tr>
        <td><strong>${esc(p.nombre)}</strong></td>
        <td class="muted">${esc(p.servicio||'—')}</td>
        <td>${fmtMoney(p.monto, p.moneda)}</td>
        <td><span class="badge ${p.estado==='pagado'?'badge-interest':p.estado==='pendiente'?'badge-waiting':'badge-neutral'}">${p.estado}</span></td>
        <td class="muted">${fmtDate(p.fecha)}</td>
        <td class="muted" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(p.notas||'—')}</td>
        <td>
          <button class="btn btn-danger btn-sm" onclick="deletePago(${p.id})">✕</button>
        </td>
      </tr>
    `).join('') || '<tr><td colspan="7" class="text-muted" style="padding:24px;text-align:center">Sin pagos registrados</td></tr>';
  }
}

function openPaymentModal() {
  document.getElementById('p-fecha').value = new Date().toISOString().slice(0,10);
  openModal('payment-modal');
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
  });
  if (r) {
    showToast('Pago guardado', 'success');
    closeModal('payment-modal');
    loadFinanzas();
  }
}

async function deletePago(id) {
  if (!confirm('¿Eliminar este pago?')) return;
  const r = await api(`/api/finanzas/pago/${id}`, 'DELETE');
  if (r) { showToast('Pago eliminado', 'success'); loadFinanzas(); }
}

// ── Renovaciones ─────────────────────────────────────────────

async function loadRenovaciones() {
  const data = await api('/api/renewals');
  if (!data) return;

  const c = document.getElementById('renewal-sections');
  if (!c) return;

  const sections = [
    { key: '7d', title: '🔴 Esta semana', cls: 'renewal-urgent' },
    { key: '30d', title: '🟡 Próximos 30 días', cls: 'renewal-soon' },
    { key: '60d', title: '🟢 Próximos 60 días', cls: 'renewal-ok' },
  ];

  c.innerHTML = sections.map(s => {
    const items = data[s.key] || [];
    return `
      <div class="card" style="margin-bottom:16px">
        <div class="card-title">${s.title} (${items.length})</div>
        ${items.length ? items.map(r => `
          <div class="renewal-item">
            <div class="renewal-dias ${s.cls}">${r.dias < 0 ? 'VENC' : r.dias + 'd'}</div>
            <div style="flex:1">
              <div style="font-size:13px;font-weight:500">${esc(r.nombre)}</div>
              <div class="text-sm text-muted">${r.tipo} · ${r.fecha}</div>
            </div>
            <div class="text-sm text-muted">${esc(r.telefono||'')}</div>
          </div>
        `).join('') : '<div class="empty"><div class="empty-msg">Sin renovaciones en este período</div></div>'}
      </div>
    `;
  }).join('');
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
        <div style="font-size:13px;font-weight:600;color:var(--text)">${esc(t.nombre)}</div>
        <span class="badge badge-neutral">${t.tipo}</span>
        ${!t.activo ? '<span class="badge badge-rejected">Inactivo</span>' : ''}
        <div class="ml-auto flex gap-8">
          <button class="btn btn-ghost btn-sm" onclick="editTemplate(${t.id})">Editar</button>
          <button class="btn btn-danger btn-sm" onclick="deleteTemplate(${t.id})">Eliminar</button>
        </div>
      </div>
      <div style="font-family:var(--mono);font-size:12px;color:var(--text-2);background:var(--bg);border-radius:6px;padding:10px;white-space:pre-wrap">${esc(t.contenido)}</div>
    </div>
  `).join('') || '<div class="empty"><div class="empty-icon">☰</div><div class="empty-msg">Sin templates</div></div>';
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
  if (!confirm('¿Eliminar este template?')) return;
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
    { key: 'MAX_MENSAJES_POR_DIA', label: 'Mensajes por día', desc: 'Límite de envíos diarios' },
    { key: 'INTERVALO_SEGUNDOS', label: 'Intervalo entre mensajes (seg)', desc: 'Pausa entre envíos de WhatsApp' },
    { key: 'SCORE_MIN_TO_CONTACT', label: 'Score mínimo para contactar', desc: 'Leads por debajo de este score son descartados' },
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
  if (r) showToast('Configuración guardada', 'success');
}

async function runMigration() {
  const r = await api('/api/migrate', 'POST');
  if (r) showToast(r.message || `${r.imported} leads importados`, 'success');
}

// ── Modal helpers ────────────────────────────────────────────

function openModal(id) {
  document.getElementById(id)?.classList.add('open');
}

function closeModal(id) {
  document.getElementById(id)?.classList.remove('open');
}

// Close on backdrop click
document.addEventListener('click', e => {
  if (e.target.classList.contains('modal-backdrop')) {
    e.target.classList.remove('open');
  }
});

// ── API helper ───────────────────────────────────────────────

async function api(url, method = 'GET', body = null) {
  try {
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json' },
    };
    if (body !== null) opts.body = JSON.stringify(body);

    const r = await fetch(url, opts);
    const data = await r.json();

    if (!r.ok) {
      showToast(data.error || `Error ${r.status}`, 'error');
      return null;
    }
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

// ── Utilities ────────────────────────────────────────────────

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
  if (!s) return '—';
  try {
    const d = new Date(s);
    if (isNaN(d)) return s.slice(0,10);
    return d.toLocaleDateString('es-AR', { day:'2-digit', month:'short', year:'numeric' });
  } catch { return '—'; }
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
  if (label) label.textContent = connected ? 'Conectado' : 'Sin conexión';
}

function globalSearch(q) {
  if (state.currentPage === 'leads') {
    debounce(loadLeads, 300)();
  }
}

function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

// ── Init ─────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  loadDashboard();
});
