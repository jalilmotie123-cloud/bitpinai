import csv, io, math, os, statistics
from bisect import bisect_left
from datetime import datetime, timezone

HORIZONS=(300,900,1800,3600,7200,14400,21600,43200,86400)
SLIPPAGE_BPS=(0,5,10,20,30)
FEE_SIDE=0.0035
FILES=("market_data_v2.csv","market_data_v3.csv","matches_clean.csv","tradeflow_features_v3.csv")
SYMBOLS={"SOL_USDT","SOL/USDT","SOL-USDT","SOLUSDT"}
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def n(v):
    try:
        x=float(v); return x if math.isfinite(x) else None
    except: return None

def ts(v):
    x=n(v)
    if x is not None:
        if abs(x)>100000000000: return x/1000.0
        if abs(x)>1000000000: return x
    s=str(v or "").strip()
    for f in ("%Y-%m-%d %H:%M:%S.%f","%Y-%m-%d %H:%M:%S","%Y-%m-%dT%H:%M:%S.%f","%Y-%m-%dT%H:%M:%S"):
        try: return datetime.strptime(s,f).replace(tzinfo=timezone.utc).timestamp()
        except ValueError: pass
    return None

def val(r,names):
    d={str(k).lower():v for k,v in r.items()}
    for k in names:
        if k.lower() in d: return d[k.lower()]
    return None

def read(path):
    raw=open(path,"rb").read(); nul=raw.count(b"\0")
    raw=raw.replace(b"\0",b"")
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig",errors="replace")))),nul

def sol(r):
    s=val(r,("symbol","market","pair","ticker"))
    return s is None or str(s).strip().upper() in SYMBOLS

def q(a,p):
    if not a:return None
    a=sorted(a); z=(len(a)-1)*p; i=int(z); j=min(i+1,len(a)-1)
    return a[i]+(a[j]-a[i])*(z-i)

def st(a):
    if not a:return {"N":0}
    return {"N":len(a),"mean":statistics.mean(a),"median":statistics.median(a),
            "p10":q(a,.10),"p25":q(a,.25),"p50":q(a,.50),"p75":q(a,.75),
            "p90":q(a,.90),"p95":q(a,.95),"p99":q(a,.99),
            "win":sum(x>0 for x in a)/len(a)}

def audit(path):
    z={"file":os.path.basename(path),"exists":os.path.exists(path)}
    if not z["exists"]: return z
    rows,nul=read(path); z["rows"]=len(rows); z["nul_bytes"]=nul
    if not rows:return z
    keys=list(rows[0]); tk=next((k for k in keys if k.lower() in ("time","timestamp","datetime","date")),None)
    ik=next((k for k in keys if k.lower() in ("id","trade_id","event_id")),None)
    pk=next((k for k in keys if k.lower() in ("price","last_price")),None)
    bk=next((k for k in keys if k.lower()=="bid"),None); ak=next((k for k in keys if k.lower()=="ask"),None)
    times=[]; ids=[]; missing=badp=badba=0
    for r in rows:
        missing += sum(v is None or str(v).strip()=="" for v in r.values())
        t=ts(r.get(tk)) if tk else None
        if t is not None: times.append(t)
        if ik and r.get(ik): ids.append(str(r[ik]).strip())
        if pk: badp += int((lambda x:x is None or x<=0)(n(r.get(pk))))
        if bk or ak:
            b=n(r.get(bk)) if bk else None; a=n(r.get(ak)) if ak else None
            badba += int(b is None or a is None or b<=0 or a<=0 or a<b)
    times.sort(); gaps=[b-a for a,b in zip(times,times[1:]) if b>=a]
    z.update(start=datetime.fromtimestamp(min(times),timezone.utc).isoformat() if times else None,
             end=datetime.fromtimestamp(max(times),timezone.utc).isoformat() if times else None,
             duration_sec=max(times)-min(times) if times else None,
             duplicate_timestamps=len(times)-len(set(times)),
             duplicate_ids=len(ids)-len(set(ids)),missing_values=missing,
             invalid_prices=badp,invalid_bid_ask=badba,
             timestamp_ordering="NONDECREASING",median_interval=statistics.median(gaps) if gaps else None,
             p90_interval=q(gaps,.90),p95_interval=q(gaps,.95),p99_interval=q(gaps,.99),
             max_gap=max(gaps) if gaps else None)
    return z

