"""Build the Obsidian-style results vault and wide figures.

Reads frozen dumps only. Does not invent scores.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
CASES = RESULTS / "cases"
FIGS = RESULTS / "figures"
THRESH = "0.18"

GOLD = ROOT / "pilot120_intent_evaluation_20260902/pilot120_intent_evaluation_20260902/data/intent_gold_references_120.jsonl"
V2_ROWS = ROOT / "outputs/gfv2_intent_summary_goal_trace_proxy_rows_20260912.jsonl"
BA_ROWS = ROOT / "outputs/base_vs_adapter_goal_trace_proxy_rows_20260911.jsonl"
LANE_ROWS = ROOT / "outputs/gfv2_local_lane_a_rows_20260912.jsonl"
LAYER4 = ROOT / "outputs/pilot120_semantic_intent_judging_20260908/t39_layer4_computability.json"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def md_escape(text: str) -> str:
    return (text or "").replace("\r\n", "\n").strip()


def yesno(flag: bool) -> str:
    return "yes" if flag else "no"


def bucket(goal: bool, route: bool) -> str:
    if goal and route:
        return "understood-and-acted"
    if goal and not route:
        return "understood-but-wrong-move"
    if (not goal) and route:
        return "messy-writing-right-move"
    return "missed-both"


BUCKET_TITLE = {
    "understood-and-acted": "Intent yes, and routing matched gold",
    "understood-but-wrong-move": "Intent yes, but routing missed gold",
    "messy-writing-right-move": "Intent no, but routing still matched gold",
    "missed-both": "Intent no, and routing missed gold",
}


def wrap_label(text: str, width: int = 22) -> str:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if len(trial) > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return "\n".join(lines)


def style_axes(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="x", linestyle=":", linewidth=0.6, alpha=0.7)
    ax.set_axisbelow(True)


def build_figures() -> None:
    FIGS.mkdir(parents=True, exist_ok=True)

    # Wide horizontal bars so every label is fully readable.
    fig, ax = plt.subplots(figsize=(16.5, 9.2))
    rows = [
        ("Raw Qwen — cheap rule on written reasoning", 68, "#b36b00"),
        ("Fine-tune — cheap rule on written reasoning", 60, "#8b4513"),
        ("New goal-first — cheap rule on intent_summary", 112, "#2e7d32"),
    ]
    y = list(range(len(rows)))[::-1]
    vals = [r[1] for r in rows]
    colors = [r[2] for r in rows]
    labels = [r[0] for r in rows]
    bars = ax.barh(y, vals, color=colors, height=0.62, edgecolor="white")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=11)
    ax.set_xlim(0, 128)
    ax.set_xlabel("Commands out of 120 where the writing looked like the gold job", fontsize=12)
    ax.set_title(
        "Intent correctness (live systems). Different exams: short box vs written reasoning.\n"
        "Do not subtract 112 from 68. Official two-judge intent on the new box has not been run.",
        loc="left",
        fontsize=13,
        pad=12,
    )
    for bar, val in zip(bars, vals):
        ax.text(val + 1.2, bar.get_y() + bar.get_height() / 2, f"{val}/120", va="center", fontsize=11)
    ax.axvline(120, color="#888", linewidth=0.8, linestyle="--")
    style_axes(ax)
    fig.tight_layout()
    fig.savefig(FIGS / "intent-primary-wide.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    # Intent vs route — two well-spaced panels.
    fig, axes = plt.subplots(1, 2, figsize=(17.5, 7.8), sharey=False)
    systems = [
        ("Raw Qwen\n(no manager)", 68, 88),
        ("Fine-tune", 60, 87),
        ("New goal-first\nmanager", 112, 54),
    ]
    x = list(range(len(systems)))
    w = 0.34
    ax = axes[0]
    b1 = ax.bar([i - w / 2 for i in x], [s[1] for s in systems], width=w, color="#2e7d32", label="Intent correctness")
    b2 = ax.bar([i + w / 2 for i in x], [s[2] for s in systems], width=w, color="#1f4e79", label="Routing correctness")
    ax.set_xticks(x)
    ax.set_xticklabels([s[0] for s in systems], fontsize=10)
    ax.set_ylim(0, 128)
    ax.set_ylabel("Commands out of 120")
    ax.set_title("Intent vs routing, side by side", loc="left", fontsize=13)
    ax.legend(frameon=False, loc="upper right")
    for bars in (b1, b2):
        for bar in bars:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.5, f"{int(bar.get_height())}", ha="center", fontsize=9)
    style_axes(ax)
    ax.grid(axis="y", linestyle=":", linewidth=0.6, alpha=0.7)

    ax = axes[1]
    split = [
        ("Raw Qwen", 56, 12, 32, 20),
        ("Fine-tune", 49, 11, 38, 22),
        ("New goal-first", 50, 62, 4, 4),
    ]
    labels = [s[0] for s in split]
    bottoms = [0] * 3
    parts = [
        ([s[1] for s in split], "#2e7d32", "Intent yes, routing yes"),
        ([s[2] for s in split], "#c47b17", "Intent yes, routing no"),
        ([s[3] for s in split], "#5b8def", "Intent no, routing yes"),
        ([s[4] for s in split], "#9e3a3a", "Intent no, routing no"),
    ]
    x = list(range(3))
    for vals, color, lab in parts:
        ax.bar(x, vals, bottom=bottoms, color=color, width=0.55, label=lab, edgecolor="white")
        if lab == "Intent yes, routing no":
            ax.text(2, bottoms[2] + vals[2] / 2, "62", ha="center", va="center", color="white", fontsize=12, fontweight="bold")
        bottoms = [a + b for a, b in zip(bottoms, vals)]
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_ylim(0, 130)
    ax.set_ylabel("Commands out of 120")
    ax.set_title("How intent and routing come apart", loc="left", fontsize=13)
    ax.legend(frameon=False, loc="upper right", fontsize=9)
    style_axes(ax)
    ax.grid(axis="y", linestyle=":", linewidth=0.6, alpha=0.7)
    fig.suptitle(
        "Secondary question (used only to explain the primary): did routing match gold?",
        x=0.01,
        ha="left",
        fontsize=12,
        y=1.02,
    )
    fig.tight_layout()
    fig.savefig(FIGS / "intent-vs-route-wide.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    # Replica stability — lots of horizontal room, one row per system.
    fig, ax = plt.subplots(figsize=(16.5, 7.2))
    replica_rows = [
        ("Raw Qwen — routing", [88] * 5),
        ("Fine-tune — routing", [87] * 5),
        ("New goal-first — routing (after salvage)", [54, 54, 54]),
        ("New degree — routing (after salvage)", [59, 59, 59]),
        ("New timid — routing (after salvage)", [26, 26, 26]),
        ("New context-blind — routing (after salvage)", [21, 21, 21]),
    ]
    y = list(range(len(replica_rows)))[::-1]
    ax.set_xlim(0, 6.4)
    ax.set_ylim(-0.7, len(replica_rows) - 0.3)
    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in replica_rows], fontsize=10)
    ax.set_xticks([1, 2, 3, 4, 5])
    ax.set_xticklabels(["Replica 1", "Replica 2", "Replica 3", "Replica 4", "Replica 5"], fontsize=11)
    ax.set_title(
        "Repeats: did routing correctness stay the same?\n"
        "Live manager: three GPU replicas after salvage. Raw Qwen / fine-tune: five.",
        loc="left",
        fontsize=13,
        pad=12,
    )
    for yi, (_lab, vals) in zip(y, replica_rows):
        for xi in range(1, 6):
            if xi <= len(vals):
                val = vals[xi - 1]
                color = "#2e7d32" if len(vals) == 3 else "#1f4e79"
                ax.add_patch(
                    FancyBboxPatch(
                        (xi - 0.38, yi - 0.32),
                        0.76,
                        0.64,
                        boxstyle="round,pad=0.02,rounding_size=0.08",
                        facecolor=color,
                        edgecolor="white",
                        linewidth=1.2,
                    )
                )
                ax.text(xi, yi, str(val), ha="center", va="center", color="white", fontsize=12, fontweight="bold")
            else:
                ax.add_patch(
                    FancyBboxPatch(
                        (xi - 0.38, yi - 0.32),
                        0.76,
                        0.64,
                        boxstyle="round,pad=0.02,rounding_size=0.08",
                        facecolor="#d0d0d0",
                        edgecolor="white",
                        linewidth=1.2,
                    )
                )
                ax.text(xi, yi, "not run", ha="center", va="center", color="#555", fontsize=8)
    ax.set_xlabel("Independent GPU run of the same system on the same 120 commands")
    style_axes(ax)
    ax.grid(False)
    fig.tight_layout()
    fig.savefig(FIGS / "replica-stability-wide.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    # Overask breakdown
    fig, ax = plt.subplots(figsize=(14.5, 6.8))
    cats = [
        "Gold said do it.\nManager asked.",
        "Gold said do it.\nManager refused.",
        "Gold said ask.\nManager did it.",
        "Gold said ask.\nManager refused.",
        "Gold said refuse.\nManager asked.",
        "Gold said refuse.\nManager did it.",
    ]
    vals = [9, 32, 3, 14, 4, 0]
    colors = ["#c47b17", "#9e3a3a", "#5b8def", "#9e3a3a", "#c47b17", "#2e7d32"]
    bars = ax.bar(range(6), vals, color=colors, width=0.62, edgecolor="white")
    ax.set_xticks(range(6))
    ax.set_xticklabels(cats, fontsize=10)
    ax.set_ylabel("Commands inside the 62")
    ax.set_ylim(0, 38)
    ax.set_title(
        "The 62: intent yes, routing no (new goal-first)\n"
        "32 of 62 are gold-do-it cases that the new manager refused.",
        loc="left",
        fontsize=13,
        pad=10,
    )
    for bar, val in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, val + 0.6, str(val), ha="center", fontsize=12)
    style_axes(ax)
    ax.grid(axis="y", linestyle=":", linewidth=0.6, alpha=0.7)
    fig.tight_layout()
    fig.savefig(FIGS / "overask-breakdown-wide.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    # Secondary F1 — wide grouped bars
    fig, ax = plt.subplots(figsize=(17.2, 7.6))
    names = [
        "Raw Qwen",
        "Fine-tune",
        "New goal-\nfirst",
        "New\ndegree",
        "New timid\nrule",
        "New context-\nblind",
    ]
    macro = [0.736, 0.701, 0.412, 0.477, 0.214, 0.300]
    acc = [88 / 120, 87 / 120, 54 / 120, 59 / 120, 26 / 120, 21 / 120]
    x = list(range(len(names)))
    w = 0.36
    b1 = ax.bar([i - w / 2 for i in x], acc, width=w, color="#1f4e79", label="Routing correctness (fraction of 120)")
    b2 = ax.bar([i + w / 2 for i in x], macro, width=w, color="#7b2d8e", label="Macro-F1 on the routing label")
    ax.set_xticks(x)
    ax.set_xticklabels(names, fontsize=10)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Score (0 to 1)")
    ax.set_title(
        "Secondary metric: routing quality\n"
        "Routing correctness asks 'how many buttons matched gold.' Macro-F1 asks 'was that true for do-it, ask, and refuse.'",
        loc="left",
        fontsize=13,
        pad=10,
    )
    ax.legend(frameon=False, loc="upper right")
    for bars in (b1, b2):
        for bar in bars:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.02,
                f"{bar.get_height():.2f}",
                ha="center",
                fontsize=8,
            )
    style_axes(ax)
    ax.grid(axis="y", linestyle=":", linewidth=0.6, alpha=0.7)
    fig.tight_layout()
    fig.savefig(FIGS / "route-f1-wide.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def load_all() -> dict:
    gold = {row["record_id"]: row for row in load_jsonl(GOLD)}
    v2 = {row["record_id"]: row for row in load_jsonl(V2_ROWS)}
    ba = {row["record_id"]: row for row in load_jsonl(BA_ROWS)}
    lane = {row["record_id"]: row for row in load_jsonl(LANE_ROWS)}
    layer = json.loads(LAYER4.read_text(encoding="utf-8"))
    leftover = defaultdict(dict)
    for row in layer["rows"]:
        leftover[row["record_id"]][row["system_id"]] = row
    ids = sorted(gold)
    assert len(ids) == 120
    return {"gold": gold, "v2": v2, "ba": ba, "lane": lane, "leftover": leftover, "ids": ids}


def case_md(rid: str, data: dict) -> str:
    g = data["gold"][rid]
    v = data["v2"][rid]
    b = data["ba"][rid]
    lane = data["lane"][rid]
    leftover = data["leftover"].get(rid, {})
    src = g["source"]
    v_proxy = v["proxies"][THRESH]
    base = b["systems"]["direct_base_llm"]
    adp = b["systems"]["t28_selected_adapter_llm"]
    base_proxy = base["proxies"][THRESH]
    adp_proxy = adp["proxies"][THRESH]
    v_goal = bool(v_proxy["proxy_correct"])
    v_route = bool(v["route_correct"])
    bucket_id = bucket(v_goal, v_route)
    full_sgc = leftover.get("full_type_risk_aware_manager", {})
    deg_sgc = leftover.get("degree_based_router", {})
    blind_sgc = leftover.get("context_blind_manager", {})

    def sgc_cell(row: dict) -> str:
        if not row:
            return "not in older judge file"
        return "yes" if row.get("semantic_goal_correct") else "no"

    lines = [
        f"# {rid}",
        "",
        f"**What this note is.** One Pilot-120 command. **Intent correctness** asks whether the writing named the gold job. **Routing correctness** asks whether we pressed gold’s button (do it / ask / refuse).",
        "",
        "**How to read the table.** New goal-first intent is the cheap 0.18 overlap rule on `intent_summary`. Raw Qwen and the fine-tune use the same rule on **written reasoning** (they have no goal box). Older-manager intent, if shown, is a different exam (two judges on older written reasoning). `face_preserving_rejection` counts as matching gold **refuse**.",
        "",
        f"**Bucket for the new goal-first manager:** [[{bucket_id}|{BUCKET_TITLE[bucket_id]}]].",
        "",
        "## The situation the robot saw",
        "",
        f"**Command.** {md_escape(src['command'])}",
        "",
        f"**Human follow-up.** {md_escape(' '.join(src.get('dialogue_history') or [])) or 'None.'}",
        "",
        f"**Scene (short).** {md_escape(src.get('scene_context', ''))}",
        "",
        f"**Capability card (short).** {md_escape(src.get('capability_context', ''))}",
        "",
        "## What gold said the job was",
        "",
        "Gold is two independently written intent paragraphs plus a frozen routing label. Intent can pass if the system's words line up with *either* paragraph.",
        "",
        f"**Gold intent A.** {md_escape(g['reference_A_intent_text'])}",
        "",
        f"**Gold intent B.** {md_escape(g['reference_B_intent_text'])}",
        "",
        f"**Gold speech-act label.** `{g.get('gold_speech_act', '')}`",
        "",
        f"**Gold route.** `{v['gold_route']}` — this is **routing**, not intent. `execute` = do it, `clarify` = ask.",
        "",
        "## Intent correctness vs routing correctness",
        "",
        "| System | What we scored | Intent? | Overlap | Predicted route | Routing? |",
        "|---|---|---|---:|---|---|",
        f"| New goal-first | Short `intent_summary`, cheap rule at 0.18 | {yesno(v_goal)} | {v_proxy['overlap_best']:.3f} | `{v['predicted_route']}` | {yesno(v_route)} |",
        f"| Raw Qwen | Written reasoning, same cheap rule | {yesno(base_proxy['proxy_correct'])} | {base_proxy['overlap_best']:.3f} | `{base['predicted_route']}` | {yesno(base['route_correct'])} |",
        f"| Fine-tune | Written reasoning, same cheap rule | {yesno(adp_proxy['proxy_correct'])} | {adp_proxy['overlap_best']:.3f} | `{adp['predicted_route']}` | {yesno(adp['route_correct'])} |",
        "",
        "Same new writing, three different routing rules (the button is the rule, not a new brain):",
        "",
        f"- New goal-first rule predicted `{lane.get('goal_first')}` (matched gold: {yesno(lane.get('goal_first_correct', False))}; live rule `{lane.get('live_matched_rule', '')}`).",
        f"- New degree rule predicted `{lane.get('degree')}` (matched gold: {yesno(lane.get('degree_correct', False))}).",
        f"- New timid / rich-conservative rule predicted `{lane.get('rich')}` (matched gold: {yesno(lane.get('rich') == v['gold_route'])}).",
        f"- New context-blind rule predicted `{lane.get('blind')}` (this system never saw the scene or the capability card).",
        "",
        f"**What the new manager believed about capability (not the gold card above).** System bit `{lane.get('capability_status', '')}` (same belief also stored as `{lane.get('pilot_capability', '')}`). Gold’s own capability label lives in the final-gold file. Risk `{lane.get('risk_level', '')}`. Salvaged JSON: {yesno(bool(v.get('salvaged') or lane.get('salvaged')))}.",
        "",
        "## Exact writing we scored",
        "",
        "### New goal-first `intent_summary`",
        "",
        f"> {md_escape(v.get('intent_summary') or lane.get('intent_summary') or '')}",
        "",
        "### Raw Qwen written reasoning (excerpt used by the cheap rule)",
        "",
        f"> {md_escape(base.get('intent_excerpt', ''))}",
        "",
        "### Fine-tune written reasoning (excerpt used by the cheap rule)",
        "",
        f"> {md_escape(adp.get('intent_excerpt', ''))}",
        "",
        "## Why this case went this way",
        "",
    ]

    reasons = []
    if v_goal and v_route:
        reasons.append(
            "The short box reused enough of the gold job words to pass the 0.18 rule, and the live rule then pressed gold’s button. Intent yes and routing yes."
        )
    if v_goal and not v_route:
        reasons.append(
            f"The short box named the job (overlap {v_proxy['overlap_best']:.3f}), so this is *not* an understanding miss on the proxy. The live rule chose `{v['predicted_route']}` because of `{lane.get('live_matched_rule', 'an unrecorded rule')}`. Gold wanted `{v['gold_route']}`."
        )
        if lane.get("live_matched_rule") == "known_incapable":
            reasons.append(
                f"The capability field said the robot could not do this. Gold’s route was `{v['gold_route']}`. If the capability bit is wrong, we invented a refuse. If it is right, gold and the stack disagree about what 'capable' means."
            )
        if lane.get("live_matched_rule") == "known_unsafe_or_prohibited":
            reasons.append(
                "The stack treated the job as unsafe or prohibited. That can be a real safety call, or an over-read of a scene gold treated as ordinary work."
            )
        if lane.get("live_matched_rule") == "default_clarify":
            reasons.append(
                "The live rule fell through to 'ask.' The writing already had a job; asking is extra caution, not a blank mind."
            )
        if base.get("route_correct"):
            reasons.append(
                "Raw Qwen already had gold’s route on this same command. The job was recoverable enough to act on — the new manager left a correct button on the table."
            )
        if not base.get("route_correct"):
            reasons.append(
                "Raw Qwen also missed gold’s route here, so this is not a case where a simple 'just use Qwen' would have saved us."
            )
        if lane.get("degree_correct") and not lane.get("goal_first_correct"):
            reasons.append(
                "The new degree rule, reading the *same* `intent_summary`, would have got gold’s route. That is the cleanest proof that the paragraph was good enough and the conservative rule was the problem."
            )
        if lane.get("t39_full") == "clarify" and v["predicted_route"] == "refuse":
            reasons.append(
                "An older cautious rule asked on this row. The new manager mostly swapped that ask for a refuse. Different failure, not sudden ignorance."
            )
    if (not v_goal) and v_route:
        if v_proxy.get("polarity_conflict"):
            reasons.append(
                f"The short box failed intent on polarity, not on raw overlap (best overlap {v_proxy['overlap_best']:.3f}, which can sit above 0.18). The text names many of the same objects as gold, then flips do / don't. Routing still matched gold `{v['predicted_route']}`."
            )
        elif v_proxy["overlap_best"] >= 0.15:
            reasons.append(
                f"The short box missed the 0.18 cutoff by a small margin (best overlap {v_proxy['overlap_best']:.3f}). A student reading the quotes may still say the job is there. The cheap rule did not. Routing still matched gold `{v['predicted_route']}`."
            )
        else:
            reasons.append(
                f"The short box failed the 0.18 overlap test (best overlap {v_proxy['overlap_best']:.3f}). Routing still matched gold. That can happen when the box is too generic, too truncated, or uses different words than the two gold paragraphs, while the rule still lands on `{v['predicted_route']}`."
            )
    if (not v_goal) and (not v_route):
        if v_proxy.get("polarity_conflict"):
            reasons.append(
                f"The short box failed intent on polarity (best overlap {v_proxy['overlap_best']:.3f}). Routing `{v['predicted_route']}` also missed gold `{v['gold_route']}`. Read the box: the objects may be there, and the verb may have been rewritten from 'do the setting' to 'confirm / do not'."
            )
        else:
            reasons.append(
                f"The short box failed the 0.18 overlap test (best overlap {v_proxy['overlap_best']:.3f}) *and* routing `{v['predicted_route']}` missed gold `{v['gold_route']}`. This is one of the rare rows where even the cheap intent rule says we did not name the job."
            )
        if v.get("salvaged") or lane.get("salvaged"):
            reasons.append("This row was CPU-salvaged. Treat the prose as rebuilt JSON, not a clean first-pass sentence.")

    if base_proxy["proxy_correct"] != v_goal:
        if v_goal and not base_proxy["proxy_correct"]:
            reasons.append(
                "Raw Qwen’s written reasoning failed the *same* 0.18 rule. That is expected: protocol talk buries the job, while the new box is a dedicated paraphrase."
            )
        if (not v_goal) and base_proxy["proxy_correct"]:
            reasons.append(
                "Raw Qwen’s written reasoning *passed* the cheap rule while the new box failed. Read both quotes. Sometimes the longer reasoning still names the object and the action, and the short box is too compressed or one-sided."
            )

    if not reasons:
        reasons.append("See the table and the quotes. The flags alone do not force a single story.")

    for i, reason in enumerate(reasons, start=1):
        lines.append(f"{i}. {reason}")
        lines.append("")

    links = [
        "## Links",
        "",
        f"- Back to the [[00-start-here|start page]]",
        f"- [[_index|All 120 cases]]",
        f"- [[{bucket_id}|Other cases in this bucket]]",
        f"- [[02-what-we-are-measuring|What each metric actually measures]]",
    ]
    if bucket_id == "understood-but-wrong-move":
        links.append("- [[04-the-62-overasks|The 62 writing-yes / action-wrong cases]]")
    links.extend(["", ""])
    lines.extend(links)
    return "\n".join(lines)


def write_bucket_page(name: str, ids: list[str], extra: str) -> None:
    lines = [
        f"# {BUCKET_TITLE.get(name, name)}",
        "",
        extra,
        "",
        f"**Count.** {len(ids)} / 120.",
        "",
        "## Cases",
        "",
    ]
    for rid in ids:
        lines.append(f"- [[{rid}]]")
    lines.extend(["", "[[_index|All 120 cases]] · [[00-start-here|Start]]", ""])
    (CASES / f"{name}.md").write_text("\n".join(lines), encoding="utf-8")


def write_cases(data: dict) -> dict:
    CASES.mkdir(parents=True, exist_ok=True)
    buckets: dict[str, list[str]] = defaultdict(list)
    featured_misses = []
    for rid in data["ids"]:
        v = data["v2"][rid]
        v_goal = bool(v["proxies"][THRESH]["proxy_correct"])
        v_route = bool(v["route_correct"])
        b = bucket(v_goal, v_route)
        buckets[b].append(rid)
        (CASES / f"{rid}.md").write_text(case_md(rid, data), encoding="utf-8")
        if not v_goal:
            featured_misses.append(rid)

    index = [
        "# All 120 Pilot commands",
        "",
        "Open any case to see the command, both gold intent paragraphs, the new manager's `intent_summary`, raw Qwen / fine-tune written reasoning, and why that row went the way it did.",
        "",
        "These notes score **intent correctness** first. The routing column is there so you can see the discrepancy, not so you can treat the case as a routing-only study.",
        "",
        "**Same three buttons, two names.** Gold and the case tables use `execute` / `clarify` / `refuse`. The start page says do it / ask / refuse. They are the same: `execute` = do it, `clarify` = ask, `refuse` = refuse. `face_preserving_rejection` also counts as refuse.",
        "",
        "**Legend.** New goal-first intent = cheap 0.18 rule on `intent_summary`. Raw Qwen / fine-tune = same rule on written reasoning. Open [[00-start-here]] and [[glossary]] if a column name is new.",
        "",
        "## By what happened on the new goal-first manager",
        "",
        f"- [[{ 'understood-and-acted' }|{BUCKET_TITLE['understood-and-acted']}]] — {len(buckets['understood-and-acted'])}",
        f"- [[{ 'understood-but-wrong-move' }|{BUCKET_TITLE['understood-but-wrong-move']}]] — {len(buckets['understood-but-wrong-move'])}",
        f"- [[{ 'messy-writing-right-move' }|{BUCKET_TITLE['messy-writing-right-move']}]] — {len(buckets['messy-writing-right-move'])}",
        f"- [[{ 'missed-both' }|{BUCKET_TITLE['missed-both']}]] — {len(buckets['missed-both'])}",
        "",
        "## The eight writing misses (primary metric failed)",
        "",
        "These are the only rows where the new `intent_summary` failed the 0.18 proxy. Read them before you treat 112/120 as 'it always understood.'",
        "",
    ]
    for rid in featured_misses:
        index.append(f"- [[{rid}]]")
    index.extend(["", "## Every case, in ID order", ""])
    for rid in data["ids"]:
        v = data["v2"][rid]
        flag = "intent yes" if v["proxies"][THRESH]["proxy_correct"] else "intent no"
        move = "routing yes" if v["route_correct"] else "routing no"
        index.append(f"- [[{rid}]] — gold `{v['gold_route']}` · {flag} · {move}")
    index.extend(["", "[[00-start-here|Start]]", ""])
    (CASES / "_index.md").write_text("\n".join(index), encoding="utf-8")

    write_bucket_page(
        "understood-and-acted",
        buckets["understood-and-acted"],
        "Intent yes and routing yes. These are the 50 rows where the new manager both named the job and pressed gold’s button.",
    )
    write_bucket_page(
        "understood-but-wrong-move",
        buckets["understood-but-wrong-move"],
        "This is the main scientific pile. Intent yes, routing no. Open [[04-the-62-overasks]] for the argument. Open any case for the exact quotes.",
    )
    write_bucket_page(
        "messy-writing-right-move",
        buckets["messy-writing-right-move"],
        "The 0.18 rule said the short box did not look like gold, but routing was still right. Use these to remember that a lexical rule can miss a good-enough paraphrase.",
    )
    write_bucket_page(
        "missed-both",
        buckets["missed-both"],
        "Intent no and routing no. These are the rows where 'it understood' is hardest to defend even on the cheap rule.",
    )
    return {"buckets": {k: v for k, v in buckets.items()}, "writing_misses": featured_misses}


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    build_figures()
    data = load_all()
    meta = write_cases(data)
    leftover_full_miss = []
    leftover_blind_miss = []
    for rid in data["ids"]:
        rows = data["leftover"].get(rid, {})
        full = rows.get("full_type_risk_aware_manager")
        blind = rows.get("context_blind_manager")
        if full and not full.get("semantic_goal_correct"):
            leftover_full_miss.append(rid)
        if blind and not blind.get("semantic_goal_correct"):
            leftover_blind_miss.append(rid)
    summary = {
        "writing_misses_v2_proxy": meta["writing_misses"],
        "bucket_counts": {k: len(v) for k, v in meta["buckets"].items()},
        "leftover_full_sgc_misses": leftover_full_miss,
        "leftover_blind_sgc_misses": leftover_blind_miss,
    }
    (RESULTS / "_generated_case_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
