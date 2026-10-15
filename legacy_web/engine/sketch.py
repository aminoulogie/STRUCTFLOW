"""Footing drawings (plan + section) for the report."""
from __future__ import annotations

from io import BytesIO

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402


def _bars_txt(b):
    return f"{b['n']} HA{b['phi']} e={b['s'] * 100:.0f} cm" if b else "—"


def draw(res, cover):
    g = res.geo
    bx, by = res.rc["X"]["bars"], res.rc["Y"]["bars"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 5.2), gridspec_kw=dict(width_ratios=[1, 1.15]))

    # ---- plan
    ax1.add_patch(Rectangle((-g.A / 2, -g.B / 2), g.A, g.B, fill=False, lw=1.6))
    ax1.add_patch(Rectangle((-g.ap / 2, -g.bp / 2), g.ap, g.bp, fc="#d9d9d9", ec="k", lw=1.2))
    pa, pb = res.gi.plate_a, res.gi.plate_b
    if pa and pb:
        ax1.add_patch(Rectangle((-pa / 2, -pb / 2), pa, pb, fill=False, ec="#1f4e79", lw=1, ls="--"))
    for i in range(by["n"]):  # bars // B (spread along A)
        x = -g.A / 2 + cover + i * by["s"]
        ax1.plot([x, x], [-g.B / 2 + cover, g.B / 2 - cover], color="#c00000", lw=0.6)
    for i in range(bx["n"]):  # bars // A (spread along B)
        y = -g.B / 2 + cover + i * bx["s"]
        ax1.plot([-g.A / 2 + cover, g.A / 2 - cover], [y, y], color="#1f4e79", lw=0.6)
    ax1.annotate("", (-g.A / 2, -g.B / 2 - 0.15), (g.A / 2, -g.B / 2 - 0.15), arrowprops=dict(arrowstyle="<->"))
    ax1.text(0, -g.B / 2 - 0.28, f"A = {g.A:.2f} m", ha="center", fontsize=9)
    ax1.annotate("", (-g.A / 2 - 0.15, -g.B / 2), (-g.A / 2 - 0.15, g.B / 2), arrowprops=dict(arrowstyle="<->"))
    ax1.text(-g.A / 2 - 0.28, 0, f"B = {g.B:.2f} m", va="center", rotation=90, fontsize=9)
    ax1.text(0, g.B / 2 + 0.12, f"// A : {_bars_txt(bx)}", ha="center", fontsize=8, color="#1f4e79")
    ax1.text(0, g.B / 2 + 0.28, f"// B : {_bars_txt(by)}", ha="center", fontsize=8, color="#c00000")
    ax1.text(0, 0, f"fût\n{g.ap * 100:.0f}×{g.bp * 100:.0f}", ha="center", va="center", fontsize=7)
    ax1.set_title("Vue en plan", fontsize=10)
    ax1.set_aspect("equal")
    ax1.set_xlim(-g.A / 2 - 0.45, g.A / 2 + 0.2)
    ax1.set_ylim(-g.B / 2 - 0.4, g.B / 2 + 0.45)
    ax1.axis("off")

    # ---- section along A
    D, h, Hp = g.D, g.h, g.Hp
    ax2.add_patch(Rectangle((-g.A / 2, -D), g.A, h, fc="#efefef", ec="k", lw=1.6))
    ax2.add_patch(Rectangle((-g.ap / 2, -D + h), g.ap, Hp, fc="#d9d9d9", ec="k", lw=1.2))
    ax2.plot([-g.A / 2 - 0.4, g.A / 2 + 0.4], [0, 0], color="#7f6000", lw=1)
    ax2.text(g.A / 2 + 0.05, 0.03, "TN ±0.00", fontsize=8, color="#7f6000")
    ax2.add_patch(Rectangle((-(pa or g.ap * 0.8) / 2, -D + h + Hp), (pa or g.ap * 0.8), 0.03, fc="#1f4e79"))
    ax2.plot([0, 0], [-D + h + Hp + 0.03, -D + h + Hp + 0.45], color="#1f4e79", lw=4)
    ax2.text(0.06, -D + h + Hp + 0.3, "poteau\nmétallique", fontsize=7, color="#1f4e79")
    yb = -D + cover
    ax2.plot([-g.A / 2 + cover, g.A / 2 - cover], [yb, yb], color="#1f4e79", lw=2)
    if res.rc["X"]["bars_top"]:
        ax2.plot([-g.A / 2 + cover, g.A / 2 - cover], [-D + h - cover] * 2, color="#7030a0", lw=1.5)
    ax2.add_patch(Rectangle((-g.A / 2 - 0.1, -D - 0.1), g.A + 0.2, 0.1, fc="#bfbfbf", ec="none"))
    ax2.text(0, -D - 0.2, "béton de propreté", ha="center", fontsize=7)
    ax2.annotate("", (g.A / 2 + 0.15, -D), (g.A / 2 + 0.15, -D + h), arrowprops=dict(arrowstyle="<->"))
    ax2.text(g.A / 2 + 0.2, -D + h / 2, f"h = {h:.2f}", va="center", fontsize=8)
    ax2.annotate("", (-g.A / 2 - 0.2, -D), (-g.A / 2 - 0.2, 0), arrowprops=dict(arrowstyle="<->"))
    ax2.text(-g.A / 2 - 0.25, -D / 2, f"D = {D:.2f}", va="center", ha="right", fontsize=8)
    ax2.text(g.ap / 2 + 0.05, -D + h + Hp / 2, f"Hp = {Hp:.2f}", fontsize=8)
    ax2.set_title("Coupe selon A", fontsize=10)
    ax2.set_aspect("equal")
    ax2.set_xlim(-g.A / 2 - 0.7, g.A / 2 + 0.7)
    ax2.set_ylim(-D - 0.3, g.h_above + 0.6)
    ax2.axis("off")
    fig.suptitle(f"Semelle {res.gi.name}", fontsize=11, weight="bold")
    buf = BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=160)
    plt.close(fig)
    return buf.getvalue()