def market(path):
    rows,_=read(path); out=[]
    for r in rows:
        if not sol(r):continue
        t=ts(val(r,("time","timestamp","datetime","date"))); b=n(val(r,("bid",))); a=n(val(r,("ask",)))
        if t is None or b is None or a is None or b<=0 or a<=0 or a<b:continue
        out.append((t,b,a,(a+b)/2))
    out.sort(); seen=set(); return [x for x in out if not (x[0] in seen or seen.add(x[0]))]

def align_signals(market,path):
    if not os.path.exists(path):return []
    rows,_=read(path); mt=[x[0] for x in market]; d=[]
    for r in rows:
        if not sol(r):continue
        t=ts(val(r,("time","timestamp","datetime","date")))
        if t is None:continue
        j=bisect_left(mt,t)
        if j<len(mt):d.append(mt[j]-t)
    return d

def points(m,h):
    t=[x[0] for x in m]; out=[]
    for i,e in enumerate(m):
        j=bisect_left(t,e[0]+h,i+1)
        if j>=len(m):break
        x=m[j]
        mid=x[3]/e[3]-1
        execgross=x[1]/e[2]-1
        net=x[1]*(1-FEE_SIDE)/(e[2]*(1+FEE_SIDE))-1
        spread=(1+mid)/(1+execgross)-1
        out.append((e[0],mid,execgross,net,spread))
    return out

def mfe_mae(m,h):
    t=[x[0] for x in m]; out=[]
    for i,e in enumerate(m):
        j=bisect_left(t,e[0]+h,i+1)
        if j>=len(m):break
        hi=max(x[1] for x in m[i+1:j+1]); lo=min(x[1] for x in m[i+1:j+1])
        out.append((hi/e[2]-1,lo/e[2]-1))
    return out

def block(t,a,b): return min(3,int((t-a)/((b-a)/4)))

