// Binario Websites Dashboard — Premium SaaS
// State management, animations, real-time updates

let fullData = null;
let currentPage = 'dashboard';
let leadsPage = 1;
let leadsPerPage = 20;
let leadsSort = { column: 'nombre', direction: 'asc' };
let activityChart = null;

// DOM Elements
const refreshBtn = document.getElementById('refresh-btn');
const updateTimeSpan = document.getElementById('update-time');
const executiveSummarySpan = document.querySelector('.summary-text');

// Helper: Format number with K/M
function formatNumber(num) {
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
    return num.toString();
}

// Helper: Count animation
function animateValue(element, start, end, duration = 800) {
    if (!element) return;
    const range = end - start;
    const increment = range / (duration / 16);
    let current = start;
    const timer = setInterval(() => {
        current += increment;
        if ((increment > 0 && current >= end) || (increment < 0 && current <= end)) {
            current = end;
            clearInterval(timer);
        }
        element.textContent = formatNumber(Math.floor(current));
    }, 16);
}

// Render KPI Cards
function renderKPIs(stats) {
    const container = document.getElementById('kpi-grid');
    const cards = [
        {
            label: 'Leads totales',
            value: stats.total,
            sub: 'en el dataset',
            icon: 'fa-database',
            stage: 'total'
        },
        {
            label: 'Mensajes enviados',
            value: stats.enviados,
            sub: `${stats.tasa_envio}% del total`,
            icon: 'fa-comment-dots',
            stage: 'sent'
        },
        {
            label: 'Webs generadas',
            value: stats.con_web,
            sub: `${stats.tasa_web}% de contactados`,
            icon: 'fa-code',
            stage: 'website'
        },
        {
            label: 'Sitios publicados',
            value: stats.con_link,
            sub: `${stats.tasa_deploy}% de webs`,
            icon: 'fa-globe',
            stage: 'deployed'
        }
    ];

    container.innerHTML = cards.map(card => `
        <div class="kpi-card" data-stage="${card.stage}">
            <div class="kpi-header">
                <span>${card.label}</span>
                <div class="kpi-icon"><i class="fas ${card.icon}"></i></div>
            </div>
            <div class="kpi-value" data-value="${card.value}">0</div>
            <div class="kpi-sub">${card.sub}</div>
        </div>
    `).join('');

    const valueElements = document.querySelectorAll('.kpi-value');
    const values = [stats.total, stats.enviados, stats.con_web, stats.con_link];
    valueElements.forEach((el, i) => {
        animateValue(el, 0, values[i], 800);
    });
}

// Render Funnel
function renderFunnel(stats) {
    const container = document.getElementById('funnel');
    const stages = [
        { label: 'Leads',        value: stats.total,    stage: 'total',    loss: null },
        { label: 'Enviados',     value: stats.enviados, stage: 'sent',     loss: stats.total - stats.enviados },
        { label: 'Web generada', value: stats.con_web,  stage: 'website',  loss: stats.enviados - stats.con_web },
        { label: 'Publicados',   value: stats.con_link, stage: 'deployed', loss: stats.con_web - stats.con_link }
    ];

    container.innerHTML = stages.map((stage, i) => `
        ${i > 0 ? '<div class="funnel-arrow"><i class="fas fa-arrow-right"></i></div>' : ''}
        <div class="funnel-stage" data-stage="${stage.stage}">
            <div class="value" data-value="${stage.value}">0</div>
            <div class="label">${stage.label}</div>
            ${stage.loss !== null && stage.loss > 0 ? `<div class="funnel-loss">-${stage.loss} no pasaron</div>` : ''}
        </div>
    `).join('');

    const funnelValues = document.querySelectorAll('.funnel-stage .value');
    const values = stages.map(s => s.value);
    funnelValues.forEach((el, i) => {
        animateValue(el, 0, values[i], 800);
    });
}

