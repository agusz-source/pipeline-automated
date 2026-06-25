// Binario Websites Dashboard

const PALETTE = ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#06b6d4', '#ec4899'];

let fullData = null;
let fullFinanzasData = null;
let currentPage = 'dashboard';
let leadsPage = 1;
const leadsPerPage = 20;
let leadsSort = { column: 'score', direction: 'desc' };
let activityChart = null;
let revenueChart = null;
let paymentStatusChart = null;

const refreshBtn = document.getElementById('refresh-btn');
const updateTimeSpan = document.getElementById('update-time');
const summaryText = document.getElementById('summary-text');

// ── Helpers ──────────────────────────────────────────────────

function formatNumber(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000)    return (n / 1000).toFixed(0) + 'K';
    return String(n);
}

function formatMoney(amount, moneda = 'ARS') {
    const prefix = moneda === 'USD' ? 'U$D ' : '$';
    if (amount >= 1000000) return prefix + (amount / 1000000).toFixed(2) + 'M';
    if (amount >= 1000)    return prefix + (amount / 1000).toFixed(0) + 'K';
    return prefix + amount.toLocaleString('es-AR');
}

function animateValue(el, start, end, duration = 700, fmt = null) {
    if (!el) return;
    if (end === start) { el.textContent = fmt ? fmt(end) : formatNumber(end); return; }
    const step = (end - start) / (duration / 16);
    let cur = start;
    const t = setInterval(() => {
        cur += step;
        const done = step > 0 ? cur >= end : cur <= end;
        if (done) { cur = end; clearInterval(t); }
        el.textContent = fmt ? fmt(Math.floor(cur)) : formatNumber(Math.floor(cur));
    }, 16);
}

function escapeHtml(s) {
    if (!s) return '';
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
}

function formatDate(s) {
    if (!s) return '—';
    try {
        const d = new Date(s);
        if (isNaN(d)) return s.slice(0,10) || '—';
        return d.toLocaleDateString('es-AR', { day: '2-digit', month: 'short', year: 'numeric' });
    } catch { return '—'; }
}

function responseLabel(cat) {
    const map = {
        interest: ['Interesado', 'badge-interest'],
        price_request: ['Pidió precio', 'badge-price'],
        info_request: ['Pidió info', 'badge-info'],
        positive_intent: ['Lista positiva', 'badge-interest'],
        follow_up: ['Follow-up', 'badge-info'],
        rejection: ['Rechazo', 'badge-rejected'],
        neutral: ['Neutral', 'badge-neutral'],
    };
    return map[cat] || ['', ''];
}

// ── Dashboard KPIs ────────────────────────────────────────

function renderKPIs(stats) {
    const grid = document.getElementById('kpi-grid');
    const cards = [
        { label: 'Leads en CRM',     value: stats.total,        sub: 'registros totales',             icon: 'fa-database',     stage: 'total' },
        { label: 'Enviados',         value: stats.enviados,     sub: `${stats.tasa_envio}% del total`,icon: 'fa-comment-dots', stage: 'sent' },
        { label: 'Respondieron',     value: stats.respondieron, sub: `${stats.tasa_respuesta}% de enviados`, icon: 'fa-reply', stage: 'replied' },
        { label: 'Interesados',      value: stats.interesados,  sub: `${stats.tasa_interes}% de respuestas`,icon: 'fa-thumbs-up', stage: 'interested' },
        { label: 'Webs generadas',   value: stats.con_web,      sub: `${stats.tasa_web}% de interesados`,  icon: 'fa-code',     stage: 'website' },
        { label: 'Sitios live',      value: stats.con_link,     sub: `${stats.tasa_deploy}% de webs`,      icon: 'fa-globe',    stage: 'deployed' },
    ];
    grid.innerHTML = cards.map(c => `
        <div class="kpi-card" data-stage="${c.stage}">
            <div class="kpi-header"><span>${c.label}</span><div class="kpi-icon"><i class="fas ${c.icon}"></i></div></div>
            <div class="kpi-value">0</div>
            <div class="kpi-sub">${c.sub}</div>
        </div>`).join('');
    grid.querySelectorAll('.kpi-value').forEach((el, i) => animateValue(el, 0, cards[i].value));
}

function renderPipeline(stats) {
    const c = document.getElementById('pipeline');
    const stages = [
        { label: 'Dataset',        value: stats.total,        stage: 'total',      color: '#3b82f6' },
        { label: 'Enviados',       value: stats.enviados,     stage: 'sent',       color: '#8b5cf6' },
        { label: 'Respondieron',   value: stats.respondieron, stage: 'replied',    color: '#06b6d4' },
        { label: 'Interesados',    value: stats.interesados,  stage: 'interested', color: '#f59e0b' },
        { label: 'Web generada',   value: stats.con_web,      stage: 'website',    color: '#ec4899' },
        { label: 'Live',           value: stats.con_link,     stage: 'deployed',   color: '#10b981' },
        { label: 'Clientes',       value: stats.clientes || 0,stage: 'client',     color: '#22c55e' },
    ];
    const maxVal = stages[0].value || 1;
    c.innerHTML = stages.map((s, i) => {
        const pct = Math.max(8, (s.value / maxVal) * 100);
        const loss = i > 0 ? stages[i - 1].value - s.value : 0;
        return `
        <div class="pipeline-stage">
            <div class="pipeline-bar-wrap">
                <div class="pipeline-bar" style="height:${pct}%;background:${s.color}" data-h="${pct}"></div>
            </div>
            <div class="pipeline-value" style="color:${s.color}">0</div>
            <div class="pipeline-label">${s.label}</div>
            ${loss > 0 ? `<div class="pipeline-loss">-${loss}</div>` : ''}
        </div>`;
    }).join('<div class="pipeline-arrow"><i class="fas fa-chevron-right"></i></div>');
    c.querySelectorAll('.pipeline-value').forEach((el, i) => animateValue(el, 0, stages[i].value));
}

