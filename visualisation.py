"""All Plotly charts for the SWES Stress Lens dashboard."""

import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from typing import Dict, List


# ─── Colour palette ───
AGENT_COLOURS = {
    "bank": "#1f77b4",
    "hedge_fund": "#ff7f0e",
    "ldi_pension": "#2ca02c",
    "insurer": "#d62728",
    "oef_mmf": "#9467bd",
}

AGENT_LABELS = {
    "bank": "Banks",
    "hedge_fund": "Hedge Funds",
    "ldi_pension": "LDI / Pension",
    "insurer": "Insurers",
    "oef_mmf": "OEF / MMF",
}


def plot_market_evolution(daily_market: List[Dict]) -> go.Figure:
    """Multi-panel chart of market variable paths over 10 days."""
    df = pd.DataFrame(daily_market)
    days = df["day"] + 1

    fig = make_subplots(
        rows=3, cols=2,
        subplot_titles=[
            "Gilt Yields (bps chg)", "Credit Spreads (bps chg)",
            "Equity & FX (% chg)", "Repo Haircuts (ppt chg)",
            "Market Functioning", "VIX Level",
        ],
        vertical_spacing=0.08, horizontal_spacing=0.08,
    )

    # Gilt yields
    fig.add_trace(go.Scatter(x=days, y=df["gilt_10y_yield_chg_bps"], name="Gilt 10Y", line=dict(color="#1f77b4")), row=1, col=1)
    fig.add_trace(go.Scatter(x=days, y=df["gilt_30y_yield_chg_bps"], name="Gilt 30Y", line=dict(color="#aec7e8")), row=1, col=1)
    fig.add_trace(go.Scatter(x=days, y=df["il_gilt_yield_chg_bps"], name="IL Gilt", line=dict(color="#17becf")), row=1, col=1)

    # Credit spreads
    fig.add_trace(go.Scatter(x=days, y=df["ig_corp_spread_chg_bps"], name="IG Spread", line=dict(color="#2ca02c")), row=1, col=2)
    fig.add_trace(go.Scatter(x=days, y=df["hy_corp_spread_chg_bps"], name="HY Spread", line=dict(color="#d62728")), row=1, col=2)

    # Equity & FX
    fig.add_trace(go.Scatter(x=days, y=df["equity_chg_pct"], name="Equity", line=dict(color="#ff7f0e")), row=2, col=1)
    fig.add_trace(go.Scatter(x=days, y=df["fx_gbpusd_chg_pct"], name="GBP/USD", line=dict(color="#9467bd")), row=2, col=1)

    # Repo haircuts
    fig.add_trace(go.Scatter(x=days, y=df["repo_haircut_gilt_chg_pct"], name="Gilt Haircut", line=dict(color="#8c564b")), row=2, col=2)
    fig.add_trace(go.Scatter(x=days, y=df["repo_haircut_corp_chg_pct"], name="Corp Haircut", line=dict(color="#e377c2")), row=2, col=2)

    # Market functioning
    fig.add_trace(go.Scatter(x=days, y=df["gilt_bid_ask_spread_bps"], name="Gilt Bid-Ask", line=dict(color="#1f77b4", dash="dash")), row=3, col=1)
    fig.add_trace(go.Scatter(x=days, y=df["repo_market_availability_pct"] * 100, name="Repo Avail %", line=dict(color="#2ca02c", dash="dash")), row=3, col=1)

    # VIX
    fig.add_trace(go.Scatter(x=days, y=df["vix_level"], name="VIX", line=dict(color="#d62728"), fill="tozeroy"), row=3, col=2)

    fig.update_layout(height=800, showlegend=True, template="plotly_white",
                      title_text="Market Evolution Over Stress Scenario")
    return fig