// Render Categories
function renderCategories(categorias) {
    const container = document.getElementById('categories-list');
    const total = categorias.reduce((sum, c) => sum + c.total, 0);
    
    container.innerHTML = categorias.map(cat => `
        <div class="category-item">
            <span class="category-name">${cat.nombre}</span>
            <div class="category-bar-container">
                <div class="category-bar" style="width: 0%" data-width="${(cat.total / total) * 100}"></div>
            </div>
            <span class="category-percent">${cat.tasa_envio}% conv</span>
        </div>
    `).join('');
    
    // Animate bars
    setTimeout(() => {
        document.querySelectorAll('.category-bar').forEach(bar => {
            bar.style.width = bar.dataset.width + '%';
        });
    }, 100);
}

// Render Deployments Timeline
function renderDeployments(leads, limit = 10) {
    const deployed = leads.filter(l => l.live_url).slice(0, limit);
    const container = document.getElementById('deployments-timeline');

    if (deployed.length === 0) {
        container.innerHTML = '<div class="empty-state"><i class="fas fa-inbox"></i><p>No hay sitios publicados todavia</p></div>';
        return;
    }

    container.innerHTML = deployed.map(d => `
        <div class="timeline-item">
            <div class="timeline-left">
                <div class="timeline-icon"><i class="fas fa-check-circle"></i></div>
                <div class="timeline-content">
                    <div class="timeline-title">${escapeHtml(d.nombre || '—')}</div>
                    <div class="timeline-url"><a href="${d.live_url}" target="_blank" style="color: var(--accent); text-decoration: none;">${d.live_url}</a></div>
                </div>
            </div>
            <div class="timeline-right">
                <div class="timeline-date">${formatDate(d.fecha_envio_links || d.fecha_envio)}</div>
                <div class="timeline-time badge badge-deployed">Live</div>
            </div>
        </div>
    `).join('');
}

// Render Full Deployments
function renderFullDeployments(leads) {
    const deployed = leads.filter(l => l.live_url);
    const container = document.getElementById('deployments-full');

    if (deployed.length === 0) {
        container.innerHTML = '<div class="empty-state"><i class="fas fa-inbox"></i><p>No hay sitios publicados todavia</p></div>';
        return;
    }

    container.innerHTML = deployed.map(d => `
        <div class="timeline-item">
            <div class="timeline-left">
                <div class="timeline-icon"><i class="fas fa-rocket"></i></div>
                <div class="timeline-content">
                    <div class="timeline-title">${escapeHtml(d.nombre || '—')}</div>
                    <div class="timeline-url"><a href="${d.live_url}" target="_blank" style="color: var(--accent); text-decoration: none;">${d.live_url}</a></div>
                </div>
            </div>
            <div class="timeline-right">
                <div class="timeline-date">${formatDate(d.fecha_envio_links || d.fecha_envio)}</div>
                <div class="timeline-time badge badge-deployed">Live</div>
            </div>
        </div>
    `).join('');
}

// Render Activity Chart
function renderActivityChart(leads) {
    const ctx = document.getElementById('activity-chart').getContext('2d');
    const last30Days = Array.from({ length: 30 }, (_, i) => {
        const d = new Date();
        d.setDate(d.getDate() - i);
        return d.toISOString().split('T')[0];
    }).reverse();
    
    const counts = last30Days.map(day => {
        return leads.filter(l => (l.fecha_envio || '').startsWith(day)).length;
    });
    
    if (activityChart) activityChart.destroy();
    
    activityChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: last30Days.map(d => d.slice(5)),
            datasets: [{
                label: 'Leads sent',
                data: counts,
                borderColor: '#10b981',
                backgroundColor: 'rgba(16, 185, 129, 0.05)',
                borderWidth: 2,
                fill: true,
                tension: 0.3,
                pointRadius: 0,
                pointHoverRadius: 4,
                pointHoverBackgroundColor: '#10b981'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false },
                tooltip: { backgroundColor: '#1e1e1e', titleColor: '#fff', bodyColor: '#a1a1aa' }
            },
            scales: {
                y: { grid: { color: '#2a2a2a' }, ticks: { color: '#71717a' } },
                x: { grid: { display: false }, ticks: { color: '#71717a', maxRotation: 45, minRotation: 45 } }
            }
        }
    });
}

