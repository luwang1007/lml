"""
prepare_data.py
从 Kaggle Favorita 原始 train.csv 裁剪出 5 家门店子集。

使用方法：
  1. 从 Kaggle 下载竞赛数据，解压到 data/raw/：
       kaggle competitions download -c store-sales-time-series-forecasting
       unzip store-sales-time-series-forecasting.zip -d data/raw/
  2. python prepare_data.py

输出：data/raw/train_subset.csv（约 278,520 行，5家门店×33品类×约1688天）
"""
import os
import sys
import pandas as pd

RAW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'raw')
TRAIN_PATH  = os.path.join(RAW_DIR, 'train.csv')
OUTPUT_PATH = os.path.join(RAW_DIR, 'train_subset.csv')
TARGET_STORES = [1, 2, 3, 4, 5]


def prepare():
    if not os.path.exists(TRAIN_PATH):
        print(f'错误：未找到 {TRAIN_PATH}')
        print('请先从 Kaggle 下载竞赛数据：')
        print('  kaggle competitions download -c store-sales-time-series-forecasting')
        print('  unzip store-sales-time-series-forecasting.zip -d data/raw/')
        sys.exit(1)

    print(f'读取原始数据：{TRAIN_PATH} ...')
    df = pd.read_csv(TRAIN_PATH, parse_dates=['date'])

    subset = df[df['store_nbr'].isin(TARGET_STORES)].copy()
    subset = subset.sort_values(['store_nbr', 'family', 'date']).reset_index(drop=True)

    subset.to_csv(OUTPUT_PATH, index=False)

    n_stores   = subset['store_nbr'].nunique()
    n_families = subset['family'].nunique()
    n_days     = subset['date'].nunique()
    print(f'裁剪完成：{len(subset):,} 行 → {OUTPUT_PATH}')
    print(f'  门店：{sorted(subset["store_nbr"].unique())}  ({n_stores} 家)')
    print(f'  品类：{n_families} 个')
    print(f'  日期：{subset["date"].min().date()} 至 {subset["date"].max().date()}  ({n_days} 天)')

    expected = n_stores * n_families * n_days
    if len(subset) != expected:
        print(f'  注意：实际 {len(subset):,} 行 ≠ 预期 {expected:,} 行（部分日期/品类缺失，正常）')

    missing_files = []
    for fname in ['holidays_events.csv', 'stores.csv']:
        if not os.path.exists(os.path.join(RAW_DIR, fname)):
            missing_files.append(fname)
    if missing_files:
        print(f'  警告：以下辅助文件未找到，请确认已解压：{missing_files}')
    else:
        print('  辅助文件 holidays_events.csv 和 stores.csv 均已就位')


if __name__ == '__main__':
    prepare()
