import csv, math, statistics
from datetime import datetime

INPUT = 'matches_clean.csv'
WINDOWS = (30, 60, 120)
HORIZONS = (30, 60, 120, 300)
TRAIN_FRAC = 0.70
FEE_RT_PCT = 0.70

def ts(x):
    try: return float(x)
    except: return datetime.fromisoformat(x.replace('Z','+00:00')).timestamp()

def pct(future, now): return (future/now - 1)*100 if now else float('nan')

def qtile(v,q):
    v=sorted(v)
    if not v:return 0.0
    p=(len(v)-1)*q; a=int(p); b=min(a+1,len(v)-1); return v[a]+(v[b]-v[a])*(p-a)

def load():
    out=[]; seen=set()
    with open(INPUT,encoding='utf-8-sig',newline='') as f:
        r=csv.DictReader(f)
        for x in r:
            if x['id'] in seen: continue
            seen.add(x['id'])
            try:
                row=(ts(x['time']),float(x['price']),float(x['quote_amount']),x['side'].strip().lower())
                if row[3] in ('buy','sell') and all(math.isfinite(z) for z in row[:3]) and row[1]>0: out.append(row)
            except: pass
    out.sort(key=lambda z:z[0]); return out

def feat(a,i,w):
    t=a[i][0]; j=i; b=s=n=0.0; bn=sn=0; sizes=[]
    while j>=0 and t-a[j][0]<=w:
        _,_,q,side=a[j]; sizes.append(q)
        if side=='buy': b+=q; bn+=1
        else: s+=q; sn+=1
        j-=1
    tot=b+s; cnt=bn+sn
    if tot<=0 or cnt==0:return None
    sv=sorted(sizes); p90=sv[int(.9*(len(sv)-1))]
    large=sum(q for q in sizes if q>=p90)/tot
    return {'delta_ratio':(b-s)/tot,'count_imb':(bn-sn)/cnt,'intensity':cnt/w,'large_ratio':large}

def future(a,i,h):
    t0,p0=a[i][0],a[i][1]; j=i+1; last=None
    while j<len(a) and a[j][0]-t0<=h: last=a[j][1]; j+=1
    return None if last is None else pct(last,p0)

a=load(); print('TRADE FLOW PROBE'); print('UNIQUE_ROWS:',len(a))
if len(a)<300: print('TOO FEW DATA'); raise SystemExit
split=int(len(a)*TRAIN_FRAC)
for w in WINDOWS:
    train=[]; test=[]
    for i in range(len(a)):
        f=feat(a,i,w)
        if f is not None: (train if i<split else test).append((i,f))
    print(f'\nWINDOW {w}s | train={len(train)} test={len(test)}')
    for name in ('delta_ratio','count_imb','intensity','large_ratio'):
        lo=qtile([f[name] for _,f in train],.1); hi=qtile([f[name] for _,f in train],.9)
        for side,sel in (('LONG',lambda z:z>=hi),('SHORT',lambda z:z<=lo)):
            chosen=[(i,f) for i,f in test if sel(f[name])]
            print(f'  {name} {side}: n={len(chosen)} p10={lo:.6g} p90={hi:.6g}')
            for h in HORIZONS:
                rs=[]
                for i,_ in chosen:
                    r=future(a,i,h)
                    if r is not None: rs.append(r if side=='LONG' else -r)
                if rs:
                    m=statistics.mean(rs); win=sum(x>0 for x in rs)/len(rs)*100; fee=m-FEE_RT_PCT
                    print(f'    H{h}s n={len(rs)} mean={m:+.4f}% win={win:.1f}% after_fee_screen={fee:+.4f}%')
print('\nNOTE: This is exploratory OOS and NOT executable PnL because matches_clean.csv has no bid/ask. No threshold tuning on test data.')
