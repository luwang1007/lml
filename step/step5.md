# Step 5 — 预测模型：Prophet（v3）

> **修订说明（v3）**：适配 Favorita 数据集；节假日来源改为直接读取 `data/raw/holidays_events.csv`（Favorita 自带，包含厄瓜多尔国家级/地区级节假日），不再动态生成中国节假日；促销效果可通过 `onpromotion` 列作为外部回归量传入 Prophet（regressor）；序列长度约1688点。

## 目标
实现 `modules/prophet_model.py`，基于 Facebook Prophet 对**单条时间序列**进行训练与预测，输出预测值、置信区间及分量分解。

## Prophet 可用性检查

```python
try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False
    logger.warning('Prophet 未安装。设置 PROPHET_ENABLED=False 可跳过此模块。')
```

若 `PROPHET_AVAILABLE=False` 且调用 `fit()`，抛出：
```
ImportError('Prophet 未安装，请按 README 安装说明处理，或在 config.py 设置 PROPHET_ENABLED=False')
```

## 核心类设计：`ProphetModel`

```python
class ProphetModel:
    def __init__(self, config: dict = None):
        """
        默认参数：
        {
          'changepoint_prior_scale': 0.05,
          'seasonality_prior_scale': 10.0,
          'seasonality_mode': 'multiplicative',
          'yearly_seasonality': True,
          'weekly_seasonality': True,
          'daily_seasonality': False,
          'forecast_days': 30,
          'use_onpromotion': False    # 是否将 onpromotion 作为回归量
        }
        """
```

### `_load_holidays()` — 加载节假日

**直接读取 Favorita 自带的 `holidays_events.csv`**，不再硬编码或动态生成：

```python
def _load_holidays(self) -> pd.DataFrame:
    """
    加载 data/raw/holidays_events.csv，转为 Prophet holidays 格式。
    
    Favorita holidays_events.csv 字段：
      date, type, locale, locale_name, description, transferred
    
    type 含义：
      Holiday   → 法定节假日
      Event     → 特殊事件（如地震、世界杯）
      Additional → 追加假日
      Bridge    → 补班/调休
      Transfer  → 调换假日
    
    处理规则：
      只取 type in ['Holiday', 'Event', 'Additional']
      transferred=True 的行跳过（已被调换，原日期无效）
    
    返回 Prophet 格式 DataFrame：
    columns: [ds, holiday, lower_window, upper_window]
    
    window 设置：
      Holiday  → lower_window=-1, upper_window=1
      Event    → lower_window=0,  upper_window=0
      Additional → lower_window=0, upper_window=0
    
    文件不存在时返回 None（Prophet 不加 holidays，降级处理）
    """
    holidays_path = os.path.join(DATA_RAW_DIR, 'holidays_events.csv')
    if not os.path.exists(holidays_path):
        logger.warning('未找到 holidays_events.csv，Prophet 将不使用节假日特征')
        return None
    
    hdf = pd.read_csv(holidays_path, parse_dates=['date'])
    hdf = hdf[
        (hdf['type'].isin(['Holiday', 'Event', 'Additional'])) &
        (~hdf['transferred'].astype(bool))
    ].copy()
    
    # 映射 window
    hdf['lower_window'] = hdf['type'].map({'Holiday': -1, 'Event': 0, 'Additional': 0})
    hdf['upper_window'] = hdf['type'].map({'Holiday': 1,  'Event': 0, 'Additional': 0})
    
    return hdf.rename(columns={'date': 'ds', 'description': 'holiday'})[
        ['ds', 'holiday', 'lower_window', 'upper_window']
    ]
```

### `_prepare_dataframe(series, onpromotion_series=None)` — 格式转换