function renderCategories(cats) {
    const c = document.getElementById('categories-list');
    const total = cats.reduce((s, x) => s + x.total, 0);
    c.innerHTML = cats.map((cat, i) => {
        const color = PALETTE[i % PALETTE.length];
        const pct = total ? (cat.total / total) * 100 : 0;
        return `<div class="category-item">
            <span class="category-name">${escapeHtml(cat.nombre)}</span>
            <div class="category-bar-container">
                <div class="category-bar" style="width:0%;background:${color}" data-w="${pct}"></div>
            </div>
            <span class="category-percent" style="color:${color}">${cat.tasa_envio}%</span>
        </div>`;
    }).join('');
    setTimeout(() => c.querySelectorAll('.category-bar').forEach(b => b.style.width = b.dataset.w + '%'), 80);
}

function renderDeployments(leads, limit = 8) {
    const deployed = leads.filter(l => l.live_url).slice(0, limit);
    const c = document.getElementById('deployments-timeline');
    if (!deployed.length) { c.innerHTML = '<div class="empty-state"><i class="fas fa-inbox"></i><p>Sin sitios publicados todavía</p></div>'; return; }
    c.innerHTML = deployed.map(d => `
        <div class="timeline-item">
            <div class="timeline-left">
                <div class="timeline-icon"><i class="fas fa-check-circle"></i></div>
                <div class="timeline-content">
                    <div class="timeline-title">${escapeHtml(d.nombre || '—')}</div>
                    <div class="timeline-url"><a href="${escapeHtml(d.live_url)}" target="_blank" style="color:var(--accent);text-decoration:none">${escapeHtml(d.live_url)}</a></div>
                </div>
            </div>
            <div class="timeline-right">
                <div class="timeline-date">${formatDate(d.fecha_envio_links || d.fecha_envio)}</div>
                <span class="badge badge-deployed">Live</span>
            </div>
        </div>`).join('');
}

function renderFullDeployments(leads) {
    const deployed = leads.filter(l => l.live_url);
    const c = document.getElementById('deployments-full');
    if (!deployed.length) { c.innerHTML = '<div class="empty-state"><i class="fas fa-inbox"></i><p>Sin sitios publicados todavía</p></div>'; return; }
    c.innerHTML = deployed.map(d => `
        <div class="timeline-item">
            <div class="timeline-left">
                <div class="timeline-icon"><i class="fas fa-rocket"></i></div>
                <div class="timeline-content">
                    <div class="timeline-title">${escapeHtml(d.nombre || '—')}</div>
                    <div class="timeline-url"><a href="${escapeHtml(d.live_url)}" target="_blank" style="color:var(--accent);text-decoration:none">${escapeHtml(d.live_url)}</a></div>
                </div>
            </div>
            <div class="timeline-right">
                <div class="timeline-date">${formatDate(d.fecha_envio_links || d.fecha_envio)}</div>
                <span class="badge badge-deployed">Live</span>
            </div>
        </div>`).join('');
}

