# Step 2 — 数据层：数据清洗与预处理（v3）

> **修订说明（v3）**：适配 Favorita 数据集字段（`store_nbr`/`family`/`sales`/`onpromotion`），去除原 `unit_price`/`sales_amount` 相关逻辑；节假日事件日历改为从 `holidays_events.csv` 直接加载（Favorita 自带，无需硬编码）；分组键由 `(product_id, store_id)` 改为 `(family, store_nbr)`。  
> **Oracle审核修复**：明确 `onpromotion` 为**可选列**（存在时处理，不存在时跳过，不报错）；修正数据量口径为 278,520行。

## 目标
实现 `modules/data_processor.py`，完成数据导入、校验、清洗、特征工程，将干净数据落盘到 `data/processed/`，返回路径元数据供 Flask Session 引用。

## 数据字段说明（Favorita）

| 字段 | 类型 | 说明 |
|------|------|------|
| `date` | date | 日期（2013-01-01 至 2017-08-15） |
| `store_nbr` | int | 门店编号（1–5，裁剪后）|
| `family` | str | 商品品类（33个，如 GROCERY I、BEVERAGES）|
| `sales` | float | **核心指标**：日销售量（≥0，可为小数）|
| `onpromotion` | int | 当日该品类促销商品数量（≥0）|

> **注意**：Favorita 无 `unit_price` 和 `sales_amount` 列，本模块不做金额校验。`sales` 字段含义是销售量，不是销售金额。

## 交付物清单
- [ ] `modules/data_processor.py`
- [ ] `data/processed/clean_{session_id}.csv`（清洗后全量数据）
- [ ] `data/processed/meta_{session_id}.json`（路径 + 数据概况，Flask Session 只存此文件路径）

## 核心类设计：`DataProcessor`

```python
class DataProcessor:
    def __init__(self, filepath: str, session_id: str):
        """
        filepath:   上传文件的绝对路径（.csv 或 .xlsx）
        session_id: 用于命名输出文件��隔离不同上传会话
        """
```

### 1. `load()` — 加载

编码处理顺序（仅 CSV）：
1. UTF-8
2. UTF-8-SIG（带 BOM）
3. GBK
4. 以上均失败 → 抛出 `ValueError('文件编码无法识别，请转存为 UTF-8 格式')`

xls（旧格式）：直接拒绝：
```
'不支持 .xls 格式，请在 Excel 中另存为 .xlsx 再上传'
```

### 2. `validate()` — 校验

**完整校验规则**：

| 规则 | 级别 | 处理 |
|------|------|------|
| 必要列存在：`date, store_nbr, family, sales` | ERROR | 缺少任一则拒绝 |
| `date` 可解析为 datetime | ERROR | 无法解析则拒绝 |
| `sales` 可转数值 | ERROR | 非数值则拒绝 |
| `(date, family, store_nbr)` 联合唯一 | WARNING | 重复则聚合求和 |
| 日期在组内递增 | WARNING | 乱序则自动排序 |
| `sales >= 0` | WARNING | 负值置零 |
| `onpromotion >= 0`（**可选列**，存在时才检查）| WARNING | 负值置零；列不存在则跳过此规则 |
| 数据量 ≥ 90 天 | WARNING | 提示"预测精度可能偏低" |
| 连续缺失 ≤ 30 天（每个序列）| WARNING | 超过则标注序列名 |

返回结构：
```python
{
  'valid': bool,
  'errors': [...],
  'warnings': [...],
  'stats': {
    'rows': int, 'date_range': {...},
    'families': [...], 'stores': [...],
    'missing_count': int, 'duplicate_rows': int
  }
}
```

### 3. `clean()` — 清洗主流程

顺序（不可颠倒）：
1. 日期解析标准化 → datetime64，按 `(store_nbr, family, date)` 排序
2. 数值列类型转换（`pd.to_numeric(errors='coerce')`）
3. 重复行聚合（同 family+store_nbr+date → 求和）
4. 负值处理（`sales < 0 → 0`；若 `onpromotion` 列存在则 `onpromotion < 0 → 0`）
5. 缺失值处理（`handle_missing`）
6. 异常值标记+处理（`handle_outliers`）

### 4. `handle_missing()` — 缺失值处理

**必须按 `(family, store_nbr)` 分组后在组内操作**：

```python
# ✅ 正确
df.groupby(['family','store_nbr']).apply(
    lambda g: g['sales'].interpolate(method='time')
)

# ❌ 错误（跨序列污染）
df['sales'].interpolate(method='time')
```

| 字段 | 缺失天数 | 策略 |
|------|---------|------|
| `sales` | ≤7天 | 线性时间插值 |
| `sales` | 8–30天 | 前向填充，再按同月均值修正 |
| `sales` | >30天 | 填充组内中位数，记录警告 |
| `onpromotion` | 任意 | **可选列**：存在时前向填充→后向填充→0；列不存在则跳过 |

### 5. `handle_outliers()` — 异常值处理

**核心原则：区分"录入错误"与"真实业务波动"，保留后者**

Favorita 自带 `holidays_events.csv`，直接加载作为事件日历（不再硬编码）：

