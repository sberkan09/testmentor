import sys, json, re, collections
o = json.load(open(sys.argv[1])); srs = json.load(open(sys.argv[2]))
ref = collections.Counter(r for v in o.values() for tc in v['tcs'] for r in tc['refs'])
tcs_by = collections.defaultdict(set)
for f,v in o.items():
    for tc in v['tcs']:
        for r in tc['refs']: tcs_by[r].add(f+'#'+tc['no'])
nt = set()
for l in open(sys.argv[3]):
    m = re.match(r'^\s{0,12}(\d\.\d+(?:\.\d+)+)\b', l)
    if m: nt.add(m.group(1))
def norm(t): return not (t.startswith('Intentionally') or t.startswith('Note') or t.startswith('Justification'))
for pre in sys.argv[4:]:
    groups = collections.defaultdict(lambda: [0,0,0,0])
    for k,t in srs.items():
        if not (k.startswith(pre+'.')): continue
        depth = len(pre.split('.'))+1
        g = '.'.join(k.split('.')[:depth])
        if k == g: continue  # heading
        groups[g][0]+=1
        if norm(t):
            groups[g][1]+=1
            if k in ref: groups[g][2]+=1
            if k in nt: groups[g][3]+=1
    tot=[0,0,0,0]
    for g in sorted(groups, key=lambda x:[int(p) for p in x.split('.')]):
        a=groups[g]; tot=[x+y for x,y in zip(tot,a)]
        print(f"  {g:10} numbered={a[0]:3} normative={a[1]:3} referenced={a[2]:3} in_T3={a[3]}")
    print(pre, 'TOTAL', tot)