function renderActivityChart(leads) {
    const ctx = document.getElementById('activity-chart').getContext('2d');
    const days = Array.from({length: 30}, (_, i) => {
        const d = new Date(); d.setDate(d.getDate() - (29 - i));
        return d.toISOString().split('T')[0];
    });
    const counts = days.map(day => leads.filter(l => (l.fecha_envio || '').startsWith(day)).length);
    if (activityChart) activityChart.destroy();
    activityChart = new Chart(ctx, {
        type: 'line',
        data: { labels: days.map(d => d.slice(5)), datasets: [{ label: 'Enviados', data: counts, borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.08)', borderWidth: 2, fill: true, tension: 0.4, pointRadius: 0, pointHoverRadius: 5, pointHoverBackgroundColor: '#3b82f6' }] },
        options: { responsive: true, maintainAspectRatio: true,
            plugins: { legend: { display: false }, tooltip: { backgroundColor: '#18182a', titleColor: '#fff', bodyColor: '#9898b8', borderColor: '#252538', borderWidth: 1 } },
            scales: { y: { grid: { color: '#252538' }, ticks: { color: '#5a5a78' }, beginAtZero: true }, x: { grid: { display: false }, ticks: { color: '#5a5a78', maxRotation: 45, minRotation: 45 } } }
        }
    });
}

function renderAnalytics(cats) {
    const c = document.getElementById('analytics-grid');
    const total = cats.reduce((s, x) => s + x.total, 0);
    c.innerHTML = cats.map((cat, i) => {
        const color = PALETTE[i % PALETTE.length];
        const pct = total ? (cat.total / total) * 100 : 0;
        return `<div class="analytics-card" style="border-left-color:${color}">
            <div class="analytics-header">
                <strong>${escapeHtml(cat.nombre)}</strong>
                <span class="badge" style="background:${color}22;color:${color}">${cat.tasa_envio}% enviados</span>
            </div>
            <div class="category-bar-container" style="margin:10px 0">
                <div class="category-bar" style="width:0%;background:${color}" data-w="${pct}"></div>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--text-tertiary)">
                <span>${cat.total} leads</span>
                <span>${cat.enviados} enviados</span>
                <span style="color:var(--amber)">${cat.interesados || 0} interesados</span>
                <span style="color:${color}">${cat.convertidos} live</span>
            </div>
        </div>`;
    }).join('');
    setTimeout(() => c.querySelectorAll('.category-bar').forEach(b => b.style.width = b.dataset.w + '%'), 80);
}

// ── Renewals ──────────────────────────────────────────────

function renderRenewals(renewals) {
    const total = Object.values(renewals).reduce((s, a) => s + a.length, 0);

    // Badge on nav
    const badge = document.getElementById('renewal-badge');
    if (badge) {
        const urgent = renewals['7d']?.length || 0;
        if (urgent > 0) {
            badge.textContent = urgent;
            badge.style.display = 'inline-flex';
        } else {
            badge.style.display = 'none';
        }
    }

    // Banner
    const banner = document.getElementById('renewals-banner');
    const bannerText = document.getElementById('renewals-banner-text');
    if (banner && bannerText) {
        if (total > 0) {
            bannerText.textContent = `${total} renovación(es) próxima(s) — ${renewals['7d']?.length || 0} urgentes`;
            banner.style.display = 'flex';
        } else {
            banner.style.display = 'none';
        }
    }

    renderRenewalWindow('7d', renewals['7d'] || []);
    renderRenewalWindow('30d', renewals['30d'] || []);
    renderRenewalWindow('60d', renewals['60d'] || []);
}

function renderRenewalWindow(key, items) {
    const list = document.getElementById(`renewals-${key}`);
    const badge = document.getElementById(`badge-${key}`);
    if (badge) badge.textContent = items.length;

    if (!list) return;
    if (!items.length) {
        list.innerHTML = key === '7d'
            ? '<div class="empty-state"><i class="fas fa-check-circle"></i><p>Sin vencimientos urgentes</p></div>'
            : '<div class="empty-state"><i class="fas fa-calendar-check"></i><p>Sin vencimientos</p></div>';
        return;
    }

    list.innerHTML = items.map(item => {
        const vencido = item.dias < 0;
        const dotClass = vencido ? 'red' : (item.dias <= 7 ? 'red' : (item.dias <= 30 ? 'yellow' : 'green'));
        const diasLabel = vencido ? `Vencido hace ${Math.abs(item.dias)} días` : (item.dias === 0 ? 'Vence hoy' : `${item.dias} días`);
        return `<div class="renewal-item" data-tel="${escapeHtml(item.telefono)}">
            <div class="renewal-item-left">
                <span class="renewal-dot ${dotClass}"></span>
                <div>
                    <div class="renewal-name">${escapeHtml(item.nombre)}</div>
                    <div class="renewal-type">${escapeHtml(item.tipo)}</div>
                </div>
            </div>
            <div class="renewal-item-right">
                <div class="renewal-date">${escapeHtml(item.fecha)}</div>
                <div class="renewal-days ${vencido ? 'overdue' : ''}">${diasLabel}</div>
            </div>
        </div>`;
    }).join('');

    list.querySelectorAll('.renewal-item[data-tel]').forEach(el => {
        el.addEventListener('click', () => openEditLead(el.dataset.tel));
    });
}

function populateRenewalLeadSelect(leads) {
    const sel = document.getElementById('renewal-lead-select');
    if (!sel) return;
    const clients = leads.filter(l => l.live_url || l.fecha_entrega);
    sel.innerHTML = '<option value="">— Seleccionar cliente —</option>' +
        clients.map(l => `<option value="${escapeHtml(l.telefono)}" data-lead='${JSON.stringify(l).replace(/'/g, "&#39;")}'>${escapeHtml(l.nombre)} (${escapeHtml(l.telefono)})</option>`).join('');

    sel.addEventListener('change', () => {
        const opt = sel.options[sel.selectedIndex];
        const form = document.getElementById('renewal-dates-form');
        if (!opt.value) { form.style.display = 'none'; return; }
        const lead = JSON.parse(opt.getAttribute('data-lead') || '{}');
        document.getElementById('ren-entrega').value = lead.fecha_entrega || '';
        document.getElementById('ren-web').value = lead.fecha_renovacion_web || '';
        document.getElementById('ren-hosting').value = lead.fecha_renovacion_hosting || '';
        document.getElementById('ren-mant').value = lead.fecha_renovacion_mantenimiento || '';
        form.style.display = 'grid';
    });
}

async function saveRenewalDates() {
    const btn = document.getElementById('save-renewal-btn');
    btn.disabled = true;
    const sel = document.getElementById('renewal-lead-select');
    const telefono = sel.value;
    if (!telefono) { btn.disabled = false; return; }
    const body = {
        telefono,
        fecha_entrega: document.getElementById('ren-entrega').value,
        fecha_renovacion_web: document.getElementById('ren-web').value,
        fecha_renovacion_hosting: document.getElementById('ren-hosting').value,
        fecha_renovacion_mantenimiento: document.getElementById('ren-mant').value,
    };
    try {
        const res = await fetch('/api/lead', { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) });
        if (res.ok) {
            btn.innerHTML = '<i class="fas fa-check"></i> Guardado';
            setTimeout(() => { btn.innerHTML = '<i class="fas fa-save"></i> Guardar fechas'; btn.disabled = false; }, 2000);
            await updateDashboard();
        } else {
            alert('Error al guardar'); btn.disabled = false;
        }
    } catch { alert('Error de conexión'); btn.disabled = false; }
}

// ── Leads Table ───────────────────────────────────────────

function getLeadPayment(telefono) {
    return fullFinanzasData?.pagos.find(p => p.telefono === telefono) || null;
}

function scoreBar(score) {
    if (!score && score !== 0) return '<span style="color:var(--text-tertiary)">—</span>';
    const n = parseInt(score);
    const color = n >= 70 ? '#10b981' : (n >= 50 ? '#f59e0b' : '#f97316');
    return `<div class="score-bar-wrap" title="Score: ${n}">
        <div class="score-bar" style="width:${n}%;background:${color}"></div>
        <span class="score-num" style="color:${color}">${n}</span>
    </div>`;
}

function renderLeadsTable(leads, search = '', statusFilter = 'all') {
    let filtered = leads.filter(l => {
        const q = search.toLowerCase();
        const matchSearch = (l.nombre || '').toLowerCase().includes(q) || (l.categoria || '').toLowerCase().includes(q) || (l.telefono || '').includes(q);
        let matchStatus = true;
        const resp = (l.estado_respuesta || '');
        if (statusFilter === 'pending')    matchStatus = (l.enviado || '').toUpperCase() !== 'SI';
        if (statusFilter === 'sent')       matchStatus = (l.enviado || '').toUpperCase() === 'SI' && !l.project_path;
        if (statusFilter === 'interested') matchStatus = ['interest', 'price_request', 'follow_up', 'positive_intent'].includes(resp);
        if (statusFilter === 'rejected')   matchStatus = resp === 'rejection';
        if (statusFilter === 'website')    matchStatus = !!l.project_path && !l.live_url;
        if (statusFilter === 'deployed')   matchStatus = !!l.live_url;
        if (statusFilter === 'client')     matchStatus = !!l.fecha_entrega;
        return matchSearch && matchStatus;
    });

    filtered.sort((a, b) => {
        let av = a[leadsSort.column] || '', bv = b[leadsSort.column] || '';
        if (leadsSort.column === 'enviado') { av = av.toUpperCase() === 'SI' ? 1 : 0; bv = bv.toUpperCase() === 'SI' ? 1 : 0; }
        if (leadsSort.column === 'score')   { av = parseInt(av) || 0; bv = parseInt(bv) || 0; }
        if (av < bv) return leadsSort.direction === 'asc' ? -1 : 1;
        if (av > bv) return leadsSort.direction === 'asc' ? 1 : -1;
        return 0;
    });

    const totalPages = Math.ceil(filtered.length / leadsPerPage);
    const start = (leadsPage - 1) * leadsPerPage;
    const page = filtered.slice(start, start + leadsPerPage);

    const tbody = document.getElementById('leads-tbody');
    tbody.innerHTML = page.map(l => {
        let label = 'Pendiente', cls = 'badge-pending';
        if ((l.enviado || '').toUpperCase() !== 'SI')  { label = 'Pendiente'; cls = 'badge-pending'; }
        else if (l.fecha_entrega)                       { label = 'Cliente'; cls = 'badge-client'; }
        else if (l.live_url)                            { label = 'Publicado'; cls = 'badge-deployed'; }
        else if (l.project_path)                        { label = 'Web lista'; cls = 'badge-website'; }
        else                                            { label = 'Enviado'; cls = 'badge-sent'; }

        const resp = l.estado_respuesta || '';
        const [respLabel, respCls] = responseLabel(resp);

        const pago = getLeadPayment(l.telefono);
        let pagoHtml = '<span style="color:var(--text-tertiary)">—</span>';
        if (pago) {
            const pc = { pagado: '#10b981', pendiente: '#f97316', parcial: '#f59e0b' }[pago.estado] || '#9898b8';
            pagoHtml = `<span style="color:${pc};font-weight:600">${formatMoney(pago.monto, pago.moneda)}</span>`;
        }

        return `<tr>
            <td><strong>${escapeHtml(l.nombre || '—')}</strong></td>
            <td style="color:var(--text-secondary)">${escapeHtml(l.categoria || '—')}</td>
            <td>${scoreBar(l.score)}</td>
            <td style="color:var(--text-tertiary);font-size:12px">${escapeHtml(l.telefono || '—')}</td>
            <td><span class="badge ${cls}">${label}</span></td>
            <td>${respLabel ? `<span class="badge ${respCls}">${respLabel}</span>` : '<span style="color:var(--text-tertiary)">—</span>'}</td>
            <td>${l.live_url ? `<a href="${escapeHtml(l.live_url)}" target="_blank" style="color:var(--accent);font-size:12px">🔗 Ver sitio</a>` : '<span style="color:var(--text-tertiary)">—</span>'}</td>
            <td>${pagoHtml}</td>
            <td>
                <button class="btn-icon edit-lead-btn" data-tel="${escapeHtml(l.telefono)}" title="Editar"><i class="fas fa-edit"></i></button>
            </td>
        </tr>`;
    }).join('');

    tbody.querySelectorAll('.edit-lead-btn').forEach(btn => btn.addEventListener('click', () => openEditLead(btn.dataset.tel)));

    const pag = document.getElementById('leads-pagination');
    pag.innerHTML = Array.from({length: Math.min(totalPages, 10)}, (_, i) => i + 1)
        .map(i => `<button class="page-btn ${i === leadsPage ? 'active' : ''}" data-page="${i}">${i}</button>`).join('');
    pag.querySelectorAll('.page-btn').forEach(btn => btn.addEventListener('click', () => {
        leadsPage = parseInt(btn.dataset.page);
        renderLeadsTable(leads, document.getElementById('search-leads')?.value || '', document.getElementById('status-filter')?.value || 'all');
    }));
}

// ── Edit Lead Modal ───────────────────────────────────────

function openEditLead(telefono) {
    const lead = fullData?.leads.find(l => l.telefono === telefono);
    if (!lead) return;
    const parsedt = s => { try { return s ? new Date(s).toISOString().slice(0,16) : ''; } catch { return ''; } };
    document.getElementById('edit-telefono').value        = lead.telefono || '';
    document.getElementById('edit-nombre').value          = lead.nombre || '';
    document.getElementById('edit-enviado').value         = (lead.enviado || '').toUpperCase() === 'SI' ? 'SI' : '';
    document.getElementById('edit-fecha-envio').value     = parsedt(lead.fecha_envio);
    document.getElementById('edit-estado-respuesta').value= lead.estado_respuesta || '';
    document.getElementById('edit-fecha-respuesta').value = parsedt(lead.fecha_respuesta);
    document.getElementById('edit-project-path').value    = lead.project_path || '';
    document.getElementById('edit-live-url').value        = lead.live_url || '';
    document.getElementById('edit-enviado-links').value   = (lead.enviado_links || '').toUpperCase() === 'SI' ? 'SI' : '';
    document.getElementById('edit-fecha-links').value     = parsedt(lead.fecha_envio_links);
    document.getElementById('edit-notas').value           = lead.notas || '';
    document.getElementById('edit-fecha-entrega').value   = lead.fecha_entrega || '';
    document.getElementById('edit-ren-web').value         = lead.fecha_renovacion_web || '';
    document.getElementById('edit-ren-hosting').value     = lead.fecha_renovacion_hosting || '';
    document.getElementById('edit-ren-mant').value        = lead.fecha_renovacion_mantenimiento || '';

    // Load conversation
    loadConversation(telefono);
    // Default to basic tab
    switchModalTab('lead-basic');
    openModal('modal-edit-lead');
}

async function loadConversation(telefono) {
    const c = document.getElementById('conversation-timeline');
    if (!c) return;
    try {
        const msgs = await fetch(`/api/conversations/${encodeURIComponent(telefono)}`).then(r => r.json());
        if (!msgs.length) {
            c.innerHTML = '<div class="empty-state"><i class="fas fa-comments"></i><p>Sin mensajes registrados</p></div>';
            return;
        }
        const catColors = { rejection:'#f97316', interest:'#10b981', price_request:'#f59e0b', info_request:'#3b82f6', positive_intent:'#22c55e', follow_up:'#8b5cf6', neutral:'#9898b8' };
        c.innerHTML = msgs.map(m => {
            const dir = m.direction === 'in' ? 'in' : 'out';
            const [rl] = responseLabel(m.category || '');
            const color = catColors[m.category] || '#9898b8';
            return `<div class="msg msg-${dir}">
                <div class="msg-bubble">${escapeHtml(m.text || '')}</div>
                <div class="msg-meta">
                    <span>${formatDate(m.timestamp)}</span>
                    ${rl ? `<span class="badge" style="background:${color}22;color:${color};font-size:10px">${rl}</span>` : ''}
                </div>
            </div>`;
        }).join('');
    } catch { c.innerHTML = '<div class="empty-state"><i class="fas fa-exclamation-triangle"></i><p>Error cargando conversación</p></div>'; }
}

async function saveLeadChanges() {
    const btn = document.getElementById('save-lead-btn');
    btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Guardando...';
    const body = {
        telefono:                      document.getElementById('edit-telefono').value,
        enviado:                       document.getElementById('edit-enviado').value,
        fecha_envio:                   document.getElementById('edit-fecha-envio').value,
        estado_respuesta:              document.getElementById('edit-estado-respuesta').value,
        fecha_respuesta:               document.getElementById('edit-fecha-respuesta').value,
        project_path:                  document.getElementById('edit-project-path').value,
        live_url:                      document.getElementById('edit-live-url').value,
        enviado_links:                 document.getElementById('edit-enviado-links').value,
        fecha_envio_links:             document.getElementById('edit-fecha-links').value,
        notas:                         document.getElementById('edit-notas').value,
        fecha_entrega:                 document.getElementById('edit-fecha-entrega').value,
        fecha_renovacion_web:          document.getElementById('edit-ren-web').value,
        fecha_renovacion_hosting:      document.getElementById('edit-ren-hosting').value,
        fecha_renovacion_mantenimiento:document.getElementById('edit-ren-mant').value,
    };
    try {
        const res = await fetch('/api/lead', { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) });
        if (res.ok) { closeModal('modal-edit-lead'); await updateDashboard(); }
        else { const e = await res.json(); alert('Error: ' + (e.error || 'Desconocido')); }
    } catch { alert('Error de conexión'); }
    finally { btn.disabled = false; btn.innerHTML = '<i class="fas fa-save"></i> Guardar cambios'; }
}

