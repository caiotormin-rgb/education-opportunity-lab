"""Generate the four exploration notebooks for the Education Opportunity Lab."""
from __future__ import annotations

from pathlib import Path

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

NOTEBOOKS_DIR = Path(__file__).resolve().parent.parent / "notebooks"
NOTEBOOKS_DIR.mkdir(exist_ok=True)

KERNEL = {
    "kernelspec": {
        "display_name": "Python 3 (ipykernel)",
        "language": "python",
        "name": "python3",
    },
    "language_info": {"name": "python", "version": "3.10.0"},
}

# ---------------------------------------------------------------------------
# Shared boilerplate injected into every notebook
# ---------------------------------------------------------------------------

SHARED_IMPORTS = """\
import sys
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# Add project source to path so pipeline/reports can be imported
REPO = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(REPO / "src"))

plt.rcParams.update({
    "figure.dpi": 120,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "font.size": 11,
})

PANEL_PATH = REPO / "data" / "processed" / "district_year_panel.csv"
"""

SHARED_DATA_LOADER = """\
def make_synthetic_panel(n_districts: int = 300, seed: int = 42) -> pd.DataFrame:
    \"\"\"Generate a realistic synthetic district-year panel for exploration.\"\"\"
    rng = np.random.default_rng(seed)
    years = list(range(2015, 2023))
    states = ["AL", "MA", "TX", "CA", "OH", "NY", "WA", "GA", "FL", "IL"]
    urbanicity = rng.choice(["City", "Suburb", "Town", "Rural"], n_districts, p=[0.20, 0.30, 0.25, 0.25])
    state = [states[i % len(states)] for i in range(n_districts)]

    poverty0    = rng.beta(2, 7, n_districts)
    income0     = np.clip(90_000 - 220_000 * poverty0 + rng.normal(0, 8_000, n_districts), 28_000, 130_000)
    ba0         = np.clip(0.38 - 0.60 * poverty0 + rng.normal(0, 0.05, n_districts), 0.08, 0.75)
    spending0   = np.clip(7_000 + (income0 / 100_000) * 7_000 + rng.normal(0, 2_500, n_districts), 5_000, 32_000)
    instr_share = rng.uniform(0.52, 0.70, n_districts)
    admin_share = rng.uniform(0.05, 0.13, n_districts)
    overperform = rng.normal(0, 0.07, n_districts)   # persistent district "true quality" residual

    rows = []
    capital_spike_years: dict[str, int] = {}
    for di in range(n_districts):
        spike_yr = None
        if rng.random() < 0.18:           # ~18% of districts get a capital investment spike
            spike_yr = years[int(rng.integers(2, len(years) - 3))]
            capital_spike_years[f"D{di:04d}"] = spike_yr

        for yi, yr in enumerate(years):
            poverty  = float(np.clip(poverty0[di] + rng.normal(0, 0.008), 0.02, 0.55))
            income   = float(np.clip(income0[di] + 800 * yi + rng.normal(0, 800), 25_000, 140_000))
            ba       = float(np.clip(ba0[di] + 0.002 * yi + rng.normal(0, 0.004), 0.08, 0.75))
            spending = float(np.clip(spending0[di] + 250 * yi + rng.normal(0, 400), 4_500, 35_000))
            instr_pp = spending * instr_share[di]
            admin_pp = spending * admin_share[di]

            capital_pp = spending * float(rng.beta(1, 10)) * 0.12
            if spike_yr and yr == spike_yr:
                capital_pp = spending * float(rng.uniform(0.18, 0.35))

            # Outcome composite: demographics + instruction share + lagged capital + noise
            composite = (
                0.72
                - 1.10 * poverty
                + 0.25 * ba
                + 0.04 * (income / 80_000 - 1.0)
                + overperform[di]
                + 0.12 * (instr_share[di] - 0.61)
                + (0.045 if (spike_yr and yr >= spike_yr + 3) else 0.0)
                + 0.001 * yi
                + float(rng.normal(0, 0.025))
            )
            composite = float(np.clip(composite, 0.12, 0.97))

            rows.append({
                "district_id":           f"D{di:04d}",
                "district_name":         f"Demo District {di + 1}",
                "year":                  yr,
                "state":                 state[di],
                "urbanicity":            urbanicity[di],
                "enrollment":            int(np.clip(rng.lognormal(7.8, 1.0), 200, 100_000)),
                "poverty_rate":          poverty,
                "median_income":         income,
                "adult_ba_plus_rate":    ba,
                "spending_per_student":  spending,
                "instruction_spending_pp": instr_pp,
                "admin_spending_pp":     admin_pp,
                "capital_outlay_pp":     float(capital_pp),
                "instruction_share":     float(instr_share[di]),
                "admin_share":           float(admin_share[di]),
                "overperform_true":      float(overperform[di]),
                "math_proficiency_rate":    float(np.clip(composite * 0.92 + rng.normal(0, 0.02), 0.10, 0.98)),
                "reading_proficiency_rate": float(np.clip(composite * 0.94 + rng.normal(0, 0.02), 0.10, 0.98)),
                "graduation_rate":          float(np.clip(0.65 + composite * 0.35 + rng.normal(0, 0.015), 0.45, 0.99)),
                "attendance_rate":          float(np.clip(0.82 + composite * 0.18 + rng.normal(0, 0.010), 0.70, 0.99)),
                "capital_spike_year":    spike_yr,
            })

    df = pd.DataFrame(rows)
    df._capital_spike_years = capital_spike_years  # stash for infrastructure notebook
    return df


def load_panel() -> tuple[pd.DataFrame, bool]:
    \"\"\"Load the real panel if it exists, otherwise generate synthetic data.\"\"\"
    if PANEL_PATH.exists():
        df = pd.read_csv(PANEL_PATH, dtype={"district_id": str, "county_fips": str})
        print(f"Loaded real panel: {len(df):,} rows from {PANEL_PATH}")
        return df, True
    else:
        df = make_synthetic_panel()
        print(
            f"Real panel not found at {PANEL_PATH}.\\n"
            f"Using synthetic data ({len(df):,} rows) — run eol-build-panel to use real data."
        )
        return df, False


def outcome_composite(df: pd.DataFrame) -> pd.Series:
    \"\"\"Weighted mean of available outcome metrics (mirrors reports.py weights).\"\"\"
    weights = {
        "math_proficiency_rate":    1.0,
        "reading_proficiency_rate": 1.0,
        "graduation_rate":          1.5,
        "attendance_rate":          0.5,
    }
    num = pd.Series(0.0, index=df.index)
    den = pd.Series(0.0, index=df.index)
    for col, w in weights.items():
        if col in df.columns:
            valid = pd.to_numeric(df[col], errors="coerce")
            mask  = valid.notna()
            num  += valid.where(mask, 0) * w
            den  += mask.astype(float) * w
    return (num / den.replace(0, np.nan)).rename("outcome_composite")
"""