def plot_agent_buffers_timeseries(daily_agents: List[Dict]) -> go.Figure:
    """Timeseries of average buffer (B3/B0) by agent type, with min/max bands."""
    df = pd.DataFrame(daily_agents)
    df["buffer_ratio"] = df["B3"] / df["B0"].replace(0, np.nan)
    df["buffer_ratio"] = df["buffer_ratio"].fillna(1.0)

    fig = go.Figure()

    for atype, colour in AGENT_COLOURS.items():
        adf = df[df["agent_type"] == atype]
        if adf.empty:
            continue
        grouped = adf.groupby("day")["buffer_ratio"]
        mean = grouped.mean()
        lo = grouped.min()
        hi = grouped.max()
        days = mean.index + 1

        label = AGENT_LABELS.get(atype, atype)
        fig.add_trace(go.Scatter(
            x=days, y=hi, mode="lines", line=dict(width=0),
            showlegend=False, name=f"{label} max",
            legendgroup=atype,
        ))
        fig.add_trace(go.Scatter(
            x=days, y=lo, mode="lines", line=dict(width=0),
            fill="tonexty", fillcolor=colour.replace(")", ",0.15)").replace("rgb", "rgba"),
            showlegend=False, name=f"{label} min",
            legendgroup=atype,
        ))
        fig.add_trace(go.Scatter(
            x=days, y=mean, mode="lines+markers",
            line=dict(color=colour, width=2),
            name=label,
            legendgroup=atype,
        ))

    fig.add_hline(y=0, line_dash="dash", line_color="red", annotation_text="Buffer exhausted")
    fig.update_layout(
        title="Liquidity Buffer Trajectories by Agent Type (B3/B0)",
        xaxis_title="Day", yaxis_title="Buffer Ratio (B3/B0)",
        template="plotly_white", height=500,
    )
    return fig


def plot_waterfall(results: Dict) -> go.Figure:
    """Waterfall chart: B0 → E1 → B1 → reactions → B2 → E2 → B3 (system-wide)."""
    df = pd.DataFrame(results["daily_agents"])
    last_day = df[df["day"] == df["day"].max()]

    b0 = last_day["B0"].sum()
    e1 = last_day["E1"].sum()
    b1 = last_day["B1"].sum()
    b2 = last_day["B2"].sum()
    e2 = last_day["E2"].sum()
    b3 = last_day["B3"].sum()
    reactions = b2 - b1

    fig = go.Figure(go.Waterfall(
        name="System-Wide Liquidity",
        orientation="v",
        measure=["absolute", "relative", "total", "relative", "total", "relative", "total"],
        x=["B0<br>(Initial)", "E1<br>(Shock)", "B1<br>(Post-shock)",
           "Reactions<br>(Mitigation)", "B2<br>(Post-reaction)",
           "E2<br>(Feedback)", "B3<br>(Final)"],
        y=[b0, -e1, b1, reactions, b2, -e2, b3],
        connector={"line": {"color": "rgb(63, 63, 63)"}},
        decreasing={"marker": {"color": "#d62728"}},
        increasing={"marker": {"color": "#2ca02c"}},
        totals={"marker": {"color": "#1f77b4"}},
    ))

    fig.update_layout(
        title="System-Wide Liquidity Waterfall (Final Day)",
        yaxis_title="Liquidity Buffer (mm)",
        template="plotly_white", height=450,
    )
    return fig


def plot_amplification_gauge(amp_ratios: Dict) -> go.Figure:
    """Gauge showing system-wide amplification ratio."""
    system_amp = amp_ratios.get("System-Wide", 1.0)

    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=system_amp,
        delta={"reference": 1.0, "increasing": {"color": "red"}},
        title={"text": "System-Wide Amplification Ratio"},
        gauge={
            "axis": {"range": [0.5, 5.0]},
            "bar": {"color": "#d62728" if system_amp > 2.0 else "#ff7f0e" if system_amp > 1.5 else "#2ca02c"},
            "steps": [
                {"range": [0.5, 1.5], "color": "#d4edda"},
                {"range": [1.5, 2.5], "color": "#fff3cd"},
                {"range": [2.5, 5.0], "color": "#f8d7da"},
            ],
            "threshold": {
                "line": {"color": "red", "width": 4},
                "thickness": 0.75,
                "value": 3.0,
            },
        },
    ))
    fig.update_layout(height=300)
    return fig


def plot_margin_calls_by_type(daily_agents: List[Dict]) -> go.Figure:
    """Bar chart of cumulative margin calls by agent type."""
    df = pd.DataFrame(daily_agents)
    last_day = df[df["day"] == df["day"].max()]
    grouped = last_day.groupby("agent_type")["cum_margin"].sum().reset_index()
    grouped["label"] = grouped["agent_type"].map(AGENT_LABELS)
    grouped["colour"] = grouped["agent_type"].map(AGENT_COLOURS)

    fig = go.Figure(go.Bar(
        x=grouped["label"],
        y=grouped["cum_margin"],
        marker_color=grouped["colour"],
        text=grouped["cum_margin"].apply(lambda x: f"{x:,.0f}"),
        textposition="auto",
    ))
    fig.update_layout(
        title="Cumulative Margin Calls by Agent Type (mm)",
        yaxis_title="Margin Calls (mm)",
        template="plotly_white", height=400,
    )
    return fig


