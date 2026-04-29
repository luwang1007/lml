document.addEventListener('DOMContentLoaded', async () => {
    const sessionId = getSessionId();
    if (!sessionId) {
        window.location.href = '/';
        return;
    }

    const filterFamily = document.getElementById('filter-family');
    const filterStore = document.getElementById('filter-store');
    const btnRefresh = document.getElementById('btn-refresh');
    const granularityRadios = document.querySelectorAll('input[name="granularity"]');

    let trendChart = registerChart('chart-trend');
    let monthlyChart = registerChart('chart-monthly');
    let pieChart = registerChart('chart-pie');
    let topChart = registerChart('chart-top');

    async function init() {
        showLoading('加载数据中...');
        try {
            const [overview, monthly, pie, top] = await Promise.all([
                apiFetch(`/api/analysis/overview?session_id=${sessionId}`),
                apiFetch(`/api/analysis/monthly_comparison?session_id=${sessionId}`),
                apiFetch(`/api/analysis/category_pie?session_id=${sessionId}`),
                apiFetch(`/api/analysis/top_families?session_id=${sessionId}&n=10`)
            ]);

            renderKPICards(overview);
            populateDropdowns(overview);
            
            renderMonthlyComparison(monthly);
            renderCategoryPie(pie);
            renderTopFamilies(top);

            await refreshTrend();
        } catch (error) {
            showToast('error', error.message);
        } finally {
            hideLoading();
        }
    }

    function populateDropdowns(overview) {
        Object.keys(FAMILY_ZH_MAP).forEach(f => {
            const opt = document.createElement('option');
            opt.value = f;
            opt.textContent = FAMILY_ZH_MAP[f];
            filterFamily.appendChild(opt);
        });

        for (let i = 1; i <= 5; i++) {
            const opt = document.createElement('option');
            opt.value = i;
            opt.textContent = `门店 ${i}`;
            filterStore.appendChild(opt);
        }
    }

    function renderKPICards(overview) {
        document.getElementById('kpi-total').textContent = overview.total_sales ? formatNumber(overview.total_sales, 0) : '-';
        document.getElementById('kpi-avg-daily').textContent = overview.avg_daily_sales ? formatNumber(overview.avg_daily_sales, 0) : '-';
        document.getElementById('kpi-yoy').textContent = overview.yoy_growth !== null && overview.yoy_growth !== undefined ? `${overview.yoy_growth}%` : '-';
        document.getElementById('kpi-best-family').textContent = overview.best_family ? overview.best_family.name_zh : '-';
    }

    async function refreshTrend() {
        const granularity = document.querySelector('input[name="granularity"]:checked').value;
        const family = filterFamily.value;
        const store = filterStore.value;

        showLoading('刷新趋势图...');
        try {
            const trendData = await apiFetch(`/api/analysis/trend?session_id=${sessionId}&granularity=${granularity}&family=${family}&store_nbr=${store}`);
            renderTrendChart(trendData);
        } catch (error) {
            showToast('error', error.message);
        } finally {
            hideLoading();
        }
    }

    function renderTrendChart(data) {
        if (!data.series || !data.series.length) return;
        const option = baseChartOption({
            xAxis: { type: 'category', data: data.xAxis },
            yAxis: { type: 'value' },
            series: [{
                data: data.series[0].data,
                type: 'line',
                smooth: true,
                areaStyle: { opacity: 0.08 },
                itemStyle: { color: CHART_COLORS[0] }
            }],
        });
        trendChart.setOption(option);
    }

    function renderMonthlyComparison(data) {
        const rawSeries = Array.isArray(data.series) ? data.series : [];
        const series = rawSeries.map(s => ({
            name: s.name,
            type: 'bar',
            data: Array.isArray(s.data) ? s.data : []
        }));
        const option = baseChartOption({
            legend: { data: rawSeries.map(s => s.name) },
            xAxis: { type: 'category', data: Array.isArray(data.months) ? data.months : [] },
            yAxis: { type: 'value' },
            series: series,
        });
        monthlyChart.setOption(option);
    }

    function renderCategoryPie(data) {
        const pieData = Array.isArray(data.series) ? data.series : [];

        const option = baseChartOption({
            tooltip: { trigger: 'item' },
            legend: { type: 'scroll', bottom: 0 },
            series: [{
                type: 'pie',
                radius: ['40%', '70%'],
                center: ['50%', '46%'],
                data: pieData,
                label: { color: '#605e5c', fontSize: 11 },
                emphasis: { scaleSize: 4 }
            }]
        });
        pieChart.setOption(option);
    }

    function renderTopFamilies(data) {
        const families = Array.isArray(data.families) ? [...data.families].reverse() : [];
        const sales = Array.isArray(data.sales) ? [...data.sales].reverse() : [];

        const option = baseChartOption({
            tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
            xAxis: { type: 'value' },
            yAxis: { type: 'category', data: families },
            series: [{
                type: 'bar',
                data: sales,
                itemStyle: { color: CHART_COLORS[1], borderRadius: [0, 2, 2, 0] }
            }],
            grid: { left: 96, right: 28, bottom: 36, top: 18, containLabel: true }
        });
        topChart.setOption(option);
    }

    btnRefresh.addEventListener('click', refreshTrend);
    granularityRadios.forEach(r => r.addEventListener('change', refreshTrend));
    filterFamily.addEventListener('change', refreshTrend);
    filterStore.addEventListener('change', refreshTrend);

    init();
});
