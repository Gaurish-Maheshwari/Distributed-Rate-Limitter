"""Regenerates the behaviour charts in docs/img/.

The simulators below mirror the logic of the Lua scripts in app/limiters/lua/
but take an explicit clock, so the charts are deterministic and need no Redis.
Run:  pip install matplotlib && python docs/generate_figures.py
"""
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = Path(__file__).parent / "img"
OUT.mkdir(exist_ok=True)
GREEN, RED, BLUE, GREY, ORANGE = "#16a34a", "#dc2626", "#2563eb", "#94a3b8", "#ea580c"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "figure.dpi": 150, "axes.grid": True, "grid.alpha": 0.25})


# ---------------- simulators (same maths as the Lua scripts) ----------------
class TokenBucket:
    def __init__(self, limit, window, burst=None):
        self.cap = burst or limit
        self.rate = limit / window
        self.tokens, self.ts = float(self.cap), None

    def refilled(self, now):
        if self.ts is None:
            return self.tokens
        return min(self.cap, self.tokens + (now - self.ts) * self.rate)

    def allow(self, now, cost=1):
        tokens = self.refilled(now)
        ok = tokens >= cost
        if ok:
            tokens -= cost
        self.tokens, self.ts = tokens, now
        return ok


class LeakyBucket:
    def __init__(self, limit, window, burst=None):
        self.cap = burst or limit
        self.rate = limit / window
        self.level, self.ts = 0.0, None

    def drained(self, now):
        if self.ts is None:
            return self.level
        return max(0.0, self.level - (now - self.ts) * self.rate)

    def allow(self, now, cost=1):
        level = self.drained(now)
        ok = level + cost <= self.cap
        if ok:
            level += cost
        self.level, self.ts = level, now
        return ok


class FixedWindow:
    def __init__(self, limit, window):
        self.limit, self.window, self.counts = limit, window, {}

    def allow(self, now, cost=1):
        idx = math.floor(now / self.window)
        if self.counts.get(idx, 0) + cost > self.limit:
            return False
        self.counts[idx] = self.counts.get(idx, 0) + cost
        return True


class SlidingLog:
    def __init__(self, limit, window):
        self.limit, self.window, self.log = limit, window, []

    def allow(self, now, cost=1):
        self.log = [t for t in self.log if t > now - self.window]
        if len(self.log) + cost > self.limit:
            return False
        self.log += [now] * cost
        return True


class SlidingCounter:
    def __init__(self, limit, window):
        self.limit, self.window, self.counts = limit, window, {}

    def estimate(self, now):
        idx = math.floor(now / self.window)
        weight = (self.window - (now - idx * self.window)) / self.window
        return self.counts.get(idx - 1, 0) * weight + self.counts.get(idx, 0)

    def allow(self, now, cost=1):
        if self.estimate(now) + cost > self.limit:
            return False
        idx = math.floor(now / self.window)
        self.counts[idx] = self.counts.get(idx, 0) + cost
        return True


def markers(ax, times, results, y=0.0):
    for t, ok in zip(times, results):
        ax.scatter(t, y, marker="o" if ok else "X", s=70, color=GREEN if ok else RED,
                   zorder=5, edgecolor="white", linewidth=0.6)


# ---------------- Figure 1: token bucket ----------------
def fig_token_bucket():
    tb = TokenBucket(limit=10, window=60, burst=5)  # 1 token / 6 s, holds 5
    req = [1, 1.5, 2, 2.5, 3, 4, 9, 14, 15, 21, 22, 23, 40, 41]
    res, tl, tv = [], [], []
    clock = [i / 10 for i in range(0, 501)]
    probe = TokenBucket(10, 60, 5)
    events = iter(req)
    nxt = next(events, None)
    for t in clock:
        while nxt is not None and nxt <= t:
            res.append(probe.allow(nxt))
            nxt = next(events, None)
        tl.append(t)
        tv.append(probe.refilled(t) if probe.ts is not None else 5)
    fig, ax = plt.subplots(figsize=(9, 3.8))
    ax.step(tl, tv, where="post", color=BLUE, linewidth=2)
    ax.axhline(5, color=GREY, linestyle="--", linewidth=1)
    ax.text(0.5, 5.12, "capacity (burst) = 5 tokens", color=GREY, fontsize=9)
    markers(ax, req, res, y=-0.45)
    ax.set_ylim(-0.9, 5.8)
    ax.set_xlim(0, 50)
    ax.set_xlabel("time (seconds)")
    ax.set_ylabel("tokens in bucket")
    ax.set_title("Token bucket: limit 10/min, burst 5  (refill = 1 token every 6 s)")
    ax.annotate("burst: 5 requests pass\ninstantly, then bucket is empty", xy=(3.2, 0.4), xytext=(4.5, 3.9),
                arrowprops=dict(arrowstyle="->", color=ORANGE), color=ORANGE, fontsize=9)
    ax.annotate("after waiting, one token\nhas refilled: request passes", xy=(9, 1.3), xytext=(15, 2.3),
                arrowprops=dict(arrowstyle="->", color=ORANGE), color=ORANGE, fontsize=9)
    ax.scatter([], [], marker="o", color=GREEN, label="allowed (200)")
    ax.scatter([], [], marker="X", color=RED, label="denied (429)")
    ax.legend(loc="upper right", frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "token_bucket.png")
    plt.close(fig)


