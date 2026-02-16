"""Time-stepped simulation loop with network-propagated feedback."""

from typing import List, Dict
from market import MarketState, load_scenario, get_scenario_day
from agents.base import BaseAgent
from network import RelationshipNetwork
from engine.feedback import compute_stage3_feedback


def run_simulation(
    agents: List[BaseAgent],
    network: RelationshipNetwork,
    scenario_path: str = "data/scenario_swes1.json",
    enable_feedback: bool = True,
    feedback_iterations: int = 3,
) -> Dict:
    """
    Run 10-day simulation with network-propagated feedback.
    """
    scenario = load_scenario(scenario_path)
    market = MarketState()
    n_days = scenario.get("horizon_days", 10)

    daily_market = []
    daily_agents = []

    for agent in agents:
        agent.compute_initial_buffer()
    initial_buffers = {a.name: a.liquidity.B0 for a in agents}

    for day in range(n_days):
        market.day = day
        day_values = get_scenario_day(scenario, day)
        if day == 0:
            prev = {k: 0.0 for k in day_values}
        else:
            prev = get_scenario_day(scenario, day - 1)
        day_delta = {k: day_values[k] - prev.get(k, 0.0) for k in day_values}
        market.apply_exogenous_scenario(day_values)

        # Stage 1
        for agent in agents:
            agent.reset_daily()
            agent.compute_initial_buffer()
            agent.compute_stage1(market, day_delta, network, agents)

        # Stage 2 — reactions flow through network
        for agent in agents:
            agent.compute_stage2(market, network, agents)

        # Pass 1: all agents register selling pressure to market
        for agent in agents:
            agent.register_actions_to_market(market)

        # Pass 2: banks absorb from the full daily selling total,
        # proportional to their remaining capacity (gilt + corp separately)
        banks = [a for a in agents if a.agent_type == "bank"]
        gilt_remaining_total = sum(
            b.gilt_mm_appetite_mm * (1.0 - b.mm_appetite_consumed_pct)
            for b in banks
        )
        corp_remaining_total = sum(
            b.corp_mm_appetite_mm * (1.0 - b.corp_appetite_consumed_pct)
            for b in banks
        )
        for bank in banks:
            gilt_share = 0.0
            corp_share = 0.0
            if gilt_remaining_total > 0:
                gilt_rem = bank.gilt_mm_appetite_mm * (1.0 - bank.mm_appetite_consumed_pct)
                gilt_share = market.endogenous_gilt_selling_mm * (gilt_rem / gilt_remaining_total)
            if corp_remaining_total > 0:
                corp_rem = bank.corp_mm_appetite_mm * (1.0 - bank.corp_appetite_consumed_pct)
                corp_share = market.endogenous_corp_selling_mm * (corp_rem / corp_remaining_total)
            bank.post_registration_update(gilt_share, corp_share)

        # Stage 3 — network-propagated feedback
        if enable_feedback:
            for _ in range(feedback_iterations):
                market.apply_endogenous_feedback()
                compute_stage3_feedback(agents, market, network)
        else:
            for agent in agents:
                agent.liquidity.E2 = 0.0
                agent.liquidity.B3 = agent.liquidity.B2

        # Record
        daily_market.append(market.snapshot())
        for agent in agents:
            snap = agent.daily_snapshot()
            snap["day"] = day
            daily_agents.append(snap)

        _update_balance_sheets(agents)

    # Amplification ratios — per agent AND per agent TYPE (aggregated)
    amp_ratios = _compute_amplification(agents, initial_buffers)

    # Summary
    summary = _compute_summary(agents, market)

    return {
        "daily_market": daily_market,
        "daily_agents": daily_agents,
        "amplification_ratios": amp_ratios,
        "summary": summary,
        "initial_buffers": initial_buffers,
        "network_summary": network.network_summary(),
    }


def _compute_amplification(agents, initial_buffers):
    ratios = {}
    # Per agent
    for a in agents:
        direct = initial_buffers[a.name] - a.liquidity.B1
        total = initial_buffers[a.name] - a.liquidity.B3
        ratios[a.name] = total / direct if direct > 0 else 1.0

    # Per agent type
    from collections import defaultdict
    type_direct = defaultdict(float)
    type_total = defaultdict(float)
    for a in agents:
        d = max(initial_buffers[a.name] - a.liquidity.B1, 0.001)
        t = max(initial_buffers[a.name] - a.liquidity.B3, 0.001)
        type_direct[a.agent_type] += d
        type_total[a.agent_type] += t
    for atype in type_direct:
        ratios[f"Type:{atype}"] = type_total[atype] / type_direct[atype]

    # System-wide
    total_d = sum(max(initial_buffers[a.name] - a.liquidity.B1, 0.001) for a in agents)
    total_t = sum(max(initial_buffers[a.name] - a.liquidity.B3, 0.001) for a in agents)
    ratios["System-Wide"] = total_t / total_d if total_d > 0 else 1.0

    return ratios


def _compute_summary(agents, market):
    hfs = [a for a in agents if a.agent_type == "hedge_fund"]
    hfs_seeking = [h for h in hfs if getattr(h, "has_ever_sought_repo", False)]
    hfs_refused = [h for h in hfs if getattr(h, "repo_refused_by_all", False)]
    return {
        "total_agents": len(agents),
        "agents_reacted": sum(1 for a in agents if a.has_reacted),
        "total_margin_calls_mm": sum(a.cumulative_margin_calls_mm for a in agents),
        "total_asset_sales_mm": sum(a.cumulative_asset_sales_mm for a in agents),
        "nbfi_gilt_sales_mm": sum(a.cumulative_gilt_sales_mm for a in agents if a.agent_type != "bank"),
        "total_repo_demand_mm": sum(a.cumulative_repo_demand_mm for a in agents),
        "final_gilt_yield": market.gilt_10y_yield_chg_bps,
        "final_ig_spread": market.ig_corp_spread_chg_bps,
        "final_repo_avail": market.repo_market_availability_pct,
        "hfs_seeking_repo": len(hfs_seeking),
        "hfs_refused_by_all": len(hfs_refused),
    }


def _update_balance_sheets(agents):
    for agent in agents:
        for action, amount in agent.reactions.items():
            if "sell_gilt" in action:
                item = agent.get_item("Gilt Holdings") or agent.get_item("Gilt Positions (net)")
                if item:
                    item.amount_mm = max(0, item.amount_mm - amount)
            elif "sell_corp" in action:
                item = agent.get_item("Corporate Bonds") or agent.get_item("Corporate Bond Holdings") or agent.get_item("Corp Bond Positions")
                if item:
                    item.amount_mm = max(0, item.amount_mm - amount)
