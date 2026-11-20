import sys, re, json, collections, os

o = json.load(open(sys.argv[1]))
ref = collections.Counter(r for v in o.values() for tc in v["tcs"] for r in tc["refs"])
srs = {}
for fn in sys.argv[2:]:
    for line in open(fn, encoding="utf-8", errors="replace"):
        m = re.match(r"^\s{0,3}(\d\.\d+(?:\.\d+){2,6})\s+([A-Z(a-z\[\"].*)$", line)
        if m and "....." in line:
            m = None
        if m:
            k, txt = m.group(1), m.group(2).strip()
            if k not in srs:
                srs[k] = txt


def classify(t):
    if t.startswith("Intentionally deleted"):
        return "del"
    if t.startswith("Note") or t.startswith("Justification"):
        return "note"
    if re.search(r"\bshall\b", t):
        return "shall"
    return "other"


sec = collections.defaultdict(lambda: collections.Counter())
for k, t in srs.items():
    s = ".".join(k.split(".")[:2])
    c = classify(t)
    sec[s][c] += 1
    sec[s]["all"] += 1
    # covered: clause or any ancestor/descendant referenced
    if k in ref:
        sec[s]["cov_exact"] += 1
    if c == "shall" and k in ref:
        sec[s]["cov_shall"] += 1
for s in sorted(sec, key=lambda x: [int(p) for p in x.split(".")]):
    c = sec[s]
    if c["all"] >= 15:
        print(
            f"{s:6} all={c['all']:4} shall1st={c['shall']:4} note={c['note']:3} del={c['del']:3} cov_exact={c['cov_exact']:4} cov_shall={c['cov_shall']:4}"
        )
json.dump(srs, open(os.path.join(os.path.dirname(sys.argv[1]), "srs_clauses.json"), "w"))