// ── Finanzas ──────────────────────────────────────────────

function renderFinanzasKPIs(stats) {
    const grid = document.getElementById('finanzas-kpi-grid');
    const cards = [
        { label: 'Total cobrado ARS', value: stats.total_ars,     fmt: v => '$' + formatNumber(v),    sub: `${stats.clientes_pagados} pagados`,    icon: 'fa-peso-sign', stage: 'ars' },
        { label: 'Total cobrado USD', value: stats.total_usd,     fmt: v => 'U$D ' + formatNumber(v), sub: 'dólares',                              icon: 'fa-dollar-sign', stage: 'usd' },
        { label: 'Por cobrar ARS',    value: stats.pendiente_ars, fmt: v => '$' + formatNumber(v),    sub: `${stats.clientes_pendientes} pend.`,    icon: 'fa-clock', stage: 'pend' },
        { label: 'Clientes total',    value: stats.total_clientes,fmt: v => String(v),               sub: `prom. $${formatNumber(stats.promedio_ars)}`, icon: 'fa-users', stage: 'cnt' },
    ];
    grid.innerHTML = cards.map(c => `
        <div class="kpi-card" data-stage="${c.stage}">
            <div class="kpi-header"><span>${c.label}</span><div class="kpi-icon"><i class="fas ${c.icon}"></i></div></div>
            <div class="kpi-value">0</div>
            <div class="kpi-sub">${c.sub}</div>
        </div>`).join('');
    grid.querySelectorAll('.kpi-value').forEach((el, i) => animateValue(el, 0, cards[i].value, 700, cards[i].fmt));
}

