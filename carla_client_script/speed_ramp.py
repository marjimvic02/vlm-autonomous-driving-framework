"""Illustrate the commanded speed ramp; this is not measured vehicle speed."""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

plt.rcParams.update({"font.family": "serif", "font.size": 11})

RAMP_RATE = 3.0  # m/s^2  (Table 8)
DT = 0.1  # 100 ms -> 10 Hz ramp update

# planner decisions: (time_of_decision, commanded_target_speed)
decisions = [
    (0.0, 8.0),
    (3.5, 13.0),  # SPEED_UP
    (7.0, 4.0),  # SLOW_DOWN
    (11.0, 8.0),  # back to cruise
]

t_end = 15.0
t = np.arange(0, t_end + DT, DT)

# --- target: step function held until next decision ---
target = np.zeros_like(t)
for i, ti in enumerate(t):
    # last decision at or before ti
    cur = decisions[0][1]
    for td, sp in decisions:
        if ti >= td:
            cur = sp
    target[i] = cur

# --- actual speed: ramp toward target at RAMP_RATE, updated every DT ---
speed = np.zeros_like(t)
v = 3.0  # initial speed
for i, ti in enumerate(t):
    tgt = target[i]
    dv = RAMP_RATE * DT
    if v < tgt:
        v = min(v + dv, tgt)
    elif v > tgt:
        v = max(v - dv, tgt)
    speed[i] = v

fig, ax = plt.subplots(figsize=(8.4, 4.3))

# target step (commanded)
ax.step(
    t,
    target,
    where="post",
    color="#cc7a2e",
    lw=1.8,
    ls="--",
    label="commanded target speed (planner)",
)
# ramped speed command
ax.plot(t, speed, color="#3b5b92", lw=2.4, label="ramped speed command (10 Hz)")

# mark planner decision instants
for td, sp in decisions:
    ax.axvline(td, color="#bbbbbb", lw=0.9, ls=":", zorder=0)
    ax.plot(
        td,
        sp,
        marker="v",
        ms=9,
        color="#cc7a2e",
        zorder=5,
        markeredgecolor="black",
        markeredgewidth=0.5,
    )
ax.text(
    decisions[1][0] + 0.15,
    decisions[1][1] + 0.5,
    "planner decision",
    fontsize=8,
    color="#cc7a2e",
    style="italic",
)

# annotate ramp slope
ax.annotate(
    "RAMP_RATE = 3 m/s$^2$\n(updated every 100 ms)",
    xy=(4.7, 10.5),
    xytext=(8.1, 11.0),
    fontsize=9,
    color="#3b5b92",
    ha="left",
    arrowprops=dict(arrowstyle="->", color="#3b5b92", lw=1.0),
)

# annotate sparse vs dense
ax.annotate(
    "",
    xy=(0.4, 14.2),
    xytext=(3.5, 14.2),
    arrowprops=dict(arrowstyle="<->", color="#888888", lw=1.0),
)
ax.text(
    2.0,
    14.4,
    "planner decides every few seconds",
    fontsize=8,
    color="#555555",
    ha="center",
    va="bottom",
)

ax.set_xlabel("Time (s)")
ax.set_ylabel("Speed (m/s)")
ax.set_xlim(0, t_end)
ax.set_ylim(0, 15.5)
ax.legend(loc="lower right", fontsize=9, frameon=True, framealpha=0.95)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.grid(True, alpha=0.25, lw=0.6)

fig.tight_layout()
fig.savefig("speed_ramp.pdf", bbox_inches="tight")
fig.savefig("speed_ramp.png", dpi=140, bbox_inches="tight")
print("saved")

# --- verify ramp physics ---
# max change per step should be RAMP_RATE*DT = 0.3 m/s
dv_max = np.max(np.abs(np.diff(speed)))
print("max |dv| per 100ms step = %.3f m/s (should be <= %.3f)" % (dv_max, RAMP_RATE * DT))
# time to go 8->13 should be 5/3 = 1.67 s
print("ramp 8->13 expected %.2f s" % ((13 - 8) / RAMP_RATE))
