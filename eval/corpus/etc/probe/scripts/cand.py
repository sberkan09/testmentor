import sys, json, re, statistics
o = json.load(open(sys.argv[1]))
def unit(r):
    m = re.match(r'(\d+(?:\.\d+)+)', r); n = m.group(1)
    c = re.search(r'Condition Id \[\d+\]', r)
    s = re.search(r' ([SDA]\d{1,3})\b', r)
    if c: return n + ' ' + c.group(0)
    if s and n.startswith('5.'): return n + ' ' + s.group(1)
    if 'table - ' in r: return n + ' table:' + r.split('table - ',1)[1][:40]
    return n
def inr(u, pres):
    n = u.split(' ')[0]
    return any(n == p or n.startswith(p + '.') for p in pres)
cands = {
 'A modes+transitions 4.4,4.6': ['4.4', '4.6'],
 'B SDM 3.13.8-3.13.11': ['3.13.8', '3.13.9', '3.13.10', '3.13.11'],
 'C radio+location 3.5,3.6': ['3.5', '3.6'],
 'D location/track/MA 3.6-3.8': ['3.6', '3.7', '3.8'],
 'E SoM 5.4': ['5.4'], 'A0 modes 4.4': ['4.4'],
}
for name, pres in cands.items():
    touch, inside, single = [], [], []
    for f, tcs in o.items():
        for tc in tcs:
            if tc['deleted'] or not tc['refs']: continue
            us = sorted(set(unit(r) for r in tc['refs']))
            k = [u for u in us if inr(u, pres)]
            if not k: continue
            touch.append((f, tc, us))
            if len(k) == len(us): inside.append((f, tc, us))
            if len(us) == 1: single.append((f, tc, us))
    U_touch = set(u for _, _, us in touch for u in us if inr(u, pres))
    U_in = set(u for _, _, us in inside for u in us)
    U_single = set(u for _, _, us in single for u in us)
    nI0 = sum(1 for _, tc, _ in inside if tc['nI'] == 0)
    uft = sum(1 for _, tc, _ in inside if tc['useft'] > 0)
    st = [tc['nsteps'] for _, tc, _ in inside]
    feats = sorted(set(f for f, _, _ in inside))
    print(f"{name}: TCs touching={len(touch)} inside-only={len(inside)} single-unit={len(single)} | units touched={len(U_touch)} units w/ inside-only TC={len(U_in)} units w/ single-ref TC={len(U_single)} | inside TCs: noI={nI0} useFT={uft} median steps={statistics.median(st) if st else 0} feats={len(feats)}")
