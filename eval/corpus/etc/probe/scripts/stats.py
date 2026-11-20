import sys, json, collections, statistics

o = json.load(open(sys.argv[1]))
nrefs = [len(tc["refs"]) for v in o.values() for tc in v["tcs"]]
print(
    "refs/tc median",
    statistics.median(nrefs),
    "mean",
    round(statistics.mean(nrefs), 1),
    "zero",
    sum(1 for x in nrefs if x == 0),
    "one",
    sum(1 for x in nrefs if x == 1),
)
# per chapter (SUBSET-026 chapter.section) coverage: unique clauses referenced
clauses = collections.Counter()
for v in o.values():
    for tc in v["tcs"]:
        for r in tc["refs"]:
            clauses[r] += 1
bysec = collections.defaultdict(set)
for c in clauses:
    bysec[".".join(c.split(".")[:2])].add(c)
for s in sorted(bysec, key=lambda x: [int(p) for p in x.split(".")]):
    print(s, len(bysec[s]))
print("unique clauses", len(clauses))
# features listing with ntc
for f, v in o.items():
    print(f, v["ntc"], len(v["tcs"]), v["title"][:50])