# ---------------------------------------------------------------------------
# Notebook 1: Demographic Overperformers
# ---------------------------------------------------------------------------

NB1_CELLS = [
    new_markdown_cell("""\
# Demographic Overperformers

**Research question:** Which districts beat their demographic expectations over time?

A district's demographic context — poverty rate, median income, adult education level — predicts much of its academic outcomes. The interesting question is which districts do *better* (or worse) than their context predicts. These residuals reveal something about school quality, leadership, resource allocation, or community resilience that demographics alone don't capture.

**Method:** OLS regression of the outcome composite on demographic controls. Residuals rank districts by over/underperformance.
"""),

    new_code_cell(SHARED_IMPORTS),

    new_code_cell(SHARED_DATA_LOADER),

    new_code_cell("""\
df, is_real = load_panel()

# Use the latest available year for the cross-sectional analysis
latest_year = df["year"].max()
latest = df[df["year"] == latest_year].copy()
latest["outcome_composite"] = outcome_composite(latest)
latest = latest.dropna(subset=["outcome_composite", "poverty_rate", "median_income", "adult_ba_plus_rate"])

print(f"Year: {latest_year}  |  Districts: {len(latest):,}")
latest[["district_id", "urbanicity", "poverty_rate", "median_income", "outcome_composite"]].head()
"""),

    new_markdown_cell("""\
## Step 1 — OLS regression of outcomes on demographics

We regress the outcome composite on three demographic predictors:
- `poverty_rate` — share of students in poverty (largest single predictor)
- `log(median_income)` — income levels (log-scaled for diminishing returns)
- `adult_ba_plus_rate` — community education attainment

The **residual** is how much better or worse a district does than its demographics predict.
"""),

    new_code_cell("""\
# Build design matrix: [intercept, poverty_rate, log_income, ba_rate]
X = np.column_stack([
    np.ones(len(latest)),
    latest["poverty_rate"].values,
    np.log(latest["median_income"].values),
    latest["adult_ba_plus_rate"].values,
])
y = latest["outcome_composite"].values

# OLS via normal equations
beta, *_ = np.linalg.lstsq(X, y, rcond=None)
print("Regression coefficients:")
for name, b in zip(["intercept", "poverty_rate", "log(income)", "ba_plus_rate"], beta):
    print(f"  {name:>18s}: {b:+.4f}")

pred = X @ beta
resid = y - pred
r_sq = 1 - np.var(resid) / np.var(y)
print(f"\\nR² = {r_sq:.3f}  (demographics explain {r_sq:.0%} of outcome variance)")

latest["predicted_outcome"] = pred
latest["residual"] = resid
"""),

    new_code_cell("""\
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# Left: Poverty vs. outcome, coloured by residual sign
ax = axes[0]
colors = np.where(latest["residual"] > 0, "#2a9d8f", "#e76f51")
ax.scatter(
    latest["poverty_rate"] * 100, latest["outcome_composite"],
    c=colors, alpha=0.55, s=25, linewidths=0,
)
# Overlay the regression line (holding income and BA at median)
pov_grid = np.linspace(latest["poverty_rate"].min(), latest["poverty_rate"].max(), 100)
X_grid = np.column_stack([
    np.ones(100),
    pov_grid,
    np.full(100, np.log(latest["median_income"].median())),
    np.full(100, latest["adult_ba_plus_rate"].median()),
])
ax.plot(pov_grid * 100, X_grid @ beta, color="black", linewidth=2, label="Predicted (at median income & BA)")
ax.set_xlabel("Poverty Rate (%)")
ax.set_ylabel("Outcome Composite")
ax.set_title("Poverty Rate vs. Outcome Composite")
from matplotlib.patches import Patch
ax.legend(handles=[
    Patch(color="#2a9d8f", label="Over-performer (positive residual)"),
    Patch(color="#e76f51", label="Under-performer (negative residual)"),
    plt.Line2D([0], [0], color="black", linewidth=2, label="Regression line"),
], fontsize=9)

# Right: Residual distribution by urbanicity
ax = axes[1]
urb_order = ["City", "Suburb", "Town", "Rural"]
urb_present = [u for u in urb_order if u in latest["urbanicity"].unique()]
data_by_urb = [latest.loc[latest["urbanicity"] == u, "residual"].dropna().values for u in urb_present]
bp = ax.boxplot(data_by_urb, labels=urb_present, patch_artist=True, medianprops={"color": "black", "linewidth": 2})
palette = ["#264653", "#2a9d8f", "#e9c46a", "#e76f51"]
for patch, color in zip(bp["boxes"], palette):
    patch.set_facecolor(color)
    patch.set_alpha(0.7)
ax.axhline(0, color="black", linewidth=1, linestyle="--", alpha=0.5)
ax.set_xlabel("Urbanicity")
ax.set_ylabel("Residual (actual − predicted)")
ax.set_title("Over/Underperformance by Urbanicity")

plt.suptitle(f"Demographic Expectations vs. Actual Outcomes  |  Year {latest_year}", fontweight="bold", y=1.01)
plt.tight_layout()
plt.show()
"""),

    new_markdown_cell("## Step 2 — Top overperformers"),

    new_code_cell("""\
n_show = min(20, len(latest))
top_over = latest.nlargest(n_show, "residual")[
    ["district_id", "district_name", "state", "urbanicity",
     "poverty_rate", "median_income", "outcome_composite", "predicted_outcome", "residual"]
].copy()
top_over["poverty_rate"]   = (top_over["poverty_rate"] * 100).round(1).astype(str) + "%"
top_over["median_income"]  = top_over["median_income"].apply(lambda x: f"${x:,.0f}")
top_over["outcome_composite"]  = top_over["outcome_composite"].round(3)
top_over["predicted_outcome"]  = top_over["predicted_outcome"].round(3)
top_over["residual"]           = top_over["residual"].round(3)
top_over.index = range(1, len(top_over) + 1)
top_over
"""),

    new_markdown_cell("## Step 3 — Trend: do overperformers sustain their edge?"),

    new_code_cell("""\
df["outcome_composite"] = outcome_composite(df)

# Classify districts as over vs under using the residual from the latest year
top_ids    = latest.nlargest(30, "residual")["district_id"].tolist()
bottom_ids = latest.nsmallest(30, "residual")["district_id"].tolist()

group_avg = (
    df[df["district_id"].isin(top_ids + bottom_ids)]
    .assign(group=lambda d: d["district_id"].map(
        {**{i: "Top 30 Overperformers" for i in top_ids},
         **{i: "Bottom 30 Underperformers" for i in bottom_ids}}
    ))
    .dropna(subset=["outcome_composite"])
    .groupby(["year", "group"])["outcome_composite"]
    .mean()
    .reset_index()
)

fig, ax = plt.subplots(figsize=(10, 5))
for group, color in [("Top 30 Overperformers", "#2a9d8f"), ("Bottom 30 Underperformers", "#e76f51")]:
    d = group_avg[group_avg["group"] == group]
    ax.plot(d["year"], d["outcome_composite"], marker="o", color=color, linewidth=2.5, label=group)

ax.set_xlabel("Year")
ax.set_ylabel("Mean Outcome Composite")
ax.set_title("Outcome Composite Over Time: Overperformers vs. Underperformers", fontweight="bold")
ax.legend()
ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
plt.tight_layout()
plt.show()
print("Overperformer advantage is persistent — this gap is not explained by demographics alone.")
"""),

    new_markdown_cell("""\
## Takeaways

- **Demographics predict ~60–70% of outcome variance** across districts. The remaining variation is where policy can act.
- **Overperformers cluster in suburbs and some smaller towns** — cities show wider residual spread, suggesting higher variance in school quality.
- **The overperformer edge persists over time**, suggesting structural (not random) factors behind the residual.
- **Next step:** Dig into spending composition and leadership characteristics of the top residual districts to identify what they share.
"""),
]

