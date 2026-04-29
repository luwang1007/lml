# Step 3 — 分析层：数据分析与可视化（v3）

> **修订说明（v3）**：适配 Favorita 字段（`family`/`store_nbr`/`sales`/`onpromotion`）；去除原来基于 `sales_amount`/`unit_price` 的金额分析，改为纯销售量分析；品类维度由 `category` 改为 `family`（含中文映射）；门店标识由 `store_id` 改为 `store_nbr`；新增 `onpromotion` 促销效果分析（P1）。

## 目标
实现 `modules/analyzer.py`，输��� ECharts 可直接消费的 JSON 数据，支撑前端图表渲染。**本模块不生成图片**，只输出结构化数据。

## 图表优先级（按此顺序实现）

### 主线（必须完成，分析页 P0）

| 优先级 | 图表 | 方法 | ECharts 类型 |
|--------|------|------|------------|
| P0-1 | 销售量趋势折线图 | `get_trend_chart()` | Line |
| P0-2 | 月度同比柱状图 | `get_monthly_comparison()` | Bar（分组）|
| P0-3 | 商品品类占比 | `get_category_pie()` | Pie |
| P0-4 | TOP 10 品类排行 | `get_top_families()` | Bar（横向）|

### 可选（时间允许再做，P1）

| 优先级 | 图表 | 方法 |
|--------|------|------|
| P1-1 | 品类相关性热力图 | `get_correlation_heatmap()` |
| P1-2 | 星期效应柱状图 | `get_weekday_pattern()` |
| P1-3 | STL 季节性分解 | `get_seasonal_decomposition()` |
| P1-4 | 促销效果分析 | `get_promotion_effect()` |

## 核心类设计：`DataAnalyzer`

```python
class DataAnalyzer:
    def __init__(self, df: pd.DataFrame):
        """接收 DataProcessor.clean() 后的干净数据"""
        self._df = df
        # 预计算常用聚合��避免重复计算
        self._daily_total = df.groupby('date')[['sales']].sum()
```

### 通用返回格式

所有方法统一返回：
```python
{
  'success': True,
  'data': { ... }    # 图表数据
}
# 或出错时：
{
  'success': False,
  'error': '人类可读的原因说明'
}
```

---

### P0-1 `get_overview_stats()` — KPI 总览

```python
def get_overview_stats(self) -> dict:
    """
    返回首屏 KPI 卡片数据（4个指标）：
    {
      'success': True,
      'data': {
        'total_sales':      float,   # 总销售量（件）
        'avg_daily_sales':  float,   # 日均销售量
        'yoy_growth':       float,   # 同比增长率（%），数据不足2年则返回 null
        'best_family':   {'name': str, 'name_zh': str, 'sales': float},
        'date_range':    {'start': str, 'end': str, 'days': int},
        'store_count':   int,
        'family_count':  int
      }
    }
    """
```

### P0-1 `get_trend_chart()` — 销售量趋势

```python
def get_trend_chart(self,
                    granularity: str = 'monthly',
                    family: str = 'all',
                    store_nbr: int = 0) -> dict:
    """
    granularity: 'daily' | 'weekly' | 'monthly'
    family:      'all' 或具体品类名（英文原始名）
    store_nbr:   0（所有门店）或具体门店编号（1–5）
    
    返回 ECharts option 所需数据：
    {
      'success': True,
      'data': {
        'xAxis': ['2013-01', '2013-02', ...],
        'series': [
          {'name': '销售量（件）', 'data': [float, ...]}
        ]
      }
    }
    
    前置检查：
    - granularity='daily' 且数据量 > 365 天时，自动降级为 weekly 并附 warning
    - 筛选后数据为空时，返回 success=False + error 说明
    """
```

### P0-2 `get_monthly_comparison()` — 月度同比

```python
def get_monthly_comparison(self) -> dict:
    """
    按年分组的月度销售量对比。
    {
      'success': True,
      'data': {
        'months': ['1月','2月',...,'12月'],
        'series': [
          {'name': '2013年', 'data': [float or null, ...]},
          {'name': '2014年', 'data': [float, ...]},
          ...
          {'name': '2017年', 'data': [float or null, ...]}  # 仅有1-8月
        ]
      }
    }
    前置检查：数据跨度 < 13个月时返回 success=False，error='数据不足一年，无法做同比分析'
    """
```

### P0-3 `get_category_pie()` — 品类占比