# ---------------- Figure 2: leaky bucket ----------------
def fig_leaky_bucket():
    lb = LeakyBucket(limit=10, window=60, burst=5)  # drains 1 unit / 6 s
    req = [1, 1.5, 2, 2.5, 3, 4, 9, 14, 15, 21, 22, 23, 40, 41]
    probe = LeakyBucket(10, 60, 5)
    res, tl, tv = [], [], []
    events = iter(req)
    nxt = next(events, None)
    for i in range(0, 501):
        t = i / 10
        while nxt is not None and nxt <= t:
            res.append(probe.allow(nxt))
            nxt = next(events, None)
        tl.append(t)
        tv.append(probe.drained(t))
    fig, ax = plt.subplots(figsize=(9, 3.8))
    ax.fill_between(tl, tv, step="post", color=BLUE, alpha=0.25)
    ax.step(tl, tv, where="post", color=BLUE, linewidth=2)
    ax.axhline(5, color=RED, linestyle="--", linewidth=1)
    ax.text(0.5, 5.12, "capacity = 5  (overflow = rejected)", color=RED, fontsize=9)
    markers(ax, req, res, y=-0.45)
    ax.set_ylim(-0.9, 5.8)
    ax.set_xlim(0, 50)
    ax.set_xlabel("time (seconds)")
    ax.set_ylabel("water level in bucket")
    ax.set_title("Leaky bucket (meter): each request adds 1; level drains steadily at 1 per 6 s")
    ax.scatter([], [], marker="o", color=GREEN, label="allowed (200)")
    ax.scatter([], [], marker="X", color=RED, label="denied (429)")
    ax.legend(loc="upper right", frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "leaky_bucket.png")
    plt.close(fig)


# ---------------- Figure 3: fixed window boundary problem ----------------
def fig_boundary():
    limit, window = 5, 10
    req = [7.5, 8.0, 8.5, 9.0, 9.5, 10.2, 10.6, 11.0, 11.4, 11.8]
    fixed, log = FixedWindow(limit, window), SlidingLog(limit, window)
    rf = [fixed.allow(t) for t in req]
    rl = [log.allow(t) for t in req]
    fig, axes = plt.subplots(2, 1, figsize=(9, 4.4), sharex=True)
    for ax, res, title in ((axes[0], rf, "Fixed window: allows 10 requests in 4.3 s (2x the limit)"),
                           (axes[1], rl, "Sliding window log: allows only 5 in any 10 s span")):
        ax.axvline(10, color=ORANGE, linestyle="--", linewidth=1.5)
        ax.axvspan(0, 10, color=BLUE, alpha=0.06)
        ax.axvspan(10, 20, color=ORANGE, alpha=0.06)
        markers(ax, req, res)
        ax.set_ylim(-0.6, 0.6)
        ax.set_yticks([])
        ax.set_title(title, fontsize=10, loc="left")
        ax.grid(False)
    axes[0].text(8, 0.4, "window 1", ha="center", color=BLUE)
    axes[0].text(12, 0.4, "window 2", ha="center", color=ORANGE)
    axes[1].set_xlim(6, 14)
    axes[1].set_xlabel("time (seconds)   [limit = 5 per 10 s, window boundary at t = 10]")
    axes[1].scatter([], [], marker="o", color=GREEN, label="allowed")
    axes[1].scatter([], [], marker="X", color=RED, label="denied")
    axes[1].legend(loc="lower right", frameon=False, ncol=2)
    fig.tight_layout()
    fig.savefig(OUT / "fixed_vs_sliding_boundary.png")
    plt.close(fig)


# ---------------- Figure 4: sliding window counter estimate ----------------
def fig_sliding_counter():
    prev, cur, limit, window = 8, 3, 10, 60
    xs = [i / 10 for i in range(0, 601)]
    est = [prev * (window - t) / window + cur for t in xs]
    fig, ax = plt.subplots(figsize=(9, 3.8))
    ax.plot(xs, est, color=BLUE, linewidth=2.2)
    ax.axhline(limit, color=RED, linestyle="--", linewidth=1)
    ax.text(45, limit + 0.15, "limit = 10", color=RED)
    ax.scatter([15], [8 * 0.75 + 3], color=ORANGE, zorder=5, s=60)
    ax.annotate("at t = 15 s: weight = (60-15)/60 = 0.75\nestimate = 8 x 0.75 + 3 = 9\n"
                "one more request fits (9 + 1 = 10)", xy=(15, 9), xytext=(28, 10.45),
                arrowprops=dict(arrowstyle="->", color=ORANGE), color=ORANGE, fontsize=9)
    ax.set_xlim(0, 60)
    ax.set_ylim(2.5, 12)
    ax.set_xlabel("seconds into the current window")
    ax.set_ylabel("estimated requests in the last 60 s")
    ax.set_title("Sliding window counter: estimate = previous x weight + current  (previous = 8, current = 3)")
    fig.tight_layout()
    fig.savefig(OUT / "sliding_window_counter.png")
    plt.close(fig)