// Render Analytics Grid
function renderAnalytics(categorias) {
    const container = document.getElementById('analytics-grid');
    const total = categorias.reduce((sum, c) => sum + c.total, 0);

    container.innerHTML = categorias.map(cat => `
        <div class="analytics-card">
            <div class="analytics-header">
                <strong>${cat.nombre}</strong>
                <span class="badge ${cat.tasa_envio > 50 ? 'badge-deployed' : 'badge-pending'}">${cat.tasa_envio}% enviados</span>
            </div>
            <div class="category-bar-container" style="margin: 12px 0;">
                <div class="category-bar" style="width: 0%" data-width="${(cat.total / total) * 100}"></div>
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 13px; color: var(--text-tertiary);">
                <span>${cat.total} leads</span>
                <span>${cat.enviados} enviados</span>
                <span>${cat.convertidos} publicados</span>
            </div>
        </div>
    `).join('');

    setTimeout(() => {
        document.querySelectorAll('#analytics-grid .category-bar').forEach(bar => {
            bar.style.width = bar.dataset.width + '%';
        });
    }, 100);
}

// Render Leads Table with Pagination and Sorting
function renderLeadsTable(leads, search = '', statusFilter = 'all') {
    let filtered = leads.filter(l => {
        const matchesSearch = (l.nombre || '').toLowerCase().includes(search.toLowerCase()) ||
                              (l.categoria || '').toLowerCase().includes(search.toLowerCase());
        let matchesStatus = true;
        if (statusFilter === 'pending') matchesStatus = (l.enviado || '').toUpperCase() !== 'SI';
        else if (statusFilter === 'sent') matchesStatus = (l.enviado || '').toUpperCase() === 'SI' && !l.project_path;
        else if (statusFilter === 'website') matchesStatus = !!l.project_path && !l.live_url;
        else if (statusFilter === 'deployed') matchesStatus = !!l.live_url;
        return matchesSearch && matchesStatus;
    });
    
    // Sorting
    filtered.sort((a, b) => {
        let aVal = a[leadsSort.column] || '';
        let bVal = b[leadsSort.column] || '';
        if (leadsSort.column === 'enviado') {
            aVal = (a.enviado || '').toUpperCase() === 'SI' ? 1 : 0;
            bVal = (b.enviado || '').toUpperCase() === 'SI' ? 1 : 0;
        }
        if (aVal < bVal) return leadsSort.direction === 'asc' ? -1 : 1;
        if (aVal > bVal) return leadsSort.direction === 'asc' ? 1 : -1;
        return 0;
    });
    
    const totalPages = Math.ceil(filtered.length / leadsPerPage);
    const start = (leadsPage - 1) * leadsPerPage;
    const paginated = filtered.slice(start, start + leadsPerPage);
    
    const tbody = document.getElementById('leads-tbody');
    tbody.innerHTML = paginated.map(l => {
        let status = '';
        let statusClass = '';
        if ((l.enviado || '').toUpperCase() !== 'SI') {
            status = 'Pending';
            statusClass = 'badge-pending';
        } else if (!l.project_path) {
            status = 'Sent';
            statusClass = 'badge-sent';
        } else if (!l.live_url) {
            status = 'Website Ready';
            statusClass = 'badge-website';
        } else {
            status = 'Deployed';
            statusClass = 'badge-deployed';
        }
        
        return `
            <tr>
                <td>${escapeHtml(l.nombre || '—')}</td>
                <td>${escapeHtml(l.categoria || '—')}</td>
                <td>${escapeHtml(l.telefono || '—')}</td>
                <td><span class="badge ${statusClass}">${status}</span></td>
                <td>${l.project_path ? '✅' : '❌'}</td>
                <td>${l.live_url ? '<a href="' + l.live_url + '" target="_blank" style="color: var(--accent);">🔗</a>' : '❌'}</td>
            </tr>
        `;
    }).join('');
    
    // Pagination
    const pagination = document.getElementById('leads-pagination');
    let paginationHtml = '';
    for (let i = 1; i <= Math.min(totalPages, 10); i++) {
        paginationHtml += `<button class="page-btn ${i === leadsPage ? 'active' : ''}" data-page="${i}">${i}</button>`;
    }
    pagination.innerHTML = paginationHtml;
    document.querySelectorAll('.page-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            leadsPage = parseInt(btn.dataset.page);
            renderLeadsTable(leads, document.getElementById('search-leads')?.value || '', document.getElementById('status-filter')?.value || 'all');
        });
    });
}

