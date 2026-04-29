import os
import json
import math
import uuid
import logging
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

from config import (
    DATA_RAW_DIR, DATA_PROC_DIR,
    COL_DATE, COL_STORE, COL_FAMILY, COL_SALES, COL_ONPROMO,
    TRAIN_RATIO, VAL_RATIO,
)

logger = logging.getLogger(__name__)

REQUIRED_COLS = [COL_DATE, COL_STORE, COL_FAMILY, COL_SALES]


class DataProcessor:
    def __init__(self, filepath: str, session_id: str = None):
        self.filepath   = filepath
        self.session_id = session_id or uuid.uuid4().hex
        self._df        = None
        self._events    = None

    # ── 加载 ──────────────────────────────────────────────────────

    def load(self) -> pd.DataFrame:
        ext = os.path.splitext(self.filepath)[1].lower()
        if ext == '.xls':
            raise ValueError('不支持 .xls 格式，请在 Excel 中另存为 .xlsx 再上传')
        if ext == '.xlsx':
            self._df = pd.read_excel(self.filepath, engine='openpyxl')
        else:
            self._df = self._read_csv_with_encoding(self.filepath)
        return self._df

    def _read_csv_with_encoding(self, path: str) -> pd.DataFrame:
        for enc in ('utf-8', 'utf-8-sig', 'gbk'):
            try:
                return pd.read_csv(path, encoding=enc)
            except (UnicodeDecodeError, Exception):
                continue
        raise ValueError('文件编码无法识别，请转存为 UTF-8 格式')

    # ── 校验 ─────────────────────────────────────────────��────────

    def validate(self) -> dict:
        df = self._df
        errors, warnings = [], []

        missing_cols = [c for c in REQUIRED_COLS if c not in df.columns]
        if missing_cols:
            errors.append(f'数据缺少必要列：{", ".join(missing_cols)}')

        if errors:
            return {'valid': False, 'errors': errors, 'warnings': warnings, 'stats': {}}

        try:
            pd.to_datetime(df[COL_DATE])
        except Exception:
            errors.append(f'列 "{COL_DATE}" 无法解析为日期格式')

        if not pd.to_numeric(df[COL_SALES], errors='coerce').notna().any():
            errors.append(f'列 "{COL_SALES}" 无法转换为数值')

        if errors:
            return {'valid': False, 'errors': errors, 'warnings': warnings, 'stats': {}}

        dup_mask = df.duplicated(subset=[COL_DATE, COL_FAMILY, COL_STORE], keep=False)
        dup_count = int(dup_mask.sum())
        if dup_count:
            warnings.append(f'检测到 {dup_count} 条重复行，已聚合求和')

        if (pd.to_numeric(df[COL_SALES], errors='coerce') < 0).any():
            warnings.append('存在负数销售量，将自动置零')

        has_onpromo = COL_ONPROMO in df.columns
        if has_onpromo and (pd.to_numeric(df[COL_ONPROMO], errors='coerce') < 0).any():
            warnings.append('存在负数促销量，将自动置零')

        date_col = pd.to_datetime(df[COL_DATE], errors='coerce')
        n_days = date_col.dt.date.nunique()
        if n_days < 90:
            warnings.append(f'数据量不足（{n_days} 天），预测精度可能偏低，建议至少 90 天')

        stats = {
            'rows':       len(df),
            'date_range': {
                'start': str(date_col.min().date()),
                'end':   str(date_col.max().date()),
                'days':  n_days,
            },
            'families':      sorted(df[COL_FAMILY].dropna().unique().tolist()),
            'stores':        sorted(df[COL_STORE].dropna().unique().tolist()),
            'missing_count': int(df.isnull().sum().sum()),
            'duplicate_rows': dup_count,
        }
        return {'valid': True, 'errors': errors, 'warnings': warnings, 'stats': stats}

    # ── 清洗主流程 ────────────────────────────────────────────────

    def clean(self) -> pd.DataFrame:
        df = self._df.copy()

        df[COL_DATE] = pd.to_datetime(df[COL_DATE], errors='coerce')
        df[COL_SALES] = pd.to_numeric(df[COL_SALES], errors='coerce')
        if COL_ONPROMO in df.columns:
            df[COL_ONPROMO] = pd.to_numeric(df[COL_ONPROMO], errors='coerce').fillna(0)

        df = df.sort_values([COL_STORE, COL_FAMILY, COL_DATE]).reset_index(drop=True)

        agg_dict = {COL_SALES: 'sum'}
        if COL_ONPROMO in df.columns:
            agg_dict[COL_ONPROMO] = 'sum'
        df = df.groupby([COL_DATE, COL_FAMILY, COL_STORE], as_index=False).agg(agg_dict)

        df[COL_SALES] = df[COL_SALES].clip(lower=0)
        if COL_ONPROMO in df.columns:
            df[COL_ONPROMO] = df[COL_ONPROMO].clip(lower=0)

        df = self.handle_missing(df)
        df = self.handle_outliers(df)

        self._df = df
        return df

    # ── 缺失值处理 ────────────────────────────────────────────────

    def handle_missing(self, df: pd.DataFrame) -> pd.DataFrame:
        def _fix_group(g: pd.DataFrame) -> pd.DataFrame:
            g = g.set_index(COL_DATE).sort_index()
            missing = g[COL_SALES].isna()
            consec_max = self._max_consecutive_missing(missing)

            if consec_max <= 7:
                g[COL_SALES] = g[COL_SALES].interpolate(method='time')
            elif consec_max <= 30:
                g[COL_SALES] = g[COL_SALES].ffill()
                monthly_mean = g[COL_SALES].groupby(g.index.month).transform('mean')
                g.loc[missing, COL_SALES] = monthly_mean[missing]
            else:
                median_val = g[COL_SALES].median()
                g[COL_SALES] = g[COL_SALES].fillna(median_val)
                key = f"{g[COL_FAMILY].iloc[0] if COL_FAMILY in g.columns else '?'}"
                logger.warning('序列 %s 缺失超过30天，已用中位数填充', key)

            if COL_ONPROMO in g.columns:
                g[COL_ONPROMO] = g[COL_ONPROMO].ffill().bfill().fillna(0)

            g[COL_SALES] = g[COL_SALES].fillna(0).clip(lower=0)
            return g.reset_index()

        results = []
        for (family, store), grp in df.groupby([COL_FAMILY, COL_STORE]):
            fixed = _fix_group(grp.copy())
            fixed[COL_FAMILY] = family
            fixed[COL_STORE]  = store
            results.append(fixed)

        return pd.concat(results, ignore_index=True)

    def _max_consecutive_missing(self, mask: pd.Series) -> int:
        max_run = 0
        run = 0
        for v in mask:
            if v:
                run += 1
                max_run = max(max_run, run)
            else:
                run = 0
        return max_run

    # ── 异常值处理 ────────────────────────────────────────────────

    def handle_outliers(self, df: pd.DataFrame) -> pd.DataFrame:
        events = self._load_events()
        df['is_event']   = False
        df['is_outlier'] = False

        def _fix_group(g: pd.DataFrame) -> pd.DataFrame:
            g = g.set_index(COL_DATE).sort_index()
            rolling_med = g[COL_SALES].rolling(7, center=True, min_periods=1).median()
            q1 = g[COL_SALES].quantile(0.25)
            q3 = g[COL_SALES].quantile(0.75)
            iqr_upper = q3 + 3.0 * (q3 - q1)

            for idx in g.index:
                date_str = idx.strftime('%Y-%m-%d')
                val = g.at[idx, COL_SALES]
                med = rolling_med.at[idx]
                on_event = date_str in events

                if on_event:
                    g.at[idx, 'is_event'] = True
                    continue

                if med > 0 and val > med * 10 and val > iqr_upper:
                    window = g[COL_SALES].iloc[
                        max(0, g.index.get_loc(idx) - 3):
                        g.index.get_loc(idx) + 4
                    ]
                    neighbors = window.drop(labels=[idx], errors='ignore')
                    if (neighbors < val * 0.5).all():
                        g.at[idx, COL_SALES]   = float(med)
                        g.at[idx, 'is_outlier'] = True

            return g.reset_index()

        results = []
        for (family, store), grp in df.groupby([COL_FAMILY, COL_STORE]):
            fixed = _fix_group(grp.copy())
            fixed[COL_FAMILY] = family
            fixed[COL_STORE]  = store
            results.append(fixed)

        return pd.concat(results, ignore_index=True)

    def _load_events(self) -> set:
        path = os.path.join(DATA_RAW_DIR, 'holidays_events.csv')
        if not os.path.exists(path):
            return set()
        try:
            hdf = pd.read_csv(path, parse_dates=['date'])
            hdf = hdf[
                hdf['type'].isin(['Holiday', 'Event', 'Additional']) &
                (~hdf['transferred'].astype(bool))
            ]
            return set(hdf['date'].dt.strftime('%Y-%m-%d').tolist())
        except Exception as e:
            logger.warning('加载 holidays_events.csv 失败：%s，降级处理', e)
            return set()

    # ── 特征工程 ──────────────────────────────────────────────────

    def feature_engineering(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df[COL_DATE] = pd.to_datetime(df[COL_DATE])

        df['year']          = df[COL_DATE].dt.year
        df['month']         = df[COL_DATE].dt.month
        df['day']           = df[COL_DATE].dt.day
        df['weekday']       = df[COL_DATE].dt.dayofweek
        df['is_weekend']    = (df['weekday'] >= 5).astype(int)
        df['week_of_year']  = df[COL_DATE].dt.isocalendar().week.astype(int)
        df['quarter']       = df[COL_DATE].dt.quarter
        df['days_to_monthend'] = df[COL_DATE].dt.days_in_month - df[COL_DATE].dt.day

        events = self._load_events()
        df['is_holiday'] = df[COL_DATE].dt.strftime('%Y-%m-%d').isin(events).astype(int)

        for lag in [7, 14, 30]:
            col_lag = f'sales_lag{lag}'
            df[col_lag] = (
                df.groupby([COL_FAMILY, COL_STORE])[COL_SALES]
                .transform(lambda x: x.shift(lag))
            )
        for win in [7, 30]:
            col_roll = f'sales_rolling{win}_mean'
            df[col_roll] = (
                df.groupby([COL_FAMILY, COL_STORE])[COL_SALES]
                .transform(lambda x: x.rolling(win, min_periods=1).mean())
            )
        return df

    # ── 聚合 ──────────────────────────────────────────────────────

    def aggregate(self, df: pd.DataFrame) -> dict:
        df[COL_DATE] = pd.to_datetime(df[COL_DATE])
        daily_total = df.groupby(COL_DATE)[COL_SALES].sum()

        by_family = (
            df.groupby(COL_FAMILY)[COL_SALES].sum()
            .reset_index()
            .rename(columns={COL_SALES: 'total_sales'})
        )
        by_store = (
            df.groupby(COL_STORE)[COL_SALES].sum()
            .reset_index()
            .rename(columns={COL_SALES: 'total_sales'})
        )

        by_family_store = {}
        for (fam, store), grp in df.groupby([COL_FAMILY, COL_STORE]):
            series = grp.set_index(COL_DATE)[COL_SALES].sort_index()
            by_family_store[f'{fam}_{store}'] = series

        return {
            'daily_total':      daily_total,
            'by_family':        by_family,
            'by_store':         by_store,
            'by_family_store':  by_family_store,
        }

    # ── 时序切分 ──────────────────────────────────────────────────

    def split_timeseries(self, series: pd.Series):
        n       = len(series)
        n_train = int(n * TRAIN_RATIO)
        n_val   = int(n * VAL_RATIO)
        train = series.iloc[:n_train]
        val   = series.iloc[n_train:n_train + n_val]
        test  = series.iloc[n_train + n_val:]
        assert train.index.max() < val.index.min(), '时序切分顺序错误：train 与 val 重叠'
        assert val.index.max()   < test.index.min(), '时序切分顺序错误：val 与 test 重叠'
        return train, val, test

    # ── 归一化 ────────────────────────────────────────────────────

    def normalize(self, train: pd.Series, val: pd.Series, test: pd.Series):
        scaler = MinMaxScaler()
        scaler.fit(train.values.reshape(-1, 1))
        train_s = scaler.transform(train.values.reshape(-1, 1)).flatten()
        val_s   = scaler.transform(val.values.reshape(-1, 1)).flatten()
        test_s  = scaler.transform(test.values.reshape(-1, 1)).flatten()
        return train_s, val_s, test_s, scaler

    # ── 落盘 ──────────────────────────────────────────────────────

    def save_processed(self, df: pd.DataFrame, agg: dict) -> str:
        os.makedirs(DATA_PROC_DIR, exist_ok=True)
        sid = self.session_id

        clean_path       = os.path.join(DATA_PROC_DIR, f'clean_{sid}.csv')
        daily_total_path = os.path.join(DATA_PROC_DIR, f'daily_total_{sid}.csv')
        meta_path        = os.path.join(DATA_PROC_DIR, f'meta_{sid}.json')

        df.to_csv(clean_path, index=False)
        agg['daily_total'].to_csv(daily_total_path, header=True)

        summary = self._get_summary(df)
        meta = {
            'session_id':      sid,
            'created_at':      datetime.now().isoformat(),
            'created_timestamp': datetime.now().timestamp(),
            'clean_csv':       clean_path,
            'daily_total_csv': daily_total_path,
            'summary':         summary,
        }
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2, default=_json_default)

        return meta_path

    def _get_summary(self, df: pd.DataFrame) -> dict:
        df[COL_DATE] = pd.to_datetime(df[COL_DATE])
        from config import FAMILY_ZH_MAP

        families_info = []
        for fam, grp in df.groupby(COL_FAMILY):
            families_info.append({
                'name':        fam,
                'name_zh':     FAMILY_ZH_MAP.get(fam, fam),
                'total_sales': float(grp[COL_SALES].sum()),
            })

        replaced = int(df['is_outlier'].sum()) if 'is_outlier' in df.columns else 0
        kept     = int(df['is_event'].sum())   if 'is_event'   in df.columns else 0

        return {
            'total_rows':         len(df),
            'date_range': {
                'start': str(df[COL_DATE].min().date()),
                'end':   str(df[COL_DATE].max().date()),
                'days':  int(df[COL_DATE].dt.date.nunique()),
            },
            'families':           families_info,
            'family_count':       df[COL_FAMILY].nunique(),
            'stores':             sorted(df[COL_STORE].unique().tolist()),
            'store_count':        df[COL_STORE].nunique(),
            'missing_before':     0,
            'missing_after':      int(df[COL_SALES].isna().sum()),
            'outliers_replaced':  replaced,
            'outliers_kept':      kept,
            'completeness_rate':  1.0,
            'warnings':           [],
        }

    @staticmethod
    def load_processed(meta_path: str) -> pd.DataFrame:
        with open(meta_path, encoding='utf-8') as f:
            meta = json.load(f)
        return pd.read_csv(meta['clean_csv'], parse_dates=[COL_DATE])

    # ── 完整流水线（Flask 调用入口）────��─────────────────────────

    def process(self) -> tuple:
        self.load()
        validation = self.validate()
        if not validation['valid']:
            raise ValueError('; '.join(validation['errors']))
        df  = self.clean()
        agg = self.aggregate(df)
        meta_path = self.save_processed(df, agg)
        return meta_path, validation


def _json_default(obj):
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return None if (math.isnan(obj) or math.isinf(obj)) else float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (pd.Timestamp, datetime)):
        return str(obj)
    raise TypeError(f'Object of type {type(obj)} is not JSON serializable')