function renderRevenueChart(pagos) {
    const ctx = document.getElementById('revenue-chart')?.getContext('2d');
    if (!ctx) return;
    const last6 = Array.from({length: 6}, (_, i) => { const d = new Date(); d.setMonth(d.getMonth() - (5 - i)); return d.toISOString().slice(0, 7); });
    const byMonth = Object.fromEntries(last6.map(m => [m, 0]));
    pagos.filter(p => p.moneda === 'ARS' && p.estado === 'pagado').forEach(p => { const m = (p.fecha || '').slice(0,7); if (m in byMonth) byMonth[m] += p.monto; });
    const labels = last6.map(m => { const [y,mo] = m.split('-'); return new Date(y, mo-1).toLocaleDateString('es-AR',{month:'short',year:'2-digit'}); });
    if (revenueChart) revenueChart.destroy();
    revenueChart = new Chart(ctx, {
        type: 'bar',
        data: { labels, datasets: [{ label: 'ARS cobrado', data: last6.map(m => byMonth[m]), backgroundColor: 'rgba(245,158,11,0.7)', borderColor: '#f59e0b', borderWidth: 2, borderRadius: 6 }] },
        options: { responsive: true, maintainAspectRatio: true,
            plugins: { legend: { display: false }, tooltip: { backgroundColor: '#18182a', callbacks: { label: c => '$' + c.raw.toLocaleString('es-AR') } } },
            scales: { y: { grid: { color: '#252538' }, ticks: { color: '#5a5a78', callback: v => '$' + formatNumber(v) }, beginAtZero: true }, x: { grid: { display: false }, ticks: { color: '#5a5a78' } } }
        }
    });
}

