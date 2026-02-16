"""Streamlit entry point for SWES Private Markets Stress Lens."""

import streamlit as st
import pandas as pd
from agent_factory import generate_all_agents
from network import RelationshipNetwork
from engine.simulation import run_simulation
from visualisation import (
    plot_market_evolution,
    plot_agent_buffers_timeseries,
    plot_waterfall,
    plot_amplification_gauge,
    plot_margin_calls_by_type,
    plot_sankey,
    plot_network_graph,
    plot_agent_distribution,
    plot_type_amplification,
    plot_amplification_timeseries,
    plot_repo_refusal_rate,
    plot_bank_capacity_heatmap,
    plot_bank_combined_capacity_heatmap,
    plot_swes_comparison,
)

st.set_page_config(
    page_title="SWES Stress Lens",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("SWES Private Markets Stress Lens")
st.caption("SWES 1 Channel Pack — Fast Channel (10 Business Days) — Heterogeneous Multi-Agent Network Model")


# ── Sidebar ──
with st.sidebar:
    st.header("Simulation Controls")

    enable_feedback = st.toggle("System-Wide Feedback", value=True,
                                help="Enable/disable second-round amplification effects")

    feedback_iterations = st.slider("Feedback Iterations per Day", 1, 5, 3,
                                    help="Number of feedback rounds per time step")

    random_seed = st.number_input("Random Seed", value=42, step=1,
                                   help="Change seed to see different network topologies and agent params")

    st.markdown("---")
    st.header("Buffer Usability")
    usability_override = st.slider(
        "Bank Buffer Usability",
        0.0, 1.0, 0.0, 0.05,
        help="0% = buffers are floors (procyclical). 100% = fully usable. Farmer et al. 2020."
    )
    st.caption("Higher -> banks absorb more -> less amplification")

    st.markdown("---")
    st.header("Network")


@st.cache_resource
def setup(seed: int):
    agents = generate_all_agents(seed=seed)
    network = RelationshipNetwork()
    network.build_network(agents, seed=seed)
    return agents, network


agents, network = setup(random_seed)

# Show network info in sidebar
with st.sidebar:
    st.write(f"Agents: {len(agents)}")
    ns = network.network_summary()
    st.write(f"Relationships: {ns['total_edges']}")
    st.write(f"Bank-HF: {ns['bank_hf_edges']}")
    st.write(f"Bank-LDI: {ns['bank_ldi_edges']}")
    st.write(f"Bank-Insurer: {ns['bank_insurer_edges']}")
    st.write(f"NBFI-OEF: {ns['nbfi_oef_edges']}")

    st.markdown("---")
    st.header("Agent Population")
    from collections import Counter
    type_counts = Counter(a.agent_type for a in agents)
    for atype, count in sorted(type_counts.items()):
        st.write(f"{atype}: {count}")


# ── Run simulation ──
@st.cache_data
def run_sim(seed: int, feedback: bool, fb_iters: int, bank_usability: float = 0.0):
    agents_fresh = generate_all_agents(seed=seed)
    net = RelationshipNetwork()
    net.build_network(agents_fresh, seed=seed)
    for a in agents_fresh:
        if a.agent_type == "bank":
            a.buffer_usability = bank_usability
    results = run_simulation(
        agents_fresh, net,
        enable_feedback=feedback,
        feedback_iterations=fb_iters,
    )
    return results, agents_fresh, net


results, sim_agents, sim_network = run_sim(random_seed, enable_feedback, feedback_iterations, usability_override)

# ── Summary metrics ──
summary = results["summary"]
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Agents", summary["total_agents"])
with col2:
    st.metric("Agents Reacted", summary["agents_reacted"])
with col3:
    st.metric("Total Margin Calls", f"£{summary['total_margin_calls_mm']/1000:.1f}bn")
with col4:
    amp = results["amplification_ratios"].get("System-Wide", 1.0)
    st.metric("Amplification", f"{amp:.2f}x",
              delta=f"{amp - 1.0:+.2f}x" if amp > 1.0 else None,
              delta_color="inverse")


# ── Tabs ──
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Market Evolution",
    "Agent Buffers",
    "System Dynamics",
    "Network View",
    "SWES Comparison",
])

with tab1:
    st.header("Market Evolution")
    st.plotly_chart(plot_market_evolution(results["daily_market"]), use_container_width=True)

    st.subheader("Scenario Narrative")
    import json
    with open("data/scenario_swes1.json") as f:
        scenario = json.load(f)
    for day_key, event in scenario["narrative_events"].items():
        day_num = day_key.replace("day_", "Day ")
        st.markdown(f"**{day_num}:** {event}")

with tab2:
    st.header("Agent Liquidity Buffers")
    st.plotly_chart(plot_agent_buffers_timeseries(results["daily_agents"]), use_container_width=True)

    st.subheader("System-Wide Liquidity Waterfall")
    st.plotly_chart(plot_waterfall(results), use_container_width=True)

    st.subheader("Amplification Ratio")
    st.plotly_chart(plot_amplification_timeseries(results["daily_agents"], results["initial_buffers"]),
                    use_container_width=True)

    num_days = max(r["day"] for r in results["daily_agents"]) + 1
    selected_day = st.selectbox("Select Day", options=list(range(num_days)),
                                format_func=lambda d: f"Day {d + 1}",
                                index=num_days - 1)
    col_g, col_b = st.columns([1, 2])
    with col_g:
        st.plotly_chart(plot_amplification_gauge(results["amplification_ratios"]), use_container_width=True)
    with col_b:
        st.plotly_chart(plot_type_amplification(results["daily_agents"], results["initial_buffers"], day=selected_day),
                        use_container_width=True)

with tab3:
    st.header("System Dynamics")

    st.subheader("Margin Calls by Agent Type")
    st.plotly_chart(plot_margin_calls_by_type(results["daily_agents"]), use_container_width=True)

    st.subheader("Stress Flow (Sankey)")
    st.plotly_chart(plot_sankey(results["daily_agents"]), use_container_width=True)

with tab4:
    st.header("Relationship Network")
    st.plotly_chart(plot_network_graph(sim_network, sim_agents), use_container_width=True)

    st.subheader("Outcome Distributions by Agent Type")
    st.plotly_chart(plot_agent_distribution(results["daily_agents"]), use_container_width=True)

    st.subheader("Repo Refusal Rate")
    st.plotly_chart(plot_repo_refusal_rate(summary), use_container_width=True)

    st.subheader("Bank Capacity Heatmap (Gilt)")
    st.plotly_chart(plot_bank_capacity_heatmap(sim_agents), use_container_width=True)

    st.subheader("Bank Capacity Heatmap (Gilt + Corp Combined)")
    st.plotly_chart(plot_bank_combined_capacity_heatmap(sim_agents), use_container_width=True)

with tab5:
    st.header("Model vs SWES 1 Published Findings")
    st.plotly_chart(plot_swes_comparison(summary), use_container_width=True)

    st.subheader("Calibration Anchors")
    from config import SWES1_ANCHORS
    anchor_df = pd.DataFrame([
        {"Metric": k.replace("_", " ").title(), "SWES 1 Value": v}
        for k, v in SWES1_ANCHORS.items()
    ])
    st.dataframe(anchor_df, use_container_width=True, hide_index=True)

    st.subheader("Network Summary")
    net_summary = results["network_summary"]
    st.json(net_summary)


# ── Footer ──
st.markdown("---")
st.caption("SWES Private Markets Stress Lens v1.0 — Sprint 1: SWES 1 Channel Pack (Fast Channel)")
st.caption("Coded by Soham Das, CFA")
