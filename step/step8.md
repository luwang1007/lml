# Step 8 — Flask 后端 API（v3）

> **修订说明（v3）**：适配 Favorita 字段（`family`/`store_nbr`/`sales`）；预测接口参数改为 `family`+`store_nbr`；分析接口筛选参数同步更新；上传汇总中 `products` 改为 `families`；其余响应格式、Session管理、TaskManager不变。

## 统一响应格式

所有 API 统一使用以下格式：

```json
// 成功
{
  "code": 200,
  "message": "ok",
  "data": { ... }
}

// 失败
{
  "code": 400,
  "message": "文件格式不支持，请上传 CSV 或 xlsx 文件",
  "data": null
}
```

**Flask 统一错误处理器**：
```python
@app.errorhandler(Exception)
def handle_error(e):
    code = getattr(e, 'code', 500)
    return jsonify({'code': code, 'message': str(e), 'data': None}), code
```

## 页面路由

| 路由 | 说明 |
|------|------|
| `GET /` | 首页（数据上传页）|
| `GET /analysis` | 数据分析页 |
| `GET /prediction` | 预测配置页 |
| `GET /report` | 预测报告页 |

## API 接口（完整参数契约）

---

### 数据管理

#### `POST /api/upload`

| 参数 | 位置 | 必填 | 说明 |
|------|------|------|------|
| `file` | multipart | ✅ | .csv 或 .xlsx，≤ 16 MB |

**成功 Response**：
```json
{
  "code": 200, "message": "ok",
  "data": {
    "session_id": "uuid4字符串",
    "summary": {
      "total_rows": 278520,
      "date_range": {"start": "2013-01-01", "end": "2017-08-15", "days": 1688},
      "families": [{"name": "BEVERAGES", "name_zh": "饮料", "total_sales": 123456.0}],
      "stores": [1, 2, 3, 4, 5],
      "missing_before": 210, "missing_after": 0,
      "outliers_replaced": 18, "outliers_kept": 95,
      "completeness_rate": 1.0,
      "warnings": ["检测到 5 条重复行，已聚合求和"]
    }
  }
}
```

**失败场景**：

| 情况 | code | message |
|------|------|---------|
| 未选文件 | 400 | "请选择要上传的文件" |
| 文件扩展名不支持 | 400 | "不支持 .xls 格式，请另存为 .xlsx 再上传" |
| 文件超过 16 MB | 413 | "文件大小超过限制（16 MB）" |
| 缺少必要列 | 400 | "数据缺少必要列：sales" |
| 编码无法识别 | 400 | "文件编码无法识别，请转存为 UTF-8 格式" |

---

#### `GET /api/data/summary`

| 参数 | 位置 | 必填 | 说明 |
|------|------|------|------|
| `session_id` | query | ✅ | 上传时返回的 session_id |

Session 不存在时：`{"code": 404, "message": "会话已过期，请重新上传数据"}`

---

### 分析 API

所有分析接口均要求 `session_id` query 参数（必填）。

#### `GET /api/analysis/overview`
返回 `DataAnalyzer.get_overview_stats()` 结果。

#### `GET /api/analysis/trend`

| 参数 | 位置 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `session_id` | query | ✅ | — | |
| `granularity` | query | ❌ | `monthly` | `daily`/`weekly`/`monthly` |
| `family` | query | ❌ | `all` | 品类名（英文原始）或 `all` |
| `store_nbr` | query | ❌ | `0` | 门店编号或 `0`（所有门店）|

#### `GET /api/analysis/monthly_comparison`
仅需 `session_id`。

#### `GET /api/analysis/category_pie`
仅需 `session_id`。

#### `GET /api/analysis/top_families`

| 参数 | 位置 | 默认值 |
|------|------|--------|
| `n` | query | 10（范围 1–33）|

#### `GET /api/analysis/correlation`（可选，P1）
仅需 `session_id`。

#### `GET /api/analysis/weekday`（可选，P1）
仅需 `session_id`。

#### `GET /api/analysis/seasonal`（可选，P1）

| 参数 | 默认值 |
|------|--------|
| `family` | `all`（聚合总销量）|
| `store_nbr` | `0`（所有门店）|
| `period` | 7（天）|

#### `GET /api/analysis/promotion`（可选，P1，Favorita 特有）

| 参数 | 默认值 |
|------|--------|
| `family` | `all` |

#### `GET /api/analysis/adf`（仅预测配置页使用）

| 参数 | 必填 | 说明 |
|------|------|------|
| `family` | ✅ | 具体品类名（英文）|
| `store_nbr` | ✅ | 具体门店编号 |

返回 ADF 检验结果：
```json
{
  "code": 200, "message": "ok",
  "data": {
    "adf_statistic": -4.23,
    "p_value": 0.0008,
    "is_stationary": true,
    "conclusion": "序列平稳（p=0.0008 < 0.05），ARIMA 建议 d=0",
    "suggested_d": 0
  }
}
```

---

### 预测 API

#### `POST /api/predict/start`

**Request Body（JSON）**：

| 字段 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `session_id` | ✅ | — | |
| `family` | ✅ | — | 具体品类名（英文原始，如 "BEVERAGES"）|
| `store_nbr` | ✅ | — | 具体门店编号（整数，1–5）|
| `forecast_days` | ❌ | 30 | 范围 7–90 |
| `models` | ❌ | `["ARIMA","Prophet"]` | 可选模型列表 |
| `arima_config` | ❌ | `{}` | 覆盖默认 ARIMA 参数 |
| `prophet_config` | ❌ | `{}` | 覆盖默认 Prophet 参数；`use_onpromotion` 可在此设置为 `true` |
| `lstm_config` | ❌ | `{}` | 覆盖默认 LSTM 参数 |

