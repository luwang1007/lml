# Step 10 — 系统集成测试与部署（v3）

> **修订说明（v3）**：适配 Favorita 字段（`family`/`store_nbr`/`sales`/`onpromotion`）；测试数据文件更新为 Favorita 格式；预测接口参数 `product_id`→`family`，`store_id`→`store_nbr`；验收标准中行数由 32,880 改为约 278,520；新增 holidays_events.csv 加载测试和降级测试；明确 prepare_data.py 为测试前置条件。

## 目标
验证系统端到端完整功能，重点保障主链路（上传→分析→预测→报告）的鲁棒性。

## 测试文件结构

```
tests/
├── conftest.py               # pytest fixtures（app client, 测试数据等）
├── test_data_processor.py    # 数据处理单元测试
├── test_models.py            # 模型单元测试
├── test_api.py               # API 集成测试
└── test_data/
    ├── valid_utf8.csv        # 正常 Favorita 格式（UTF-8）
    ├── valid_gbk.csv         # GBK 编码
    ├── valid_xlsx.xlsx       # xlsx 格式
    ├── missing_column.csv    # 缺少 sales 列
    ├── negative_values.csv   # 含负数销售量
    ├── duplicate_rows.csv    # 含重复行
    ├── short_series.csv      # 仅 60 天数据
    ├── all_zeros.csv         # 销售量全为 0
    └── invalid.xls           # 不支持的 xls 格式
```

**测试数据格式**（所有 CSV 均使用 Favorita 字段）：
```
date,store_nbr,family,sales,onpromotion
2013-01-01,1,BEVERAGES,520.0,0
2013-01-01,1,PRODUCE,1200.5,12
...
```

---

## test_data_processor.py — 数据处理单元测试

### Happy Path

| 测试名 | 输入 | 断言 |
|--------|------|------|
| `test_load_utf8_csv` | valid_utf8.csv | 正常加载，字段含 date/store_nbr/family/sales |
| `test_load_gbk_csv` | valid_gbk.csv | 正常加载，中文不乱码 |
| `test_load_xlsx` | valid_xlsx.xlsx | 正常加载 |
| `test_clean_no_missing` | 清洗后 | `isnull().sum().sum() == 0` |
| `test_clean_no_negative` | 清洗后 | `(df['sales'] < 0).sum() == 0` |
| `test_feature_cols_count` | feature_engineering 后 | 新增列数 ≥ 12 |
| `test_split_order` | split_timeseries | `train.index.max() < val.index.min() < test.index.min()` |
| `test_normalize_no_leakage` | normalize | `scaler.data_min_ == train.values.min()` |
| `test_save_load_roundtrip` | save/load | 加载后 DataFrame 与原始一致 |
| `test_holidays_loaded` | clean() | `is_event=True` 的行存在（holidays_events.csv 能加载）|

### 边界与异常

| 测试名 | 输入 | 断言 |
|--------|------|------|
| `test_load_xls_rejected` | invalid.xls | 抛出 ValueError，message 含 ".xlsx" 字样 |
| `test_validate_missing_required_col` | missing_column.csv | `valid=False`，errors 含 "sales" |
| `test_validate_date_unparseable` | date 列全为 "abc" | `valid=False`，errors 含 "date" |
| `test_clean_negative_values` | negative_values.csv | 清洗后无负值（sales 和 onpromotion 均≥0）|
| `test_clean_duplicate_rows` | duplicate_rows.csv | 重复行被聚合，行数减少 |
| `test_holiday_not_replaced` | 含厄瓜多尔节假日高峰的数据 | is_event=True 的行，sales 值不变 |
| `test_interpolation_per_group` | 跨品类数据 | 每个 (family, store_nbr) 组内插值不污染其他组 |
| `test_short_series_warning` | short_series.csv（60天）| validate 返回 warnings 含"数据量不足" |
| `test_all_zeros_series` | all_zeros.csv | clean() 不崩溃，填充后全为 0 |
| `test_onpromotion_non_negative` | 含负数 onpromotion | 清洗后 `(df['onpromotion'] < 0).sum() == 0` |
| `test_onpromotion_column_missing` | CSV 不含 onpromotion 列 | clean() 正常运行，不报错 |
| `test_holidays_file_missing_degrades` | 删除 holidays_events.csv | clean() 和 Prophet fit() 均不崩溃，is_event 列全 False |

---

## test_models.py — 模型单元测试

### ARIMA