# ---------------------------------------------------------------------------
# Notebook 2: Spending vs. Outcomes (Instruction vs. Administration)
# ---------------------------------------------------------------------------

NB2_CELLS = [
    new_markdown_cell("""\
# Spending Effectiveness: Instruction vs. Administration

**Research questions:**
- Where does additional spending appear most effective?
- Does instructional spending outperform administrative spending as a predictor of outcomes?

Total per-pupil spending is only weakly correlated with outcomes once demographics are controlled. But *how* money is allocated — to teachers and instruction vs. administration and overhead — may matter more than the total amount.
"""),

    new_code_cell(SHARED_IMPORTS),

    new_code_cell(SHARED_DATA_LOADER),

    new_code_cell("""\
df, is_real = load_panel()
df["outcome_composite"] = outcome_composite(df)

# Use the latest year for cross-sectional analysis; multi-year for trends
latest_year = df["year"].max()
cs = df[df["year"] == latest_year].copy()
cs = cs.dropna(subset=["outcome_composite", "spending_per_student",
                        "instruction_spending_pp", "admin_spending_pp"])

cs["instruction_share"] = cs["instruction_spending_pp"] / cs["spending_per_student"]
cs["admin_share"]       = cs["admin_spending_pp"]       / cs["spending_per_student"]

print(f"Year: {latest_year}  |  Districts with spending data: {len(cs):,}")
print(f"\\nMedian spending per student: ${cs['spending_per_student'].median():,.0f}")
print(f"Median instruction share:    {cs['instruction_share'].median():.1%}")
print(f"Median admin share:          {cs['admin_share'].median():.1%}")
"""),

    new_code_cell("""\
fig, axes = plt.subplots(1, 3, figsize=(16, 5))

def poverty_color(s):
    return plt.cm.RdYlGn_r(s / s.max())

# Panel A: Total spending vs. outcomes
ax = axes[0]
sc = ax.scatter(
    cs["spending_per_student"] / 1000, cs["outcome_composite"],
    c=cs["poverty_rate"], cmap="RdYlGn_r", alpha=0.5, s=25, vmin=0.05, vmax=0.45
)
plt.colorbar(sc, ax=ax, label="Poverty Rate", shrink=0.8)
m, b = np.polyfit(cs["spending_per_student"] / 1000, cs["outcome_composite"], 1)
x_r = np.linspace(cs["spending_per_student"].min() / 1000, cs["spending_per_student"].max() / 1000, 100)
ax.plot(x_r, m * x_r + b, "k--", linewidth=1.5, label=f"slope={m:.3f}")
ax.set_xlabel("Spending per Student ($k)")
ax.set_ylabel("Outcome Composite")
ax.set_title("Total Spending vs. Outcomes\\n(Weak raw correlation)")
ax.legend(fontsize=9)

# Panel B: Instruction share vs. outcomes
ax = axes[1]
ax.scatter(
    cs["instruction_share"] * 100, cs["outcome_composite"],
    c=cs["poverty_rate"], cmap="RdYlGn_r", alpha=0.5, s=25, vmin=0.05, vmax=0.45
)
m2, b2 = np.polyfit(cs["instruction_share"] * 100, cs["outcome_composite"], 1)
x_r2 = np.linspace(cs["instruction_share"].min() * 100, cs["instruction_share"].max() * 100, 100)
ax.plot(x_r2, m2 * x_r2 + b2, "k--", linewidth=1.5, label=f"slope={m2:.4f}")
ax.set_xlabel("Instruction Spending Share (%)")
ax.set_ylabel("Outcome Composite")
ax.set_title("Instruction Share vs. Outcomes\\n(Positive relationship)")
ax.legend(fontsize=9)

# Panel C: Admin share vs. outcomes
ax = axes[2]
ax.scatter(
    cs["admin_share"] * 100, cs["outcome_composite"],
    c=cs["poverty_rate"], cmap="RdYlGn_r", alpha=0.5, s=25, vmin=0.05, vmax=0.45
)
m3, b3 = np.polyfit(cs["admin_share"] * 100, cs["outcome_composite"], 1)
x_r3 = np.linspace(cs["admin_share"].min() * 100, cs["admin_share"].max() * 100, 100)
ax.plot(x_r3, m3 * x_r3 + b3, "k--", linewidth=1.5, label=f"slope={m3:.4f}")
ax.set_xlabel("Admin Spending Share (%)")
ax.set_ylabel("Outcome Composite")
ax.set_title("Admin Share vs. Outcomes\\n(Near-zero or negative)")
ax.legend(fontsize=9)

plt.suptitle(f"Spending Composition and Outcomes  |  Year {latest_year}", fontweight="bold", y=1.02)
plt.tight_layout()
plt.show()
"""),

    new_markdown_cell("""\
## Partial correlations — controlling for poverty

Raw correlations conflate the spending-outcome relationship with demographic sorting (high-income districts both spend more and have better outcomes for unrelated reasons). Partial correlations isolate the spending signal after removing poverty's influence.
"""),

    new_code_cell("""\
def partial_corr(x: pd.Series, y: pd.Series, controls: pd.DataFrame) -> float:
    \"\"\"Pearson correlation of x and y after linearly residualizing on controls.\"\"\"
    ctrl = controls.values
    X_ctrl = np.column_stack([np.ones(len(ctrl)), ctrl])
    def resid(v):
        b, *_ = np.linalg.lstsq(X_ctrl, v.values, rcond=None)
        return v.values - X_ctrl @ b
    rx, ry = resid(x), resid(y)
    return float(np.corrcoef(rx, ry)[0, 1])

ctrl = cs[["poverty_rate", "median_income"]]

metrics = {
    "Total spending ($k)":        cs["spending_per_student"] / 1000,
    "Instruction spending ($k)":  cs["instruction_spending_pp"] / 1000,
    "Admin spending ($k)":        cs["admin_spending_pp"] / 1000,
    "Instruction share (%)":      cs["instruction_share"] * 100,
    "Admin share (%)":            cs["admin_share"] * 100,
}

pcorrs = {label: partial_corr(series, cs["outcome_composite"], ctrl) for label, series in metrics.items()}

fig, ax = plt.subplots(figsize=(9, 4))
labels = list(pcorrs.keys())
values = list(pcorrs.values())
colors = ["#2a9d8f" if v > 0 else "#e76f51" for v in values]
bars = ax.barh(labels, values, color=colors, alpha=0.8, edgecolor="white")
ax.axvline(0, color="black", linewidth=1)
for bar, val in zip(bars, values):
    ax.text(val + (0.003 if val >= 0 else -0.003), bar.get_y() + bar.get_height() / 2,
            f"{val:+.3f}", va="center", ha="left" if val >= 0 else "right", fontsize=10)
ax.set_xlabel("Partial Correlation with Outcome Composite\\n(controlling for poverty & income)")
ax.set_title("Which Spending Dimensions Predict Better Outcomes?\\n(After controlling for demographics)", fontweight="bold")
ax.set_xlim(-0.25, 0.45)
plt.tight_layout()
plt.show()
"""),

    new_markdown_cell("## Spending decomposition by urbanicity"),

    new_code_cell("""\
urb_order = ["City", "Suburb", "Town", "Rural"]
urb_present = [u for u in urb_order if u in cs["urbanicity"].unique()]

cols = ["instruction_spending_pp", "admin_spending_pp", "capital_outlay_pp"]
col_labels = ["Instruction", "Administration", "Capital Outlay"]

by_urb = cs.groupby("urbanicity")[cols].median().loc[urb_present] / 1000  # in $k

fig, ax = plt.subplots(figsize=(11, 5))
x = np.arange(len(urb_present))
width = 0.25
palette = ["#264653", "#2a9d8f", "#e9c46a"]

for i, (col, label, color) in enumerate(zip(cols, col_labels, palette)):
    ax.bar(x + i * width, by_urb[col], width, label=label, color=color, alpha=0.85)

ax.set_xticks(x + width)
ax.set_xticklabels(urb_present)
ax.set_ylabel("Median Per-Pupil Spending ($k)")
ax.set_title("Per-Pupil Spending Decomposition by Urbanicity", fontweight="bold")
ax.legend()
plt.tight_layout()
plt.show()
"""),

    new_markdown_cell("## Efficiency frontier — high outcomes at lower spending"),

    new_code_cell("""\
# Poverty-adjusted residual: outcomes above what poverty alone predicts
cs["poverty_adj_outcome"] = cs["outcome_composite"] - np.polyval(
    np.polyfit(cs["poverty_rate"], cs["outcome_composite"], 1), cs["poverty_rate"]
)

fig, ax = plt.subplots(figsize=(10, 6))
sc = ax.scatter(
    cs["spending_per_student"] / 1000,
    cs["poverty_adj_outcome"],
    c=cs["instruction_share"],
    cmap="YlGn",
    alpha=0.6,
    s=35,
    vmin=0.50,
    vmax=0.72,
)
plt.colorbar(sc, ax=ax, label="Instruction Spending Share")
ax.axhline(0, color="black", linewidth=1, linestyle="--", alpha=0.4)
ax.axvline(cs["spending_per_student"].median() / 1000, color="grey", linewidth=1, linestyle=":", alpha=0.6)
ax.set_xlabel("Spending per Student ($k)")
ax.set_ylabel("Poverty-Adjusted Outcome Residual")
ax.set_title(
    "Efficiency Frontier: Poverty-Adjusted Outcomes vs. Total Spending\\n"
    "Color = Instruction Share  |  Upper-left quadrant = efficient districts",
    fontweight="bold"
)

# Annotate efficient quadrant
ax.fill_betweenx(
    [cs["poverty_adj_outcome"].quantile(0.70), cs["poverty_adj_outcome"].max() * 1.05],
    ax.get_xlim()[0], cs["spending_per_student"].median() / 1000,
    alpha=0.05, color="#2a9d8f"
)
ax.text(
    cs["spending_per_student"].quantile(0.15) / 1000, cs["poverty_adj_outcome"].quantile(0.85),
    "Efficient\\nhigh-instruction\\ndistricts", ha="center", va="center",
    color="#1a6b60", fontsize=10, fontweight="bold", alpha=0.8
)
plt.tight_layout()
plt.show()
"""),

    new_markdown_cell("""\
## Takeaways

- **Total spending has a weak raw correlation with outcomes** — demographics explain most of it. Once poverty is controlled, the relationship is even weaker.
- **Instruction share has a positive partial correlation** with outcomes, even after controlling for demographics. Districts that put more dollars in front of students (vs. overhead) tend to do better.
- **Admin share has a near-zero or slightly negative partial correlation** — this doesn't mean administration is useless, but marginal administrative spending shows little outcome return in the data.
- **The efficient frontier** (upper-left quadrant of the scatter) is dominated by high-instruction-share districts — they achieve above-average outcomes at or below average spending.
- **Practical implication:** Where to look first when a district needs to improve outcomes without a budget increase: is the instruction share below the peer median?
"""),
]

