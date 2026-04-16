"""UK choropleth maps of first-time-buyer price growth.

Reads county_stats.csv (produced by analyse.py) and the cached 2013 ONS
LAD GeoJSON (via analysis/cache/gb_lad.geojson). Because the dataset uses
post-2013 LAD codes for LADs that have since been merged into new
unitaries (Dorset, Buckinghamshire, Somerset, North Yorkshire, etc.),
we expand new codes onto their constituent 2013 polygons so every LAD
in the dataset appears on the map.

Outputs:
  outputs/map_full_period.png      static choropleth, 2012 → Jan 2026
  outputs/map_latest_12m.png       static choropleth, latest 12-month change
  outputs/uk_ftb_interactive.html  Plotly map with year slider 2013–2026
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from matplotlib.colors import TwoSlopeNorm

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "First-Time-Buyer-Former-Owner-Occupied-2026-01.csv"
OUT = ROOT / "outputs"
CACHE = ROOT / "cache"

# New LAD (2019–2023 reorganisation) → constituent 2013 LAD codes.
# The dataset only carries the new code, so we map it onto the old polygons
# that cover the same geography — the new-code FTB value is replicated
# across each constituent polygon for rendering.
NEW_TO_OLD = {
    "E06000058": ["E06000028", "E07000048", "E06000029"],          # Bournemouth, Christchurch and Poole
    "E06000059": ["E07000049", "E07000050", "E07000051",
                  "E07000052", "E07000053"],                       # Dorset
    "E06000060": ["E07000004", "E07000005", "E07000006",
                  "E07000007"],                                    # Buckinghamshire
    "E06000061": ["E07000150", "E07000152", "E07000153",
                  "E07000156"],                                    # North Northamptonshire
    "E06000062": ["E07000151", "E07000154", "E07000155"],          # West Northamptonshire
    "E06000063": ["E07000026", "E07000028", "E07000029"],          # Cumberland
    "E06000064": ["E07000027", "E07000030", "E07000031"],          # Westmorland and Furness
    "E06000065": ["E07000163", "E07000164", "E07000165",
                  "E07000166", "E07000167", "E07000168",
                  "E07000169"],                                    # North Yorkshire
    "E06000066": ["E07000187", "E07000188", "E07000189",
                  "E07000190", "E07000191"],                       # Somerset
    "E07000244": ["E07000205", "E07000206"],                       # East Suffolk
    "E07000245": ["E07000201", "E07000204"],                       # West Suffolk
    "E08000038": ["E08000016"],                                    # Barnsley
    "E08000039": ["E08000019"],                                    # Sheffield
    "S12000047": ["S12000015"],                                    # Fife
    "S12000048": ["S12000024"],                                    # Perth and Kinross
    "S12000049": ["S12000046"],                                    # City of Glasgow
    "S12000050": ["S12000044"],                                    # North Lanarkshire
}


def load_boundaries() -> gpd.GeoDataFrame:
    gdf = gpd.read_file(CACHE / "gb_lad.geojson")
    gdf = gdf.rename(columns={"LAD13CD": "code_2013", "LAD13NM": "lad_name"})
    return gdf[["code_2013", "lad_name", "geometry"]].to_crs(epsg=27700)


def expand_stats(stats: pd.DataFrame, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Attach each LAD's metric(s) to every matching 2013 polygon."""
    old_to_new: dict[str, str] = {}
    for new, olds in NEW_TO_OLD.items():
        for o in olds:
            old_to_new[o] = new

    gdf = gdf.copy()
    gdf["code"] = gdf["code_2013"].map(lambda c: old_to_new.get(c, c))
    merged = gdf.merge(stats, on="code", how="left")
    return merged


def diverging_choropleth(gdf: gpd.GeoDataFrame, column: str, title: str,
                         outfile: Path, unit: str = "%") -> None:
    valid = gdf[column].dropna()
    vmax = max(abs(valid.min()), abs(valid.max()))
    norm = TwoSlopeNorm(vmin=-vmax, vcenter=0, vmax=vmax)

    fig, ax = plt.subplots(figsize=(11, 13))
    gdf.plot(column=column, ax=ax, cmap="RdYlGn", norm=norm,
             edgecolor="white", linewidth=0.2,
             missing_kwds={"color": "#dddddd", "label": "No data"})
    ax.set_axis_off()
    ax.set_title(title, fontsize=13, wrap=True)

    sm = plt.cm.ScalarMappable(cmap="RdYlGn", norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.6, pad=0.02)
    cbar.set_label(f"FTB price change ({unit})")

    fig.tight_layout()
    fig.savefig(outfile, dpi=130, bbox_inches="tight")
    plt.close(fig)