def plot_sankey(daily_agents: List[Dict]) -> go.Figure:
    """Sankey diagram: margin calls → actions → market impact."""
    df = pd.DataFrame(daily_agents)
    last_day = df[df["day"] == df["day"].max()]

    types = list(AGENT_LABELS.keys())
    type_labels = [AGENT_LABELS[t] for t in types]

    # Nodes: agent types (0-4), action types (5-8), market variables (9-11)
    node_labels = type_labels + ["Gilt Sales", "Corp Sales", "Repo Demand", "MMF Redemptions",
                                  "Gilt Market", "Corp Market", "Repo Market"]
    node_colours = [AGENT_COLOURS[t] for t in types] + \
                   ["#bcbd22", "#e377c2", "#17becf", "#7f7f7f",
                    "#1f77b4", "#ff7f0e", "#2ca02c"]

    source, target, value = [], [], []

    for i, atype in enumerate(types):
        adf = last_day[last_day["agent_type"] == atype]
        sales = adf["cum_sales"].sum()
        repo = adf["cum_repo"].sum()

        if sales > 0:
            source.append(i); target.append(5); value.append(sales * 0.6)  # Gilt sales
            source.append(i); target.append(6); value.append(sales * 0.4)  # Corp sales
        if repo > 0:
            source.append(i); target.append(7); value.append(repo)

    # Actions → Markets
    total_gilt = sum(v for s, t, v in zip(source, target, value) if t == 5)
    total_corp = sum(v for s, t, v in zip(source, target, value) if t == 6)
    total_repo = sum(v for s, t, v in zip(source, target, value) if t == 7)

    if total_gilt > 0:
        source.append(5); target.append(9); value.append(total_gilt)
    if total_corp > 0:
        source.append(6); target.append(10); value.append(total_corp)
    if total_repo > 0:
        source.append(7); target.append(11); value.append(total_repo)

    fig = go.Figure(go.Sankey(
        node=dict(label=node_labels, color=node_colours, pad=15, thickness=20),
        link=dict(source=source, target=target, value=value),
    ))
    fig.update_layout(title="Flow of Stress: Agents -> Actions -> Markets", height=500)
    return fig


def plot_network_graph(network, agents) -> go.Figure:
    """NetworkX visualisation showing the bipartite bank-HF graph."""
    import networkx as nx

    G = network.graph
    pos = nx.spring_layout(G, seed=42, k=2.0)

    # Separate by type
    agent_map = {a.name: a for a in agents}

    edge_x, edge_y = [], []
    for edge in G.edges():
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])

    edge_trace = go.Scatter(
        x=edge_x, y=edge_y, mode="lines",
        line=dict(width=0.3, color="#cccccc"),
        hoverinfo="none",
    )

    # Node traces by agent type
    traces = [edge_trace]
    for atype, colour in AGENT_COLOURS.items():
        nodes = [n for n in G.nodes() if agent_map.get(n) and agent_map[n].agent_type == atype]
        if not nodes:
            continue
        nx_vals = [pos[n][0] for n in nodes]
        ny_vals = [pos[n][1] for n in nodes]
        sizes = [max(8, min(30, agent_map[n].size_factor * 0.00005)) for n in nodes]
        colours = []
        for n in nodes:
            a = agent_map[n]
            if a.has_reacted:
                colours.append("red")
            else:
                colours.append(colour)

        traces.append(go.Scatter(
            x=nx_vals, y=ny_vals, mode="markers+text",
            marker=dict(size=sizes, color=colours, line=dict(width=1, color="white")),
            text=[n.split(" ")[0] for n in nodes],
            textposition="top center",
            textfont=dict(size=7),
            name=AGENT_LABELS.get(atype, atype),
            hovertext=[f"{n}<br>Size: {agent_map[n].size_factor:,.0f}<br>Reacted: {agent_map[n].has_reacted}" for n in nodes],
            hoverinfo="text",
        ))

    fig = go.Figure(data=traces)
    fig.update_layout(
        title="Agent Relationship Network",
        showlegend=True,
        template="plotly_white",
        height=600,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
    )
    return fig


