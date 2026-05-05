document.addEventListener('DOMContentLoaded', async () => {
    const taskId = getTaskId();
    if (!taskId) {
        window.location.href = '/prediction';
        return;
    }

    const btnExport = document.getElementById('btn-export');
    btnExport.href = `/api/export/forecast?task_id=${taskId}&format=csv`;

    let forecastChart = registerChart('chart-forecast');
    let barChart = registerChart('chart-bar');
    let radarChart = registerChart('chart-radar');
    let componentsChart = registerChart('chart-components');
    let lstmLossChart = registerChart('chart-lstm-loss');

    async function init() {
        showLoading('加载预测报告...');
        try {
            const data = await apiFetch(`/api/predict/result?task_id=${taskId}`);
            
            const familyName = FAMILY_ZH_MAP[data.family] || data.family;
            document.getElementById('report-title').textContent = `预测报告: ${familyName} (门店 ${data.store_nbr})`;
            document.getElementById('summary-target').textContent = `${familyName} / 门店 ${data.store_nbr}`;
            document.getElementById('summary-days').textContent = `${data.forecast_days} 天`;
            document.getElementById('summary-best-model').textContent = data.evaluation.best_model || '未评估';

            renderForecastChart(data.models, data.evaluation);
            renderMetricsTable(data.evaluation.metrics_table);
            renderBarChart(data.evaluation.bar_chart);
            
            if (Object.keys(data.models).length >= 2) {
                renderRadarChart(data.evaluation.radar_chart);
            } else {
                document.getElementById('chart-radar').parentElement.parentElement.classList.add('d-none');
            }

            renderRecommendation(data.evaluation);

            if (data.models.Prophet && data.models.Prophet.components) {
                document.getElementById('container-components').classList.remove('d-none');
                renderComponentsChart(data.models.Prophet.dates, data.models.Prophet.components);
            }

            if (data.models.LSTM && data.models.LSTM.training_history) {
                document.getElementById('container-lstm-loss').classList.remove('d-none');
                renderTrainingHistory(data.models.LSTM.training_history);
            }

        } catch (error) {
            showToast('error', error.message);
        } finally {
            hideLoading();
        }
    }

    function renderForecastChart(models, evaluation) {
        const series = [];
        const legendData = [];
        let dates = [];

        Object.keys(models).forEach(m => {
            const modelData = models[m];
            if (!dates.length) dates = modelData.dates;

            legendData.push(m);
            series.push({
                name: m,
                type: 'line',
                data: modelData.forecast,
                smooth: true,
                symbol: 'none',
                lineStyle: { width: 3 },
                emphasis: { focus: 'series' }
            });

            if (Array.isArray(modelData.lower_ci) && Array.isArray(modelData.upper_ci)) {
                series.push({
                    name: `${m} Lower`,
                    type: 'line',
                    data: modelData.lower_ci,
                    lineStyle: { opacity: 0 },
                    stack: `conf-${m}`,
                    symbol: 'none',
                    tooltip: { show: false }
                });
                series.push({
                    name: `${m} Upper`,
                    type: 'line',
                    data: modelData.upper_ci.map((u, i) => u - (modelData.lower_ci[i] || 0)),
                    lineStyle: { opacity: 0 },
                    areaStyle: { opacity: 0.2 },
                    stack: `conf-${m}`,
                    symbol: 'none',
                    tooltip: { show: false }
                });
            }
        });

        const option = baseChartOption({
            legend: { data: legendData },
            xAxis: { type: 'category', data: dates },
            yAxis: { type: 'value' },
            series: series,
            dataZoom: [{ type: 'inside' }, { type: 'slider' }]
        });
        forecastChart.setOption(option);
    }

    function renderMetricsTable(metricsTable) {
        const tbody = document.querySelector('#metrics-table tbody');
        tbody.innerHTML = '';

        (Array.isArray(metricsTable) ? metricsTable : []).forEach(row => {
            const tr = document.createElement('tr');
            if (row.rank === 1) tr.classList.add('table-success');
            
            tr.innerHTML = `
                <td class="fw-bold">${row.model.toUpperCase()}</td>
                <td><span class="badge ${row.rank === 1 ? 'bg-success' : 'bg-secondary'}">No.${row.rank}</span></td>
                <td>${row.mae.toFixed(2)}</td>
                <td>${row.rmse.toFixed(2)}</td>
                <td>${row.mape.toFixed(2)}%</td>
                <td>${row.smape.toFixed(2)}%</td>
                <td>${row.r2.toFixed(4)}</td>
                <td class="fw-bold text-primary">${row.score.toFixed(2)}</td>
            `;
            tbody.appendChild(tr);
        });
    }

    function renderBarChart(barChartData) {
        const safeData = barChartData || {};
        const models = Array.isArray(safeData.models) ? safeData.models.map(m => String(m).toUpperCase()) : [];
        const series = [
            { name: 'MAE', type: 'bar', data: Array.isArray(safeData.mae) ? safeData.mae : [] },
            { name: 'RMSE', type: 'bar', data: Array.isArray(safeData.rmse) ? safeData.rmse : [] },
            { name: 'MAPE (%)', type: 'bar', data: Array.isArray(safeData.mape) ? safeData.mape : [] }
        ];

        const option = baseChartOption({
            tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
            legend: { data: ['MAE', 'RMSE', 'MAPE (%)'] },
            xAxis: { type: 'category', data: models },
            yAxis: { type: 'value' },
            series: series,
        });
        barChart.setOption(option);
    }

    function renderRadarChart(radarChartData) {
        const safeData = radarChartData || {};
        const indicator = (Array.isArray(safeData.indicators) ? safeData.indicators : []).map(ind => ({
            name: typeof ind === 'string' ? ind : ind.name,
            max: typeof ind === 'string' ? 1 : ind.max
        }));
        const seriesData = (Array.isArray(safeData.series) ? safeData.series : []).map(s => ({
            name: String(s.name).toUpperCase(),
            value: s.values || s.value || []
        }));

        const option = baseChartOption({
            tooltip: {},
            legend: { data: seriesData.map(s => s.name), bottom: 0 },
            radar: {
                indicator: indicator,
                splitLine: { lineStyle: { color: 'rgba(255,255,255,0.12)' } },
                splitArea: { areaStyle: { color: ['rgba(255,255,255,0.04)', 'rgba(124,249,200,0.05)'] } },
                axisName: { color: '#AAB6C9', fontSize: 11 }
            },
            series: [{
                type: 'radar',
                data: seriesData,
                areaStyle: { opacity: 0.18 }
            }]
        });
        radarChart.setOption(option);
    }

    function renderComponentsChart(dates, components) {
        const series = [];
        const legendData = [];

        ['trend', 'weekly', 'yearly', 'holidays'].forEach(comp => {
            if (components[comp]) {
                legendData.push(comp);
                series.push({
                    name: comp,
                    type: 'line',
                    data: components[comp],
                    smooth: true,
                    symbol: 'none'
                });
            }
        });

        const option = baseChartOption({
            legend: { data: legendData },
            xAxis: { type: 'category', data: dates },
            yAxis: { type: 'value' },
            series: series,
            dataZoom: [{ type: 'inside' }, { type: 'slider' }]
        });
        componentsChart.setOption(option);
    }

    function renderTrainingHistory(history) {
        const trainLoss = Array.isArray(history.train_loss) ? history.train_loss : [];
        const valLoss = Array.isArray(history.val_loss) ? history.val_loss : [];
        const epochs = Array.from({length: trainLoss.length}, (_, i) => i + 1);
        
        const option = baseChartOption({
            legend: { data: ['Train Loss', 'Val Loss'] },
            xAxis: { type: 'category', data: epochs, name: 'Epoch' },
            yAxis: { type: 'value', name: 'Loss' },
            series: [
                { name: 'Train Loss', type: 'line', data: trainLoss, smooth: true },
                { name: 'Val Loss', type: 'line', data: valLoss, smooth: true }
            ]
        });
        lstmLossChart.setOption(option);
    }

    function renderRecommendation(evaluation) {
        const bestModel = (evaluation.best_model || '').toUpperCase() || '未知';
        document.getElementById('rec-model-name').textContent = bestModel;
        const bestMetrics = (evaluation.metrics_table || []).find(m => m.rank === 1);
        if (!bestMetrics) return;
        const reason = `在本次预测中，${bestModel} 模型表现最佳。其综合评分为 ${bestMetrics.score.toFixed(2)}，MAPE 为 ${bestMetrics.mape.toFixed(2)}%，R² 达到 ${bestMetrics.r2.toFixed(4)}。建议在实际业务中采用该模型的预测结果作为参考。`;
        document.getElementById('rec-reason').textContent = reason;
    }

    init();
});
