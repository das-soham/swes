"""
Factory module: generates heterogeneous agents from parameter distributions.
Each agent is unique but drawn from realistic ranges.
"""

import numpy as np
import json
from typing import List, Dict
from agents.bank import BankAgent
from agents.hedge_fund import HedgeFundAgent
from agents.ldi_pension import LDIPensionAgent
from agents.insurer import InsurerAgent
from agents.oef_mmf import OEFMMFAgent
from agents.base import BaseAgent
from config import AgentType


def generate_all_agents(
    dist_path: str = "data/agent_distributions.json",
    seed: int = 42,
) -> List[BaseAgent]:
    """
    Master factory: generates all agents from distributions.
    Returns a list of 60-75 heterogeneous agents.
    """
    rng = np.random.default_rng(seed)
    with open(dist_path) as f:
        dists = json.load(f)

    agents = []
    agents.extend(_generate_banks(dists["bank"], rng))
    agents.extend(_generate_hedge_funds(dists["hedge_fund"], rng))
    agents.extend(_generate_ldi_pensions(dists["ldi_pension"], rng))
    agents.extend(_generate_insurers(dists["insurer"], rng))
    agents.extend(_generate_oef_mmfs(dists["oef_mmf"], rng))

    return agents


def _generate_banks(dist: Dict, rng) -> List[BankAgent]:
    """Generate 10-15 banks across size tiers."""
    banks = []
    idx = 0
    for tier in dist["size_distribution"]["tiers"]:
        for i in range(tier["count"]):
            idx += 1
            total_bs_bn = rng.uniform(*tier["total_bs_bn_range"])
            total_bs_mm = total_bs_bn * 1000

            # Sample behavioural parameters
            bp = dist["behavioural_params"]
            risk_appetite = rng.uniform(*bp["risk_appetite"]["range"])
            theta = rng.uniform(*bp["theta_range"])

            # Balance sheet composition (as % of total BS)
            comp = dist["balance_sheet_composition"]
            config = {
                "name": f"Bank_{idx:02d} ({tier['label']})",
                "tier": tier["label"],
                "total_bs_mm": total_bs_mm,
                "theta": theta,
                "risk_appetite": risk_appetite,
                "balance_sheet": {
                    "gilt_holdings_mm": total_bs_mm * rng.uniform(*comp["gilt_holdings_pct_of_bs"]),
                    "corp_bond_holdings_mm": total_bs_mm * rng.uniform(*comp["corp_bond_pct_of_bs"]),
                    "equity_portfolio_mm": total_bs_mm * 0.005,  # Small
                    "repo_lending_mm": total_bs_mm * rng.uniform(*comp["repo_lending_pct_of_bs"]),
                    "derivative_assets_mm": total_bs_mm * rng.uniform(*comp["derivative_assets_pct_of_bs"]),
                    "boe_facility_eligible_mm": total_bs_mm * rng.uniform(*comp["boe_eligible_pct_of_bs"]),
                    "wholesale_funding_mm": total_bs_mm * rng.uniform(*comp["wholesale_funding_pct_of_bs"]),
                    "cet1_buffer_mm": total_bs_mm * 0.5 * rng.uniform(*comp["cet1_pct_of_rwa"]),
                },
                "market_making_capacity": {
                    "gilt_appetite_mm": rng.uniform(*tier["gilt_mm_appetite_range"]),
                    "corp_bond_appetite_mm": rng.uniform(*tier["gilt_mm_appetite_range"]) * 0.3,
                    "appetite_consumed_pct": 0.0,
                },
                "repo_provision": {
                    "total_capacity_mm": total_bs_mm * rng.uniform(0.03, 0.08),
                    "willingness_to_roll_pct": rng.uniform(*bp["repo_willingness_roll_range"]),
                    "willingness_to_extend_new_pct": rng.uniform(*bp["repo_willingness_new_range"]),
                    "haircut_sensitivity": 1.0 + (1.0 - risk_appetite),
                },
            }
            banks.append(BankAgent(config))

    return banks


def _generate_hedge_funds(dist: Dict, rng) -> List[HedgeFundAgent]:
    """Generate 30-40 hedge funds across strategies and sizes."""
    funds = []
    idx = 0

    # Assign strategies
    strategy_list = []
    for strat, count in dist["strategy_distribution"].items():
        strategy_list.extend([strat] * count)
    rng.shuffle(strategy_list)

    # Assign sizes
    size_list = []
    for tier in dist["size_distribution"]["tiers"]:
        for _ in range(tier["count"]):
            size_list.append(rng.uniform(*tier["aum_bn_range"]))
    rng.shuffle(size_list)

    for i in range(dist["count"]):
        idx += 1
        strategy = strategy_list[i]
        aum_bn = size_list[i]
        aum_mm = aum_bn * 1000
        profile = dist["strategy_profiles"][strategy]

        bp = dist["behavioural_params"]
        config = {
            "name": f"HF_{idx:02d} ({strategy[:8]})",
            "strategy": strategy,
            "aum_mm": aum_mm,
            "theta": rng.uniform(*bp["theta_range"]),
            "strategy_profile": profile,
            "gross_leverage": rng.uniform(*profile["gross_leverage_range"]),
            "var_utilisation": rng.uniform(*bp["var_utilisation_range"]),
            "deleverage_trigger_var_pct": bp["deleverage_trigger_var_pct"],
            "repo_dependence": profile.get("repo_dependence", "medium"),
        }
        funds.append(HedgeFundAgent(config))

    return funds