```python
def _load_events(self) -> set:
    """从 data/raw/holidays_events.csv 加载节假日+促销事件日期集合"""
    holidays_path = os.path.join(DATA_RAW_DIR, 'holidays_events.csv')
    if not os.path.exists(holidays_path):
        return set()
    hdf = pd.read_csv(holidays_path, parse_dates=['date'])
    # 只取 Ecuador 国家级和地区级节假日（type in ['Holiday','Event','Additional']）
    return set(hdf['date'].dt.strftime('%Y-%m-%d').tolist())
```

```
录入错误（替换为 7 天滚动中位数）：
  条件：孤立单天异常（前后 3 天均正常）
       AND 该日期不在 holidays_events.csv 中
       AND 值 > rolling_median × 10（极端偏离）

真实业务波动（保留，标记 is_outlier=True）：
  条件：已知节假日/促销日期间
       OR 连续 ≥3 天持续高销量
       OR 值在 IQR 范围内（Q3 + 3.0×IQR）
```

输出新增列：
- `is_outlier`（bool）：检测到的业务波动，值保留
- `is_event`（bool）：已知节假日/促销日（来自 holidays_events.csv）

### 6. `feature_engineering()` — 特征工程

新增列（供 LSTM 可选使用；ARIMA/Prophet **不依赖**这些列）：

```
时间特征：year, month, day, weekday, is_weekend, week_of_year, quarter
业务特征：is_holiday, is_event, days_to_monthend
促销特征：onpromotion（可选列，存在时直接保留；不存在时不新增）
滞后特征（按组）：sales_lag7, lag14, lag30
滚动统计（按组）：sales_rolling7_mean, rolling30_mean
```

> 前 `seq_len` 天的 lag/rolling 会出现 NaN，属正常现象，LSTM 使用时从第 seq_len 天开始。

### 7. `aggregate()` — 聚合视图

```python
{
  'daily_total':     按日期聚合的全部总销售量（DatetimeIndex Series）
  'by_family':       各品类汇总 DataFrame（含中文名映射）
  'by_store':        各门店汇总 DataFrame
  'by_family_store': {'BEVERAGES_1': pd.Series, ...}  # 各序列（DatetimeIndex）
}
```

### 8. `split_timeseries()` — 时序切分

```python
def split_timeseries(self, series: pd.Series) -> tuple:
    """严格按时间顺序，绝对不能 shuffle"""
    n = len(series)
    n_train = int(n * TRAIN_RATIO)
    n_val   = int(n * VAL_RATIO)
    train = series.iloc[:n_train]
    val   = series.iloc[n_train:n_train+n_val]
    test  = series.iloc[n_train+n_val:]
    assert train.index.max() < val.index.min()
    assert val.index.max()   < test.index.min()
    return train, val, test
```

### 9. `normalize()` — 归一化

```python
def normalize(self, train, val, test):
    scaler = MinMaxScaler()
    scaler.fit(train.values.reshape(-1,1))   # 只在 train 上 fit
    train_s = scaler.transform(train.values.reshape(-1,1)).flatten()
    val_s   = scaler.transform(val.values.reshape(-1,1)).flatten()
    test_s  = scaler.transform(test.values.reshape(-1,1)).flatten()
    return train_s, val_s, test_s, scaler
```

### 10. `save_processed()` — 落盘元数��

```python
def save_processed(self, df, agg) -> str:
    """
    保存文件：
      data/processed/clean_{session_id}.csv
      data/processed/daily_total_{session_id}.csv
      data/processed/meta_{session_id}.json

    meta JSON 格式：
    {
      "session_id": "xxx",
      "created_at": "2024-01-01T10:00:00",
      "clean_csv": "/abs/path/clean_xxx.csv",
      "daily_total_csv": "/abs/path/daily_total_xxx.csv",
      "summary": { get_summary() 的返回值 }
    }

    返回 meta 文件的绝对路径
    Flask Session 只存此路径字符串，不存 DataFrame
    """

def load_processed(self, meta_path: str) -> pd.DataFrame:
    """从 meta JSON 读取路径，加载清洗后数据"""
    with open(meta_path) as f:
        meta = json.load(f)
    return pd.read_csv(meta['clean_csv'], parse_dates=['date'])
```

## 验收标准

- [ ] `load()` 对 UTF-8、UTF-8-SIG、GBK 编码的 CSV 均可读取
- [ ] `load()` 对 `.xls` 文件返回明确错误，不崩溃
- [ ] `validate()` 对缺少 `sales` 列的文件返回 `valid=False`，errors 非空
- [ ] `validate()` 对重复行返回 warning，继续处理
- [ ] `clean()` 后 `df.isnull().sum().sum() == 0`
- [ ] `clean()` 后 `(df['sales'] < 0).sum() == 0`
- [ ] **`clean()` 不替换已知节假日的高销量**（is_event=True 的行，sales 值不变）
- [ ] `onpromotion` 列存在时：`clean()` 后 `(df['onpromotion'] < 0).sum() == 0`
- [ ] `onpromotion` 列**不存在**时：`clean()` 正常运行，不抛异常
- [ ] 所有插值/rolling 在 `(family, store_nbr)` 组内执行（单元测试验证）
- [ ] `split_timeseries()` 断言通过：train < val < test（时间顺序）
- [ ] `normalize()` scaler 只 fit train，测试：`scaler.data_min_ == train.values.min()`
- [ ] `save_processed()` 生成 meta JSON；`load_processed()` 无内存缓存，纯从文件读
- [ ] 处理 278,520 条记录，`clean()` 耗时 < 10 秒
