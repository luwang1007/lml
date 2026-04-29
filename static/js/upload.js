document.addEventListener('DOMContentLoaded', () => {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const btnSelectFile = document.getElementById('btn-select-file');
    const btnUpload = document.getElementById('btn-upload');
    const selectedFilename = document.getElementById('selected-filename');
    const progressContainer = document.getElementById('upload-progress-container');
    const progressBar = document.getElementById('upload-progress');
    const summarySection = document.getElementById('summary-section');

    let currentFile = null;

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

    async function uploadFile(file) {
        const formData = new FormData();
        formData.append('file', file);

        btnUpload.disabled = true;
        progressContainer.classList.remove('d-none');
        progressBar.style.width = '50%';
        progressBar.textContent = '上传中...';

        try {
            const data = await apiFetch('/api/upload', {
                method: 'POST',
                body: formData
            });
            
            progressBar.style.width = '100%';
            progressBar.textContent = '上传成功';
            progressBar.classList.remove('progress-bar-animated');
            progressBar.classList.add('bg-success');
            
            setSessionId(data.session_id);
            renderSummary(data.summary);
            showToast('success', '数据上传成功');
        } catch (error) {
            progressBar.style.width = '100%';
            progressBar.textContent = '上传失败';
            progressBar.classList.remove('progress-bar-animated');
            progressBar.classList.add('bg-danger');
            showToast('error', error.message);
            btnUpload.disabled = false;
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
    }
});