> **`use_onpromotion` 说明**：若设为 `true`，Prophet 将 `onpromotion` 列作为外部回归量。未来预测期（`forecast_days` 天）的促销量**默认置 0**（保守无促销假设）。前端无需上传未来促销数据，后端自动填充。

**Response**：
```json
{"code": 200, "message": "ok", "data": {"task_id": "uuid4"}}
```

**失败场景**：

| 情况 | code | message |
|------|------|---------|
| models 为空列表 | 400 | "至少选择一个预测模型" |
| models 含非法值 | 400 | "不支持的模型：XXX" |
| forecast_days 超范围 | 400 | "预测天数需在 7–90 之间" |
| session_id 不存在 | 404 | "会话已过期，请重新上传数据" |
| family 不在数据集中 | 400 | "品类不存在：XXX，请重新选择" |
| store_nbr 不在数据集中 | 400 | "门店不存在：XXX，请重新选择" |
| LSTM 选中但未启用 | 400 | "LSTM 模块未启用，请在 config.py 设置 LSTM_ENABLED=True" |

#### `GET /api/predict/progress`

| 参数 | 必填 |
|------|------|
| `task_id` | ✅ |

```json
{
  "code": 200, "message": "ok",
  "data": {
    "task_id": "xxx",
    "status": "running",
    "progress": 45,
    "current_step": "训练 Prophet 模型...",
    "model_status": {
      "ARIMA":   "done",
      "Prophet": "running",
      "LSTM":    "pending"
    },
    "error": null
  }
}
```

**进度分配**：

| 阶段 | 进度 |
|------|------|
| 数据准备 | 0% → 5% |
| 每个模型（均分剩余 85%）| 5% → 90% |
| 评估与汇总 | 90% → 100% |

#### `GET /api/predict/result`

status 非 done 时：`{"code": 400, "message": "任务尚未完成"}`

**成功 Response 结构**：
```json
{
  "code": 200, "message": "ok",
  "data": {
    "family": "BEVERAGES", "family_zh": "饮料",
    "store_nbr": 1,
    "forecast_days": 30,
    "models": {
      "ARIMA": {
        "forecast": [...], "lower_ci": [...], "upper_ci": [...], "dates": [...],
        "order": [1,1,1], "aic": 1234.5,
        "fitted_vs_actual": {"dates": [...], "actual": [...], "fitted": [...]}
      },
      "Prophet": {
        "forecast": [...], "lower_ci": [...], "upper_ci": [...], "dates": [...],
        "components": {"trend": [...], "weekly": [...], "yearly": [...], "holidays": [...]},
        "changepoints": {"dates": [...], "deltas": [...]}
      },
      "LSTM": {
        "forecast": [...], "dates": [...],
        "training_history": {"epochs": [...], "train_loss": [...], "val_loss": [...]},
        "model_params": {"seq_len": 30, "hidden_size": 64, "best_epoch": 38}
      }
    },
    "evaluation": {
      "metrics_table": [...],
      "best_model": "Prophet",
      "best_reason": "综合评分最高（MAPE: 8.3%）",
      "bar_chart": {...},
      "radar_chart": {...},
      "prediction_chart": {...}
    }
  }
}
```

#### `POST /api/predict/cancel`

| 参数 | 必填 |
|------|------|
| `task_id` | ✅（JSON Body）|

---

### 导出 API

#### `GET /api/export/forecast`

| 参数 | 必填 | 默认值 |
|------|------|--------|
| `task_id` | ✅ | — |
| `format` | ❌ | `csv` |

Response：Content-Disposition: attachment; filename="forecast_{family}_{store_nbr}_{date}.csv"

---

## Session 管理（落盘方案）

```python
# Flask Session
session['meta_path'] = '/abs/path/meta_{session_id}.json'

# 获取数据时
meta_path = session.get('meta_path')
if not meta_path or not os.path.exists(meta_path):
    return jsonify({'code': 404, 'message': '会话已过期，请重新上传数据'})
df = DataProcessor.load_processed(meta_path)
```

## `TaskManager`

```python
class TaskManager:
    _lock = threading.Lock()
    _tasks: dict = {}

    @classmethod
    def create(cls) -> str: ...

    @classmethod
    def update(cls, task_id, progress, step, model_status): ...

    @classmethod
    def complete(cls, task_id, result): ...

    @classmethod
    def fail(cls, task_id, error): ...

    @classmethod
    def cancel(cls, task_id): ...

    @classmethod
    def get(cls, task_id) -> dict: ...
```

## 验收标准

- [ ] `POST /api/upload` 成功返回 `session_id`，meta JSON 文件落盘
- [ ] `POST /api/upload` 对 .xls 返回 400 + 明确错误信息
- [ ] `GET /api/analysis/overview` 不存在 session 返回 404
- [ ] `GET /api/analysis/adf?family=BEVERAGES&store_nbr=1` 返回 ADF 结果 + `suggested_d`
- [ ] `POST /api/predict/start`（family="INVALID"）返回 400
- [ ] `POST /api/predict/start` models=[] 返回 400
- [ ] `GET /api/predict/progress` status 正常流转（pending→running→done）
- [ ] `POST /api/predict/cancel` 标记 cancelled，后台线程在 1 个 epoch 内停止
- [ ] 所有 API response 均通过 `json.loads()` 无异常（无 NaN）
- [ ] 并发两个 session 上传，互不干扰
