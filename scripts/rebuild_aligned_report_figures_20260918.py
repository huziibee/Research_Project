"""Regenerate misaligned report figures with pedantic labels and real temperature data."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPORT_FIGS = Path(r"C:\Users\huzii\Documents\University\Research Report\figures")
VAULT_FIGS = Path(r"C:\Users\huzii\Documents\University\Research Project\latest results\figures")
OUTS = [REPORT_FIGS, VAULT_FIGS]
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
    ax.grid(True, linestyle=":", linewidth=0.6, alpha=0.7)
    ax.set_axisbelow(True)


# --- Figure 1: T0 intent screen, explicitly labelled ---
fig, ax = plt.subplots(figsize=(14.5, 6.4))
rows = [
    ("Raw Qwen (T0 intent-box)", 120, "#1f4e79"),
    ("Fine-tune (T0 intent-box)", 119, "#2f6aa3"),
    ("Goal-first (T0 matched)", 112, "#2e7d32"),
]
y = list(range(len(rows)))[::-1]
bars = ax.barh(y, [r[1] for r in rows], color=[r[2] for r in rows], height=0.58, edgecolor="white")
ax.set_yticks(y)
ax.set_yticklabels([r[0] for r in rows], fontsize=11)
ax.set_xlim(0, 128)
ax.set_xlabel("Automatic-overlap screen correct / 120  (Jaccard ≥ 0.18 on intent_summary)", fontsize=11)
ax.set_title(
    "Figure layer: T0 matched-set automatic screen (not two-judge; not T0.7).\n"
    "Official two-judge at T0: Raw 113 = Goal-first 113 (Fine-tune 107).  "
    "At study default T0.7, shared GF auto screen = 117/120.",
    loc="left",
    fontsize=12,
    pad=10,
)
for bar, val in zip(bars, [r[1] for r in rows]):
    ax.text(val + 1.0, bar.get_y() + bar.get_height() / 2, f"{val}/120", va="center", fontsize=11)
ax.axvline(120, color="#888", linewidth=0.8, linestyle="--")
style(ax)
fig.tight_layout()
save(fig, "intent-primary-wide.png")


# --- Routing: T0 six-system + T0.7 managers side note in title ---
fig, ax = plt.subplots(figsize=(12.5, 6.2))
labels = [
    "Raw\nQwen",
    "Fine-\ntune",
    "Goal-\nfirst",
    "Degree",
    "Timid",
    "Context-\nblind",
]
# T0 matched (mechanism / six-system panel)
vals_t0 = [88, 87, 54, 59, 26, 21]
colors = ["#1f4e79", "#1f4e79", "#2e7d32", "#2e7d32", "#2e7d32", "#2e7d32"]
bars = ax.bar(range(len(labels)), vals_t0, color=colors, edgecolor="white")
ax.set_xticks(range(len(labels)))
ax.set_xticklabels(labels, fontsize=10)
ax.set_ylim(0, 120)
ax.set_ylabel("Routing correct / 120")
ax.set_title(
    "Routing correctness on the T0 matched set (mechanism panel).\n"
    "Study-default T0.7 managers (unified): GF 54 · Degree 57 · Timid 29 · Blind 21.  "
    "Raw/FT have no matched T0.7 routing emit yet.",
    loc="left",
    fontsize=12,
    pad=10,
)
for b, v in zip(bars, vals_t0):
    ax.text(b.get_x() + b.get_width() / 2, v + 2, f"{v}/120", ha="center", fontsize=10)
style(ax)
fig.tight_layout()
save(fig, "routing-correct-wide.png")


# --- Temperature line graph with REAL numbers ---
# Routing (prefer unified where available)
temps = [0.0, 0.3, 0.5, 0.7, 1.0]
gf_route = [49, 47, 51, 54, 42]  # 0.0 unified; 0.3 mega; 0.5/0.7/1.0 unified
deg_route = [57, 56, 69, 57, 54]
# Intent auto shared (where known)
intent_temps = [0.0, 0.3, 0.5, 0.7]
intent_vals = [112, 108, 117, 117]  # salvage / mega / unified / unified

fig, ax = plt.subplots(figsize=(11.5, 6.5))
ax.plot(temps, gf_route, "o-", color="#2e7d32", linewidth=2.2, markersize=8, label="Goal-first routing")
ax.plot(temps, deg_route, "s--", color="#6a1b9a", linewidth=1.8, markersize=7, label="Degree routing")
ax.plot(intent_temps, intent_vals, "^-", color="#1f4e79", linewidth=1.8, markersize=7, label="GF intent auto screen")
ax.axvline(0.7, color="#888", linestyle="--", linewidth=1.2, label="Study default 0.7")
ax.set_xlim(-0.05, 1.05)
ax.set_ylim(0, 130)
ax.set_xlabel("Decoding temperature")
ax.set_ylabel("Correct / 120")
ax.set_title(
    "Intent screen and routing vs temperature\n"
    "Routing: unified T0.0/0.5/0.7/1.0; T0.3 uses mega pre-fix (caveat).  "
    "Intent screen: T0 salvage / mega 0.3 / unified 0.5–0.7 (T1.0 screen not plotted).",
    loc="left",
    fontsize=11,
    pad=10,
)
for t, v in zip(temps, gf_route):
    ax.annotate(str(v), (t, v), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=9, color="#2e7d32")
for t, v in zip(temps, deg_route):
    ax.annotate(str(v), (t, v), textcoords="offset points", xytext=(0, -14), ha="center", fontsize=8, color="#6a1b9a")
ax.legend(frameon=False, loc="lower left")
style(ax)
fig.tight_layout()
save(fig, "temperature-intent-routing-line.png")

print("done")
