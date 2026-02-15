"""OEF / MMF agent — redemption-driven mechanics."""

from typing import Dict, List
from agents.base import BaseAgent, BalanceSheetItem
from config import REACTION_PARAMS, BUFFER_PARAMS
import numpy as np


class OEFMMFAgent(BaseAgent):

    def __init__(self, config: Dict):
        name = config["name"]
        theta = config["theta"]
        aum_mm = config["aum_mm"]
        super().__init__(name=name, agent_type="oef_mmf", theta=theta, size_factor=aum_mm)

        self.strategy = config["strategy"]
        self.aum_mm = aum_mm
        self.pension_investor_pct = config["pension_investor_pct"]
        self.insurer_investor_pct = config["insurer_investor_pct"]
        self.cash_buffer_pct = config["cash_buffer_pct"]

        strat_comp = config["strategy_composition"]

        # Build balance sheet from strategy composition
        gilt_pct = self._mid(strat_comp.get("gilt_pct", [0.2, 0.3]))
        corp_pct = self._mid(strat_comp.get("corp_pct", [0.1, 0.2]))
        abs_pct = self._mid(strat_comp.get("abs_pct", [0.0, 0.05]))
        cash_pct = self._mid(strat_comp.get("cash_pct", [0.0, 0.0]))
        if cash_pct == 0:
            cash_pct = self.cash_buffer_pct

        self.balance_sheet = [
            BalanceSheetItem("Gilt Holdings", aum_mm * gilt_pct, "liquid_asset",
                             {"gilt_10y_yield": -0.0005, "gilt_30y_yield": -0.0006},
                             is_collateral_eligible=True, is_reaction_instrument=True),
            BalanceSheetItem("Corporate Bond Holdings", aum_mm * corp_pct, "liquid_asset",
                             {"ig_corp_spread": -0.0004, "hy_corp_spread": -0.0002},
                             is_collateral_eligible=True, is_reaction_instrument=True),
            BalanceSheetItem("ABS Holdings", aum_mm * abs_pct, "illiquid_asset",
                             {"ig_corp_spread": -0.0002}),
            BalanceSheetItem("Cash Buffer", aum_mm * cash_pct, "liquid_asset",
                             {}),
        ]

        self.cumulative_redemption_inflows_mm = 0.0

    def compute_initial_buffer(self) -> float:
        """OEF buffer = fraction of cash buffer."""
        bp = BUFFER_PARAMS["oef_mmf"]
        cash = self.get_item("Cash Buffer")
        cash_val = cash.amount_mm if cash else 0.0
        self.liquidity.B0 = max(cash_val * bp["cash_mult"], self.aum_mm * bp["floor_pct_of_aum"])
        return self.liquidity.B0

    def _mid(self, r):
        if isinstance(r, (list, tuple)) and len(r) == 2:
            return (r[0] + r[1]) / 2.0
        return 0.0

    def compute_mtm_impact(self, market, day_delta: Dict[str, float]) -> float:
        total_mtm = 0.0
        for item in self.balance_sheet:
            for var, sens in item.sensitivity_map.items():
                delta = day_delta.get(var, 0.0)
                impact = item.amount_mm * sens * delta
                total_mtm += abs(impact)
        return total_mtm

    def compute_margin_calls(self, market) -> float:
        # OEFs/MMFs typically don't face margin calls (no derivatives)
        return 0.0

    def compute_redemptions(self, market, network, agents: List) -> float:
        """
        OEFs face redemptions from connected stressed NBFIs.
        Check which NBFIs are connected via network and how stressed they are.
        Higher NBFI stress → higher redemption demands on this OEF.
        """
        if not network:
            return 0.0

        redeemers = network.get_oef_redeemers(self.name)
        if not redeemers:
            return 0.0

        agent_map = {a.name: a for a in agents}
        total_redemptions = 0.0

        for nbfi_name in redeemers:
            nbfi = agent_map.get(nbfi_name)
            if nbfi is None:
                continue

            # Calculate stress level of the redeeming NBFI
            if nbfi.liquidity.B0 > 0:
                stress_ratio = nbfi.liquidity.E1 / nbfi.liquidity.B0
            else:
                stress_ratio = 0.0

            # Only stressed NBFIs redeem aggressively
            if stress_ratio > 0.3:
                # Redemption proportional to NBFI stress and its size
                base_redemption = nbfi.size_factor * 0.001 * stress_ratio

                # Type-specific redemption rates
                if nbfi.agent_type == "ldi_pension":
                    base_redemption *= (self.pension_investor_pct * 2.0)
                elif nbfi.agent_type == "insurer":
                    base_redemption *= (self.insurer_investor_pct * 1.5)
                elif nbfi.agent_type == "hedge_fund":
                    base_redemption *= 0.5

                total_redemptions += base_redemption

        self.cumulative_redemption_inflows_mm += total_redemptions
        return total_redemptions

    def compute_reactions(self, market, network=None, agents=None) -> Dict[str, float]:
        reactions = {}
        caps = REACTION_PARAMS["oef_mmf"]
        shortfall = max(0, -self.liquidity.B1) + self.liquidity.E1 * 0.1

        # 1. Use cash buffer first
        cash = self.get_item("Cash Buffer")
        if cash and cash.amount_mm > 0:
            use = min(shortfall * 0.5, cash.amount_mm * 0.7)
            reactions["use_cash_buffer"] = use
            shortfall -= use

        # 2. Sell gilts (last resort)
        if shortfall > 0:
            sf, hc = caps["sell_gilt"]
            gilt = self.get_item("Gilt Holdings")
            if gilt and gilt.amount_mm > 0:
                sell = min(shortfall * sf, gilt.amount_mm * hc)
                reactions["sell_gilt"] = sell
                shortfall -= sell

        # 3. Sell corporate bonds (last resort)
        if shortfall > 0:
            sf, hc = caps["sell_corp"]
            corp = self.get_item("Corporate Bond Holdings")
            if corp and corp.amount_mm > 0:
                sell = min(shortfall * sf, corp.amount_mm * hc)
                reactions["sell_corp_bonds"] = sell
                shortfall -= sell

        # 4. Suspend redemptions (extreme stress — swing pricing / gates)
        if shortfall > 0 and self.aum_mm > 0:
            redemption_ratio = self.cumulative_redemption_inflows_mm / self.aum_mm
            if redemption_ratio > 0.15:
                # Apply swing pricing / gates — reduce effective outflow
                reactions["swing_pricing"] = shortfall * 0.2

        return reactions
