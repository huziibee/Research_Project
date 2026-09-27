"""Regenerate intent-only figures and low-risk routing table for the report."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(r"C:\Users\huzii\Documents\University\Research Project")
REPORT_FIGS = Path(r"C:\Users\huzii\Documents\University\Research Report\figures")
VAULT_FIGS = ROOT / "latest results" / "figures"
RESULTS_FIGS = ROOT / "results" / "figures"
OUTS = [REPORT_FIGS, VAULT_FIGS, RESULTS_FIGS]
for d in OUTS:
    d.mkdir(parents=True, exist_ok=True)


def save(fig, name: str) -> None:
    for d in OUTS:
        fig.savefig(d / name, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", name)


def style(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="x", linestyle=":", linewidth=0.6, alpha=0.7)
    ax.set_axisbelow(True)


# --- Figure 1: intent box automatic overlap only ---
fig, ax = plt.subplots(figsize=(14.5, 6.2))
rows = [
    ("Raw Qwen — automatic overlap on intent_summary", 120, "#1f4e79"),
    ("Fine-tune — automatic overlap on intent_summary", 119, "#2f6aa3"),
    ("New goal-first — automatic overlap on intent_summary", 112, "#2e7d32"),
]
y = list(range(len(rows)))[::-1]
bars = ax.barh(y, [r[1] for r in rows], color=[r[2] for r in rows], height=0.58, edgecolor="white")
ax.set_yticks(y)
ax.set_yticklabels([r[0] for r in rows], fontsize=11)
ax.set_xlim(0, 128)
ax.set_xlabel("Commands out of 120 (same field: intent_summary)", fontsize=12)
ax.set_title(
    "Intent screen on dedicated job boxes only (Jaccard ≥ 0.18).\n"
    "Official primary remains two-judge: Raw 113, Fine-tune 107, Goal-first 113.",
    loc="left",
    fontsize=13,
    pad=10,
)
for bar, val in zip(bars, [r[1] for r in rows]):
    ax.text(val + 1.0, bar.get_y() + bar.get_height() / 2, f"{val}/120", va="center", fontsize=11)
ax.axvline(120, color="#888", linewidth=0.8, linestyle="--")
style(ax)
fig.tight_layout()
save(fig, "intent-primary-wide.png")

# --- Figure 2: intent (two-judge / box) vs routing ---
fig, axes = plt.subplots(1, 2, figsize=(15.5, 6.5))
systems = [
    ("Raw Qwen", 113, 88),
    ("Fine-tune", 107, 87),
    ("Goal-first", 113, 54),
]
x = range(len(systems))
w = 0.36
axes[0].bar([i - w / 2 for i in x], [s[1] for s in systems], width=w, label="Two-judge intent", color="#1f4e79")
axes[0].bar([i + w / 2 for i in x], [s[2] for s in systems], width=w, label="Routing", color="#b36b00")
axes[0].set_xticks(list(x))
axes[0].set_xticklabels([s[0] for s in systems])
axes[0].set_ylim(0, 130)
axes[0].set_ylabel("Correct / 120")
axes[0].set_title("Official intent vs secondary routing")
axes[0].legend(frameon=False)
style(axes[0])

# right: dissociation stack for goal-first automatic screen
axes[1].bar(["Intent yes\n& route yes", "Intent yes\n& route no", "Intent no\n& route yes", "Intent no\n& route no"],
            [50, 62, 4, 4], color=["#2e7d32", "#c62828", "#90a4ae", "#546e7a"])
axes[1].set_title("Goal-first automatic screen × routing")
axes[1].set_ylabel("Rows")
style(axes[1])
fig.tight_layout()
save(fig, "intent-vs-route-wide.png")

# --- heatmap again ---
mat = [[50, 62], [4, 4]]
fig, ax = plt.subplots(figsize=(7.2, 4.8))
im = ax.imshow(mat, cmap=plt.cm.Blues, vmin=0, vmax=70)
for i in range(2):
    for j in range(2):
        v = mat[i][j]
        ax.text(j, i, str(v), ha="center", va="center", fontsize=22,
                color="white" if v >= 35 else "#0b1f33",
                fontweight="bold" if (i, j) == (0, 1) else "normal")
ax.set_xticks([0, 1], ["Routing correct", "Routing wrong"])
ax.set_yticks([0, 1], ["Intent yes", "Intent no"])
ax.set_title("Goal-first automatic-overlap × routing (N = 120)")
fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04).set_label("Row count")
fig.tight_layout()
save(fig, "intent-routing-heatmap-wide.png")

# --- low-risk routing ---
gold = [json.loads(l) for l in (ROOT / "data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
risk = {}
rp = ROOT / "data/annotations/pilot_120_v1/pilot_120_gold_risk_official.jsonl"
for l in rp.read_text(encoding="utf-8").splitlines():
    if not l.strip():
        continue
    r = json.loads(l)
    risk[r["record_id"]] = str(r.get("gold_risk_level") or r.get("risk_level") or "").lower()
print("risk_counts", Counter(risk.values()))
low_ids = {rid for rid, v in risk.items() if v == "low"}
gold_route = {}
for r in gold:
    gold_route[r["record_id"]] = r.get("terminal_strategy") or r.get("gold_terminal_strategy")


def load_routes(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for l in path.read_text(encoding="utf-8").splitlines():
        if not l.strip():
            continue
        r = json.loads(l)
        route = r.get("terminal_strategy") or r.get("predicted_terminal_strategy")
        if route is None and isinstance(r.get("parsed"), dict):
            route = r["parsed"].get("terminal_strategy")
        if route is None and isinstance(r.get("prediction"), dict):
            route = r["prediction"].get("terminal_strategy")
        out[r["record_id"]] = route
    return out


def low_acc(routes: dict[str, str]) -> tuple[int, int]:
    ok = sum(1 for rid in low_ids if routes.get(rid) == gold_route.get(rid))
    return ok, len(low_ids)


mgr = {
    "goal_first": ROOT / "outputs/cluster_pulls/r1_manager/predictions/goal_first_manager_v2.predictions.jsonl",
    "degree": ROOT / "outputs/cluster_pulls/r1_manager/predictions/degree_based_router_v2.predictions.jsonl",
    "timid": ROOT / "outputs/cluster_pulls/r1_manager/predictions/rich_conservative_manager_v2.predictions.jsonl",
    "blind": ROOT / "outputs/cluster_pulls/r1_manager/predictions/goal_first_context_blind_v2.predictions.jsonl",
}
low_table = {}
for name, path in mgr.items():
    ok, n = low_acc(load_routes(path))
    low_table[name] = {"correct": ok, "n": n, "rate": ok / n if n else None}
    print(name, ok, n)

# raw/ft: search non-intent-box preds
raw_paths = sorted((ROOT / "outputs").rglob("*direct_base*.predictions.jsonl"))
ft_paths = sorted((ROOT / "outputs").rglob("*t28_selected*.predictions.jsonl"))
# prefer review_bundles / t39 style without intent_box in path
def pick(paths):
    for p in paths:
        s = str(p).replace("\\", "/")
        if "intent_box" in s:
            continue
        return p
    return paths[0] if paths else None

raw_p = pick(raw_paths)
ft_p = pick(ft_paths)
print("raw_p", raw_p)
print("ft_p", ft_p)
if raw_p:
    ok, n = low_acc(load_routes(raw_p))
    low_table["raw"] = {"correct": ok, "n": n, "rate": ok / n if n else None, "path": str(raw_p)}
    print("raw", ok, n)
if ft_p:
    ok, n = low_acc(load_routes(ft_p))
    low_table["fine_tune"] = {"correct": ok, "n": n, "rate": ok / n if n else None, "path": str(ft_p)}
    print("ft", ok, n)

out = ROOT / "outputs/cluster_pulls/final_close_20260913/low_risk_routing_accuracy.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"n_low": len(low_ids), "risk_counts": dict(Counter(risk.values())), "systems": low_table}, indent=2) + "\n", encoding="utf-8")
print("saved", out)
