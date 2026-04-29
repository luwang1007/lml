document.addEventListener('DOMContentLoaded', async () => {
    const sessionId = getSessionId();
    if (!sessionId) {
        window.location.href = '/';
        return;
    }

    const predFamily = document.getElementById('pred-family');
    const predStore = document.getElementById('pred-store');
    const adfResult = document.getElementById('adf-result');
    const forecastDays = document.getElementById('forecast-days');
    const forecastDaysVal = document.getElementById('forecast-days-val');
    const btnStart = document.getElementById('btn-start');
    const btnCancel = document.getElementById('btn-cancel');
    const progressPanel = document.getElementById('progress-panel');
    const predictionPreview = document.getElementById('prediction-preview');
    const configPanel = document.getElementById('config-panel');
    const taskProgress = document.getElementById('task-progress');
    const taskStep = document.getElementById('task-step');

    let pollInterval = null;

    Object.keys(FAMILY_ZH_MAP).forEach(f => {
        const opt = document.createElement('option');
        opt.value = f;
        opt.textContent = FAMILY_ZH_MAP[f];
        predFamily.appendChild(opt);
    });

    for (let i = 1; i <= 5; i++) {
        const opt = document.createElement('option');
        opt.value = i;
        opt.textContent = `门店 ${i}`;
        predStore.appendChild(opt);
    }

    forecastDays.addEventListener('input', (e) => {
        forecastDaysVal.textContent = e.target.value;
    });

    ['prophet-cps', 'lstm-epochs', 'lstm-seq'].forEach(id => {
        const el = document.getElementById(id);
        const valEl = document.getElementById(`${id}-val`);
        el.addEventListener('input', (e) => {
            valEl.textContent = e.target.value;
        });
    });

    const toggleCollapse = (checkboxId, collapseId) => {
        const cb = document.getElementById(checkboxId);
        const col = document.getElementById(collapseId);
        cb.addEventListener('change', () => {
            if (cb.checked) col.classList.add('show');
            else col.classList.remove('show');
        });
    };
    toggleCollapse('model-arima', 'params-arima');
    toggleCollapse('model-prophet', 'params-prophet');
    toggleCollapse('model-lstm', 'params-lstm');

    const runADF = async () => {
        const family = predFamily.value;
        const store = predStore.value;
        try {
            const data = await apiFetch(`/api/analysis/adf?session_id=${sessionId}&family=${family}&store_nbr=${store}`);
            adfResult.classList.remove('d-none');
            adfResult.innerHTML = `
                <strong>ADF 检验结果:</strong><br>
                统计量: ${data.adf_statistic.toFixed(4)}<br>
                P值: ${data.p_value.toFixed(4)}<br>
                建议差分阶数: d=${data.suggested_d}<br>
                结论: <span class="badge ${data.is_stationary ? 'bg-success' : 'bg-warning'}">${data.is_stationary ? '平稳' : '非平稳'}</span>
            `;
        } catch (error) {
            console.error('ADF failed', error);
        }
    };

    predFamily.addEventListener('change', runADF);
    predStore.addEventListener('change', runADF);
    runADF();

    btnStart.addEventListener('click', async () => {
        const models = [];
        if (document.getElementById('model-arima').checked) models.push('ARIMA');
        if (document.getElementById('model-prophet').checked) models.push('Prophet');
        if (document.getElementById('model-lstm').checked) models.push('LSTM');

        if (models.length === 0) {
            showToast('error', '请至少选择一个模型');
            return;
        }

        const config = {
            session_id: sessionId,
            family: predFamily.value,
            store_nbr: parseInt(predStore.value),
            forecast_days: parseInt(forecastDays.value),
            models: models,
            arima_config: {
                criterion: document.querySelector('input[name="arima-criterion"]:checked').value
            },
            prophet_config: {
                changepoint_prior_scale: parseFloat(document.getElementById('prophet-cps').value),
                seasonality_mode: document.querySelector('input[name="prophet-seasonality"]:checked').value,
                use_onpromotion: document.getElementById('prophet-promo').checked
            },
            lstm_config: {
                epochs: parseInt(document.getElementById('lstm-epochs').value),
                seq_len: parseInt(document.getElementById('lstm-seq').value)
            }
        };

        try {
            const data = await apiFetch('/api/predict/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });
            setTaskId(data.task_id);
            showProgressPanel(models);
            startPolling(data.task_id);
        } catch (error) {
            showToast('error', error.message);
        }
    });

    btnCancel.addEventListener('click', async () => {
        const taskId = getTaskId();
        if (!taskId) return;
        try {
            await apiFetch('/api/predict/cancel', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ task_id: taskId })
            });
            stopPolling();
            hideProgressPanel();
            showToast('info', '预测任务已取消');
        } catch (error) {
            showToast('error', error.message);
        }
    });

    function showProgressPanel(models) {
        progressPanel.classList.remove('d-none');
        if (predictionPreview) predictionPreview.classList.add('d-none');
        configPanel.classList.add('opacity-50');
        btnStart.disabled = true;
        
        ['ARIMA', 'Prophet', 'LSTM'].forEach(m => {
            const el = document.getElementById(`status-${m.toLowerCase()}`);
            if (models.includes(m)) {
                el.classList.remove('d-none');
                el.querySelector('.status-icon').textContent = '⏳';
            } else {
                el.classList.add('d-none');
            }
        });
    }

    function hideProgressPanel() {
        progressPanel.classList.add('d-none');
        if (predictionPreview) predictionPreview.classList.remove('d-none');
        configPanel.classList.remove('opacity-50');
        btnStart.disabled = false;
    }

    function startPolling(taskId) {
        pollInterval = setInterval(async () => {
            try {
                const data = await apiFetch(`/api/predict/progress?task_id=${taskId}`);
                updateProgress(data);
                if (data.status === 'done') {
                    stopPolling();
                    showToast('success', '预测完成！正在跳转报告...');
                    setTimeout(() => window.location.href = '/report', 1500);
                } else if (data.status === 'failed') {
                    stopPolling();
                    showToast('error', `预测失败: ${data.error}`);
                    hideProgressPanel();
                }
            } catch (error) {
                stopPolling();
                showToast('error', error.message);
                hideProgressPanel();
            }
        }, 2000);
    }

    function stopPolling() {
        if (pollInterval) clearInterval(pollInterval);
        pollInterval = null;
    }

    function updateProgress(data) {
        taskProgress.style.width = `${data.progress}%`;
        taskProgress.textContent = `${data.progress}%`;
        taskStep.textContent = data.current_step;

        if (data.model_status) {
            Object.keys(data.model_status).forEach(m => {
                const status = data.model_status[m];
                const iconEl = document.querySelector(`#status-${m.toLowerCase()} .status-icon`);
                if (!iconEl) return;
                if (status === 'running') iconEl.textContent = '🔄';
                else if (status === 'done' || status === 'completed') iconEl.textContent = '✅';
                else if (status === 'failed') iconEl.textContent = '❌';
                else iconEl.textContent = '⏳';
            });
        }
    }
});