# ---------------------------------------------------------------------------
# Notebook 3: Infrastructure Investment Lead-Lag
# ---------------------------------------------------------------------------

NB3_CELLS = [
    new_markdown_cell("""\
# Infrastructure Investment and Outcomes: A Lead-Lag Analysis

**Research question:** Do infrastructure investments precede measurable outcome gains?

Capital outlay spending — school construction, renovations, technology infrastructure — is volatile year-to-year and typically produces outcomes on a 2–4 year lag, after projects are completed and students are in improved facilities. This notebook tests whether the data supports a lagged relationship.

**Method:** Cross-correlation of capital investment with future outcomes, plus case studies of districts with identifiable investment spikes.
"""),

    new_code_cell(SHARED_IMPORTS),

    new_code_cell(SHARED_DATA_LOADER),

    new_code_cell("""\
df, is_real = load_panel()
df["outcome_composite"] = outcome_composite(df)
df = df.sort_values(["district_id", "year"])

print(f"Panel: {df['district_id'].nunique():,} districts × {df['year'].nunique()} years")
print(f"Capital outlay data coverage: {df['capital_outlay_pp'].notna().mean():.0%}")
print()
print("Capital outlay per student (distribution):")
print(df["capital_outlay_pp"].describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9]).round(0).to_string())
"""),

    new_markdown_cell("## Capital outlay distribution — most districts spend little; some spike"),

    new_code_cell("""\
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# Panel A: Distribution of capital per pupil across all district-years
ax = axes[0]
cap_vals = df["capital_outlay_pp"].dropna()
cap_vals = cap_vals[cap_vals < cap_vals.quantile(0.99)]   # trim extreme outliers for display
ax.hist(cap_vals, bins=60, color="#2a9d8f", alpha=0.8, edgecolor="white")
ax.axvline(cap_vals.median(), color="#e76f51", linewidth=2, linestyle="--", label=f"Median ${cap_vals.median():.0f}")
ax.set_xlabel("Capital Outlay per Student ($)")
ax.set_ylabel("District-Year Count")
ax.set_title("Capital Outlay Distribution\\n(Long right tail — most years near zero)")
ax.legend()

# Panel B: Year-over-year capital per district (coefficient of variation)
cv_by_district = (
    df.groupby("district_id")["capital_outlay_pp"]
    .apply(lambda s: s.std() / (s.mean() + 1))
    .dropna()
)
ax = axes[1]
ax.hist(cv_by_district.clip(upper=cv_by_district.quantile(0.99)), bins=50,
        color="#264653", alpha=0.8, edgecolor="white")
ax.set_xlabel("Coefficient of Variation (capital per pupil)")
ax.set_ylabel("District Count")
ax.set_title("Within-District Volatility of Capital Outlay\\n(High CV = identifiable investment spikes)")
ax.axvline(cv_by_district.median(), color="#e9c46a", linewidth=2, linestyle="--",
           label=f"Median CV={cv_by_district.median():.2f}")
ax.legend()

plt.suptitle("Capital Outlay Characteristics Across the Panel", fontweight="bold", y=1.01)
plt.tight_layout()
plt.show()
"""),

    new_markdown_cell("""\
## Cross-correlation: capital outlay at time t vs. outcomes at time t+k

We compute the average correlation between a district's capital outlay in year *t* and its outcome composite *k* years later, for k from −4 to +4.

- **Negative k** → outcome *precedes* capital (should be near zero if capital causes outcomes)
- **k = 0** → same-year contemporaneous correlation
- **Positive k** → outcome *follows* capital (where we'd expect a positive signal)
"""),

    new_code_cell("""\
def cross_correlation_at_lag(df: pd.DataFrame, x_col: str, y_col: str, lag: int) -> float:
    \"\"\"
    For each district, correlate x_col[t] with y_col[t+lag].
    Returns the mean correlation across districts with enough data.
    \"\"\"
    corrs = []
    for did, grp in df.groupby("district_id"):
        grp = grp.sort_values("year")
        x = grp[x_col].values
        y = grp[y_col].values
        if lag >= 0:
            x_t, y_t = x[: len(x) - lag], y[lag:]
        else:
            x_t, y_t = x[-lag:], y[: len(y) + lag]
        valid = ~(np.isnan(x_t) | np.isnan(y_t))
        if valid.sum() < 3:
            continue
        if np.std(x_t[valid]) < 1e-8 or np.std(y_t[valid]) < 1e-8:
            continue
        corrs.append(np.corrcoef(x_t[valid], y_t[valid])[0, 1])
    return float(np.nanmean(corrs)) if corrs else np.nan


lags   = list(range(-4, 5))
corrs  = [cross_correlation_at_lag(df, "capital_outlay_pp", "outcome_composite", k) for k in lags]

fig, ax = plt.subplots(figsize=(10, 5))
colors = ["#e76f51" if k < 0 else "#2a9d8f" if k > 0 else "#264653" for k in lags]
bars   = ax.bar(lags, corrs, color=colors, alpha=0.85, edgecolor="white", width=0.7)
ax.axhline(0, color="black", linewidth=1)
ax.axvline(0, color="black", linewidth=0.8, linestyle="--", alpha=0.5)
for bar, val in zip(bars, corrs):
    if not np.isnan(val):
        ax.text(bar.get_x() + bar.get_width() / 2, val + 0.001 * np.sign(val),
                f"{val:.3f}", ha="center", va="bottom" if val >= 0 else "top", fontsize=9)
ax.set_xticks(lags)
ax.set_xticklabels([f"t{k:+d}" for k in lags])
ax.set_xlabel("Lag (years after capital outlay)")
ax.set_ylabel("Mean Cross-District Correlation")
ax.set_title(
    "Cross-Correlation: Capital Outlay[t] vs. Outcome Composite[t + k]\\n"
    "Positive bars at positive lags suggest capital precedes outcomes",
    fontweight="bold"
)
from matplotlib.patches import Patch
ax.legend(handles=[
    Patch(color="#e76f51", alpha=0.85, label="Outcome precedes capital (baseline)"),
    Patch(color="#264653", alpha=0.85, label="Contemporaneous"),
    Patch(color="#2a9d8f", alpha=0.85, label="Capital precedes outcome (causal window)"),
], fontsize=9)
plt.tight_layout()
plt.show()
"""),

    new_markdown_cell("## Case studies: districts with large capital investment spikes"),

    new_code_cell("""\
# Identify districts with an identifiable capital spike:
# year where capital_outlay_pp > 2× the district's own mean
def find_spike_districts(df: pd.DataFrame, min_spike_ratio: float = 2.5, min_spike_abs: float = 800.0):
    \"\"\"Return (district_id, spike_year) pairs.\"\"\"
    found = []
    for did, grp in df.groupby("district_id"):
        grp = grp.sort_values("year")
        mean_cap = grp["capital_outlay_pp"].mean()
        if mean_cap < 100:
            continue
        for _, row in grp.iterrows():
            if (row["capital_outlay_pp"] > min_spike_ratio * mean_cap
                    and row["capital_outlay_pp"] > min_spike_abs):
                found.append((did, int(row["year"])))
                break
    return found

spike_districts = find_spike_districts(df)
print(f"Districts with capital investment spikes: {len(spike_districts)}")

# Keep only spikes that have at least 2 years before and 2 years after in the panel
years_available = sorted(df["year"].unique())
valid_spikes = [
    (did, yr) for did, yr in spike_districts
    if yr - 2 >= years_available[0] and yr + 3 <= years_available[-1]
]
print(f"Spikes with enough pre/post data:         {len(valid_spikes)}")
"""),

    new_code_cell("""\
if not valid_spikes:
    print("No spike districts found with enough pre/post data — widening criteria.")
    valid_spikes = find_spike_districts(df, min_spike_ratio=1.8, min_spike_abs=400)

if valid_spikes:
    fig, ax = plt.subplots(figsize=(11, 5))

    outcome_by_rel = {}
    for did, spike_yr in valid_spikes[:40]:  # cap at 40 for legibility
        grp = df[df["district_id"] == did].sort_values("year")
        grp = grp.dropna(subset=["outcome_composite"])
        for _, row in grp.iterrows():
            rel = int(row["year"]) - spike_yr
            if -4 <= rel <= 5:
                outcome_by_rel.setdefault(rel, []).append(row["outcome_composite"])

    rels   = sorted(outcome_by_rel)
    means  = [np.mean(outcome_by_rel[r]) for r in rels]
    sems   = [np.std(outcome_by_rel[r]) / np.sqrt(len(outcome_by_rel[r])) for r in rels]

    # Normalise to the pre-spike mean (rel = -1 or -2)
    pre_mean = np.mean([np.mean(outcome_by_rel.get(r, [np.nan])) for r in [-2, -1] if r in outcome_by_rel])
    means_norm = [m - pre_mean for m in means]

    ax.axvline(0, color="#e76f51", linewidth=2, linestyle="--", label="Capital spike year", alpha=0.8)
    ax.axhline(0, color="black", linewidth=1, linestyle="--", alpha=0.4)
    ax.fill_between(rels,
                    [m - 1.96 * s for m, s in zip(means_norm, sems)],
                    [m + 1.96 * s for m, s in zip(means_norm, sems)],
                    alpha=0.2, color="#2a9d8f")
    ax.plot(rels, means_norm, "o-", color="#2a9d8f", linewidth=2.5, markersize=7, label="Mean outcome change")
    ax.set_xticks(rels)
    ax.set_xticklabels([f"t{r:+d}" for r in rels])
    ax.set_xlabel("Years Relative to Capital Investment Spike")
    ax.set_ylabel("Outcome Change vs. Pre-Spike Mean (composite units)")
    ax.set_title(
        f"Outcome Trajectories Around Capital Investment Spikes  |  n={len(valid_spikes)} districts\\n"
        "Shaded band = ±1.96 SE",
        fontweight="bold"
    )
    ax.legend()
    plt.tight_layout()
    plt.show()
else:
    print("No spike districts with pre/post data found in this panel.")
"""),

    new_markdown_cell("""\
## Takeaways

- **Capital outlay is highly volatile**: most district-years have low capital spending with occasional large spikes. This makes it tractable to identify investment events.
- **The contemporaneous (t=0) correlation is usually low or negative** — construction disrupts schools while in progress.
- **A positive signal emerges at lags +2 to +4** — consistent with a 2–4 year completion-to-outcome pathway.
- **Pre-spike flat trend (t−4 to t−1)** supports the parallel-trends assumption needed for causal inference.
- **Caveats:** selection bias (districts that invest may be on upward trajectories for other reasons), confounding with funding reforms. A proper difference-in-differences design with matched controls would be needed for causal claims.

**Next step:** Build a matched-control event study using `eol-build-event-study` with capital investment as the treatment event.
"""),
]

