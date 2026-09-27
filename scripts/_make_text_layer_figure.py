"""One-off: draw the abstract pipeline figure for the research report."""
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

OUT_DIRS = [
    Path(r"C:\Users\huzii\Documents\University\Research Report\figures"),
    Path(r"C:\Users\huzii\Documents\University\Research Project\latest results\figures"),
]


def box(ax, x, y, w, h, fc, title, lines):
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.02,rounding_size=0.08",
            linewidth=1.2,
            edgecolor="#2c3e50",
            facecolor=fc,
        )
    )
    ax.text(
        x + w / 2,
        y + h - 0.28,
        title,
        ha="center",
        va="center",
        fontsize=10,
        color="#1a1a1a",
        fontweight="600",
    )
    for i, line in enumerate(lines):
        ax.text(
            x + w / 2,
            y + h - 0.55 - 0.28 * i,
            line,
            ha="center",
            va="center",
            fontsize=9,
            color="#555555",
        )


def main() -> None:
    fig, ax = plt.subplots(figsize=(10.2, 2.7), dpi=160)
    ax.set_xlim(0, 10.2)
    ax.set_ylim(0, 2.7)
    ax.axis("off")
    fig.patch.set_facecolor("#fafaf8")
    ax.set_facecolor("#fafaf8")

    ax.text(
        5.1,
        2.42,
        "Text-only ambiguity manager (sits in front of any robot planner)",
        ha="center",
        va="center",
        fontsize=11,
        color="#1a1a1a",
    )

    box(ax, 0.25, 0.75, 1.7, 1.25, "#ffffff", "Command", ["+ scene / dialogue", "+ capability card"])
    box(
        ax,
        2.35,
        0.75,
        2.05,
        1.25,
        "#eef3f7",
        "Ambiguity manager",
        ["(1) write the job", "(2) choose a path"],
    )

    for yi, lab in [(1.8, "Execute"), (1.2, "Ask / clarify"), (0.6, "Refuse")]:
        ax.add_patch(
            FancyBboxPatch(
                (4.8, yi),
                1.55,
                0.45,
                boxstyle="round,pad=0.02,rounding_size=0.06",
                linewidth=1.2,
                edgecolor="#2c3e50",
                facecolor="#ffffff",
            )
        )
        ax.text(5.575, yi + 0.225, lab, ha="center", va="center", fontsize=10, color="#1a1a1a")

    box(ax, 6.75, 0.75, 1.7, 1.25, "#f4f1ea", "Robot planner", ["(out of scope)"])

    ax.annotate(
        "",
        xy=(2.3, 1.35),
        xytext=(2.0, 1.35),
        arrowprops=dict(arrowstyle="->", color="#2c3e50", lw=1.2),
    )
    ax.plot([4.45, 4.75], [1.35, 1.35], color="#2c3e50", lw=1.2)
    ax.plot([4.45, 4.45], [0.825, 2.025], color="#2c3e50", lw=1.2)
    ax.plot([4.45, 4.8], [2.025, 2.025], color="#2c3e50", lw=1.2)
    ax.plot([4.45, 4.8], [0.825, 0.825], color="#2c3e50", lw=1.2)
    ax.annotate(
        "",
        xy=(6.7, 1.35),
        xytext=(6.4, 1.35),
        arrowprops=dict(arrowstyle="->", color="#2c3e50", lw=1.2),
    )

    ax.text(
        5.1,
        0.28,
        "Figure A. Two jobs of the text layer: name the intended job, then pick execute / ask / refuse.",
        ha="center",
        fontsize=8.5,
        color="#666666",
    )

    for out_dir in OUT_DIRS:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "text-layer-pipeline.png"
        fig.savefig(path, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
        print(path, path.stat().st_size)

    plt.close()


if __name__ == "__main__":
    main()
