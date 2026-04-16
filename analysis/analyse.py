"""First-time buyer dataset analysis.

Loads the monthly FTB / Former-owner-occupier CSV (2011-01 → 2026-01),
splits LAD-level rows from country aggregates, then derives growth/loss
metrics per region and writes:

  outputs/county_stats.csv     – per-region metrics used by the maps
  outputs/national_trend.png   – FTB price trajectory, UK & countries
  outputs/top_bottom_growth.png – bar chart of 10 best / 10 worst LADs
  outputs/affordability_gap.png – FTB vs former-owner-occupier prices
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "First-Time-Buyer-Former-Owner-Occupied-2026-01.csv"
OUT = ROOT / "outputs"
OUT.mkdir(parents=True, exist_ok=True)

LAD_PREFIXES = ("E06", "E07", "E08", "E09", "S12", "W06")
COUNTRY_CODES = {"K03000001": "United Kingdom", "E92000001": "England",
                 "S92000003": "Scotland", "W92000004": "Wales"}


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


def baseline_latest(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Per-region baseline (2011 avg), 5y-ago, 1y-ago, latest values."""
    latest_dt = df["Date"].max()
    one_year = latest_dt - pd.DateOffset(years=1)
    five_year = latest_dt - pd.DateOffset(years=5)

    base = (df[df["Date"].dt.year == 2011]
            .groupby(["region", "code"])[col].mean()
            .rename(f"{col}_2011_avg"))

    def snapshot(target_date: pd.Timestamp, label: str) -> pd.Series:
        window = df[(df["Date"] >= target_date - pd.DateOffset(months=2)) &
                    (df["Date"] <= target_date + pd.DateOffset(months=2))]
        return (window.groupby(["region", "code"])[col].mean()
                .rename(f"{col}_{label}"))

    latest = snapshot(latest_dt, "latest")
    ly = snapshot(one_year, "1y_ago")
    fy = snapshot(five_year, "5y_ago")
    return pd.concat([base, fy, ly, latest], axis=1)


def county_metrics(df: pd.DataFrame) -> pd.DataFrame:
    lad = df[df["is_lad"]].copy()
    price = baseline_latest(lad, "ftb_price")
    idx = baseline_latest(lad, "ftb_index")

    stats = price.join(idx, how="outer").reset_index()
    stats["growth_full_pct"] = (stats["ftb_price_latest"] /
                                stats["ftb_price_2011_avg"] - 1) * 100
    stats["growth_5y_pct"] = (stats["ftb_price_latest"] /
                              stats["ftb_price_5y_ago"] - 1) * 100
    stats["growth_1y_pct"] = (stats["ftb_price_latest"] /
                              stats["ftb_price_1y_ago"] - 1) * 100

    years = (df["Date"].max() - pd.Timestamp("2011-06-01")).days / 365.25
    stats["cagr_pct"] = ((stats["ftb_price_latest"] /
                          stats["ftb_price_2011_avg"]) ** (1 / years) - 1) * 100
    return stats.sort_values("growth_full_pct", ascending=False)


def national_trend_chart(df: pd.DataFrame) -> None:
    nations = df[df["code"].isin(COUNTRY_CODES)].copy()
    nations["region"] = nations["code"].map(COUNTRY_CODES)
    fig, ax = plt.subplots(figsize=(10, 6))
    for name, grp in nations.groupby("region"):
        grp = grp.sort_values("Date")
        ax.plot(grp["Date"], grp["ftb_price"] / 1000, label=name, lw=2)
    ax.set_title("First-time buyer average price by nation (2011–2026)")
    ax.set_xlabel("Date")
    ax.set_ylabel("Average price (£ thousand)")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "national_trend.png", dpi=130)
    plt.close(fig)


def top_bottom_chart(stats: pd.DataFrame) -> None:
    lo = stats.nsmallest(10, "growth_full_pct")
    hi = stats.nlargest(10, "growth_full_pct")
    combined = pd.concat([hi, lo])
    colors = ["#2a9d8f"] * len(hi) + ["#e76f51"] * len(lo)

    fig, ax = plt.subplots(figsize=(10, 8))
    ax.barh(combined["region"], combined["growth_full_pct"], color=colors)
    ax.invert_yaxis()
    ax.set_xlabel("FTB average price % change 2011 → 2026-01")
    ax.set_title("Top 10 growth and bottom 10 growth LADs (full period)")
    ax.axvline(0, color="black", lw=0.8)
    ax.grid(alpha=0.3, axis="x")
    fig.tight_layout()
    fig.savefig(OUT / "top_bottom_growth.png", dpi=130)
    plt.close(fig)


def affordability_chart(df: pd.DataFrame) -> None:
    uk = df[df["code"] == "K03000001"].sort_values("Date")
    if uk.empty:
        uk = df[df["code"] == "E92000001"].sort_values("Date")
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(uk["Date"], uk["ftb_price"] / 1000, label="First-time buyer", lw=2)
    ax.plot(uk["Date"], uk["foo_price"] / 1000, label="Former owner-occupier",
            lw=2, color="#e76f51")
    ax.fill_between(uk["Date"], uk["ftb_price"] / 1000, uk["foo_price"] / 1000,
                    alpha=0.15, color="grey", label="Affordability gap")
    ax.set_title("UK average price – FTB vs former owner-occupier")
    ax.set_xlabel("Date")
    ax.set_ylabel("Average price (£ thousand)")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "affordability_gap.png", dpi=130)
    plt.close(fig)


def main() -> None:
    df = load()
    stats = county_metrics(df)
    stats.to_csv(OUT / "county_stats.csv", index=False)

    national_trend_chart(df)
    top_bottom_chart(stats)
    affordability_chart(df)

    latest_dt = df["Date"].max().strftime("%Y-%m")
    uk_rows = df[df["code"] == "K03000001"]
    if uk_rows.empty:
        uk_rows = df[df["code"] == "E92000001"]
    uk_2011 = uk_rows[uk_rows["Date"].dt.year == 2011]["ftb_price"].mean()
    uk_latest = uk_rows[uk_rows["Date"] == uk_rows["Date"].max()]["ftb_price"].iloc[0]
    uk_growth = (uk_latest / uk_2011 - 1) * 100

    print(f"Latest month in data: {latest_dt}")
    print(f"UK FTB avg price 2011: £{uk_2011:,.0f}  →  {latest_dt}: £{uk_latest:,.0f}")
    print(f"UK FTB full-period growth: {uk_growth:+.1f}%")
    print(f"Counties analysed: {len(stats):,}")
    print("\nTop 5 full-period growth LADs:")
    print(stats[["region", "code", "ftb_price_2011_avg",
                 "ftb_price_latest", "growth_full_pct"]].head().to_string(index=False))
    print("\nBottom 5 full-period growth LADs:")
    print(stats[["region", "code", "ftb_price_2011_avg",
                 "ftb_price_latest", "growth_full_pct"]].tail().to_string(index=False))
    print("\nTop 5 latest 12-month growth LADs:")
    print(stats.nlargest(5, "growth_1y_pct")[
        ["region", "code", "ftb_price_1y_ago", "ftb_price_latest",
         "growth_1y_pct"]].to_string(index=False))
    print("\nBottom 5 latest 12-month growth LADs:")
    print(stats.nsmallest(5, "growth_1y_pct")[
        ["region", "code", "ftb_price_1y_ago", "ftb_price_latest",
         "growth_1y_pct"]].to_string(index=False))


if __name__ == "__main__":
    main()
