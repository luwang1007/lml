# Step 1 — 项目骨架与环境搭建

> **修订说明（v3）**：采用真实公开数据集 **Kaggle Favorita Store Sales**（Corporación Favorita 厄瓜多尔超市竞赛数据��，替换原模拟数据方案。数据规模为 5家门店 × 33品类 × 约1688天 = **278,520行**；字段映射全面更新；`generate_data.py` 改为 `prepare_data.py`（数据裁剪脚本，不再生成随机数据）。  
> **v3修订说明（Oracle审核后）**：修正行数口径（27,720→278,520）；补充统一文件命名函数 `safe_family_name()`；明确 `onpromotion` 为可选列。

## 数据集说明

| 项目 | 值 |
|------|-----|
| 名称 | Store Sales - Time Series Forecasting |
| 来源 | Kaggle 竞赛：https://www.kaggle.com/competitions/store-sales-time-series-forecasting/data |
| 下载方式 | 需 Kaggle 账号，使用 `kaggle competitions download -c store-sales-time-series-forecasting` |
| 原始规模 | train.csv 约 3,000,888 行（54家门店 × 33品类 × 约1688天） |
| 许可 | CC BY-NC-SA 4.0（仅用于本毕业设计学习研究） |
| 语言 | 英文品类名，项目内部做中文映射 |

## 数据规模（全局统一定义，后续所有 Step 均以此为准）

| 维度 | 原始数据 | 本项目裁剪后 |
|------|---------|------------|
| 门店数量 | 54 家 | **5 家**（store_nbr: 1–5） |
| 商品品类数 | 33 个 | **33 个**（全部保留）|
| 时间跨度 | 2013-01-01 至 2017-08-15（约1688天） | **同上（全部保留）** |
| 总记录数 | ~3,000,888 行 | **5 × 33 × 1688 = 278,520 行** |
| 预测粒度 | — | **单品类 + 单门店**（默认），聚合总销量（可选） |

> **品类说明**：33个品类含 GROCERY I/II、BEVERAGES、PRODUCE、CLEANING 等，项目内部映射为中文供展示。详见 `config.py` 的 `FAMILY_ZH_MAP`。

> **预测粒度说明**：系统默认针对「某品类在某门店」的日销售序列建模预测（约1688点，远优于原1096点）。前端允许用户选择品类+门店组合。

## 交付物清单
- [ ] 完整目录树（见下方结构）
- [ ] `requirements.txt`（依赖版本固定 + 安装说明）
- [ ] `config.py`（全局配置常量）
- [ ] `data/raw/train_subset.csv`（裁剪后数据，5家门店，已提交到项目）
- [ ] `data/raw/holidays_events.csv`（Favorita节假日文件，原版直接使用）
- [ ] `data/raw/stores.csv`（门店信息文件，原版直接使用）
- [ ] `prepare_data.py`（数据裁剪脚本：从原始 train.csv 提取5家门店数据）
- [ ] `README.md`（项目说明、安装步骤、数据下载方式、启动方式）

## 目录结构

