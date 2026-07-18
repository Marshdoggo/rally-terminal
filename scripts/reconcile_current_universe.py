from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from alt_asset_explorer.current_universe import build_current_asset_universe, calculate_current_universe_summary, latest_exchange_rows, normalize_asset_status, CANONICAL_STALENESS_DAYS
from alt_asset_explorer.market_table import build_market_table

def main():
    outdir=ROOT/'data'/'processed'; outdir.mkdir(parents=True, exist_ok=True)
    master=pd.read_csv(outdir/'canonical_asset_master.csv')
    decision=pd.read_csv(outdir/'rally_asset_decision_universe.csv')
    prices=pd.read_csv(outdir/'price_history.csv')
    exh=pd.read_csv(outdir/'exchange_asset_history.csv')
    market=build_market_table(master,decision,prices)
    home=market[market['is_current_listed'].fillna(False)].copy()
    latest=latest_exchange_rows(exh)
    canon=build_current_asset_universe(master,exh)
    rows=[]
    ids=sorted(set(home.asset_id.astype(str))|set(latest.asset_id.astype(str)))
    home_i=home.set_index('asset_id'); ex_i=latest.set_index('asset_id'); master_i=master.drop_duplicates('asset_id').set_index('asset_id')
    for aid in ids:
        h=home_i.loc[aid] if aid in home_i.index else pd.Series(dtype=object)
        e=ex_i.loc[aid] if aid in ex_i.index else pd.Series(dtype=object)
        m=master_i.loc[aid] if aid in master_i.index else pd.Series(dtype=object)
        hp=pd.to_numeric(pd.Series([h.get('last_price')]),errors='coerce').iloc[0]; hs=pd.to_numeric(pd.Series([h.get('shares_outstanding')]),errors='coerce').iloc[0]
        ep=pd.to_numeric(pd.Series([e.get('price')]),errors='coerce').iloc[0]; es=pd.to_numeric(pd.Series([e.get('shares_outstanding')]),errors='coerce').iloc[0]
        age=pd.to_numeric(pd.Series([e.get('observation_age_days')]),errors='coerce').iloc[0]
        reasons=[]
        if aid not in home_i.index: reasons.append('only_in_exchange_source')
        if aid not in ex_i.index: reasons.append('only_in_homepage_source')
        if pd.notna(age) and age>CANONICAL_STALENESS_DAYS: reasons.append('stale_price')
        if str(e.get('price_source',''))=='offering_price': reasons.append('offering_value_used_as_current_value')
        if pd.notna(hp) and pd.notna(ep) and abs(hp-ep)>1e-9: reasons.append('price_mismatch')
        if pd.notna(hs) and pd.notna(es) and abs(hs-es)>1e-9: reasons.append('share_count_mismatch')
        cs=normalize_asset_status(m.get('status'))
        if cs!='active_tradable': reasons.append('status_mismatch')
        if not reasons: reasons.append('reconciled')
        cm=(ep*es) if pd.notna(ep) and pd.notna(es) and (pd.isna(age) or age<=CANONICAL_STALENESS_DAYS) and str(e.get('price_source',''))!='offering_price' and cs=='active_tradable' else pd.NA
        rows.append({'asset_id':aid,'ticker':m.get('ticker',h.get('ticker',e.get('ticker'))),'asset_name':m.get('name',h.get('name',e.get('name'))),'category':m.get('category',h.get('category',e.get('category'))),'source_provenance':m.get('source_type'),'is_known_rally_asset':str(m.get('source_type',''))!='sec_synthesized','is_sample_or_fixture':False,'homepage_included':aid in home_i.index,'exchange_page_included':aid in ex_i.index,'homepage_status':h.get('status'),'exchange_status':e.get('is_active'),'canonical_status':cs,'homepage_price':hp,'exchange_price':ep,'canonical_current_price':ep if pd.notna(cm) else pd.NA,'homepage_shares':hs,'exchange_shares':es,'canonical_shares':es if pd.notna(cm) else pd.NA,'homepage_market_cap':pd.to_numeric(pd.Series([h.get('current_market_cap_usd')]),errors='coerce').iloc[0],'exchange_market_cap':pd.to_numeric(pd.Series([e.get('market_cap')]),errors='coerce').iloc[0],'canonical_market_cap':cm,'homepage_price_source':'latest_quote_or_decision_snapshot' if aid in home_i.index else pd.NA,'exchange_price_source':e.get('price_source'),'latest_observation_date':e.get('last_observation_date'),'observation_age_days':age,'offering_date':m.get('offering_date'),'last_trading_date':pd.NA,'exit_effective_date':pd.NA,'difference_reason':'|'.join(reasons),'recommended_action':'exclude_from_current_tradable_when_stale_or_offering_only' if any(r in reasons for r in ['stale_price','offering_value_used_as_current_value']) else 'no_action','data_quality_severity':'warning' if reasons!=['reconciled'] else 'info'})
    rec=pd.DataFrame(rows); rec.to_csv(outdir/'current_universe_reconciliation.csv',index=False)
    gap=(rec['exchange_market_cap'].fillna(0)-rec['homepage_market_cap'].fillna(0)).sum()
    contrib=rec.assign(difference=rec['exchange_market_cap'].fillna(0)-rec['homepage_market_cap'].fillna(0))
    contrib['difference_pct_of_total_gap']=contrib['difference']/gap if gap else 0
    contrib=contrib[['asset_id','ticker','asset_name','category','homepage_market_cap','exchange_market_cap','difference','difference_pct_of_total_gap','difference_reason','exchange_price_source','canonical_status','recommended_action']].sort_values('difference', key=lambda s:s.abs(), ascending=False)
    contrib.to_csv(outdir/'current_market_cap_difference_contributors.csv',index=False)
    pd.DataFrame([calculate_current_universe_summary(canon)]).to_csv(outdir/'current_universe_summary.csv', index=False)
if __name__=='__main__': main()