// Escape HTML
function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/[&<>]/g, function(m) {
        if (m === '&') return '&amp;';
        if (m === '<') return '&lt;';
        if (m === '>') return '&gt;';
        return m;
    });
}

// Format a date string as dd mmm yyyy (es-AR locale)
function formatDate(dateStr) {
    if (!dateStr) return '—';
    try {
        const d = new Date(dateStr);
        if (isNaN(d.getTime())) return dateStr.slice(0, 10) || '—';
        return d.toLocaleDateString('es-AR', { day: '2-digit', month: 'short', year: 'numeric' });
    } catch {
        return '—';
    }
}

// Update everything from API
async function updateDashboard() {
    try {
        const response = await fetch('/api/datos');
        const data = await response.json();
        fullData = data;
        
        const stats = data.stats;
        const leads = data.leads;
        const categorias = data.categorias;
        
        renderKPIs(stats);
        renderFunnel(stats);
        renderCategories(categorias);
        renderDeployments(leads);
        renderActivityChart(leads);
        renderLeadsTable(leads, document.getElementById('search-leads')?.value || '', document.getElementById('status-filter')?.value || 'all');
        renderFullDeployments(leads);
        renderAnalytics(categorias);
        
        // Update header
        const date = new Date(data.lastUpdated);
        updateTimeSpan.textContent = date.toLocaleTimeString();
        
        const totalLeads = stats.total;
        const conversionRate = stats.tasa_deploy;
        executiveSummarySpan.textContent = `${totalLeads} leads · ${conversionRate}% conversion · ${stats.con_link} sitios activos`;
        
    } catch (error) {
        console.error('Error fetching data:', error);
    }
}

// Navigation
function initNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    const pages = document.querySelectorAll('.page');
    
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const pageId = item.dataset.page;
            
            navItems.forEach(nav => nav.classList.remove('active'));
            item.classList.add('active');
            
            pages.forEach(page => page.classList.remove('active'));
            document.getElementById(`page-${pageId}`).classList.add('active');
            
            currentPage = pageId;
        });
    });
}

// Table sorting
function initSorting() {
    document.querySelectorAll('.data-table th[data-sort]').forEach(th => {
        th.addEventListener('click', () => {
            const column = th.dataset.sort;
            if (leadsSort.column === column) {
                leadsSort.direction = leadsSort.direction === 'asc' ? 'desc' : 'asc';
            } else {
                leadsSort.column = column;
                leadsSort.direction = 'asc';
            }
            renderLeadsTable(fullData?.leads || [], document.getElementById('search-leads')?.value || '', document.getElementById('status-filter')?.value || 'all');
        });
    });
}

// Event listeners
function initEventListeners() {
    refreshBtn.addEventListener('click', () => updateDashboard());
    
    const searchInput = document.getElementById('search-leads');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            leadsPage = 1;
            renderLeadsTable(fullData?.leads || [], e.target.value, document.getElementById('status-filter')?.value || 'all');
        });
    }
    
    const statusFilter = document.getElementById('status-filter');
    if (statusFilter) {
        statusFilter.addEventListener('change', (e) => {
            leadsPage = 1;
            renderLeadsTable(fullData?.leads || [], document.getElementById('search-leads')?.value || '', e.target.value);
        });
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initSorting();
    initEventListeners();
    updateDashboard();
    setInterval(updateDashboard, 30000); // Update every 30 seconds
});