```
sales_analysis_system/
├── app.py                    # Flask 入口
├── config.py                 # 全局配置
├── requirements.txt
├── README.md
├── prepare_data.py           # 数据裁剪脚本（从原始 train.csv 提取子集）
│
├── data/
│   ├── raw/                  # 原始数据（用户下载后放置 / 项目自带裁剪版）
│   │   ├── train_subset.csv  # 裁剪后数据（5家门店，约278,520行，随项目分发）
│   │   ├── holidays_events.csv  # Favorita 节假日事件（原版）
│   │   └── stores.csv        # 门店信息（原版）
│   ├── processed/            # 清洗后数据（运行时自动生成，不提交 git）
│   │   ├── clean_{session_id}.csv
│   │   └── meta_{session_id}.json   # session 元数据（路径引用）
│   └── models/               # 训练好的模型文件（不提交 git）
│       ├── arima_{family}_{store_nbr}.pkl
│       ├── prophet_{family}_{store_nbr}.pkl
│       └── lstm_{family}_{store_nbr}.pth
│
├── modules/
│   ├── __init__.py
│   ├── data_processor.py     # 数据清洗与预处理（Step 2）
│   ├── analyzer.py           # 数据分析与图表数据生成（Step 3）
│   ├── arima_model.py        # ARIMA 预测（Step 4）
│   ├── prophet_model.py      # Prophet 预测（Step 5）
│   ├── lstm_model.py         # LSTM 预测（Step 6，可选扩展模块）
│   ├── evaluator.py          # 模型评估对比（Step 7）
│   └── task_manager.py       # 后台任务管理（Step 8）
│
├── templates/
│   ├── base.html             # 公共布局
│   ├── index.html            # 首页/数据上传
│   ├── analysis.html         # 数据分析页
│   ├── prediction.html       # 预测配置页
│   └── report.html           # 预测报告页
│
├── static/
│   ├── css/
│   │   └── style.css
│   ├── js/
│   │   ├── upload.js
│   │   ├── analysis.js
│   │   ├── prediction.js
│   │   └── report.js
│   └── vendor/               # 离线静态资源（答辩环境兜底）
│       ├── echarts.min.js
│       ├── bootstrap.min.css
│       └── bootstrap.bundle.min.js
│
└── tests/
    ├── conftest.py
    ├── test_data_processor.py
    ├── test_models.py
    └── test_api.py
```

> **重要**：`data/processed/` 和 `data/models/` 不提交 git，添加到 `.gitignore`。

## 依赖版本（requirements.txt）

```
# Web 框架
Flask==3.0.3

# 数据处理
pandas==2.2.2
numpy==1.26.4
openpyxl==3.1.2        # Excel .xlsx 读写

# 数据分析
statsmodels==0.14.2    # ARIMA + ADF检验 + STL分解
scipy==1.13.0

# 预测模型
torch==2.3.0           # LSTM（CPU版）
prophet==1.1.5         # Facebook Prophet（安装见 README 特殊说明）
scikit-learn==1.4.2    # MinMaxScaler

# 工具
python-dateutil==2.9.0
joblib==1.4.2          # 模型序列化

# 测试
pytest==8.2.0
```

### Prophet 安装特别说明（必读）

Prophet 安装依赖 `cmdstanpy` 编译，时间较长（5–20 分钟），部分环境可能失败：

```bash
# 推荐安装顺序
pip install pystan==3.9.1
pip install prophet==1.1.5

# 若失败，在 config.py 设置 PROPHET_ENABLED = False
```

## config.py 关键配置