# ---------------- Figure 5: all five on the same traffic ----------------
def fig_comparison():
    limit, window = 5, 10
    req = sorted([0.2, 0.4, 0.6, 0.8, 1.0, 1.2] + [9.4, 9.6, 9.8, 10.0, 10.2, 10.4] + [14 + i * 1.0 for i in range(0, 17)])
    algos = [("Token bucket", TokenBucket(limit, window)), ("Leaky bucket", LeakyBucket(limit, window)),
             ("Fixed window", FixedWindow(limit, window)), ("Sliding log", SlidingLog(limit, window)),
             ("Sliding counter", SlidingCounter(limit, window))]
    fig, ax = plt.subplots(figsize=(10, 4.2))
    for row, (name, algo) in enumerate(algos):
        res = [algo.allow(t) for t in req]
        markers(ax, req, res, y=len(algos) - 1 - row)
        ax.text(-0.8, len(algos) - 1 - row, f"{name}\n({sum(res)} of {len(req)} allowed)", ha="right",
                va="center", fontsize=9)
    ax.axvline(10, color=ORANGE, linestyle=":", linewidth=1.2)
    ax.text(10.1, 4.55, "fixed-window\nboundary", color=ORANGE, fontsize=8, va="bottom")
    ax.set_xlim(-0.5, 31)
    ax.set_ylim(-0.7, 5.1)
    ax.set_yticks([])
    ax.grid(axis="y", alpha=0)
    ax.set_xlabel("time (seconds)   [every algorithm configured as 5 requests per 10 s]")
    ax.set_title("Same traffic, five algorithms: a burst, a second burst at the window edge, then steady 1 req/s")
    ax.scatter([], [], marker="o", color=GREEN, label="allowed")
    ax.scatter([], [], marker="X", color=RED, label="denied")
    ax.legend(loc="upper right", frameon=False, ncol=2)
    fig.subplots_adjust(left=0.19, right=0.98, top=0.9, bottom=0.14)
    fig.savefig(OUT / "algorithm_comparison.png")
    plt.close(fig)
    return {name: None for name, _ in algos}


# ---------------- Figure 6: race condition ----------------
def fig_race():
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6))
    for ax in axes:
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 6)
        ax.axis("off")
    # left: naive
    ax = axes[0]
    ax.set_title("Naive: read, check, write in Python", loc="left", fontsize=10.5, color=RED)
    ax.text(1.5, 5.4, "Request A", ha="center", fontweight="bold")
    ax.text(8.0, 5.4, "Request B", ha="center", fontweight="bold")
    steps = [(4.5, "read count = 9", None), (3.5, None, "read count = 9"), (2.5, "9 < 10: allow, write 10", None),
             (1.5, None, "9 < 10: allow, write 10")]
    for y, a, b in steps:
        if a:
            ax.text(1.5, y, a, ha="center", fontsize=8.5, bbox=dict(boxstyle="round", fc="#fee2e2", ec=RED))
        if b:
            ax.text(8.0, y, b, ha="center", fontsize=8.5, bbox=dict(boxstyle="round", fc="#fee2e2", ec=RED))
    ax.text(5, 0.4, "Both allowed: 11 requests pass a limit of 10", ha="center", color=RED, fontweight="bold",
            fontsize=9)
    # right: lua
    ax = axes[1]
    ax.set_title("Lua script: one atomic step inside Redis", loc="left", fontsize=10.5, color=GREEN)
    ax.text(1.5, 5.4, "Request A", ha="center", fontweight="bold")
    ax.text(8.0, 5.4, "Request B", ha="center", fontweight="bold")
    ax.text(1.5, 4.0, "script runs fully:\nread 9, allow, write 10", ha="center", fontsize=8.5,
            bbox=dict(boxstyle="round", fc="#dcfce7", ec=GREEN))
    ax.text(8.0, 4.0, "waits its turn...", ha="center", fontsize=8.5, color=GREY,
            bbox=dict(boxstyle="round", fc="#f1f5f9", ec=GREY))
    ax.text(8.0, 2.4, "script runs fully:\nread 10, deny (429)", ha="center", fontsize=8.5,
            bbox=dict(boxstyle="round", fc="#fee2e2", ec=RED))
    ax.text(5, 0.4, "Exactly 10 requests pass. Never 11.", ha="center", color=GREEN, fontweight="bold",
            fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "race_condition.png")
    plt.close(fig)


if __name__ == "__main__":
    fig_token_bucket()
    fig_leaky_bucket()
    fig_boundary()
    fig_sliding_counter()
    fig_comparison()
    fig_race()
    print("figures written to", OUT)