```python
def get_category_pie(self) -> dict:
    """
    按 family 汇总销售量占比（显示中文名）
    {
      'success': True,
      'data': {
        'series': [
          {'name': '饮料', 'value': float},     # 使用 FAMILY_ZH_MAP 转换
          {'name': '生鲜', 'value': float},
          ...
        ],
        'total': float
      }
    }
    """
```

### P0-4 `get_top_families()` — 品类排行

```python
def get_top_families(self, n: int = 10) -> dict:
    """
    {
      'success': True,
      'data': {
        'families':   ['生鲜', '饮料', ...],   # 中文名
        'sales':      [float, ...],
        'onpromotion_avg': [float, ...]         # 各品类平均促销商品数（若有此列）
      }
    }
    """
```

### P1-1 `get_correlation_heatmap()` — 相关性热力图（可选）

```python
def get_correlation_heatmap(self) -> dict:
    """
    计算各品类日销量的 Pearson 相关系数矩阵（跨所有门店聚合后）。
    使用中文品类名。
    
    前置检查：品类数 < 2 时返回 success=False
    """
```

### P1-2 `get_weekday_pattern()` — 星期效应（可选）

```python
def get_weekday_pattern(self) -> dict:
    """
    {
      'success': True,
      'data': {
        'days':      ['周一','周二','周三','周四','周五','周六','周日'],
        'avg_sales': [float, ...]
      }
    }
    """
```

### P1-3 `get_seasonal_decomposition()` — STL 分解（可选）

```python
def get_seasonal_decomposition(self,
                                family: str = None,
                                store_nbr: int = 0,
                                period: int = 7) -> dict:
    """
    family=None 时，使用 daily_total（全部品类聚合总销量）。
    store_nbr=0 时，跨所有门店聚合。
    
    前置检查：
    - 序列长度 < 2 × period：返回 success=False
    - 序列为常数：返回 success=False
    """
```

### P1-4 `get_promotion_effect()` — 促销效果分析（可选，Favorita 特有）

```python
def get_promotion_effect(self, family: str = None) -> dict:
    """
    对比促销日（onpromotion > 0）与非促销日的销售量差异。
    family=None 时跨所有品类汇总。
    
    {
      'success': True,
      'data': {
        'promo_avg':    float,  # 促销日平均销售量
        'non_promo_avg': float, # 非促销日平均销售��
        'lift_ratio':   float,  # 提升倍数（promo/non_promo）
        'by_family': [          # 各品类促销提升（TOP10）
          {'name': '饮料', 'promo_avg': float, 'non_promo_avg': float, 'lift': float},
          ...
        ]
      }
    }
    前置检查：若 onpromotion 列不存在，返回 success=False，error='数据不含促销字段'
    """
```

### `generate_analysis_report()` — 完整报告

```python
def generate_analysis_report(self) -> dict:
    return {
        'generated_at': datetime.now().isoformat(),
        'overview':     self.get_overview_stats(),
        'trend':        self.get_trend_chart(granularity='monthly'),
        'monthly_cmp':  self.get_monthly_comparison(),
        'category_pie': self.get_category_pie(),
        'top_families': self.get_top_families(10),
        # P1 可选
        'correlation':  self.get_correlation_heatmap(),
        'weekday':      self.get_weekday_pattern(),
        'promo_effect': self.get_promotion_effect(),
    }
```

## JSON 序列化保证

所有方法返回值必须满足：

```python
import json, math
def safe_json(obj):
    """确保无 numpy ��型、无 NaN、无 Inf"""
    if isinstance(obj, (np.integer,)): return int(obj)
    if isinstance(obj, (np.floating,)):
        if math.isnan(obj) or math.isinf(obj): return None
        return float(obj)
    if isinstance(obj, np.ndarray): return obj.tolist()
    return obj
```

## 验收标准

- [ ] `get_overview_stats()` 返回 `total_sales > 0`，`family_count == 33`
- [ ] `get_trend_chart(granularity='monthly')` xAxis 长度对应 2013–2017 约 56 个月
- [ ] `get_monthly_comparison()` series 包含 2013–2017 五组
- [ ] `get_category_pie()` data 中各品类 value 之和 = total
- [ ] `get_top_families(10)` families 长度 = 10，显示���文名
- [ ] `get_promotion_effect()` 对无 onpromotion 列数据返回 `success=False`，不崩溃
- [ ] `get_seasonal_decomposition()` 对常数序列返回 `success=False`，不报错
- [ ] 所有返回值通过 `json.dumps()` 无异常（无 NaN、无 numpy 类型）
- [ ] `generate_analysis_report()` 耗时 < 5 秒
