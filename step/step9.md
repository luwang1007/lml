# Step 9 — 前端页面与 ECharts 可视化（v3）

> **修订说明（v3）**：适配 Favorita 字段（`family`/`store_nbr`/`sales`）；筛选器由「商品/门店」改为「品类/门店」；数量显示由「金额+数量」改为纯「销售量」；新增促销效果图（P1）；预测配置页下拉由 P001–P010 改为 33 个品类英文名+中文名映射显示。

## 技术栈（优先使用离线资源）

```html
<!-- 优先加载 static/vendor/ 本地文件，CDN 为备用 -->
<script src="/static/vendor/echarts.min.js"></script>
<link  href="/static/vendor/bootstrap.min.css" rel="stylesheet">
<script src="/static/vendor/bootstrap.bundle.min.js"></script>
```

## 统一 JS 工具函数（所有页面共享）

```javascript
// common.js（在 base.html 中引入）

async function apiFetch(url, options = {}) {
  try {
    const resp = await fetch(url, options);
    const json = await resp.json();
    if (json.code !== 200) throw new Error(json.message);
    return json.data;
  } catch (e) {
    showToast('error', e.message);
    throw e;
  }
}

function showToast(type, message) { ... }
function showLoading(text) { ... }
function hideLoading() { ... }

const chartRegistry = [];
function registerChart(dom) {
  const chart = echarts.init(dom);
  chartRegistry.push(chart);
  return chart;
}
window.addEventListener('resize', () => chartRegistry.forEach(c => c.resize()));

function getSessionId() { return sessionStorage.getItem('session_id'); }
function setSessionId(id) { sessionStorage.setItem('session_id', id); }
function getTaskId() { return sessionStorage.getItem('task_id'); }
function setTaskId(id) { sessionStorage.setItem('task_id', id); }
```

---

## index.html — 首页/数据上传

**布局**：

```
[顶部 Banner]
  标题：商贸销售数据分析与智能预测系统
  副标题：基于 Favorita 真实零售数据 · ARIMA · Prophet · LSTM 多模型对比预测

[数据上传区]
  拖拽框（虚线边框）
  支持格式：.csv / .xlsx（≤16MB）
  [选择文件] [上传] 按钮

[上传进度条]（上传中显示）

[数据概况卡片]（上传成功后显示）
  ┌────────┬────────┬────────┬────────┐
  │ 总记录数│ 时间跨度│ 品类数量│ 门店数量│
  └────────┴────────┴────────┴────────┘
  警告信息列��（黄色 alert）
  [前往数据分析 →]
```

**upload.js 核心逻辑**：

```javascript
async function uploadFile(file) {
  const ext = file.name.split('.').pop().toLowerCase();
  if (!['csv','xlsx'].includes(ext)) {
    showToast('error', '只支持 .csv 和 .xlsx 格式');
    return;
  }
  if (file.size > 16 * 1024 * 1024) {
    showToast('error', '文件大小超过 16 MB');
    return;
  }
  
  showLoading('正在解析数据，请稍候...');
  const formData = new FormData();
  formData.append('file', file);
  
  const data = await apiFetch('/api/upload', {method:'POST', body: formData});
  hideLoading();
  
  setSessionId(data.session_id);
  renderSummary(data.summary);   // 展示 families/stores/总记录数/日期范围
  document.getElementById('goto-analysis').style.display = 'block';
}
```

---

## analysis.html — 数据分析页

**布局**：

```
[筛选栏]
  时间粒度：[日/周/月 切换按钮组]
  品类筛选：[下拉 全部/饮料/生鲜/...]    ← 显示中文名，value 为英文原始名
  门店筛选：[下拉 全部/��店1/门店2/...]
  [刷新图表] 按钮

行1：[KPI 卡片 ×4]（总销售量 / 日均销售量 / 同比增长率 / 最佳品类）

行2：[销售量趋势折线图（P0-1，全宽）]

行3：[月度同比柱状图（P0-2）] | [品类占比环形图（P0-3）]

行4：[TOP 10 品类排行横条图（P0-4，全宽）]

--- 可选区域（P1）---
行5：[品类相关性热力图]
行6：[星期效应柱状图] | [促销效果分析]
```

