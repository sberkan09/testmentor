import sys, re, os, collections, json

d = sys.argv[1]
out = {}
alltc = 0
for fn in sorted(os.listdir(d)):
    t = open(os.path.join(d, fn), encoding="utf-8", errors="replace").read()
    m = re.search(r"Test cases of Feature (\d+)\s*\n\s*\((.*?)\)", t)
    feat, title = (m.group(1), m.group(2)) if m else (fn, "?")
    tot = re.search(r"Total:\s*(\d+) Test case", t)
    ntc = int(tot.group(1)) if tot else 0
    alltc += ntc
    # split by test case
    parts = re.split(r"\nTest case (\d+)\s*\nIDENTIFICATION", t)
    tcs = []
    for i in range(1, len(parts), 2):
        body = parts[i + 1]
        # Based on requirements section up to METHOD OF TEST
        b = body.split("METHOD OF TEST")[0]
        refs = re.findall(r"Subset-026-(\d+(?:\.\d+)+)", b)
        # exclude refs in brackets after Subset-153? keep simple: unique
        steps = re.split(r"SEQUENCE OF TEST", body)
        nsteps = 0
        if len(steps) > 1:
            seq = steps[1].split("END CONDITIONS")[0]
            nsteps = len(re.findall(r"^\s{0,8}(\d{1,3})\s{2,}", seq, re.M))
        tcs.append({"no": parts[i], "refs": sorted(set(refs)), "nsteps": nsteps})
    out[feat] = {"title": title, "ntc": ntc, "tcs": tcs}
json.dump(out, open(sys.argv[2], "w"), indent=1)
print(
    "features",
    len(out),
    "testcases(total field)",
    alltc,
    "parsed",
    sum(len(v["tcs"]) for v in out.values()),
)