function renderPaymentStatusChart(stats) {
    const ctx = document.getElementById('payment-status-chart')?.getContext('2d');
    if (!ctx) return;
    const total = stats.clientes_pagados + stats.clientes_pendientes;
    if (!total) { ctx.canvas.parentElement.innerHTML = '<p style="text-align:center;color:var(--text-tertiary);padding:2rem">Sin datos todavía</p>'; return; }
    if (paymentStatusChart) paymentStatusChart.destroy();
    paymentStatusChart = new Chart(ctx, {
        type: 'doughnut',
        data: { labels: ['Pagados', 'Pendientes'], datasets: [{ data: [stats.clientes_pagados, stats.clientes_pendientes], backgroundColor: ['#10b981', '#f97316'], borderColor: '#18182a', borderWidth: 3 }] },
        options: { responsive: true, cutout: '65%', plugins: { legend: { position: 'bottom', labels: { color: '#9898b8', padding: 16, font: { size: 12 } } }, tooltip: { backgroundColor: '#18182a' } } }
    });
}

function renderPaymentsTable(pagos) {
    const tbody = document.getElementById('payments-tbody');
    const empty = document.getElementById('payments-empty');
    const table = document.getElementById('payments-table');
    if (!pagos.length) { table.style.display = 'none'; empty.style.display = 'block'; return; }
    table.style.display = ''; empty.style.display = 'none';
    const statusInfo = { pagado: ['Pagado','badge-deployed'], pendiente: ['Pendiente','badge-pending'], parcial: ['Parcial','badge-website'] };
    const today = new Date().toISOString().slice(0,10);
    tbody.innerHTML = pagos.map(p => {
        const [label, cls] = statusInfo[p.estado] || ['?', 'badge-pending'];
        const mc = { pagado: '#10b981', pendiente: '#f97316', parcial: '#f59e0b' }[p.estado] || '#9898b8';
        const vence = p.fecha_vencimiento;
        const diasRestantes = vence ? Math.ceil((new Date(vence) - new Date(today)) / 86400000) : null;
        const venceBadge = (vence && p.estado !== 'pagado')
            ? `<span class="badge ${diasRestantes <= 3 ? 'badge-critical' : 'badge-warning'}" style="margin-left:6px;font-size:10px" title="Vencimiento">⏰ ${diasRestantes <= 0 ? 'Vencido' : `${diasRestantes}d`}</span>`
            : '';
        const markPaidBtn = p.estado !== 'pagado'
            ? `<button class="btn-icon mark-paid-btn" data-tel="${escapeHtml(p.telefono)}" title="Marcar como pagado" style="color:#10b981"><i class="fas fa-check-circle"></i></button>`
            : '';
        return `<tr>
            <td><strong>${escapeHtml(p.nombre || '—')}</strong>${venceBadge}</td>
            <td style="color:var(--text-secondary)">${escapeHtml(p.servicio || 'Sitio web')}</td>
            <td style="font-weight:700;color:${mc}">${formatMoney(p.monto, p.moneda)}</td>
            <td><span class="badge ${cls}">${label}</span></td>
            <td style="color:var(--text-tertiary);font-size:12px">${formatDate(p.fecha)}</td>
            <td style="color:var(--text-tertiary);font-size:12px">${escapeHtml(p.notas || '—')}</td>
            <td>
                ${markPaidBtn}
                <button class="btn-icon edit-pay-btn" data-tel="${escapeHtml(p.telefono)}" title="Editar"><i class="fas fa-edit"></i></button>
                <button class="btn-icon danger del-pay-btn" data-tel="${escapeHtml(p.telefono)}" data-nombre="${escapeHtml(p.nombre)}" title="Eliminar"><i class="fas fa-trash"></i></button>
            </td>
        </tr>`;
    }).join('');
    tbody.querySelectorAll('.mark-paid-btn').forEach(btn => btn.addEventListener('click', () => markAsPaid(btn.dataset.tel)));
    tbody.querySelectorAll('.edit-pay-btn').forEach(btn => btn.addEventListener('click', () => { const pago = fullFinanzasData?.pagos.find(p => p.telefono === btn.dataset.tel); if (pago) openPaymentModal(pago); }));
    tbody.querySelectorAll('.del-pay-btn').forEach(btn => btn.addEventListener('click', () => { if (confirm(`Eliminar pago de ${btn.dataset.nombre}?`)) deletePayment(btn.dataset.tel); }));
}

