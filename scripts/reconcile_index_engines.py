from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]

def _legacy(path: Path):
    df=pd.read_csv(path); df['date']=pd.to_datetime(df['date']); return df

def main():
    out=ROOT/'data'/'processed'; legacy=_legacy(out/'rally_quarterly_indices.csv'); tr=_legacy(out/'index_portfolio_history.csv')
    rows=[]
    cats=['all']+sorted([c for c in tr['category'].dropna().astype(str).unique() if c!='all'])
    for cat in cats:
        lcat=legacy[legacy['category'].astype(str).eq(cat)]
        tcat=tr[(tr['category'].astype(str).eq(cat)) & (tr['rebalance_frequency'].astype(str).eq('monthly'))]
        for d in sorted(set(lcat['date']).intersection(set(tcat['date']))):
            leq=lcat[(lcat.date.eq(d)) & (lcat.weighting_method.eq('equal'))]
            lcap=lcat[(lcat.date.eq(d)) & (lcat.weighting_method.eq('market_cap'))]
            teq=tcat[(tcat.date.eq(d)) & (tcat.weighting_method.eq('equal_weight'))]
            tcap=tcat[(tcat.date.eq(d)) & (tcat.weighting_method.eq('market_cap_weight'))]
            rows.append({'date':d.date().isoformat(),'universe':'full_market' if cat=='all' else 'category','category':cat,'index_explorer_equal_weight': leq.index_level.iloc[-1] if not leq.empty else pd.NA,'total_return_equal_weight': teq.index_level.iloc[-1] if not teq.empty else pd.NA,'equal_weight_difference': (leq.index_level.iloc[-1] if not leq.empty else pd.NA) - (teq.index_level.iloc[-1] if not teq.empty else pd.NA),'index_explorer_cap_weight': lcap.index_level.iloc[-1] if not lcap.empty else pd.NA,'total_return_cap_weight': tcap.index_level.iloc[-1] if not tcap.empty else pd.NA,'cap_weight_difference': (lcap.index_level.iloc[-1] if not lcap.empty else pd.NA) - (tcap.index_level.iloc[-1] if not tcap.empty else pd.NA),'index_explorer_constituent_count': leq.constituent_count.iloc[-1] if not leq.empty else pd.NA,'total_return_constituent_count': teq.active_constituent_count.iloc[-1] if not teq.empty else pd.NA,'index_explorer_cash':0,'total_return_cash':teq.cash_value.iloc[-1] if not teq.empty else pd.NA,'rebalance_flag':teq.rebalance_flag.iloc[-1] if not teq.empty else pd.NA,'difference_reason':'legacy_quarterly_observed_rows_no_fill_vs_exit_aware_monthly_portfolio'})
    pd.DataFrame(rows).to_csv(out/'index_engine_reconciliation.csv',index=False)
if __name__=='__main__': main()
