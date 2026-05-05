"""
config.py — 全局配置常量
商贸公司销售数据分析与智能预测系统
数据集：Kaggle Favorita Store Sales（5家门店子集）
"""
import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ─── 数据路径 ────────────────────────────────────────────────────
DATA_RAW_DIR  = os.path.join(BASE_DIR, 'data', 'raw')
DATA_PROC_DIR = os.path.join(BASE_DIR, 'data', 'processed')
MODEL_DIR     = os.path.join(BASE_DIR, 'data', 'models')

# ─── Flask ───────────────────────────────────────────────────────
UPLOAD_FOLDER      = DATA_RAW_DIR
ALLOWED_EXTENSIONS = {'csv', 'xlsx'}   # 不支持 .xls（旧格式不可靠）
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB
SECRET_KEY         = os.environ.get('SECRET_KEY', 'favorita-sales-2024-dev-key')

# ─── 数据集：Favorita（全局统一，勿随意修改）────────────────────
# 本项目裁剪使用 5 家门店，33 个品类全保留
# 实际裁剪样本约 277,860 行（2013-01-01 仅部分门店有记录）
DATA_STORES = [1, 2, 3, 4, 5]          # store_nbr（整数）
DATA_FAMILIES = [                       # 33 个品类（Favorita 原始英文名称）
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

# 品类中文名映射（前端展示用；后端是唯一映射来源，前端只展示）
FAMILY_ZH_MAP = {
    'AUTOMOTIVE':                '汽车用品',
    'BABY CARE':                 '婴儿用品',
    'BEAUTY':                    '美妆',
    'BEVERAGES':                 '饮料',
    'BOOKS':                     '图书',
    'BREAD/BAKERY':              '面包烘焙',
    'CELEBRATION':               '节庆礼品',
    'CLEANING':                  '清洁用品',
    'DAIRY':                     '乳制品',
    'DELI':                      '熟食',
    'EGGS':                      '蛋类',
    'FROZEN FOODS':              '冷冻食品',
    'GROCERY I':                 '杂货I',
    'GROCERY II':                '杂货II',
    'HARDWARE':                  '五金',
    'HOME AND KITCHEN I':        '家居厨具I',
    'HOME AND KITCHEN II':       '家居厨具II',
    'HOME APPLIANCES':           '家电',
    'HOME CARE':                 '家居护理',
    'LADIESWEAR':                '女装',
    'LAWN AND GARDEN':           '园艺',
    'LINGERIE':                  '内衣',
    'LIQUOR,WINE,BEER':          '酒水',
    'MAGAZINES':                 '杂志',
    'MEATS':                     '肉类',
    'PERSONAL CARE':             '个人护理',
    'PET SUPPLIES':              '宠物用品',
    'PLAYERS AND ELECTRONICS':   '电子产品',
    'POULTRY':                   '禽肉',
    'PREPARED FOODS':            '即食食品',
    'PRODUCE':                   '生鲜',
    'SCHOOL AND OFFICE SUPPLIES': '文具办公',
    'SEAFOOD':                   '海鲜',
}

# ─── 数据字段映射（Favorita 字段名）────────────────────────────
COL_DATE    = 'date'
COL_STORE   = 'store_nbr'
COL_FAMILY  = 'family'
COL_SALES   = 'sales'
COL_ONPROMO = 'onpromotion'   # 可选列

# ─── 数据分割比例 ────────────────────────────────────────────────
TRAIN_RATIO = 0.70   # 约 1182 天
VAL_RATIO   = 0.15   # 约 253 天
TEST_RATIO  = 0.15   # 约 253 天

# ─── 预测粒度 ────────────────────────────────────────────────────
# 'single'：单品类-单门店序列（默认）
# 'total' ：所有品类+门店聚合后的总销量序列
PREDICTION_GRANULARITY = 'single'

# ─── ARIMA 参数 ──────────────────────────────────────────────────
ARIMA_P_RANGE   = range(0, 4)
ARIMA_D_RANGE   = range(0, 3)
ARIMA_Q_RANGE   = range(0, 4)
ARIMA_CRITERION = 'aic'    # 'aic' | 'bic'

# ─── LSTM 参数（扩展模块）───────────────────────────────────────
LSTM_ENABLED          = True   # 设为 False 可跳过 LSTM
LSTM_HIDDEN_SIZE      = 64
LSTM_NUM_LAYERS       = 2
LSTM_SEQ_LEN          = 30
LSTM_EPOCHS           = 50
LSTM_BATCH_SIZE       = 32
LSTM_LR               = 0.001
LSTM_LR_PATIENCE      = 10
LSTM_EARLY_STOP_PAT   = 15

# ─── Prophet 参数 ────────────────────────────────────────────────
PROPHET_ENABLED           = True   # 安装失败时设为 False
PROPHET_CHANGEPOINT_SCALE = 0.05
PROPHET_SEASONALITY_MODE  = 'multiplicative'

# ─── 预测期数 ────────────────────────────────────────────────────
FORECAST_DAYS = 30

# ─── Session 超时（秒）──────────────────────────────────────────
SESSION_TIMEOUT = 7200   # 2 小时

# ─── 随机种子 ────────────────────────────────────────────────────
RANDOM_SEED = 42


# ─── 模型文件命名（全局统一，step4/5/6 均使用此函数）────────────
def safe_family_name(family: str) -> str:
    """
    将 Favorita family 名转为安全文件名片段。
    规则：大写保留，空格→下划线，逗号→下划线，移除其他非字母数字下划线字符，
          连续下划线压缩为单个，首尾下划线去除。

    示例：
      'LIQUOR,WINE,BEER'           → 'LIQUOR_WINE_BEER'
      'HOME AND KITCHEN I'         → 'HOME_AND_KITCHEN_I'
      'GROCERY I'                  → 'GROCERY_I'
      'SCHOOL AND OFFICE SUPPLIES' → 'SCHOOL_AND_OFFICE_SUPPLIES'
      'BREAD/BAKERY'               → 'BREAD_BAKERY'
    """
    s = family.upper()
    s = s.replace(',', '_').replace(' ', '_').replace('/', '_')
    s = re.sub(r'[^A-Z0-9_]', '_', s)
    s = re.sub(r'_+', '_', s)
    return s.strip('_')