| 测试名 | 断言 |
|--------|------|
| `test_arima_stationary_d0` | 白噪声序列 → `d=0` |
| `test_arima_random_walk_d1` | 随机游走序列 → `d=1` |
| `test_arima_all_fail_fallback` | 空序列/常数序列 → fallback `(1,1,1)`，不崩溃 |
| `test_arima_predict_length` | `predict(30)` → len==30 |
| `test_arima_predict_non_negative` | 所有预测值 ≥ 0 |
| `test_arima_save_load_roundtrip` | 预测结果误差 < 1e-4 |
| `test_arima_order_cache` | 同序列第二次调用不重新搜索（计时）|

### Prophet

| 测试名 | 断言 |
|--------|------|
| `test_prophet_load_holidays` | `_load_holidays()` 返回非空 DataFrame，含 ds/holiday 列 |
| `test_prophet_holidays_no_transferred` | transferred=True 的行被过滤 |
| `test_prophet_holidays_file_missing` | holidays_events.csv 不存在时返回 None，`fit()` **不崩溃正常运行** |
| `test_prophet_disabled_raises` | PROPHET_ENABLED=False 时 `fit()` 抛 ImportError |
| `test_prophet_predict_length` | `predict(30)` → len==30 |
| `test_prophet_predict_non_negative` | 所有预测值 ≥ 0 |
| `test_prophet_components_present` | components 含 trend/weekly/yearly |
| `test_prophet_save_load_roundtrip` | 往返一致 |

### LSTM

| 测试名 | 断言 |
|--------|------|
| `test_lstm_sequence_shape` | `_create_sequences(100, 30)` → X.shape==(70,30,1) |
| `test_lstm_forward_shape` | 输入(8,30,1) → 输出(8,1) |
| `test_lstm_fit_loss_trend` | train_loss 前10轮均值 > 后10轮均值 |
| `test_lstm_predict_non_negative` | 所有预测值 ≥ 0 |
| `test_lstm_no_confidence_interval` | predict 返回中无 lower_ci / upper_ci |
| `test_lstm_disabled_skipped` | LSTM_ENABLED=False 时预测任务不包含 LSTM |
| `test_lstm_short_series` | 序列长度 < seq_len 时抛出有意义的错误 |

### 评估器

| 测试名 | 断言 |
|--------|------|
| `test_mae_basic` | `mae([3,4,5],[2,4,6])` == 1.0 |
| `test_mape_zero_actual` | actual=0 时不报 ZeroDivisionError |
| `test_compare_models_ranks` | ranks 为 [1,2]，无重复 |
| `test_compare_single_model` | 单模型时 rank=1，���常返回 |
| `test_radar_values_range` | 雷达图值全在 [0,1] |
| `test_json_serializable` | `json.dumps(compare_models(...))` 无异常 |

---

## test_api.py — API 集成测试

### 完整主链路测试

```python
def test_full_pipeline(client):
    """上传 → 分析 → 预测(仅ARIMA) → 导出"""
    
    # 1. 上传 Favorita 格式数据
    with open('tests/test_data/valid_utf8.csv', 'rb') as f:
        resp = client.post('/api/upload',
                           data={'file': (f, 'test.csv')},
                           content_type='multipart/form-data')
    assert resp.json['code'] == 200
    session_id = resp.json['data']['session_id']
    assert resp.json['data']['summary']['family_count'] > 0
    
    # 2. 分析
    resp = client.get(f'/api/analysis/overview?session_id={session_id}')
    assert resp.json['code'] == 200
    assert resp.json['data']['total_sales'] > 0
    
    # 3. 预测（ARIMA，BEVERAGES 品类，门店1，7天加速测试）
    resp = client.post('/api/predict/start', json={
        'session_id': session_id,
        'family': 'BEVERAGES',
        'store_nbr': 1,
        'models': ['ARIMA'],
        'forecast_days': 7
    })
    assert resp.json['code'] == 200
    task_id = resp.json['data']['task_id']
    
    # 4. 等待完成（最多 120 秒）
    import time
    for _ in range(60):
        time.sleep(2)
        status = client.get(f'/api/predict/progress?task_id={task_id}').json['data']
        if status['status'] == 'done': break
    assert status['status'] == 'done', f"预测超时，最终状态：{status['status']}"
    
    # 5. 结果验证
    result = client.get(f'/api/predict/result?task_id={task_id}').json['data']
    assert result['family'] == 'BEVERAGES'
    assert result['store_nbr'] == 1
    assert 'ARIMA' in result['models']
    assert len(result['models']['ARIMA']['forecast']) == 7
    assert all(v >= 0 for v in result['models']['ARIMA']['forecast'])
    
    # 6. 导出
    resp = client.get(f'/api/export/forecast?task_id={task_id}&format=csv')
    assert resp.status_code == 200
    assert 'attachment' in resp.headers.get('Content-Disposition', '')
```