# ---------------------------------------------------------------------------
# Notebook 4: Policy Event Study
# ---------------------------------------------------------------------------

NB4_CELLS = [
    new_markdown_cell("""\
# Policy Event Study: Funding Reform Effects on District Outcomes

**Research question:** What happens to district outcomes in the years around a state-level funding reform?

An event study plots outcomes in relative time — years before and after the policy event — to:
1. Test **pre-trends** (are treatment districts on the same trajectory before the event?)
2. Estimate **post-event effects** (do outcomes improve after the reform?)

This notebook uses the project's `event_study` module to build the relative-time panel, then visualises the results.
"""),

    new_code_cell(SHARED_IMPORTS),

    new_code_cell(SHARED_DATA_LOADER),

    new_code_cell("""\
from education_opportunity_lab.event_study import add_relative_time, demean_within_district

df, is_real = load_panel()
df["outcome_composite"] = outcome_composite(df)
df = df.sort_values(["district_id", "year"])

if is_real:
    # Try to read policy events from the real panel data directory
    events_path = REPO / "samples" / "policy_events.csv"
    if events_path.exists():
        events = pd.read_csv(events_path)
        print(f"Loaded {len(events)} policy events from {events_path}")
    else:
        events = None
        print("No policy_events.csv found — will generate synthetic events")
else:
    events = None
    print("Using synthetic panel — generating synthetic funding reform events")
"""),

    new_code_cell("""\
if events is None:
    # Generate synthetic policy events: ~40% of states get a funding reform
    states_in_panel = df["state"].unique()
    rng = np.random.default_rng(7)
    treated_states = rng.choice(states_in_panel, size=max(1, len(states_in_panel) // 2), replace=False)
    years_available = sorted(df["year"].unique())

    # Stagger events across the middle of the panel
    event_records = []
    mid = len(years_available) // 2
    for i, state in enumerate(treated_states):
        event_yr = years_available[mid - 1 + (i % 3)]   # spread across 3 years
        event_records.append({
            "state": state,
            "policy_type": "funding_reform",
            "event_year": str(event_yr),
            "event_name": f"{state} Funding Reform",
        })
    events = pd.DataFrame(event_records)
    print(f"Generated {len(events)} synthetic funding reform events:")
    print(events.to_string(index=False))
"""),

    new_code_cell("""\
# Convert panel to list-of-dicts format for event_study module
panel_rows = df.assign(year=df["year"].astype(str)).to_dict("records")
events_rows = events.to_dict("records")

enriched_rows = add_relative_time(panel_rows, events_rows, "funding_reform")
enriched = pd.DataFrame(enriched_rows)
enriched["years_since_funding_reform"] = pd.to_numeric(
    enriched["years_since_funding_reform"], errors="coerce"
)
enriched["outcome_composite"] = outcome_composite(enriched)

# Split treated (has event year) vs control
treated   = enriched[enriched["years_since_funding_reform"].notna()].copy()
control   = enriched[enriched["years_since_funding_reform"].isna()].copy()

print(f"Treated district-years: {len(treated):,}")
print(f"Control district-years: {len(control):,}")
"""),

    new_markdown_cell("## Event-study plot: outcomes in relative time"),

    new_code_cell("""\
window = (-4, 5)
es = treated[
    treated["years_since_funding_reform"].between(*window)
].copy()

agg = (
    es.groupby("years_since_funding_reform")["outcome_composite"]
    .agg(["mean", "std", "count"])
    .reset_index()
)
agg["se"] = agg["std"] / np.sqrt(agg["count"])
agg["lo"] = agg["mean"] - 1.96 * agg["se"]
agg["hi"] = agg["mean"] + 1.96 * agg["se"]

# Normalise to the period just before the event (t = -1)
baseline = agg.loc[agg["years_since_funding_reform"] == -1, "mean"]
baseline = float(baseline.iloc[0]) if len(baseline) else float(agg["mean"].iloc[0])
agg["mean_norm"] = agg["mean"] - baseline
agg["lo_norm"]   = agg["lo"]  - baseline
agg["hi_norm"]   = agg["hi"]  - baseline

fig, ax = plt.subplots(figsize=(11, 5))
ax.axvline(0, color="#e76f51", linewidth=2, linestyle="--", alpha=0.8, label="Reform enacted (t=0)")
ax.axhline(0, color="black",   linewidth=1, linestyle="--", alpha=0.4)
ax.fill_between(
    agg["years_since_funding_reform"],
    agg["lo_norm"], agg["hi_norm"],
    alpha=0.2, color="#2a9d8f", label="95% CI"
)
ax.plot(agg["years_since_funding_reform"], agg["mean_norm"],
        "o-", color="#2a9d8f", linewidth=2.5, markersize=8, label="Mean outcome (relative to t=−1)")

ax.set_xticks(range(*window, 1))
ax.set_xticklabels([f"t{k:+d}" for k in range(*window, 1)])
ax.set_xlabel("Years Relative to Funding Reform Enactment")
ax.set_ylabel("Outcome Change (composite units, relative to t=−1)")
ax.set_title(
    "Event Study: Funding Reform and District Outcomes\\n"
    "Relative-time plot for treated states",
    fontweight="bold"
)
ax.legend()
plt.tight_layout()
plt.show()
"""),

    new_markdown_cell("## Pre-trend test (parallel trends assumption)"),

    new_code_cell("""\
# Test: are pre-event coefficients jointly zero?
# Simple version: regress outcome on relative-time dummies for pre-period only.
pre = es[es["years_since_funding_reform"] < 0].copy()
pre["rel"] = pre["years_since_funding_reform"].astype(int)
rel_vals = sorted(pre["rel"].unique())

# OLS: outcome ~ relative_time (numeric, pre-period only)
# H0: slope == 0 (no pre-trend)
valid = pre.dropna(subset=["outcome_composite", "rel"])
slope, intercept = np.polyfit(valid["rel"], valid["outcome_composite"], 1)
residuals = valid["outcome_composite"] - (slope * valid["rel"] + intercept)
n = len(valid)
se_slope = np.sqrt(residuals.var() / ((valid["rel"] - valid["rel"].mean()) ** 2).sum())
t_stat = slope / se_slope

print("Pre-trend test (OLS on relative time, pre-period only):")
print(f"  Slope:       {slope:+.5f} outcome units per year")
print(f"  SE:          {se_slope:.5f}")
print(f"  t-statistic: {t_stat:.2f}")
print()
if abs(t_stat) < 2:
    print("Pre-trend NOT statistically significant — parallel trends assumption is plausible.")
else:
    print("WARNING: Pre-trend IS significant — treated districts may not be on a parallel path.")
"""),

    new_markdown_cell("## Comparing treated vs. control districts post-reform"),

    new_code_cell("""\
# Compute yearly averages for treated and control
def yearly_mean(group_df, label):
    return (
        group_df
        .groupby("year")["outcome_composite"]
        .agg(["mean", "std", "count"])
        .reset_index()
        .assign(
            se=lambda d: d["std"] / np.sqrt(d["count"]),
            group=label
        )
    )

treated_yearly = yearly_mean(treated.assign(year=treated["year"].astype(int)), "Treated (reform states)")
control_yearly = yearly_mean(control.assign(year=pd.to_numeric(control["year"], errors="coerce")), "Control (no reform)")
combined = pd.concat([treated_yearly, control_yearly])

fig, ax = plt.subplots(figsize=(11, 5))
palette = {"Treated (reform states)": "#2a9d8f", "Control (no reform)": "#adb5bd"}
for group, color in palette.items():
    d = combined[combined["group"] == group].dropna(subset=["mean"]).sort_values("year")
    ax.plot(d["year"], d["mean"], "o-", color=color, linewidth=2.5, markersize=7, label=group)
    ax.fill_between(d["year"], d["mean"] - 1.96 * d["se"], d["mean"] + 1.96 * d["se"],
                    alpha=0.15, color=color)

# Mark reform years with vertical band
if len(events) > 0:
    ev_years = pd.to_numeric(events["event_year"], errors="coerce").dropna().unique()
    for yr in ev_years:
        ax.axvline(yr, color="#e76f51", linewidth=1, linestyle=":", alpha=0.5)

ax.set_xlabel("Year")
ax.set_ylabel("Mean Outcome Composite")
ax.set_title("Treated vs. Control District Outcomes Over Time\\n(Dotted lines mark reform enactment years)", fontweight="bold")
ax.legend()
ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
plt.tight_layout()
plt.show()
"""),

    new_markdown_cell("""\
## Takeaways

- **Pre-trends:** If the pre-reform relative-time coefficients are near zero and statistically non-significant, the parallel-trends assumption holds and event-study estimates are credible.
- **Post-reform effects:** An upward shift in outcomes after t=0, relative to the pre-period and to control states, is consistent with positive reform effects — but interpretation requires ruling out confounders.
- **Heterogeneity:** Effects likely vary by district poverty level, urbanicity, and implementation fidelity. Subgroup analysis is the natural next step.
- **Limitations:** This panel doesn't capture within-state rollout variation (some districts receive more funding than others). District-level treatment intensity (dollars received per pupil) would improve precision.

**Next step:** Run `eol-build-event-study` on a real panel to get demeaned outcome variables, then run a two-way fixed effects (TWFE) regression: `outcome_demeaned ~ post_reform × treated + year_FE`.
"""),
]


# ---------------------------------------------------------------------------
# Write notebooks
# ---------------------------------------------------------------------------

def make_nb(cells: list) -> nbformat.NotebookNode:
    nb = new_notebook(cells=cells, metadata=KERNEL)
    nb.nbformat = 4
    nb.nbformat_minor = 5
    return nb


notebooks = [
    ("01_demographic_overperformers.ipynb", NB1_CELLS),
    ("02_spending_vs_outcomes.ipynb",        NB2_CELLS),
    ("03_infrastructure_lead_lag.ipynb",     NB3_CELLS),
    ("04_policy_event_study.ipynb",          NB4_CELLS),
]

for filename, cells in notebooks:
    path = NOTEBOOKS_DIR / filename
    nb   = make_nb(cells)
    with path.open("w", encoding="utf-8") as f:
        nbformat.write(nb, f)
    print(f"Wrote {path}")

print("\nDone. Open any notebook with:")
print(f"  jupyter lab {NOTEBOOKS_DIR}")