def plot_agent_distribution(daily_agents: List[Dict]) -> go.Figure:
    """Histogram/violin showing distribution of buffer outcomes by agent type."""
    df = pd.DataFrame(daily_agents)
    last_day = df[df["day"] == df["day"].max()].copy()
    last_day["buffer_decline_pct"] = ((last_day["B3"] - last_day["B0"]) / last_day["B0"].replace(0, np.nan)) * 100
    last_day["buffer_decline_pct"] = last_day["buffer_decline_pct"].fillna(0)
    last_day["type_label"] = last_day["agent_type"].map(AGENT_LABELS)

    fig = go.Figure()
    for atype in AGENT_COLOURS:
        adf = last_day[last_day["agent_type"] == atype]
        if adf.empty:
            continue
        fig.add_trace(go.Violin(
            y=adf["buffer_decline_pct"],
            name=AGENT_LABELS.get(atype, atype),
            box_visible=True,
            meanline_visible=True,
            fillcolor=AGENT_COLOURS[atype],
            opacity=0.6,
            line_color=AGENT_COLOURS[atype],
        ))

    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.update_layout(
        title="Distribution of Buffer Outcomes by Agent Type (Final Day)",
        yaxis_title="Buffer Change (%)",
        template="plotly_white", height=500,
        showlegend=True,
    )
    return fig


def _compute_daily_amplification(daily_agents: List[Dict], initial_buffers: Dict) -> pd.DataFrame:
    """Compute amplification ratios per agent type and system-wide for each day."""
    df = pd.DataFrame(daily_agents)
    rows = []
    for day in sorted(df["day"].unique()):
        ddf = df[df["day"] == day]
        type_direct = {}
        type_total = {}
        for _, row in ddf.iterrows():
            b0 = initial_buffers.get(row["agent"], row["B0"])
            direct = max(b0 - row["B1"], 0.001)
            total = max(b0 - row["B3"], 0.001)
            atype = row["agent_type"]
            type_direct[atype] = type_direct.get(atype, 0.0) + direct
            type_total[atype] = type_total.get(atype, 0.0) + total

        for atype in type_direct:
            ratio = type_total[atype] / type_direct[atype] if type_direct[atype] > 0 else 1.0
            rows.append({"day": day, "agent_type": atype, "amplification": ratio})

        sys_direct = sum(type_direct.values())
        sys_total = sum(type_total.values())
        rows.append({
            "day": day,
            "agent_type": "System-Wide",
            "amplification": sys_total / sys_direct if sys_direct > 0 else 1.0,
        })
    return pd.DataFrame(rows)


def plot_amplification_timeseries(daily_agents: List[Dict], initial_buffers: Dict) -> go.Figure:
    """Time series of amplification ratio by agent type and system-wide."""
    amp_df = _compute_daily_amplification(daily_agents, initial_buffers)

    fig = go.Figure()
    for atype in list(AGENT_COLOURS.keys()) + ["System-Wide"]:
        adf = amp_df[amp_df["agent_type"] == atype]
        if adf.empty:
            continue
        colour = AGENT_COLOURS.get(atype, "#7f7f7f")
        is_system = atype == "System-Wide"
        fig.add_trace(go.Scatter(
            x=adf["day"] + 1, y=adf["amplification"],
            mode="lines+markers",
            name=AGENT_LABELS.get(atype, atype),
            line=dict(color=colour, width=3 if is_system else 2,
                      dash="dash" if is_system else "solid"),
        ))

    fig.add_hline(y=1.0, line_dash="dot", line_color="gray", annotation_text="No amplification")
    fig.update_layout(
        title="Amplification Ratio Over Time",
        xaxis_title="Day", yaxis_title="Amplification Ratio",
        template="plotly_white", height=450,
    )
    return fig


def plot_type_amplification(daily_agents: List[Dict], initial_buffers: Dict, day: int = None) -> go.Figure:
    """Bar chart of amplification ratio by agent type for a selected day."""
    amp_df = _compute_daily_amplification(daily_agents, initial_buffers)

    if day is not None:
        amp_df = amp_df[amp_df["day"] == day]
        title = f"Amplification Ratio by Agent Type (Day {day + 1})"
    else:
        # Use final day
        max_day = amp_df["day"].max()
        amp_df = amp_df[amp_df["day"] == max_day]
        title = f"Amplification Ratio by Agent Type (Day {max_day + 1})"

    labels = [AGENT_LABELS.get(r["agent_type"], r["agent_type"]) for _, r in amp_df.iterrows()]
    values = amp_df["amplification"].tolist()
    colours = [AGENT_COLOURS.get(r["agent_type"], "#7f7f7f") for _, r in amp_df.iterrows()]

    fig = go.Figure(go.Bar(
        x=labels, y=values,
        marker_color=colours,
        text=[f"{v:.2f}x" for v in values],
        textposition="auto",
    ))
    fig.add_hline(y=1.0, line_dash="dash", line_color="gray", annotation_text="No amplification")
    fig.update_layout(
        title=title,
        yaxis_title="Amplification Ratio",
        template="plotly_white", height=400,
    )
    return fig


