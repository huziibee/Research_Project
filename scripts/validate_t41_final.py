import json, sys
from pathlib import Path

p = Path(sys.argv[1])
rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
ids = [x["record_id"] for x in rows]
assert len(rows) == 120 and len(set(ids)) == 120
assert all(x.get("annotation_status") == "adjudicated" for x in rows)
assert sum(x["gold"]["clarification"]["required"] for x in rows) == 23
assert sum(x["gold"]["silent_resolution"]["permitted"] for x in rows) == 51
assert sum(x["gold"]["rejection"]["required"] for x in rows) == 21
assert all(x["gold"]["cpc"]["slots"] for x in rows)
for row in rows:
    assert not any(k in {"prediction", "raw_output", "model_output", "score"} for k in row)
    assert row["provenance"]
print(json.dumps({"status": "PASS", "records": len(rows), "clarification": 23, "silent_resolution": 51, "rejection": 21}))