def main():
    paths={f:os.path.join(ROOT,f) for f in FILES}
    audits=[audit(p) for p in paths.values()]
    choices=[]
    for f in ("market_data_v2.csv","market_data_v3.csv"):
        if os.path.exists(paths[f]):
            m=market(paths[f]); choices.append((len(m),f,m))
    if not choices: raise SystemExit("NO_VALID_MARKET_DATA")
    _,mname,m=max(choices,key=lambda x:x[0])
    report=["FEASIBILITY AUDIT V1 — READ-ONLY SOL RESEARCH",
            "Canonical market source: %s (%d valid SOL snapshots)"%(mname,len(m)),
            "fee_side=0.0035 per side; configurable assumption, not verified market truth.",
            "slippage sensitivity: exactly 0/5/10/20/30 bps.",
            "Short execution: INCONCLUSIVE unless supplied data proves executable short/margin mechanics.",
            "DATA AUDIT"]
    report += [repr(x) for x in audits]
    delays=align_signals(m,paths["tradeflow_features_v3.csv"])
    report += ["CANONICAL TIMELINE",
               "signal_time uses tradeflow_features_v3 when present; entry_snapshot_time is first market snapshot at/after signal_time.",
               "signal-to-entry delay stats: "+repr(st(delays)) if delays else "signal-to-entry delay: UNAVAILABLE"]
    fields=["section","horizon_sec","block","regime","slippage_bps","N","gross_mean","gross_median","fee_cost","spread_cost_mean","net_mean","net_median","win_rate","p25","p75","p90","p95"]
    rows=[]
    start,end=m[0][0],m[-1][0]
    for h in HORIZONS:
        p=points(m,h); gross=[x[1] for x in p]; spread=[x[4] for x in p]
        report += ["","HORIZON %ss N=%d"%(h,len(p)),
                   "A Gross(mid-to-mid): "+repr(st(gross)),
                   "B Gross-Fee: fee is applied multiplicatively to mid-to-mid.",
                   "C Gross-Fee-Spread: executable ASK-to-future-BID.",
                   "Gross >0.25/0.50/0.75/1.00: "+repr({v:sum(x>v/100 for x in gross)/len(gross) if gross else 0 for v in (.25,.5,.75,1.0)}),
                   "MFE: "+repr(st([x[0] for x in mfe_mae(m,h)])),
                   "MAE: "+repr(st([x[1] for x in mfe_mae(m,h)]))]
        for slip in SLIPPAGE_BPS:
            a=[x[3]-slip/10000 for x in p]; s=st(a)
            rows.append(["horizon",h,"ALL","ALL",slip,s["N"],statistics.mean(gross) if gross else None,statistics.median(gross) if gross else None,((1+FEE_SIDE)**2-1),statistics.mean(spread) if spread else None,s.get("mean"),s.get("median"),s.get("win"),s.get("p25"),s.get("p75"),s.get("p90"),s.get("p95")])
        for b in range(4):
            z=[x for x in p if block(x[0],start,end)==b]; a=[x[3] for x in z]; s=st(a)
            rows.append(["block",h,b+1,"ALL",0,s["N"],statistics.mean([x[1] for x in z]) if z else None,statistics.median([x[1] for x in z]) if z else None,((1+FEE_SIDE)**2-1),statistics.mean([x[4] for x in z]) if z else None,s.get("mean"),s.get("median"),s.get("win"),s.get("p25"),s.get("p75"),s.get("p90"),s.get("p95")])
        q1,q2=q([x[2] for x in p],1/3),q([x[2] for x in p],2/3)
        for rg,lo,hi in (("LOW",None,q1),("MEDIUM",q1,q2),("HIGH",q2,None)):
            z=[x for x in p if (lo is None or x[2]>=lo) and (hi is None or x[2]<=hi)]; a=[x[3] for x in z]; s=st(a)
            rows.append(["regime",h,"ALL",rg,0,s["N"],statistics.mean([x[1] for x in z]) if z else None,statistics.median([x[1] for x in z]) if z else None,((1+FEE_SIDE)**2-1),statistics.mean([x[4] for x in z]) if z else None,s.get("mean"),s.get("median"),s.get("win"),s.get("p25"),s.get("p75"),s.get("p90"),s.get("p95")])
    report += ["","DECISION FRAMEWORK"]
    for h in HORIZONS:
        p=points(m,h); a=[x[3]-.002 for x in p]; s=st(a); bm=[]
        for b in range(4):bm.append(st([x[3]-.002 for x in p if block(x[0],start,end)==b]).get("mean"))
        status="INCONCLUSIVE" if s["N"]<100 else ("GO-FOR-FURTHER-RESEARCH" if s["mean"]>0 and all(x is not None and x>0 for x in bm) else "NO-GO")
        report.append("%ss: %s | N=%d | net_mean@20bps_slip=%s | blocks=%s"%(h,status,s["N"],s["mean"],bm))
    report += ["","FINAL","Gross opportunity is measured directly across all valid SOL snapshots at the nine requested horizons.",
               "Post-cost opportunity is evaluated with fee, executable spread, and exactly five slippage sensitivities.",
               "No ML, strategy, threshold sweep, TP/SL optimization, live execution, or collector modification was performed.",
               "Opportunity Engine is not justified by this audit unless a stable positive post-cost edge is evidenced."]
    out=os.path.join(ROOT,"research"); os.makedirs(out,exist_ok=True)
    with open(os.path.join(out,"feasibility_results.csv"),"w",newline="",encoding="utf-8") as f:
        w=csv.writer(f);w.writerow(fields);w.writerows(rows)
    with open(os.path.join(out,"feasibility_report.txt"),"w",encoding="utf-8") as f:f.write("\n".join(report)+"\n")

if __name__=="__main__": main()
