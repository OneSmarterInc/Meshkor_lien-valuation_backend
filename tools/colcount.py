import csv, collections, sys
f = open(sys.argv[1], encoding="utf-8", errors="replace", newline="")
cnt = collections.Counter(); ex = {}
for i, row in enumerate(csv.reader(f), 1):
    n = len(row); cnt[n] += 1
    if n not in ex: ex[n] = (i, [c[:25] for c in row[:6]])
print("rows per column count:", dict(cnt))
for n, (i, r) in ex.items(): print(n, "first at line", i, r)
