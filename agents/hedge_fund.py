"""Hedge fund agent — strategy-specific sensitivities and reactions."""

from typing import Dict, List
import numpy as np
from agents.base import BaseAgent, BalanceSheetItem
from config import REACTION_PARAMS, BUFFER_PARAMS


# Repo dependence multipliers
REPO_DEP_MULT = {
    "low": 0.2,
    "medium": 0.5,
    "high": 0.8,
    "very_high": 1.0,
}


class HedgeFundAgent(BaseAgent):

    def __init__(self, config: Dict):
        name = config["name"]
        theta = config["theta"]
        aum_mm = config["aum_mm"]
        super().__init__(name=name, agent_type="hedge_fund", theta=theta, size_factor=aum_mm)

        self.strategy = config["strategy"]
        self.aum_mm = aum_mm
        self.gross_leverage = config["gross_leverage"]
        self.var_utilisation = config["var_utilisation"]
        self.deleverage_trigger_var_pct = config["deleverage_trigger_var_pct"]
        self.repo_dependence = config.get("repo_dependence", "medium")
        self.repo_dep_mult = REPO_DEP_MULT.get(self.repo_dependence, 0.5)

        profile = config["strategy_profile"]
        self.primary_sensitivities = profile.get("primary_sensitivities", [])
        self.secondary_sensitivities = profile.get("secondary_sensitivities", [])

        # Build strategy-specific balance sheet
        gross_exposure = aum_mm * self.gross_leverage
        gilt_pct = self._sample_range(profile.get("gilt_exposure_pct", [0.0, 0.1]))
        equity_pct = self._sample_range(profile.get("equity_exposure_pct", [0.0, 0.1]))
        corp_pct = self._sample_range(profile.get("corp_bond_exposure_pct", [0.0, 0.1]))
        basis_pct = self._sample_range(profile.get("basis_trade_pct", [0.0, 0.0]))

        # Sensitivity maps differ by strategy
        gilt_sens = self._build_gilt_sensitivity()
        equity_sens = self._build_equity_sensitivity()
        corp_sens = self._build_corp_sensitivity()

        self.balance_sheet = [
            BalanceSheetItem("Gilt Positions (net)", gross_exposure * gilt_pct, "liquid_asset",
                             gilt_sens,
                             is_collateral_eligible=True, is_reaction_instrument=True),
            BalanceSheetItem("Equity Positions", gross_exposure * equity_pct, "liquid_asset",
                             equity_sens,
                             is_reaction_instrument=True),
            BalanceSheetItem("Corp Bond Positions", gross_exposure * corp_pct, "liquid_asset",
                             corp_sens,
                             is_collateral_eligible=True, is_reaction_instrument=True),
            BalanceSheetItem("Basis Trade Positions", gross_exposure * basis_pct, "liquid_asset",
                             {"bond_futures_basis": -0.001, "gilt_10y_yield": -0.0003},
                             is_reaction_instrument=True),
            BalanceSheetItem("Cash & Margin", aum_mm * 0.10, "liquid_asset", {}),
            BalanceSheetItem("Repo Borrowing", gross_exposure * self.repo_dep_mult * 0.3, "liability",
                             {}),
            BalanceSheetItem("Margin Posted", aum_mm * 0.08, "illiquid_asset",
                             {}),
        ]

        self.repo_refused_by_all = False
        self.has_ever_sought_repo = False

    def compute_initial_buffer(self) -> float:
        """HF buffer = cash/margin only (liquid positions are invested, not free)."""
        bp = BUFFER_PARAMS["hedge_fund"]
        cash = self.get_item("Cash & Margin")
        cash_val = cash.amount_mm if cash else 0.0
        self.liquidity.B0 = max(cash_val * bp["cash_mult"], self.aum_mm * bp["floor_pct_of_aum"])
        return self.liquidity.B0

    def _sample_range(self, r):
        if isinstance(r, (list, tuple)) and len(r) == 2:
            return (r[0] + r[1]) / 2.0
        return 0.0

    def _build_gilt_sensitivity(self) -> Dict[str, float]:
        sens = {}
        if "gilt_10y_yield" in self.primary_sensitivities:
            sens["gilt_10y_yield"] = -0.0006
        elif "gilt_10y_yield" in self.secondary_sensitivities:
            sens["gilt_10y_yield"] = -0.0002
        if "gilt_30y_yield" in self.primary_sensitivities:
            sens["gilt_30y_yield"] = -0.0008
        if "sonia_swap" in self.primary_sensitivities:
            sens["sonia_swap"] = -0.0003
        return sens if sens else {"gilt_10y_yield": -0.0002}

    def _build_equity_sensitivity(self) -> Dict[str, float]:
        if "equity" in self.primary_sensitivities:
            return {"equity": 0.012}
        elif "equity" in self.secondary_sensitivities:
            return {"equity": 0.005}
        return {"equity": 0.002}

    def _build_corp_sensitivity(self) -> Dict[str, float]:
        sens = {}
        if "ig_corp_spread" in self.primary_sensitivities:
            sens["ig_corp_spread"] = -0.0005
        if "hy_corp_spread" in self.primary_sensitivities:
            sens["hy_corp_spread"] = -0.0003
        return sens if sens else {"ig_corp_spread": -0.0002}

    def compute_mtm_impact(self, market, day_delta: Dict[str, float]) -> float:
        total_mtm = 0.0
        for item in self.balance_sheet:
            if item.category in ('liquid_asset', 'illiquid_asset'):
                for var, sens in item.sensitivity_map.items():
                    delta = day_delta.get(var, 0.0)
                    impact = item.amount_mm * sens * delta
                    total_mtm += abs(impact)
        # Leverage amplifies MTM
        total_mtm *= (1.0 + (self.gross_leverage - 1.0) * 0.3)
        return total_mtm

    def compute_margin_calls(self, market) -> float:
        stress = market.vix_level / 15.0
        # VM based on max primary sensitivity move (netting offsets correlated positions)
        primary_moves = [abs(market.get_variable(var)) for var in self.primary_sensitivities]
        max_move = max(primary_moves) if primary_moves else 0.0
        vm = self.aum_mm * self.gross_leverage * max_move * 0.0001 * 0.022
        # IM increase from vol spike
        im_increase = self.aum_mm * self.gross_leverage * max(0, stress - 1.0) * 0.002
        # Haircut increase (collateral revaluation)
        haircut_impact = 0.0
        if self.repo_dep_mult > 0.5:
            haircut_impact = self.aum_mm * self.repo_dep_mult * market.repo_haircut_gilt_chg_pct * 0.003
        return vm + im_increase + haircut_impact

    def compute_redemptions(self, market, network, agents: List) -> float:
        # Hedge funds don't typically face redemptions in a 10-day window
        # but very stressed ones might face LP requests
        stress = market.vix_level / 15.0
        if stress > 2.5 and self.var_utilisation > 0.85:
            return self.aum_mm * 0.02
        return 0.0

    def compute_reactions(self, market, network=None, agents=None) -> Dict[str, float]:
        reactions = {}
        caps = REACTION_PARAMS["hedge_fund"]
        shortfall = max(0, -self.liquidity.B1) + self.liquidity.E1 * 0.2  # Buffer for further calls

        # 1. Try repo from connected banks (network-aware, using bank willingness)
        if network and self.repo_dep_mult > 0:
            connected_banks = network.get_connected_banks(self.name)
            agent_map = {a.name: a for a in agents} if agents else {}
            repo_obtained = 0.0
            repo_ask = shortfall * max(self.repo_dep_mult, 0.6) * caps["repo_ask_pct"]
            if repo_ask > 0:
                self.has_ever_sought_repo = True

            for bank_name in connected_banks:
                ask_per_bank = repo_ask / max(len(connected_banks), 1)
                bank = agent_map.get(bank_name)
                if bank and hasattr(bank, 'assess_repo_request'):
                    repo_obtained += bank.assess_repo_request(self.name, ask_per_bank, network)
                else:
                    repo_obtained += ask_per_bank * market.repo_market_availability_pct

            if repo_obtained > 0:
                reactions["seek_repo"] = repo_obtained
                shortfall -= repo_obtained
            elif repo_ask > 0:
                # All banks refused — forced to sell
                self.repo_refused_by_all = True

        # 2. Strategy-specific asset sales (last resort)
        if shortfall > 0:
            if self.strategy == "relative_value":
                sf_basis, hc_basis = caps["sell_basis_unwind"]
                sf_gilt, hc_gilt = caps["sell_gilt"]
                basis = self.get_item("Basis Trade Positions")
                if basis and basis.amount_mm > 0:
                    sell = min(shortfall * sf_basis, basis.amount_mm * hc_basis)
                    reactions["sell_gilt_basis_unwind"] = sell
                    shortfall -= sell
                gilt = self.get_item("Gilt Positions (net)")
                if gilt and gilt.amount_mm > 0 and shortfall > 0:
                    sell = min(shortfall * sf_gilt, gilt.amount_mm * hc_gilt)
                    reactions["sell_gilt"] = sell
                    shortfall -= sell

            elif self.strategy == "macro_rates":
                sf, hc = caps["sell_gilt"]
                gilt = self.get_item("Gilt Positions (net)")
                if gilt and gilt.amount_mm > 0:
                    sell = min(shortfall * sf, gilt.amount_mm * hc)
                    reactions["sell_gilt"] = sell
                    shortfall -= sell

            elif self.strategy == "credit_long_short":
                sf, hc = caps["sell_corp"]
                corp = self.get_item("Corp Bond Positions")
                if corp and corp.amount_mm > 0:
                    sell = min(shortfall * sf, corp.amount_mm * hc)
                    reactions["sell_corp_bonds"] = sell
                    shortfall -= sell

            elif self.strategy == "long_short_equity":
                sf, hc = caps["sell_equity"]
                eq = self.get_item("Equity Positions")
                if eq and eq.amount_mm > 0:
                    sell = min(shortfall * sf, eq.amount_mm * hc)
                    reactions["sell_equity"] = sell
                    shortfall -= sell

            else:  # multi_strategy
                sf_ms, hc_ms = caps["multi_strategy"]
                for item_name, action_name in [
                    ("Gilt Positions (net)", "sell_gilt"),
                    ("Corp Bond Positions", "sell_corp_bonds"),
                    ("Equity Positions", "sell_equity"),
                ]:
                    if shortfall <= 0:
                        break
                    item = self.get_item(item_name)
                    if item and item.amount_mm > 0:
                        sell = min(shortfall * sf_ms, item.amount_mm * hc_ms)
                        reactions[action_name] = sell
                        shortfall -= sell

        # 3. Redeem from MMFs/OEFs if connected
        if shortfall > 0 and network:
            oef_targets = network.get_redemption_targets(self.name)
            if oef_targets:
                redeem_per_oef = min(shortfall * 0.2, self.aum_mm * 0.05) / max(len(oef_targets), 1)
                reactions["redeem_mmf"] = redeem_per_oef * len(oef_targets)

        return reactions