// ── Payment Modal ─────────────────────────────────────────

function openPaymentModal(existing = null) {
    const leads = fullData?.leads || [];
    const select = document.getElementById('pay-lead-select');
    select.innerHTML = '<option value="">— Seleccionar lead —</option>' +
        leads.map(l => `<option value="${escapeHtml(l.telefono)}" data-nombre="${escapeHtml(l.nombre)}">${escapeHtml(l.nombre)} (${escapeHtml(l.telefono)})</option>`).join('');
    document.getElementById('modal-payment-title').innerHTML = `<i class="fas fa-dollar-sign" style="color:#f59e0b;margin-right:8px"></i>${existing ? 'Editar pago' : 'Registrar pago'}`;
    if (existing) {
        document.getElementById('pay-telefono-hidden').value = existing.telefono || '';
        document.getElementById('pay-nombre').value          = existing.nombre   || '';
        document.getElementById('pay-monto').value           = existing.monto    || '';
        document.getElementById('pay-moneda').value          = existing.moneda   || 'ARS';
        document.getElementById('pay-estado').value          = existing.estado   || 'pagado';
        document.getElementById('pay-fecha').value           = existing.fecha    || '';
        document.getElementById('pay-servicio').value        = existing.servicio || 'Sitio web';
        document.getElementById('pay-notas').value           = existing.notas    || '';
        if (existing.telefono) select.value = existing.telefono;
    } else {
        ['pay-telefono-hidden','pay-nombre','pay-notas'].forEach(id => document.getElementById(id).value = '');
        document.getElementById('pay-monto').value   = fullFinanzasData?.config?.precio_sugerido || '';
        document.getElementById('pay-moneda').value  = fullFinanzasData?.config?.moneda_default || 'ARS';
        document.getElementById('pay-estado').value  = 'pagado';
        document.getElementById('pay-fecha').value   = new Date().toISOString().slice(0,10);
        document.getElementById('pay-servicio').value= 'Sitio web';
        select.value = '';
    }
    openModal('modal-payment');
}