**analysis.js 核心逻辑**：

```javascript
async function initAnalysis() {
  const sid = getSessionId();
  if (!sid) { location.href = '/'; return; }
  
  showLoading('加载分析数据...');
  
  // 并行请求 P0 图表
  const [overview, trend, monthly, pie, top] = await Promise.all([
    apiFetch(`/api/analysis/overview?session_id=${sid}`),
    apiFetch(`/api/analysis/trend?session_id=${sid}&granularity=monthly`),
    apiFetch(`/api/analysis/monthly_comparison?session_id=${sid}`),
    apiFetch(`/api/analysis/category_pie?session_id=${sid}`),
    apiFetch(`/api/analysis/top_families?session_id=${sid}&n=10`),
  ]);
  
  hideLoading();
  renderKPICards(overview);
  renderTrendChart(trend);
  renderMonthlyComparison(monthly);
  renderCategoryPie(pie);
  renderTopFamilies(top);
}

async function refreshTrend() {
  const granularity = document.querySelector('[data-granularity].active').dataset.granularity;
  const family   = document.getElementById('family-select').value;
  const storeNbr = document.getElementById('store-select').value;
  const sid = getSessionId();
  
  const data = await apiFetch(
    `/api/analysis/trend?session_id=${sid}&granularity=${granularity}&family=${encodeURIComponent(family)}&store_nbr=${storeNbr}`
  );
  renderTrendChart(data);
}
```

---

## prediction.html — 预测配置页

**左侧配置**：

```
[预测对象]
  品类：[下拉] 饮料 / 生鲜 / 肉类 / ...（显示中文名，value 为英文原始名）
  门店：[下拉] 门店1 / 门店2 / ... / 门店5

[ADF 检验结果]（选品类+门店后自动触发）
  📊 序列平稳性：平稳（p=0.0008）
  💡 建议 ARIMA d 值：0

[预测设置]
  预测天数：30天 [滑块 7–90]
  选择模型：☑ ARIMA  ☑ Prophet  ☐ LSTM（默认不勾选）

[ARIMA 参数]（可折叠）
  评判准则：● AIC  ○ BIC

[Prophet 参数]（可折叠）
  趋势灵活度：0.05 [滑块]
  季节性模式：● 乘法  ○ 加法
  使用促销特征：☐ onpromotion（Favorita 特有，勾选则将促销量作为回归量）

[LSTM 参数]（可折叠，LSTM 勾选后展示）
  训练��数：50 [���块]
  时间步长：30 [滑块]

[开始预测 ▶] 按钮
```

**prediction.js 核心逻辑**：

```javascript
// 品类或门店选择变化时自动触发 ADF 检验
async function triggerADF() {
  const family   = document.getElementById('family-select').value;
  const storeNbr = document.getElementById('store-select').value;
  if (!family || !storeNbr) return;
  
  const data = await apiFetch(
    `/api/analysis/adf?session_id=${getSessionId()}&family=${encodeURIComponent(family)}&store_nbr=${storeNbr}`
  );
  renderADFResult(data);
}
document.getElementById('family-select').addEventListener('change', triggerADF);
document.getElementById('store-select').addEventListener('change', triggerADF);

// 开始预测
async function startPrediction() {
  const config = {
    session_id:    getSessionId(),
    family:        document.getElementById('family-select').value,
    store_nbr:     parseInt(document.getElementById('store-select').value),
    forecast_days: parseInt(document.getElementById('forecast-days').value),
    models:        getSelectedModels(),
    arima_config:  getARIMAConfig(),
    prophet_config: getProphetConfig(),
    lstm_config:    getLSTMConfig(),
  };
  
  const data = await apiFetch('/api/predict/start', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(config)
  });
  
  setTaskId(data.task_id);
  showProgressPanel();
  pollProgress(data.task_id);
}

// 2 秒轮询
function pollProgress(taskId) {
  const interval = setInterval(async () => {
    const data = await apiFetch(`/api/predict/progress?task_id=${taskId}`);
    updateProgressUI(data);
    
    if (data.status === 'done') {
      clearInterval(interval);
      location.href = '/report';
    }
    if (data.status === 'failed') {
      clearInterval(interval);
      showToast('error', '预测失败：' + data.error);
      showConfigPanel();
    }
  }, 2000);
  
  document.getElementById('cancel-btn').onclick = async () => {
    await apiFetch('/api/predict/cancel', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({task_id: taskId})
    });
    clearInterval(interval);
    showConfigPanel();
  };
}
```