```python
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ─── 数据路径 ───────────────────────────────────────────────────
DATA_RAW_DIR   = os.path.join(BASE_DIR, 'data', 'raw')
DATA_PROC_DIR  = os.path.join(BASE_DIR, 'data', 'processed')
MODEL_DIR      = os.path.join(BASE_DIR, 'data', 'models')

# ─── Flask ────────────────────────────────────────────────────
UPLOAD_FOLDER      = DATA_RAW_DIR
ALLOWED_EXTENSIONS = {'csv', 'xlsx'}   # 不支持 .xls
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB

# ─── 数据集：Favorita（全局统一，勿随意修改）────────────────────
# 本项目裁剪使用 5 家门店，33 个品类全保留
DATA_STORES    = [1, 2, 3, 4, 5]       # store_nbr（整数）
DATA_FAMILIES  = [                      # 33 个品类（Favorita 原始名称）
    'AUTOMOTIVE', 'BABY CARE', 'BEAUTY', 'BEVERAGES', 'BOOKS',
    'BREAD/BAKERY', 'CELEBRATION', 'CLEANING', 'DAIRY', 'DELI',
    'EGGS', 'FROZEN FOODS', 'GROCERY I', 'GROCERY II', 'HARDWARE',
    'HOME AND KITCHEN I', 'HOME AND KITCHEN II', 'HOME APPLIANCES',
    'HOME CARE', 'LADIESWEAR', 'LAWN AND GARDEN', 'LINGERIE',
    'LIQUOR,WINE,BEER', 'MAGAZINES', 'MEATS', 'PERSONAL CARE',
    'PET SUPPLIES', 'PLAYERS AND ELECTRONICS', 'POULTRY',
    'PREPARED FOODS', 'PRODUCE', 'SCHOOL AND OFFICE SUPPLIES',
    'SEAFOOD'
]

# 品类中文名映射（前端展示用）
FAMILY_ZH_MAP = {
    'AUTOMOTIVE': '汽车用品', 'BABY CARE': '婴儿用品', 'BEAUTY': '美妆',
    'BEVERAGES': '饮料', 'BOOKS': '图书', 'BREAD/BAKERY': '面包烘焙',
    'CELEBRATION': '节庆礼品', 'CLEANING': '清洁用品', 'DAIRY': '乳制品',
    'DELI': '熟食', 'EGGS': '蛋类', 'FROZEN FOODS': '冷冻食品',
    'GROCERY I': '杂货I', 'GROCERY II': '杂货II', 'HARDWARE': '五金',
    'HOME AND KITCHEN I': '家居厨具I', 'HOME AND KITCHEN II': '家居厨具II',
    'HOME APPLIANCES': '家电', 'HOME CARE': '家居护理', 'LADIESWEAR': '女装',
    'LAWN AND GARDEN': '园艺', 'LINGERIE': '内衣', 'LIQUOR,WINE,BEER': '酒水',
    'MAGAZINES': '杂志', 'MEATS': '肉���', 'PERSONAL CARE': '个人护理',
    'PET SUPPLIES': '宠物用品', 'PLAYERS AND ELECTRONICS': '电子产品',
    'POULTRY': '禽肉', 'PREPARED FOODS': '即食食品', 'PRODUCE': '生鲜',
    'SCHOOL AND OFFICE SUPPLIES': '文具办公', 'SEAFOOD': '海鲜'
}

# ─── 数据字段映射（Favorita 字段名）────────────────────────────
COL_DATE       = 'date'
COL_STORE      = 'store_nbr'
COL_FAMILY     = 'family'
COL_SALES      = 'sales'
COL_ONPROMO    = 'onpromotion'

# ─── 数据分割比例 ────────────────────────────────────────────────
TRAIN_RATIO = 0.70   # 约 1182 天
VAL_RATIO   = 0.15   # 约 253 天
TEST_RATIO  = 0.15   # 约 253 天

# ─── 预测粒度 ─────────────────────────────────────────────────────
# 'single'：单品类-单门店序列（默认）
# 'total'：所有品类+门店聚合后的总销量序列
PREDICTION_GRANULARITY = 'single'

# ─── ARIMA 参数 ───────────────────────────────────────────────────
ARIMA_P_RANGE   = range(0, 4)
ARIMA_D_RANGE   = range(0, 3)
ARIMA_Q_RANGE   = range(0, 4)
ARIMA_CRITERION = 'aic'

# ─── LSTM 参数（扩展模块）────────────────────────────────────────
LSTM_ENABLED     = True
LSTM_HIDDEN_SIZE = 64
LSTM_NUM_LAYERS  = 2
LSTM_SEQ_LEN     = 30
LSTM_EPOCHS      = 50
LSTM_BATCH_SIZE  = 32
LSTM_LR          = 0.001
LSTM_LR_PATIENCE = 10

# ─── Prophet 参数 ─────────────────────────────────────────────────
PROPHET_ENABLED            = True
PROPHET_CHANGEPOINT_SCALE  = 0.05
PROPHET_SEASONALITY_MODE   = 'multiplicative'

# ─── 预测期数 ─────────────────────────────────────────────────────
FORECAST_DAYS = 30

# ─── Session 超时（秒）───────────────────────────────────────────
SESSION_TIMEOUT = 7200   # 2小时

# ─── 随机种子 ────────────────────────────────────────────��────────
RANDOM_SEED = 42

# ─── 模型文件命名（全局统一，step4/5/6 均使用此函数）──────────────
def safe_family_name(family: str) -> str:
    """
    将 Favorita family 名转为安全文件名片段。
    规则：大写保留，空格→下划线，逗号→下划线，移除其他非字母数字下划线字符。
    示例：
      'LIQUOR,WINE,BEER'  → 'LIQUOR_WINE_BEER'
      'HOME AND KITCHEN I' → 'HOME_AND_KITCHEN_I'
      'GROCERY I'         → 'GROCERY_I'
    """
    import re
    return re.sub(r'[^A-Z0-9_]', '_', family.upper().replace(',', '_').replace(' ', '_'))
    # 多余下划线压缩
    return re.sub(r'_+', '_', safe).strip('_')
```