def build_static_maps(stats: pd.DataFrame, gdf: gpd.GeoDataFrame) -> None:
    merged = expand_stats(stats, gdf)

    # REAL-TERMS full period (headline map).
    hi = stats["growth_full_real_pct"].max()
    lo = stats["growth_full_real_pct"].min()
    n = stats["growth_full_real_pct"].notna().sum()
    n_down = (stats["growth_full_real_pct"] < 0).sum()
    diverging_choropleth(
        merged, "growth_full_real_pct",
        title=(f"REAL FTB price change 2012 → Jan 2026 by UK LAD "
               f"(CPIH-deflated)\n"
               f"Range {lo:+.0f}% to {hi:+.0f}%   "
               f"{n_down}/{n} LADs fell in real terms   "
               f"Grey = no data or outside GB"),
        outfile=OUT / "map_full_period_real.png")

    # NOMINAL full period (reference).
    hi = stats["growth_full_pct"].max()
    lo = stats["growth_full_pct"].min()
    diverging_choropleth(
        merged, "growth_full_pct",
        title=(f"NOMINAL FTB price change 2012 → Jan 2026 by UK LAD\n"
               f"Range {lo:+.0f}% to {hi:+.0f}%   "
               f"(ignores +47% CPIH inflation over the period)"),
        outfile=OUT / "map_full_period.png")

    # REAL-TERMS latest 12 months.
    hi = stats["growth_1y_real_pct"].max()
    lo = stats["growth_1y_real_pct"].min()
    n_down_1y = (stats["growth_1y_real_pct"] < 0).sum()
    diverging_choropleth(
        merged, "growth_1y_real_pct",
        title=(f"REAL FTB price change, last 12 months to Jan 2026 "
               f"(CPIH-deflated)\n"
               f"Range {lo:+.0f}% to {hi:+.0f}%   "
               f"{n_down_1y}/{n} LADs fell in real terms this year"),
        outfile=OUT / "map_latest_12m_real.png")

    # NOMINAL latest 12 months (reference).
    hi = stats["growth_1y_pct"].max()
    lo = stats["growth_1y_pct"].min()
    diverging_choropleth(
        merged, "growth_1y_pct",
        title=(f"NOMINAL FTB price change, last 12 months to Jan 2026\n"
               f"Range {lo:+.0f}% to {hi:+.0f}%   "
               f"Red = falling, Green = rising"),
        outfile=OUT / "map_latest_12m.png")