---

## report.html — 预测报告页（3 个 Tab）

**Tab 1：预测结果对比**
- 未来 N 天三模型预测折线图（标题展示品类中文名+门店编号）
- ARIMA/Prophet 显示置信区间阴影（ECharts areaStyle）
- LSTM 仅显示折线（无置信区间）

**Tab 2：模型性能评估**
- 误差指标表格（MAE / RMSE / MAPE / SMAPE）
- 误差柱状对比图
- 雷达图（≥2个模型时显示）

**Tab 3：详细分析**
- Prophet 趋势+季节性分量折线图（若 Prophet 选中）
- LSTM 训练 Loss 曲线（若 LSTM 选中）
- 最优模型推荐文字报告

**底部操作栏**：
```
[📥 导出预测数据（CSV）]  [📥 导出 Excel]  [🔄 重新预测]
```

**report.js 核心逻辑**（家族/门店信息用于图表标题）：

```javascript
async function initReport() {
  const taskId = getTaskId();
  if (!taskId) { location.href = '/prediction'; return; }
  
  showLoading('加载���测报告...');
  const data = await apiFetch(`/api/predict/result?task_id=${taskId}`);
  hideLoading();
  
  // 标题展示品类中文名+门店
  const title = `${data.family_zh}（门店${data.store_nbr}）未来${data.forecast_days}天预测`;
  document.getElementById('report-title').textContent = title;
  
  renderForecastChart(data.models, data.evaluation);
  renderMetricsTable(data.evaluation.metrics_table);
  renderBarChart(data.evaluation.bar_chart);
  if (Object.keys(data.models).length >= 2) {
    renderRadarChart(data.evaluation.radar_chart);
  }
  if (data.models.Prophet) {
    renderComponentsChart(data.models.Prophet.components);
  }
  if (data.models.LSTM) {
    renderTrainingHistory(data.models.LSTM.training_history);
  }
  renderRecommendation(data.evaluation);
}
```

---

## style.css 关键样式

```css
.drop-zone {
  border: 2px dashed #0d6efd;
  border-radius: 12px;
  min-height: 160px;
  cursor: pointer;
  transition: background 0.2s;
}
.drop-zone.dragover { background: #e8f0fe; }

.kpi-card { border-left: 4px solid #0d6efd; border-radius: 6px; }
.kpi-value { font-size: 1.8rem; font-weight: 700; color: #0d6efd; }

.chart-container    { width: 100%; height: 380px; }
.chart-container-lg { width: 100%; height: 460px; }

#global-loading {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.4);
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  z-index: 9999;
}

.model-status-done    { color: #198754; }
.model-status-running { color: #0d6efd; animation: spin 1s linear infinite; }
.model-status-pending { color: #6c757d; }
```

## 验收标准

- [ ] 访问 `/`，拖拽区可见，上传 `train_subset.csv` 后显示数据概况（33个品类，5家门店）
- [ ] `session_id` 存入 `sessionStorage`，刷新后 `/analysis` 仍可正常加载
- [ ] 访问 `/analysis`，4 张主线图表全部渲染（无空白）
- [ ] 品类筛选下拉显示中文名（如"饮料"），请求时传英文原始名（"BEVERAGES"）
- [ ] 趋势图粒度切换（日/周/月）正常刷新
- [ ] 访问 `/prediction`，选择品类+门店后 ADF 检验结果自动显示
- [ ] 点击"开始预测"，进度面板显示，2 秒轮询更新
- [ ] 预测完成后自动跳转 `/report`，报告标题含品类中文名+门店编号
- [ ] 3 个 Tab 均正常渲染
- [ ] 导出 CSV 触发下载，文件名含品类���门店信息
- [ ] F12 控制台无 JavaScript 报错
- [ ] 断网环境下（使用 static/vendor/），页面正常显示
