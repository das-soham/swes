"""Stage 3: Network-propagated second-round feedback."""

import numpy as np
from typing import List
from agents.base import BaseAgent
from network import RelationshipNetwork
from config import FEEDBACK_PARAMS


def compute_stage3_feedback(
    agents: List[BaseAgent],
    market: 'MarketState',
    network: RelationshipNetwork,
) -> None:
    """
    Feedback propagates through bilateral relationships, not uniformly.

    When Bank_03 tightens repo:
    - ONLY HF_04, HF_08, HF_12 (connected to Bank_03) face funding stress
    - NOT HF_01, HF_02 (connected to Bank_01 which hasn't tightened)

    When HF_12 is forced to sell gilts:
    - The selling pressure hits the MARKET (aggregate level)
    - All agents with gilt exposure face additional MTM (market-level feedback)

    So there are TWO layers of feedback:
    1. Bilateral (network-routed): repo tightening, counterparty risk, redemptions
    2. Market-level (broadcast): selling pressure -> price impact -> MTM for all
    """
    s = max(1.0, market.vix_level / 15.0)
    num_reacting = sum(1 for a in agents if a.has_reacted)
    if num_reacting == 0:
        for a in agents:
            a.apply_stage3(0.0)
        return

    agent_map = {a.name: a for a in agents}

    for target in agents:
        e2 = 0.0

        # ── Layer 1: Bilateral feedback (network-routed) ──

        if target.agent_type == "hedge_fund":
            # Check if any of THIS HF's connected banks have tightened
            connected_banks = network.get_connected_banks(target.name)
            for bank_name in connected_banks:
                bank = agent_map.get(bank_name)
                if bank and bank.has_reacted:
                    # Bank has tightened -> this HF faces repo/funding stress
                    # Impact proportional to bank's reaction size and HF's repo dependence
                    bank_reaction_size = sum(bank.reactions.values())
                    repo_item = target.get_item("Repo Borrowing")
                    if repo_item:
                        bilateral_impact = (
                            repo_item.amount_mm
                            * (bank_reaction_size / max(bank.liquidity.B0, 1))
                            * s * 0.05
                        )
                        e2 += bilateral_impact

        elif target.agent_type == "bank":
            # Check if any connected HFs have failed or deleveraged heavily
            connected_hfs = network.get_connected_hfs(target.name)
            for hf_name in connected_hfs:
                hf = agent_map.get(hf_name)
                if hf and hf.has_reacted:
                    # HF deleveraging -> counterparty risk scaled by bilateral exposure
                    hf_stress = hf.liquidity.E1 / max(hf.liquidity.B0, 1)
                    repo_item = hf.get_item("Repo Borrowing")
                    hf_repo = repo_item.amount_mm if repo_item else 0.0
                    n_banks_for_hf = max(len(network.get_connected_banks(hf_name)), 1)
                    bilateral_exposure = hf_repo / n_banks_for_hf
                    coeff = FEEDBACK_PARAMS["bank_counterparty_loss_coeff"]
                    counterparty_impact = hf_stress * bilateral_exposure * coeff * s
                    e2 += counterparty_impact

        elif target.agent_type == "oef_mmf":
            # OEFs face redemptions from connected stressed NBFIs
            redeemers = network.get_oef_redeemers(target.name)
            for nbfi_name in redeemers:
                nbfi = agent_map.get(nbfi_name)
                if nbfi and nbfi.has_reacted:
                    # Stressed NBFI redeems from this OEF
                    redemption_pressure = sum(nbfi.reactions.values()) * 0.1
                    e2 += redemption_pressure

        # ── Layer 2: Market-level feedback (broadcast) ──
        # Additional MTM from endogenous price moves (already in market state)
        for item in target.balance_sheet:
            if item.category == 'liquid_asset':
                for var, sens in item.sensitivity_map.items():
                    market_feedback_mtm = item.amount_mm * abs(sens) * 0.0001 * s * 0.05
                    e2 += market_feedback_mtm * (num_reacting / len(agents))

        # ── Reputation risk (Van den End eq 7) ──
        if target.has_reacted:
            rep_impact = sum(target.reactions.values()) * (np.sqrt(s) - 1.0) * 0.15
            e2 += rep_impact

        # ── Crowding penalty ──
        # More severe when many agents of the SAME TYPE react with SAME instruments
        same_type_reacting = sum(
            1 for a in agents
            if a.agent_type == target.agent_type and a.has_reacted
        )
        same_type_total = sum(1 for a in agents if a.agent_type == target.agent_type)
        if same_type_total > 0 and target.has_reacted:
            crowding = (same_type_reacting / same_type_total) ** 2 * s * 0.03
            e2 += sum(target.reactions.values()) * crowding

        target.apply_stage3(e2)
