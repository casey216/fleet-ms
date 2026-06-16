// ── FleetHQ Main JS ──────────────────────────────────────────────────

// Sidebar toggle
function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('open');
    document.getElementById('sidebarOverlay').classList.toggle('open');
}

function closeSidebar() {
    document.getElementById('sidebar').classList.remove('open');
    document.getElementById('sidebarOverlay').classList.remove('open');
}

// Auto-dismiss flash messages
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => {
        document.querySelectorAll('.flash').forEach(el => {
            el.style.transition = 'opacity 0.5s';
            el.style.opacity = '0';
            setTimeout(() => el.remove(), 500);
        });
    }, 5000);
});

// Confirm delete modals
function confirmDelete(formId, message) {
    if (confirm(message || 'Are you sure you want to delete this? This action cannot be undone.')) {
        document.getElementById(formId).submit();
    }
}

// HTMX afterRequest: show toast for partial updates
document.addEventListener('htmx:afterRequest', (e) => {
    if (e.detail.successful && e.detail.requestConfig.headers['HX-Request']) {
        // Optionally show a success indicator
    }
});

// Chart.js defaults
if (typeof Chart !== 'undefined') {
    Chart.defaults.color = '#8b91a8';
    Chart.defaults.borderColor = '#2a2e3f';
    Chart.defaults.font.family = "'Inter', sans-serif";
    Chart.defaults.font.size = 12;
}

// Initialize charts if data attributes present
document.addEventListener('DOMContentLoaded', () => {
    // Fuel chart
    const fuelChartEl = document.getElementById('fuelChart');
    if (fuelChartEl && fuelChartEl.dataset.chart) {
        const data = JSON.parse(fuelChartEl.dataset.chart);
        new Chart(fuelChartEl, {
            type: 'line',
            data: {
                labels: data.map(d => d.month),
                datasets: [{
                    label: 'Fuel Cost',
                    data: data.map(d => d.cost),
                    borderColor: '#4f7ef8',
                    backgroundColor: 'rgba(79,126,248,0.08)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointBackgroundColor: '#4f7ef8',
                    pointRadius: 4,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: '#1a1d27',
                        borderColor: '#2a2e3f',
                        borderWidth: 1,
                        callbacks: {
                            label: ctx => ` ₦${ctx.parsed.y.toFixed(2)}`
                        }
                    }
                },
                scales: {
                    x: { grid: { color: '#2a2e3f' } },
                    y: {
                        grid: { color: '#2a2e3f' },
                        ticks: { callback: v => '₦' + v.toFixed(0) }
                    }
                }
            }
        });
    }

    // Status doughnut chart
    const statusChartEl = document.getElementById('statusChart');
    if (statusChartEl && statusChartEl.dataset.chart) {
        const data = JSON.parse(statusChartEl.dataset.chart);
        new Chart(statusChartEl, {
            type: 'doughnut',
            data: {
                labels: ['Active', 'In Maintenance', 'Out of Service', 'Reserved'],
                datasets: [{
                    data: [data.active, data.in_maintenance, data.out_of_service, data.reserved],
                    backgroundColor: ['#34d399', '#fbbf24', '#f87171', '#60a5fa'],
                    borderWidth: 0,
                    hoverOffset: 4,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '72%',
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: { padding: 16, usePointStyle: true, pointStyleWidth: 8 }
                    }
                }
            }
        });
    }

    // Reports monthly chart
    const monthlyChartEl = document.getElementById('monthlyChart');
    if (monthlyChartEl && monthlyChartEl.dataset.chart) {
        const data = JSON.parse(monthlyChartEl.dataset.chart);
        new Chart(monthlyChartEl, {
            type: 'bar',
            data: {
                labels: data.map(d => d.month),
                datasets: [
                    {
                        label: 'Fuel',
                        data: data.map(d => d.fuel),
                        backgroundColor: 'rgba(79,126,248,0.7)',
                        borderRadius: 4,
                    },
                    {
                        label: 'Maintenance',
                        data: data.map(d => d.maintenance),
                        backgroundColor: 'rgba(251,191,36,0.7)',
                        borderRadius: 4,
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'top' },
                    tooltip: {
                        backgroundColor: '#1a1d27',
                        borderColor: '#2a2e3f',
                        borderWidth: 1,
                        callbacks: {
                            label: ctx => ` ${ctx.dataset.label}: ₦${ctx.parsed.y.toFixed(2)}`
                        }
                    }
                },
                scales: {
                    x: { stacked: false, grid: { display: false } },
                    y: {
                        grid: { color: '#2a2e3f' },
                        ticks: { callback: v => '₦' + v }
                    }
                }
            }
        });
    }
});