### API 边界测试

| 测试名 | 请求 | 断言 |
|--------|------|------|
| `test_upload_no_file` | POST /api/upload（无文件）| code==400 |
| `test_upload_xls` | 上传 .xls 文件 | code==400，message 含 ".xlsx" |
| `test_upload_too_large` | 超过 16MB 的文件 | code==413 |
| `test_analysis_expired_session` | GET /api/analysis/overview?session_id=invalid | code==404 |
| `test_predict_empty_models` | models=[] | code==400 |
| `test_predict_invalid_model` | models=["XGBoost"] | code==400 |
| `test_predict_invalid_days` | forecast_days=100 | code==400 |
| `test_predict_invalid_family` | family="INVALID_FAMILY" | code==400 |
| `test_predict_invalid_store` | store_nbr=99 | code==400 |
| `test_predict_progress_not_found` | task_id=invalid | code==404 |
| `test_predict_result_not_done` | 任务 running 时请求 result | code==400 |
| `test_predict_cancel` | 启动后立即取消 | status 变为 cancelled |
| `test_two_sessions_isolated` | 两个 session 并发上传 | 互不干扰 |
| `test_json_no_nan` | 任意分析/预测 API | `json.loads(resp.data)` 无异常 |

### 性能测试

```python
def test_analysis_performance(client, valid_session_id):
    """分析页所有接口总耗时 < 10 秒"""
    import time
    t = time.time()
    for endpoint in ['overview','trend','monthly_comparison','category_pie','top_families']:
        client.get(f'/api/analysis/{endpoint}?session_id={valid_session_id}')
    assert time.time() - t < 10, "分析接口响应过慢"
```

---

## README.md 关键内容

```markdown
## 数据集说明

本项目使用 Kaggle Favorita Store Sales 竞赛数据（子集）。

下载方式：
  kaggle competitions download -c store-sales-time-series-forecasting
  unzip store-sales-time-series-forecasting.zip -d data/raw/
  python prepare_data.py    # 裁剪为5家门店子集

## 安装

python -m venv venv
source venv/bin/activate  # Linux/Mac

pip install -r requirements.txt

# Prophet 单独安装（耗时较长）
pip install pystan==3.9.1
pip install prophet==1.1.5
# 若失败：在 config.py 设置 PROPHET_ENABLED = False

# 下载离线静态文件（答辩必备）
python download_vendor.py

## 启动

python app.py
# 访问 http://localhost:5000

## 常见问题

| 问题 | 解决 |
|------|------|
| Prophet 安装失败 | 先装 pystan==3.9.1，或设 PROPHET_ENABLED=False |
| 前端白屏 | 运行 python download_vendor.py 获取离线资源 |
| 上传 xlsx 报错 | pip install openpyxl |
| LSTM 训练很慢 | 在 config.py 设置 LSTM_EPOCHS=20 |
| 找不到 train_subset.csv | 先下载 Kaggle 数据，再运行 prepare_data.py |
```

---

## 验收标准（系统级）

**前置条件（测试前必须完成）**：
1. `python prepare_data.py` 已执行，`data/raw/train_subset.csv` 存在（约278,520行，字段含 date/store_nbr/family/sales/onpromotion）
2. `data/raw/holidays_events.csv` 和 `data/raw/stores.csv` 已放置
3. 测试数据 `tests/test_data/valid_utf8.csv` 等已准备（Favorita格式）

- [ ] `python prepare_data.py` 生成约 278,520 行 `train_subset.csv`
- [ ] `python app.py` 在 5000 端口正常启动
- [ ] 主链路测试 `test_full_pipeline` 通过（BEVERAGES 品类 + 门店1 + ARIMA）
- [ ] 所有边界测试通过
- [ ] `pytest tests/ -v` 无 FAILED
- [ ] 分析接口总耗时 < 10 秒
- [ ] 任意 API 响应均通过 `json.loads()` 无 NaN 异常
- [ ] 断网环境（仅 static/vendor/ 资源）前端正常渲染
- [ ] 前端品类下拉显示中文名（如"饮料"），预测报告标题含品类中文名+门店编号