def interactive_map(stats: pd.DataFrame, gdf: gpd.GeoDataFrame,
                    real: bool = False) -> None:
    """Plotly choropleth with year slider.

    Uses go.Figure with frames that only update the `z`/hovertext arrays;
    the geojson is embedded once at layout level, so the HTML stays small.

    If ``real`` is True, the map shows CPIH-deflated prices in Jan 2026 £
    and is written to ``uk_ftb_interactive_real.html``; otherwise nominal
    prices, ``uk_ftb_interactive.html``.
    """
    from inflation import deflator  # local import to avoid circular

    df = pd.read_csv(DATA, parse_dates=["Date"])
    df = df.rename(columns={
        "Region_Name": "region", "Area_Code": "code",
        "First_Time_Buyer_Average_Price": "ftb_price",
        "First_Time_Buyer_Index": "ftb_index",
        "First_Time_Buyer_Annual_Change": "ftb_y_pct",
    })
    df = df[df["code"].str[:3].isin(["E06","E07","E08","E09","S12","W06"])]
    if real:
        infl = deflator(pd.Timestamp("2026-01-01"))
        df = df.merge(infl.rename("deflator"), left_on="Date",
                      right_index=True, how="left")
        df["ftb_price"] = df["ftb_price"] * df["deflator"]
    df["year"] = df["Date"].dt.year
    yearly = (df.groupby(["year", "region", "code"])
              [["ftb_price", "ftb_index", "ftb_y_pct"]].mean().reset_index())

    # Expand new codes onto old polygons for matching.
    old_to_new = {o: n for n, olds in NEW_TO_OLD.items() for o in olds}

    # Aggressive simplification; we view the map at UK scale so polygon detail
    # below ~1 km is not useful but it dominates file size.
    geo = gdf.to_crs(epsg=4326).copy()
    geo["geometry"] = geo["geometry"].simplify(0.01, preserve_topology=True)
    geo["code"] = geo["code_2013"].map(lambda c: old_to_new.get(c, c))

    geojson = json.loads(geo[["code_2013", "geometry"]].to_json())
    for feat in geojson["features"]:
        feat["id"] = feat["properties"]["code_2013"]

    # Per-polygon lookup of LAD region name (for hover).
    polygon_codes = geo["code_2013"].tolist()
    polygon_to_data_code = dict(zip(geo["code_2013"], geo["code"]))

    data_by_year = {y: grp.set_index("code") for y, grp in yearly.groupby("year")}

    years = sorted(data_by_year.keys())
    frames = []
    for y in years:
        lookup = data_by_year[y]
        z_vals, hover = [], []
        for pcode in polygon_codes:
            dcode = polygon_to_data_code[pcode]
            if dcode in lookup.index:
                row = lookup.loc[dcode]
                z_vals.append(row["ftb_price"])
                hover.append(
                    f"<b>{row['region']}</b><br>"
                    f"Year: {y}<br>"
                    f"FTB price: £{row['ftb_price']:,.0f}<br>"
                    f"FTB index: {row['ftb_index']:.1f}<br>"
                    f"Annual change: {row['ftb_y_pct']:+.1f}%")
            else:
                z_vals.append(None)
                hover.append(f"No data ({y})")
        frames.append(go.Frame(
            name=str(y),
            data=[go.Choroplethmapbox(z=z_vals, text=hover, hoverinfo="text")],
        ))

    # Initial trace = first year
    initial = frames[0].data[0]
    fig = go.Figure(
        data=[go.Choroplethmapbox(
            geojson=geojson,
            locations=polygon_codes,
            z=initial.z,
            text=initial.text,
            hoverinfo="text",
            colorscale="Viridis",
            zmin=50_000,
            zmax=(1_100_000 if real else 600_000),
            marker_line_width=0.2,
            marker_line_color="white",
            colorbar=dict(title=("Real FTB<br>price (Jan 2026 £)"
                                 if real else "FTB avg<br>price (£)")),
        )],
        frames=frames,
    )

    kind = "real (Jan 2026 £, CPIH-deflated)" if real else "nominal"
    fig.update_layout(
        mapbox_style="carto-positron",
        mapbox_center={"lat": 54.5, "lon": -3.3},
        mapbox_zoom=4.6,
        margin=dict(l=0, r=0, t=60, b=0),
        height=780,
        title=(f"UK first-time-buyer {kind} price by LAD, 2011–2026"
               "  (use the slider or Play to step through years)"),
        sliders=[dict(
            active=0,
            currentvalue={"prefix": "Year: "},
            steps=[dict(
                method="animate",
                label=str(y),
                args=[[str(y)], dict(mode="immediate",
                                     frame=dict(duration=400, redraw=True),
                                     transition=dict(duration=0))],
            ) for y in years],
        )],
        updatemenus=[dict(
            type="buttons", showactive=False,
            buttons=[
                dict(label="Play", method="animate",
                     args=[None, dict(frame=dict(duration=600, redraw=True),
                                      fromcurrent=True,
                                      transition=dict(duration=0))]),
                dict(label="Pause", method="animate",
                     args=[[None], dict(frame=dict(duration=0, redraw=False),
                                        mode="immediate",
                                        transition=dict(duration=0))]),
            ],
            x=0.02, y=0.02, xanchor="left", yanchor="bottom",
        )],
    )
    outfile = ("uk_ftb_interactive_real.html" if real
               else "uk_ftb_interactive.html")
    fig.write_html(OUT / outfile, include_plotlyjs="cdn")


def main() -> None:
    stats = pd.read_csv(OUT / "county_stats.csv")
    gdf = load_boundaries()
    build_static_maps(stats, gdf)
    interactive_map(stats, gdf, real=False)
    interactive_map(stats, gdf, real=True)
    print("Maps written to", OUT)


if __name__ == "__main__":
    main()
