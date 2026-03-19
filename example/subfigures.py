#!/usr/bin/env python3
"""Generate example subfigures in Nature-like style."""

import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt

R, K, N0 = 1.5, 1.0, 0.05
T_MAX = 11


def _nature_rc() -> dict:
    return {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "font.size": 10,
        "axes.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.major.width": 0.8,
        "ytick.major.width": 0.8,
        "xtick.major.size": 3,
        "ytick.major.size": 3,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "lines.linewidth": 1.5,
        "legend.frameon": False,
        "legend.fontsize": 7,
        "figure.facecolor": "none",
        "axes.facecolor": "none",
    }


def _logistic(t: np.ndarray) -> np.ndarray:
    return K / (1 + ((K - N0) / N0) * np.exp(-R * t))


def generate_logistic_logscale(output_path: str = "logistic_log.svg") -> None:
    """Logistic growth on a log y-axis."""
    t = np.linspace(0, T_MAX, 300)

    with mpl.rc_context(_nature_rc()):
        fig, ax = plt.subplots(figsize=(2.2, 1.6))
        ax.plot(t, _logistic(t), color="#1f77b4")
        ax.set_yscale("log")
        ax.set_xlabel("$t$")
        ax.set_ylabel("$N(t)$")
        ax.set_xlim(0, T_MAX)
        ax.set_xticks([0, 5, 10])
        fig.tight_layout()
        fig.savefig(output_path, format="svg", bbox_inches="tight", transparent=True)
    print(f"Saved {output_path}")


def generate_logistic_linscale(output_path: str = "logistic.svg") -> None:
    """Logistic growth on a linear y-axis."""
    t = np.linspace(0, T_MAX, 300)

    with mpl.rc_context(_nature_rc()):
        fig, ax = plt.subplots(figsize=(2.2, 1.6))
        ax.plot(t, _logistic(t), color="#2ca02c")
        ax.axhline(K, color="black", linewidth=0.6, linestyle=":")
        ax.set_xlabel("$t$")
        ax.set_ylabel("$N(t)$")
        ax.set_xlim(0, T_MAX)
        ax.set_xticks([0, 5, 10])
        ax.set_ylim(0, 1.15)
        ax.set_yticks([0, 0.5, 1.0])
        ax.set_yticklabels(["$0$", "$K/2$", "$K$"])
        fig.tight_layout()
        fig.savefig(output_path, format="svg", bbox_inches="tight", transparent=True)
    print(f"Saved {output_path}")


if __name__ == "__main__":
    generate_logistic_logscale()
    generate_logistic_linscale()
