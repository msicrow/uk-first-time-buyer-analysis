"""First-time buyer dataset analysis.

Loads monthly FTB / Former-owner-occupier CSV (2011-01 → 2026-01), splits
LAD-level rows from country aggregates, and derives growth/loss metrics
per region. Produces:

  outputs/county_stats.csv        – per-LAD metrics used by the maps
  outputs/national_trend.png      – FTB price trajectory by nation
  outputs/top_bottom_growth.png   – 10 best / 10 worst LADs, full period
  outputs/affordability_gap.png   – FTB vs former-owner-occupier prices
  outputs/data_profile.txt        – dataset shape, coverage, missingness

Baseline is the 2012 full-year mean (UK/England/Wales series start
2012-01; only Scottish LADs have 2011 data, so using 2012 keeps the
cross-country comparison consistent).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "First-Time-Buyer-Former-Owner-Occupied-2026-01.csv"
OUT = ROOT / "outputs"
OUT.mkdir(parents=True, exist_ok=True)

BASELINE_YEAR = 2012
LAD_PREFIXES = ("E06", "E07", "E08", "E09", "S12", "W06")
COUNTRY_CODES = {
    "K03000001": "United Kingdom",
    "E92000001": "England",
    "S92000003": "Scotland",
    "W92000004": "Wales",
}


def load() -> pd.DataFrame:
    df = pd.read_csv(DATA, parse_dates=["Date"])
    df = df.rename(columns={
        "Region_Name": "region",
        "Area_Code": "code",
        "First_Time_Buyer_Average_Price": "ftb_price",
        "First_Time_Buyer_Index": "ftb_index",
        "First_Time_Buyer_Monthly_Change": "ftb_m_pct",
        "First_Time_Buyer_Annual_Change": "ftb_y_pct",
        "Former_Owner_Occupier_Average_Price": "foo_price",
        "Former_Owner_Occupier_Index": "foo_index",
        "Former_Owner_Occupier_Monthly_Change": "foo_m_pct",
        "Former_Owner_Occupier_Annual_Change": "foo_y_pct",
    })
    df["Date"] = pd.to_datetime(df["Date"])
    df["prefix"] = df["code"].str[:3]
    df["is_lad"] = df["prefix"].isin(LAD_PREFIXES)
    return df


def write_profile(df: pd.DataFrame) -> None:
    lines = []
    lines.append(f"Rows: {len(df):,}")
    lines.append(f"Unique regions: {df['code'].nunique():,}")
    lines.append(f"Date range: {df['Date'].min().date()} → {df['Date'].max().date()}")
    lines.append(f"Unique area-code prefixes: {sorted(df['prefix'].unique())}")
    lines.append("")
    lines.append("Missing values per column:")
    lines.append(df.isnull().sum().to_string())
    lines.append("")
    lines.append("Country-level series first non-null FTB price:")
    for code, name in COUNTRY_CODES.items():
        sub = df[(df["code"] == code) & df["ftb_price"].notna()]
        first = sub["Date"].min() if not sub.empty else "none"
        lines.append(f"  {name:<15} ({code}): {first}")

    lad = df[df["is_lad"]]
    first_seen = lad.groupby("code")["Date"].min()
    late_starters = (first_seen.dt.year > BASELINE_YEAR).sum()
    lines.append("")
    lines.append(f"LADs total: {lad['code'].nunique()}; "
                 f"starting after {BASELINE_YEAR}: {late_starters}")
    (OUT / "data_profile.txt").write_text("\n".join(lines))


def snapshot(df: pd.DataFrame, col: str, target: pd.Timestamp,
             label: str, window_months: int = 2) -> pd.Series:
    lo = target - pd.DateOffset(months=window_months)
    hi = target + pd.DateOffset(months=window_months)
    window = df[(df["Date"] >= lo) & (df["Date"] <= hi)]
    return (window.groupby(["region", "code"])[col].mean()
            .rename(f"{col}_{label}"))


def county_metrics(df: pd.DataFrame) -> pd.DataFrame:
    lad = df[df["is_lad"]].copy()
    latest_dt = df["Date"].max()

    base = (lad[lad["Date"].dt.year == BASELINE_YEAR]
            .groupby(["region", "code"])["ftb_price"].mean()
            .rename("ftb_price_baseline"))
    base_idx = (lad[lad["Date"].dt.year == BASELINE_YEAR]
                .groupby(["region", "code"])["ftb_index"].mean()
                .rename("ftb_index_baseline"))
    latest = snapshot(lad, "ftb_price", latest_dt, "latest")
    latest_idx = snapshot(lad, "ftb_index", latest_dt, "latest")
    one_y = snapshot(lad, "ftb_price", latest_dt - pd.DateOffset(years=1), "1y_ago")
    five_y = snapshot(lad, "ftb_price", latest_dt - pd.DateOffset(years=5), "5y_ago")

    stats = pd.concat([base, base_idx, five_y, one_y, latest, latest_idx],
                      axis=1).reset_index()

    stats["growth_full_pct"] = (stats["ftb_price_latest"] /
                                stats["ftb_price_baseline"] - 1) * 100
    stats["growth_5y_pct"] = (stats["ftb_price_latest"] /
                              stats["ftb_price_5y_ago"] - 1) * 100
    stats["growth_1y_pct"] = (stats["ftb_price_latest"] /
                              stats["ftb_price_1y_ago"] - 1) * 100
    years = (latest_dt - pd.Timestamp(f"{BASELINE_YEAR}-06-01")).days / 365.25
    stats["cagr_pct"] = ((stats["ftb_price_latest"] /
                          stats["ftb_price_baseline"]) ** (1 / years) - 1) * 100
    return stats.sort_values("growth_full_pct", ascending=False)


def national_trend_chart(df: pd.DataFrame) -> str:
    nations = df[df["code"].isin(COUNTRY_CODES)].copy()
    nations["region"] = nations["code"].map(COUNTRY_CODES)
    fig, ax = plt.subplots(figsize=(10, 6))
    final_vals = {}
    for name, grp in nations.groupby("region"):
        grp = grp.sort_values("Date")
        ax.plot(grp["Date"], grp["ftb_price"] / 1000, label=name, lw=2)
        final_vals[name] = grp["ftb_price"].iloc[-1]

    uk_first = nations[nations["code"] == "K03000001"].sort_values("Date")
    uk_change = (uk_first["ftb_price"].iloc[-1] /
                 uk_first["ftb_price"].iloc[0] - 1) * 100
    title = (f"UK first-time-buyer price up {uk_change:+.0f}% since 2012; "
             f"Scotland cheapest, England priciest")
    ax.set_title(title)
    ax.set_xlabel(f"Source: HM Land Registry extract, "
                  f"Jan {df['Date'].min().year}–Jan {df['Date'].max().year}")
    ax.set_ylabel("FTB average price (£ thousand)")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(OUT / "national_trend.png", dpi=130)
    plt.close(fig)
    return title


def top_bottom_chart(stats: pd.DataFrame) -> None:
    clean = stats.dropna(subset=["growth_full_pct"])
    lo = clean.nsmallest(10, "growth_full_pct")
    hi = clean.nlargest(10, "growth_full_pct")
    combined = pd.concat([hi, lo])
    colors = ["#2a9d8f"] * len(hi) + ["#e76f51"] * len(lo)

    fig, ax = plt.subplots(figsize=(10, 8))
    ax.barh(combined["region"], combined["growth_full_pct"], color=colors)
    ax.invert_yaxis()
    ax.set_xlabel("FTB average price % change, 2012 baseline → Jan 2026")
    span_hi = hi["growth_full_pct"].iloc[0]
    span_lo = lo["growth_full_pct"].iloc[-1]
    ax.set_title(
        f"FTB price growth ranges from {span_lo:+.0f}% to {span_hi:+.0f}% "
        f"across LADs (n={len(clean)})")
    ax.axvline(0, color="black", lw=0.8)
    ax.grid(alpha=0.3, axis="x")
    fig.tight_layout()
    fig.savefig(OUT / "top_bottom_growth.png", dpi=130)
    plt.close(fig)


def affordability_chart(df: pd.DataFrame) -> None:
    uk = df[df["code"] == "K03000001"].sort_values("Date")
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(uk["Date"], uk["ftb_price"] / 1000, label="First-time buyer", lw=2)
    ax.plot(uk["Date"], uk["foo_price"] / 1000, label="Former owner-occupier",
            lw=2, color="#e76f51")
    ax.fill_between(uk["Date"], uk["ftb_price"] / 1000, uk["foo_price"] / 1000,
                    alpha=0.15, color="grey", label="Affordability gap")
    gap_start = uk["foo_price"].iloc[0] - uk["ftb_price"].iloc[0]
    gap_end = uk["foo_price"].iloc[-1] - uk["ftb_price"].iloc[-1]
    ax.set_title(
        f"FTB–FOO price gap widened from £{gap_start/1000:.0f}k "
        f"to £{gap_end/1000:.0f}k (UK, {uk['Date'].min().year}–"
        f"{uk['Date'].max().year})")
    ax.set_xlabel("Date")
    ax.set_ylabel("Average price (£ thousand)")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(OUT / "affordability_gap.png", dpi=130)
    plt.close(fig)


def main() -> None:
    df = load()
    write_profile(df)

    stats = county_metrics(df)
    stats.to_csv(OUT / "county_stats.csv", index=False)

    national_trend_chart(df)
    top_bottom_chart(stats)
    affordability_chart(df)

    latest_dt = df["Date"].max().strftime("%Y-%m")
    uk = df[df["code"] == "K03000001"].sort_values("Date")
    uk_base = uk[uk["Date"].dt.year == BASELINE_YEAR]["ftb_price"].mean()
    uk_latest = uk["ftb_price"].iloc[-1]
    uk_full = (uk_latest / uk_base - 1) * 100
    uk_1y = uk["ftb_y_pct"].iloc[-1]

    clean = stats.dropna(subset=["growth_full_pct"])
    print("=" * 60)
    print(f"Dataset: 2011-01 → {latest_dt}; baseline = 2012 mean")
    print(f"UK FTB: £{uk_base:,.0f} (2012 avg)  →  £{uk_latest:,.0f} ({latest_dt})")
    print(f"UK FTB full-period growth: {uk_full:+.1f}%  "
          f"(latest 12m: {uk_1y:+.1f}%)")
    print(f"LADs with full history: {len(clean)} of {len(stats)}")
    print("=" * 60)
    print("\nTop 5 full-period growth LADs:")
    print(clean[["region", "code", "ftb_price_baseline",
                 "ftb_price_latest", "growth_full_pct",
                 "cagr_pct"]].head().to_string(index=False))
    print("\nBottom 5 full-period growth LADs:")
    print(clean[["region", "code", "ftb_price_baseline",
                 "ftb_price_latest", "growth_full_pct",
                 "cagr_pct"]].tail().to_string(index=False))
    print("\nTop 5 latest 12-month growth LADs:")
    print(clean.nlargest(5, "growth_1y_pct")[
        ["region", "code", "ftb_price_1y_ago", "ftb_price_latest",
         "growth_1y_pct"]].to_string(index=False))
    print("\nBottom 5 latest 12-month growth LADs (biggest recent losses):")
    print(clean.nsmallest(5, "growth_1y_pct")[
        ["region", "code", "ftb_price_1y_ago", "ftb_price_latest",
         "growth_1y_pct"]].to_string(index=False))


if __name__ == "__main__":
    main()