async function savePayment() {
    const btn = document.getElementById('save-payment-btn');
    btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Guardando...';
    const select = document.getElementById('pay-lead-select');
    const selectedOpt = select.options[select.selectedIndex];
    const telefono = select.value || document.getElementById('pay-telefono-hidden').value || ('manual-' + Date.now());
    const body = {
        telefono, nombre: document.getElementById('pay-nombre').value || selectedOpt?.dataset.nombre || '',
        monto: parseFloat(document.getElementById('pay-monto').value) || 0,
        moneda: document.getElementById('pay-moneda').value,
        estado: document.getElementById('pay-estado').value,
        fecha: document.getElementById('pay-fecha').value,
        servicio: document.getElementById('pay-servicio').value,
        notas: document.getElementById('pay-notas').value,
    };
    try {
        const res = await fetch('/api/finanzas/pago', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
        if (res.ok) { closeModal('modal-payment'); await updateFinanzas(); }
        else alert('Error al guardar');
    } catch { alert('Error de conexión'); }
    finally { btn.disabled = false; btn.innerHTML = '<i class="fas fa-save"></i> Guardar'; }
}

async function deletePayment(telefono) {
    const res = await fetch('/api/finanzas/pago/' + encodeURIComponent(telefono), { method: 'DELETE' });
    if (res.ok) await updateFinanzas(); else alert('Error al eliminar');
}

async function markAsPaid(telefono) {
    const pago = fullFinanzasData?.pagos.find(p => p.telefono === telefono);
    if (!pago) return;
    const body = { ...pago, estado: 'pagado', fecha: new Date().toISOString().slice(0,10) };
    const res = await fetch('/api/finanzas/pago', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
    if (res.ok) await updateFinanzas(); else alert('Error al actualizar');
}

async function saveFinanzasConfig() {
    const btn = document.getElementById('save-config-btn');
    btn.disabled = true;
    const body = { precio_sugerido: parseFloat(document.getElementById('config-precio').value) || 0, moneda_default: document.getElementById('config-moneda').value };
    const res = await fetch('/api/finanzas/config', { method: 'PUT', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
    if (res.ok) { await updateFinanzas(); btn.textContent = '✓ Guardado'; setTimeout(() => { btn.innerHTML = 'Guardar config'; btn.disabled = false; }, 1500); }
    else btn.disabled = false;
}

// ── Data loaders ──────────────────────────────────────────

async function updateDashboard() {
    try {
        const data = await fetch('/api/datos').then(r => r.json());
        fullData = data;
        const { stats, leads, categorias, renewals } = data;
        renderKPIs(stats);
        renderPipeline(stats);
        renderCategories(categorias);
        renderDeployments(leads);
        renderActivityChart(leads);
        renderFullDeployments(leads);
        renderAnalytics(categorias);
        renderRenewals(renewals || {});
        populateRenewalLeadSelect(leads);
        renderLeadsTable(leads, document.getElementById('search-leads')?.value || '', document.getElementById('status-filter')?.value || 'all');
        updateTimeSpan.textContent = new Date(data.lastUpdated).toLocaleTimeString();
        const rc = data.renewal_count || 0;
        summaryText.textContent = `${stats.total} leads · ${stats.tasa_deploy}% publicados · ${stats.con_link} sitios live${rc > 0 ? ` · ${rc} reno.` : ''}`;
    } catch (e) { console.error('Dashboard error:', e); }
}

async function updateFinanzas() {
    try {
        const data = await fetch('/api/finanzas').then(r => r.json());
        fullFinanzasData = data;
        renderFinanzasKPIs(data.stats);
        renderRevenueChart(data.pagos);
        renderPaymentStatusChart(data.stats);
        renderPaymentsTable(data.pagos);
        const precioEl = document.getElementById('config-precio');
        const monedaEl = document.getElementById('config-moneda');
        if (precioEl) precioEl.value = data.config?.precio_sugerido || '';
        if (monedaEl) monedaEl.value = data.config?.moneda_default || 'ARS';
        if (fullData && currentPage === 'leads') renderLeadsTable(fullData.leads, document.getElementById('search-leads')?.value || '', document.getElementById('status-filter')?.value || 'all');
    } catch (e) { console.error('Finanzas error:', e); }
}

// ── Modal helpers ─────────────────────────────────────────

function openModal(id)  { document.getElementById(id)?.classList.add('active');    document.body.style.overflow = 'hidden'; }
function closeModal(id) { document.getElementById(id)?.classList.remove('active'); document.body.style.overflow = ''; }

function switchModalTab(tabId) {
    document.querySelectorAll('.modal-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.modal-tab-content').forEach(c => c.classList.remove('active'));
    document.querySelector(`.modal-tab[data-tab="${tabId}"]`)?.classList.add('active');
    document.getElementById(`tab-${tabId}`)?.classList.add('active');
}

function initModals() {
    document.querySelectorAll('[data-close]').forEach(btn => btn.addEventListener('click', () => closeModal(btn.dataset.close)));
    document.querySelectorAll('.modal-overlay').forEach(o => o.addEventListener('click', e => { if (e.target === o) closeModal(o.id); }));
    document.addEventListener('keydown', e => { if (e.key === 'Escape') document.querySelectorAll('.modal-overlay.active').forEach(m => closeModal(m.id)); });
    document.getElementById('save-lead-btn')?.addEventListener('click', saveLeadChanges);
    document.getElementById('save-payment-btn')?.addEventListener('click', savePayment);
    document.getElementById('add-payment-btn')?.addEventListener('click', () => openPaymentModal());
    document.getElementById('save-config-btn')?.addEventListener('click', saveFinanzasConfig);
    document.getElementById('save-renewal-btn')?.addEventListener('click', saveRenewalDates);
    document.getElementById('pay-lead-select')?.addEventListener('change', e => {
        const opt = e.target.options[e.target.selectedIndex];
        if (opt.value) { document.getElementById('pay-nombre').value = opt.dataset.nombre || ''; document.getElementById('pay-telefono-hidden').value = opt.value; }
    });
    document.querySelectorAll('.modal-tab').forEach(tab => tab.addEventListener('click', () => switchModalTab(tab.dataset.tab)));
}

// ── Navigation ────────────────────────────────────────────

function initNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    const pages    = document.querySelectorAll('.page');
    const titleEl  = document.getElementById('page-title');
    const labels   = { dashboard: 'Dashboard', leads: 'Leads', renovaciones: 'Renovaciones', finanzas: 'Finanzas', analytics: 'Analytics', deployments: 'Deployments' };

    navItems.forEach(item => item.addEventListener('click', e => {
        e.preventDefault();
        const id = item.dataset.page;
        navItems.forEach(n => n.classList.remove('active'));
        item.classList.add('active');
        pages.forEach(p => p.classList.remove('active'));
        document.getElementById(`page-${id}`)?.classList.add('active');
        currentPage = id;
        if (titleEl) titleEl.textContent = labels[id] || id;
        if (id === 'finanzas' && !fullFinanzasData) updateFinanzas();
    }));
}

function initSorting() {
    document.querySelectorAll('#leads-table th[data-sort]').forEach(th => th.addEventListener('click', () => {
        const col = th.dataset.sort;
        leadsSort = { column: col, direction: leadsSort.column === col && leadsSort.direction === 'asc' ? 'desc' : 'asc' };
        renderLeadsTable(fullData?.leads || [], document.getElementById('search-leads')?.value || '', document.getElementById('status-filter')?.value || 'all');
    }));
}

function initEventListeners() {
    refreshBtn?.addEventListener('click', () => { updateDashboard(); updateFinanzas(); });
    document.getElementById('search-leads')?.addEventListener('input', e => { leadsPage = 1; renderLeadsTable(fullData?.leads || [], e.target.value, document.getElementById('status-filter')?.value || 'all'); });
    document.getElementById('status-filter')?.addEventListener('change', e => { leadsPage = 1; renderLeadsTable(fullData?.leads || [], document.getElementById('search-leads')?.value || '', e.target.value); });
}

// ── Init ──────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initSorting();
    initEventListeners();
    initModals();
    updateDashboard();
    updateFinanzas();
    setInterval(() => { updateDashboard(); updateFinanzas(); }, 30000);
});