```python
def _prepare_dataframe(self, series: pd.Series,
                        onpromotion_series: pd.Series = None) -> pd.DataFrame:
    """
    转为 Prophet 要求的 ds/y 格式。
    
    onpromotion_series：若提供，加入 regressors 列（use_onpromotion=True 时使用）。
    
    y=0 处理策略（仅 seasonality_mode='multiplicative' 时）：
      - 乘法模式下 Prophet 要求 y > 0，否则拟合不稳定
      - y = 0 替换为 0.01
      - 论文中说明：'对断货日（sales=0）进行最小值平滑处理'
    
    若 seasonality_mode='additive'，则 y=0 不替换。
    """
```

### `fit(train_series, onpromotion_series=None)` — 训练

```python
def fit(self, train_series: pd.Series,
        onpromotion_series: pd.Series = None) -> None:
    """
    1. 调用 _load_holidays() 获取 Favorita 节假日
    2. 初始化 Prophet 实例，加入 holidays
    3. 若 use_onpromotion=True 且 onpromotion_series 不为 None：
       self.model.add_regressor('onpromotion')
    4. 压制 Prophet/Stan 的 stdout 日志：
       with suppress_stdout_stderr():
           self.model.fit(df)
    5. 保存 fitted_values
    """
```

### `predict(steps=30, future_onpromotion=None)` — 预测

```python
def predict(self, steps: int = 30,
            future_onpromotion: list = None) -> dict:
    """
    future_onpromotion：未来 steps 天的促销量（若有 regressor）。
    为 None 时，**默认置 0**（表示未来无促销计划），不报错。
    论文中说明：'预测期内促销量未知时，保守假设为零促销。'
    
    注意：use_onpromotion=False 时，此参数直接被忽略。
    """
    future_onpromotion：未来 steps 天的促销量（若有 regressor）。
    为 None 时，用训练集促销量均值填充。
    
    返回：
    {
      'dates':    [...],
      'forecast': [...],   # yhat，clip ≥ 0
      'lower_ci': [...],   # yhat_lower，clip ≥ 0
      'upper_ci': [...],   # yhat_upper，clip ≥ 0
      'components': {
        'trend':     [...],
        'weekly':    [...],
        'yearly':    [...],
        'holidays':  [...]    # 节假日效应
      }
    }
    """
```

### `get_changepoints()` — 趋势变点

```python
{
  'dates':  [str, ...],    # 变点日期
  'deltas': [float, ...]   # 各变点处的趋势变化量（正=加速，负=减速）
}
```

### `evaluate(test_series)` / `save()` / `load()`

与 Step 4 ARIMA 相同接口规范（`ModelEvaluator.compute_all` 统一计算）。

文件命名约定：`prophet_{safe_family_name(family)}_{store_nbr}.pkl`

> `safe_family_name()` 定义在 `config.py`，与 ARIMA/LSTM 命名规则完全一致。

## Prophet vs ARIMA 对比（论文素材）

| 维度 | ARIMA | Prophet |
|------|-------|---------|
| 趋势处理 | 差分（隐式）| 分段线性/非线性（显式）|
| 季节性 | 需 SARIMA 扩展 | 傅里叶级数（原生）|
| 节假日/促销 | 无原生支持 | 内置 events 参数 |
| 外部回归量 | 需 ARIMAX | add_regressor() 直接支持 |
| 可解释性 | 中（系数）| 高（分量分解图）|
| Favorita 数据适配 | 需手动处理节假日 | 可直接加载 holidays_events.csv |

## 验收标准

- [ ] `_load_holidays()` 正常加载 holidays_events.csv，返回非空 DataFrame
- [ ] `_load_holidays()` 对文件不存在时返回 None，fit() 不崩溃
- [ ] transferred=True 的行被过滤掉
- [ ] Prophet 未安装时，`fit()` 抛出 ImportError 而非 AttributeError
- [ ] `fit()` 对 1688 点序列耗时 < 90 秒
- [ ] `predict(30)` 长度 = 30，无 NaN，所有值 ≥ 0
- [ ] `components` 含 trend/weekly/yearly 三个非零数组
- [ ] `evaluate()` MAPE < 40%（真实数据合理范围，略放宽）
- [ ] `save()` + `load()` 往返一致