## prepare_data.py — 数据裁剪脚本

**目标**：从 Kaggle 下载的原始 `train.csv` 裁剪出 5 家门店的数据，生成 `data/raw/train_subset.csv`，供项目直接使用（无需每次重下载）。

```python
"""
prepare_data.py
从 Kaggle Favorita 原始 train.csv 裁剪出子集。

使用方法：
  1. 从 Kaggle 下载数据放到 data/raw/ 目录下（train.csv 等）
  2. python prepare_data.py

输出：data/raw/train_subset.csv（约278,520行，5家门店×33品类×1688天）
"""
import pandas as pd
import os

RAW_DIR = os.path.join(os.path.dirname(__file__), 'data', 'raw')

def prepare():
    train_path = os.path.join(RAW_DIR, 'train.csv')
    if not os.path.exists(train_path):
        raise FileNotFoundError(
            f'未找到 {train_path}\n'
            '请先从 Kaggle 下载数据：\n'
            '  kaggle competitions download -c store-sales-time-series-forecasting\n'
            '  unzip store-sales-time-series-forecasting.zip -d data/raw/'
        )
    
    print('读取原始数据...')
    df = pd.read_csv(train_path, parse_dates=['date'])
    
    # 裁剪：只取 5 家门店
    subset = df[df['store_nbr'].isin([1, 2, 3, 4, 5])].copy()
    subset = subset.sort_values(['store_nbr', 'family', 'date']).reset_index(drop=True)
    
    out_path = os.path.join(RAW_DIR, 'train_subset.csv')
    subset.to_csv(out_path, index=False)
    
    print(f'✅ 裁剪完成：{len(subset):,} 行 → {out_path}')
    print(f'   门店：{sorted(subset["store_nbr"].unique())}')
    print(f'   品类：{subset["family"].nunique()} 个')
    print(f'   日期：{subset["date"].min()} 至 {subset["date"].max()}')
    
    # 验证
    expected = 5 * 33 * subset['date'].nunique()
    if len(subset) != expected:
        print(f'⚠️  注意：实际行数 {len(subset)} ≠ 预期 {expected}（部分日期可能缺失，正常）')

if __name__ == '__main__':
    prepare()
```

## 验收标准

- [ ] `python prepare_data.py` 成功裁剪，生成 `data/raw/train_subset.csv`（约278,520行）
- [ ] CSV 含字段：`id, date, store_nbr, family, sales, onpromotion`
- [ ] `store_nbr` 只含 1–5
- [ ] `family` 含 33 个品类
- [ ] 日期范围：2013-01-01 至 2017-08-15
- [ ] `data/raw/holidays_events.csv` 和 `stores.csv` 也已放置
- [ ] `data/processed/` 和 `data/models/` 目录存在（空目录）
- [ ] `static/vendor/` 目录含 echarts.min.js、bootstrap 离线文件

## 注意事项

- 需要 Kaggle 账号下载原始数据（答辩前完成一次即可）
- `train_subset.csv` 可以直接提交到项目仓库（278,520行，约20MB）
- 原始 `train.csv`（3,000,888行，~74MB）不提交 git
- `.gitignore` 添加：`data/raw/train.csv`、`data/processed/`、`data/models/`、`__pycache__/`
- 安装 Prophet 前必须验证 Python 3.10 环境可用；如失败，设置 `PROPHET_ENABLED=False` 继续
- 答辩时使用 `static/vendor/` 离线静态资源，避免现场断网导致前端白屏
