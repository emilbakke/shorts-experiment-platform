"""Conceptual figure: the exposure chain (who decides each link and how it is measured).
Run from the repository root:  python3 figures/make_chain_figure.py
"""
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

HERE = Path(__file__).resolve().parent
BLUE, ORANGE = "#2a78d6", "#eb6834"
plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["Nimbus Sans", "Arial", "Liberation Sans", "DejaVu Sans"],
                     "pdf.fonttype": 42})

LINKS = [("Assigned", "Which feed is the\nuser presented with?", "Random assignment to a\nfeed with or without\nmanosphere clips"),
         ("Served", "Which clips appear\non the screen?", "Impression log per\nserved video"),
         ("Watched", "How long does the user\nstay with each clip?", "Time before swipe\n(device timestamps)"),
         ("Perceived", "What does the\nuser notice?", "Post-survey item on\nnoticing gender-related\nvideos"),
         ("Attitudes", "Do attitudes or\nperceptions change?", "Post-survey items on\ngender attitudes and\nbroader perceptions")]


def main():
    fig, ax = plt.subplots(figsize=(7.2, 2.4))
    ax.set_xlim(0, 114); ax.set_ylim(1.5, 36); ax.axis("off")
    w, h, gap, y, x0 = 15.5, 8.5, 4.6, 19.0, 15.5
    xs = [x0 + i * (w + gap) for i in range(5)]
    for i, (x, (name, question, measure)) in enumerate(zip(xs, LINKS)):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.2", fc="white", ec="black", lw=1.0))
        ax.text(x + w / 2, y + h / 2, name, ha="center", va="center", fontsize=10.5, fontweight="bold")
        ax.text(x + w / 2, y - 1.8, question, ha="center", va="top", fontsize=7.6, linespacing=1.15)
        ax.text(x + w / 2, y - 10.4, measure, ha="center", va="top", fontsize=7.6, linespacing=1.15)
        if i < 4:
            ax.add_patch(FancyArrowPatch((x + w + 0.5, y + h / 2), (x + w + gap - 0.5, y + h / 2), arrowstyle="-|>", mutation_scale=10,
                                         lw=1.0, color="black"))
    # row labels
    ax.text(0.3, y + h / 2, "Link in\nthe chain", ha="left", va="center", fontsize=8.2, fontweight="bold", linespacing=1.15)
    ax.text(0.3, y - 10.4, "In this\nexperiment", ha="left", va="top", fontsize=8.2, fontweight="bold", linespacing=1.15)
    ax.plot([0.3, xs[4] + w], [y - 8.9, y - 8.9], color="#b3b3b3", lw=0.6)

    # who decides each link
    def bracket(a, b, label, colour):
        yb = y + h + 2.2
        ax.plot([a, a, b, b], [yb - 1.2, yb, yb, yb - 1.2], color=colour, lw=1.6, solid_capstyle="butt")
        ax.text((a + b) / 2, yb + 1.2, label, ha="center", va="bottom", fontsize=8.8, color=colour, fontweight="bold")
    bracket(xs[0], xs[1] + w, "The platform decides", BLUE)
    bracket(xs[2], xs[2] + w, "The user decides", ORANGE)
    bracket(xs[3], xs[4] + w, "Outcomes", "black")
    fig.subplots_adjust(left=0.005, right=0.995, top=0.99, bottom=0.01)
    for ext in ("png", "pdf"):
        fig.savefig(HERE / f"figure_chain.{ext}", dpi=300)
    print("written", HERE / "figure_chain.png")


if __name__ == "__main__":
    main()