def _generate_ldi_pensions(dist: Dict, rng) -> List[LDIPensionAgent]:
    """Generate 8-12 LDI/pension funds with leverage/buffer/speed dispersion."""
    funds = []
    hd = dist["heterogeneity_dimensions"]
    comp = dist["balance_sheet_composition"]

    for i in range(dist["count"]):
        aum_bn = rng.uniform(*hd["aum_bn_range"])
        aum_mm = aum_bn * 1000
        is_pooled = rng.random() < hd["pooled_vs_segregated"]["pooled_pct"]

        config = {
            "name": f"LDI_{i+1:02d} ({'pooled' if is_pooled else 'segregated'})",
            "theta": rng.uniform(*hd["theta_range"]),
            "yield_buffer_bps": rng.uniform(*hd["yield_buffer_bps_range"]),
            "balance_sheet": {
                "gilt_holdings_mm": aum_mm * rng.uniform(*comp["gilt_pct_of_aum"]),
                "il_gilt_holdings_mm": aum_mm * rng.uniform(*comp["il_gilt_pct_of_aum"]),
                "corp_bond_holdings_mm": aum_mm * rng.uniform(*comp["corp_bond_pct_of_aum"]),
                "cash_and_mmf_mm": aum_mm * rng.uniform(*comp["cash_mmf_pct_of_aum"]),
                "derivatives_exposure_notional_mm": aum_mm * rng.uniform(*comp["derivatives_notional_multiple_of_aum"]),
                "ldi_leverage_ratio": rng.uniform(*hd["leverage_ratio_range"]),
                "unencumbered_collateral_mm": aum_mm * rng.uniform(*comp["unencumbered_collateral_pct_of_aum"]),
                "margin_posted_mm": aum_mm * 0.05,
            },
            "recapitalisation": {
                "pension_scheme_can_recapitalise_mm": aum_mm * rng.uniform(*hd["recap_available_pct_of_aum_range"]),
                "recapitalisation_speed_days": 1 if is_pooled else int(rng.integers(*hd["recapitalisation_speed_days_range"])),
                "pre_agreed_waterfall": is_pooled,
            },
        }
        funds.append(LDIPensionAgent(config))

    return funds


def _generate_insurers(dist: Dict, rng) -> List[InsurerAgent]:
    """Generate 5-8 insurers with hedge ratio and CSA dispersion."""
    insurers = []
    hd = dist["heterogeneity_dimensions"]
    comp = dist["balance_sheet_composition"]

    for i in range(dist["count"]):
        total_bn = rng.uniform(*hd["total_assets_bn_range"])
        total_mm = total_bn * 1000

        config = {
            "name": f"Insurer_{i+1:02d}",
            "theta": rng.uniform(*hd["theta_range"]),
            "hedge_ratio": rng.uniform(*hd["hedge_ratio_range"]),
            "dirty_csa_pct": rng.uniform(*hd["dirty_csa_pct_range"]),
            "balance_sheet": {
                "gilt_holdings_mm": total_mm * rng.uniform(*comp["gilt_pct"]),
                "corp_bond_holdings_mm": total_mm * rng.uniform(*comp["corp_bond_pct"]),
                "equity_portfolio_mm": total_mm * rng.uniform(*comp["equity_pct"]),
                "derivative_hedges_notional_mm": total_mm * rng.uniform(*comp["derivatives_notional_multiple"]),
                "cash_and_liquid_mm": total_mm * rng.uniform(*comp["cash_liquid_pct"]),
                "margin_posted_mm": total_mm * 0.02,
                "committed_repo_lines_mm": total_mm * rng.uniform(*comp["committed_repo_pct"]),
                "rcf_available_mm": total_mm * rng.uniform(*comp["rcf_pct"]),
            },
        }
        insurers.append(InsurerAgent(config))

    return insurers


def _generate_oef_mmfs(dist: Dict, rng) -> List[OEFMMFAgent]:
    """Generate 5-8 OEF/MMF complexes."""
    funds = []
    hd = dist["heterogeneity_dimensions"]

    strategies = []
    for strat, count in hd["strategy_distribution"].items():
        strategies.extend([strat] * count)
    rng.shuffle(strategies)

    for i in range(dist["count"]):
        aum_bn = rng.uniform(*hd["total_aum_bn_range"])
        aum_mm = aum_bn * 1000
        strategy = strategies[i]
        strat_comp = dist["strategy_compositions"][strategy]

        config = {
            "name": f"OEF_{i+1:02d} ({strategy[:8]})",
            "strategy": strategy,
            "aum_mm": aum_mm,
            "theta": rng.uniform(*hd["theta_range"]),
            "pension_investor_pct": rng.uniform(*hd["pension_investor_pct_range"]),
            "insurer_investor_pct": rng.uniform(*hd["insurer_investor_pct_range"]),
            "cash_buffer_pct": rng.uniform(*hd["cash_buffer_pct_range"]),
            "strategy_composition": strat_comp,
        }
        funds.append(OEFMMFAgent(config))

    return funds