def plot_repo_refusal_rate(summary: Dict) -> go.Figure:
    """Bar chart: model repo refusal rate vs SWES 1 benchmark."""
    total_seeking = summary.get("hfs_seeking_repo", 0)
    refused_all = summary.get("hfs_refused_by_all", 0)
    refusal_rate = refused_all / max(total_seeking, 1)
    swes_benchmark = 0.33

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=["Model Output", "SWES 1 Benchmark"],
        y=[refusal_rate * 100, swes_benchmark * 100],
        marker_color=["#ff7f0e", "#1f77b4"],
        text=[f"{refusal_rate*100:.1f}%", f"{swes_benchmark*100:.1f}%"],
        textposition="auto",
    ))
    fig.update_layout(
        title=f"Repo Refusal Rate: HFs Refused by ALL Connected Banks ({refused_all}/{total_seeking})",
        yaxis_title="Percentage (%)",
        template="plotly_white", height=350,
        yaxis=dict(range=[0, 60]),
    )
    return fig


def plot_bank_capacity_heatmap(agents) -> go.Figure:
    """Heatmap showing each bank's gilt MM capacity utilisation over 10 days."""
    banks = [a for a in agents if a.agent_type == "bank"]

    bank_names = [b.name.split(" ")[0] for b in banks]
    n_days = max(len(b.daily_capacity_history) for b in banks) if banks else 10

    z = []
    for b in banks:
        history = b.daily_capacity_history
        # Pad to n_days if needed
        while len(history) < n_days:
            history.append(history[-1] if history else 0.0)
        z.append([v * 100 for v in history[:n_days]])

    fig = go.Figure(go.Heatmap(
        z=z,
        x=[f"Day {d+1}" for d in range(n_days)],
        y=bank_names,
        colorscale="RdYlGn_r",
        zmin=0, zmax=100,
        colorbar_title="Capacity Used (%)",
    ))
    fig.update_layout(
        title="Bank Gilt Market-Making Capacity Utilisation",
        template="plotly_white", height=400,
    )
    return fig


def plot_bank_combined_capacity_heatmap(agents) -> go.Figure:
    """Heatmap showing each bank's combined (gilt + corp) MM capacity utilisation over 10 days."""
    banks = [a for a in agents if a.agent_type == "bank"]

    bank_names = [b.name.split(" ")[0] for b in banks]
    n_days = max(len(b.daily_combined_capacity_history) for b in banks) if banks else 10

    z = []
    for b in banks:
        history = b.daily_combined_capacity_history
        while len(history) < n_days:
            history.append(history[-1] if history else 0.0)
        z.append([v * 100 for v in history[:n_days]])

    fig = go.Figure(go.Heatmap(
        z=z,
        x=[f"Day {d+1}" for d in range(n_days)],
        y=bank_names,
        colorscale="RdYlGn_r",
        zmin=0, zmax=100,
        colorbar_title="Capacity Used (%)",
    ))
    fig.update_layout(
        title="Bank Combined (Gilt + Corp) Market-Making Capacity Utilisation",
        template="plotly_white", height=400,
    )
    return fig


def plot_swes_comparison(summary: Dict) -> go.Figure:
    """Compare model outputs against SWES 1 published findings."""
    from config import SWES1_ANCHORS

    metrics = [
        ("Total NBFI Margin Calls", summary["total_margin_calls_mm"] / 1000, SWES1_ANCHORS["total_nbfi_margin_calls_bn"], "bn"),
        ("NBFI Gilt Sales", summary["nbfi_gilt_sales_mm"] / 1000, SWES1_ANCHORS["nbfi_gilt_sales_bn"], "bn"),
    ]

    fig = make_subplots(rows=1, cols=len(metrics), subplot_titles=[m[0] for m in metrics])

    for i, (name, model_val, swes_val, unit) in enumerate(metrics, 1):
        fig.add_trace(go.Bar(
            x=["Model", "SWES 1"],
            y=[model_val, swes_val],
            marker_color=["#ff7f0e", "#1f77b4"],
            text=[f"{model_val:.1f}{unit}", f"{swes_val:.1f}{unit}"],
            textposition="auto",
            showlegend=False,
        ), row=1, col=i)

    fig.update_layout(
        title="Model vs SWES 1 Published Findings",
        template="plotly_white", height=350,
    )
    return fig
