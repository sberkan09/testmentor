import sys, re, os, json
d = sys.argv[1]; out = {}
SUF = r'(?: table - Condition Id \[\d+\]| table - [A-Z][^\n\[]{0,60}?(?=\s{3,}|\n|$)| [SDA]\d{1,3}(?: [a-z]\))?| - Following [^\n]{0,30}?(?=\s{3,}|\n|$))?'
R = re.compile(r'Subset-026-(\d+(?:\.\d+)+(?: [a-z]\))*)' + '(' + SUF + ')')
for fn in sorted(os.listdir(d)):
    t = open(os.path.join(d, fn), encoding='utf-8', errors='replace').read()
    m = re.search(r'Test cases of Feature (\d+)', t); feat = m.group(1)
    parts = re.split(r'\nTest case (\d+)\s*\nIDENTIFICATION', t)
    tcs = []
    for i in range(1, len(parts), 2):
        body = parts[i+1]
        deleted = bool(re.search(r'Test Case of Feature\s+Intentionally deleted', body[:1500]))
        b = body.split('METHOD OF TEST')[0]
        # drop bracketed duplicates after Subset-153 refs
        b2 = re.sub(r'\[Subset-026-[^\]]*\]?', '', b)
        refs = sorted(set((a + s).strip() for a, s in R.findall(b2)))
        seq = body.split('SEQUENCE OF TEST')[1].split('END CONDITIONS')[0] if 'SEQUENCE OF TEST' in body else ''
        steplines = [l for l in seq.split('\n') if re.match(r'^\s{0,8}\d{1,3}\s{2,}', l)]
        io = [re.search(r'\s(I/O|I|O|-)\s{2,}([A-Z]{2,5}|-)\s', l) for l in steplines]
        nI = sum(1 for x in io if x and x.group(1) in ('I','I/O'))
        nO = sum(1 for x in io if x and x.group(1) in ('O','I/O'))
        useft = len(re.findall(r'Use_FT\d+\.\d+', seq))
        tcs.append(dict(no=parts[i], deleted=deleted, refs=refs, nsteps=len(steplines), nI=nI, nO=nO, useft=useft))
    out[feat] = tcs
json.dump(out, open(sys.argv[2], 'w'), indent=0)
live = [tc for v in out.values() for tc in v if not tc['deleted']]
print('parsed tcs', sum(len(v) for v in out.values()), 'live', len(live), 'live_no_refs', sum(1 for x in live if not x['refs']))
