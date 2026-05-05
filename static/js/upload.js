document.addEventListener('DOMContentLoaded', () => {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const btnSelectFile = document.getElementById('btn-select-file');
    const btnUpload = document.getElementById('btn-upload');
    const btnLoadDemo = document.getElementById('btn-load-demo');
    const selectedFilename = document.getElementById('selected-filename');
    const progressContainer = document.getElementById('upload-progress-container');
    const progressBar = document.getElementById('upload-progress');
    const summarySection = document.getElementById('summary-section');

    let currentFile = null;
    let progressTimer = null;
    let currentProgress = 0;

    btnSelectFile.addEventListener('click', () => fileInput.click());

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileSelect(e.target.files[0]);
        }
    });

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            handleFileSelect(e.dataTransfer.files[0]);
        }
    });

    btnUpload.addEventListener('click', () => {
        if (currentFile) {
            uploadFile(currentFile);
        }
    });

    btnLoadDemo.addEventListener('click', loadDemoData);

    function handleFileSelect(file) {
        const ext = file.name.split('.').pop().toLowerCase();
        if (!['csv', 'xlsx'].includes(ext)) {
            showToast('error', '仅支持 .csv 或 .xlsx 文件');
            return;
        }
        if (file.size > 16 * 1024 * 1024) {
            showToast('error', '文件大小不能超过 16MB');
            return;
        }
        currentFile = file;
        selectedFilename.textContent = file.name;
        btnUpload.disabled = false;
    }

    function resetProgress() {
        stopLiveProgress();
        currentProgress = 0;
        setProgress(0, '准备中...');
        progressBar.classList.add('is-live');
        progressBar.classList.add('progress-bar-animated');
        progressBar.classList.remove('bg-success', 'bg-danger');
    }

    function setProgress(value, text) {
        currentProgress = Math.max(0, Math.min(100, Math.round(value)));
        progressBar.style.width = `${currentProgress}%`;
        progressBar.setAttribute('aria-valuenow', String(currentProgress));
        progressBar.dataset.progressLabel = text || `${currentProgress}%`;
        progressBar.textContent = '';
    }

    function startLiveProgress(label, ceiling = 88) {
        stopLiveProgress();
        setProgress(Math.max(currentProgress, 8), `${label} ${Math.max(currentProgress, 8)}%`);
        progressTimer = setInterval(() => {
            if (currentProgress >= ceiling) return;
            const remaining = ceiling - currentProgress;
            const step = Math.max(1, Math.ceil(remaining * 0.12));
            setProgress(currentProgress + step, `${label} ${Math.min(ceiling, currentProgress + step)}%`);
        }, 280);
    }

    function stopLiveProgress() {
        if (progressTimer) clearInterval(progressTimer);
        progressTimer = null;
    }

    function markProgressSuccess(text) {
        stopLiveProgress();
        setProgress(100, text);
        progressBar.classList.remove('is-live');
        progressBar.classList.remove('progress-bar-animated');
        progressBar.classList.add('bg-success');
    }

    function markProgressFailure(text) {
        stopLiveProgress();
        setProgress(100, text);
        progressBar.classList.remove('is-live');
        progressBar.classList.remove('progress-bar-animated');
        progressBar.classList.add('bg-danger');
    }

    async function uploadFile(file) {
        const formData = new FormData();
        formData.append('file', file);

        resetProgress();
        btnUpload.disabled = true;
        progressContainer.classList.remove('d-none');
        startLiveProgress('上传中', 86);

        try {
            const data = await apiFetch('/api/upload', {
                method: 'POST',
                body: formData
            });
            
            markProgressSuccess('上传成功');
            setSessionId(data.session_id);
            renderSummary(data.summary);
            showToast('success', '数据上传成功');
        } catch (error) {
            markProgressFailure('上传失败');
            showToast('error', error.message);
            btnUpload.disabled = false;
        }
    }

    async function loadDemoData() {
        resetProgress();
        btnLoadDemo.disabled = true;
        progressContainer.classList.remove('d-none');
        startLiveProgress('加载演示数据', 92);

        try {
            const data = await apiFetch('/api/demo/load', { method: 'POST' });
            markProgressSuccess('演示数据加载成功');
            setSessionId(data.session_id);
            renderSummary(data.summary);
            showToast('success', '演示数据已加载，可进入分析或预测');
        } catch (error) {
            markProgressFailure('演示数据加载失败');
            showToast('error', error.message);
        } finally {
            btnLoadDemo.disabled = false;
        }
    }

    function renderSummary(summary) {
        document.getElementById('summary-total-rows').textContent = summary.total_rows.toLocaleString();
        const range = summary.date_range || {};
        document.getElementById('summary-date-range').textContent = range.start && range.end
            ? `${range.start} 至 ${range.end}`
            : '-';
        document.getElementById('summary-family-count').textContent = summary.family_count;
        document.getElementById('summary-store-count').textContent = summary.store_count;

        const warningsContainer = document.getElementById('warnings-container');
        const warningsList = document.getElementById('warnings-list');
        
        if (summary.warnings && summary.warnings.length > 0) {
            warningsList.innerHTML = '';
            summary.warnings.forEach(w => {
                const li = document.createElement('li');
                li.textContent = w;
                warningsList.appendChild(li);
            });
            warningsContainer.classList.remove('d-none');
        } else {
            warningsContainer.classList.add('d-none');
        }

        summarySection.classList.remove('d-none');
        document.querySelector('.momentum-page')?.classList.add('has-import-summary');
        summarySection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
});
