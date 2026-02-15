"""Insurer agent — hedge ratio, dirty CSA mechanics."""

from typing import Dict, List
from agents.base import BaseAgent, BalanceSheetItem
from config import REACTION_PARAMS, BUFFER_PARAMS


class InsurerAgent(BaseAgent):

    def __init__(self, config: Dict):
        name = config["name"]
        theta = config["theta"]
        bs = config["balance_sheet"]
        total_mm = (bs["gilt_holdings_mm"] + bs["corp_bond_holdings_mm"] +
                    bs["equity_portfolio_mm"] + bs["cash_and_liquid_mm"])
        super().__init__(name=name, agent_type="insurer", theta=theta, size_factor=total_mm)

        self.hedge_ratio = config["hedge_ratio"]
        self.dirty_csa_pct = config["dirty_csa_pct"]
        self.total_mm = total_mm

        self.committed_repo_mm = bs["committed_repo_lines_mm"]
        self.rcf_mm = bs["rcf_available_mm"]

        self.balance_sheet = [
            BalanceSheetItem("Gilt Holdings", bs["gilt_holdings_mm"], "liquid_asset",
                             {"gilt_10y_yield": -0.0005, "gilt_30y_yield": -0.0007},
                             is_collateral_eligible=True, is_reaction_instrument=True),
            BalanceSheetItem("Corporate Bond Holdings", bs["corp_bond_holdings_mm"], "liquid_asset",
                             {"ig_corp_spread": -0.0004, "hy_corp_spread": -0.0002},
                             is_collateral_eligible=True, is_reaction_instrument=True),
            BalanceSheetItem("Equity Portfolio", bs["equity_portfolio_mm"], "liquid_asset",
                             {"equity": 0.01},
                             is_reaction_instrument=True),
            BalanceSheetItem("Derivative Hedges", bs["derivative_hedges_notional_mm"], "off_bs",
                             {"gilt_10y_yield": -0.0002, "sonia_swap": -0.0002}),
            BalanceSheetItem("Cash & Liquid", bs["cash_and_liquid_mm"], "liquid_asset",
                             {}),
            BalanceSheetItem("Margin Posted", bs["margin_posted_mm"], "illiquid_asset",
                             {}),
            BalanceSheetItem("Committed Repo Lines", bs["committed_repo_lines_mm"], "liquid_asset",
                             {},
                             is_collateral_eligible=True),
            BalanceSheetItem("RCF Available", bs["rcf_available_mm"], "liquid_asset",
                             {}),
        ]

    def compute_initial_buffer(self) -> float:
        """Insurer buffer = cash + fraction of committed lines."""
        bp = BUFFER_PARAMS["insurer"]
        cash = self.get_item("Cash & Liquid")
        repo = self.get_item("Committed Repo Lines")
        rcf = self.get_item("RCF Available")
        cash_val = cash.amount_mm if cash else 0.0
        repo_val = repo.amount_mm if repo else 0.0
        rcf_val = rcf.amount_mm if rcf else 0.0
        self.liquidity.B0 = (cash_val * bp["cash_mult"]
                             + repo_val * bp["committed_repo_mult"]
                             + rcf_val * bp["rcf_mult"])
        self.liquidity.B0 = max(self.liquidity.B0, self.total_mm * bp["floor_pct_of_assets"])
        return self.liquidity.B0

    def compute_mtm_impact(self, market, day_delta: Dict[str, float]) -> float:
        total_mtm = 0.0
        for item in self.balance_sheet:
            for var, sens in item.sensitivity_map.items():
                delta = day_delta.get(var, 0.0)
                impact = item.amount_mm * sens * delta
                total_mtm += abs(impact)
        # Hedge ratio offsets some of the impact on derivatives
        deriv = self.get_item("Derivative Hedges")
        if deriv:
            hedge_offset = total_mtm * self.hedge_ratio * 0.3
            total_mtm = max(0, total_mtm - hedge_offset)
        return total_mtm

    def compute_margin_calls(self, market) -> float:
        deriv = self.get_item("Derivative Hedges")
        if not deriv:
            return 0.0

        stress = market.vix_level / 15.0
        # VM from rate/spread moves
        vm = deriv.amount_mm * abs(market.gilt_10y_yield_chg_bps) * 0.0001 * 0.008
        # IM increase
        im = deriv.amount_mm * max(0, stress - 1.0) * 0.0008

        # Dirty CSA: insurers with dirty CSAs post bonds as collateral,
        # which get haircut during stress → additional calls
        if self.dirty_csa_pct > 0:
            haircut_impact = (deriv.amount_mm * self.dirty_csa_pct *
                              market.repo_haircut_corp_chg_pct * 0.01 * 0.05)
            vm += haircut_impact

        return vm + im

    def compute_redemptions(self, market, network, agents: List) -> float:
        # Insurers may face policy surrenders under extreme stress, but small in 10-day window
        stress = market.vix_level / 15.0
        if stress > 2.5:
            return self.total_mm * 0.005
        return 0.0

    def compute_reactions(self, market, network=None, agents=None) -> Dict[str, float]:
        reactions = {}
        caps = REACTION_PARAMS["insurer"]
        shortfall = max(0, -self.liquidity.B1) + self.liquidity.E1 * 0.1

        # 1. Draw on committed repo lines
        repo_lines = self.get_item("Committed Repo Lines")
        if repo_lines and repo_lines.amount_mm > 0:
            draw = min(shortfall * 0.3, repo_lines.amount_mm * 0.5)
            reactions["draw_repo_line"] = draw
            shortfall -= draw

        # 2. Draw on RCF
        rcf = self.get_item("RCF Available")
        if rcf and rcf.amount_mm > 0:
            draw = min(shortfall * 0.2, rcf.amount_mm * 0.5)
            reactions["draw_rcf"] = draw
            shortfall -= draw

        # 3. Seek repo from connected banks (primary funding channel)
        if shortfall > 0 and network:
            connected = [b for b, i in network.bank_insurer_edges if i == self.name]
            agent_map = {a.name: a for a in agents} if agents else {}
            repo_obtained = 0.0
            repo_ask = shortfall * caps["repo_ask_pct"]
            for bank_name in connected:
                ask_per_bank = repo_ask / max(len(connected), 1)
                bank = agent_map.get(bank_name)
                if bank and hasattr(bank, 'assess_repo_request'):
                    repo_obtained += bank.assess_repo_request(self.name, ask_per_bank, network)
                else:
                    repo_obtained += ask_per_bank * market.repo_market_availability_pct
            if repo_obtained > 0:
                reactions["seek_repo"] = repo_obtained
                shortfall -= repo_obtained

        # 4. Sell gilts (last resort)
        if shortfall > 0:
            sf, hc = caps["sell_gilt"]
            gilt = self.get_item("Gilt Holdings")
            if gilt and gilt.amount_mm > 0:
                sell = min(shortfall * sf, gilt.amount_mm * hc)
                reactions["sell_gilt"] = sell
                shortfall -= sell

        # 5. Sell corporate bonds (last resort)
        if shortfall > 0:
            sf, hc = caps["sell_corp"]
            corp = self.get_item("Corporate Bond Holdings")
            if corp and corp.amount_mm > 0:
                sell = min(shortfall * sf, corp.amount_mm * hc)
                reactions["sell_corp_bonds"] = sell
                shortfall -= sell

        # 6. Sell equity (last resort)
        if shortfall > 0:
            sf, hc = caps["sell_equity"]
            eq = self.get_item("Equity Portfolio")
            if eq and eq.amount_mm > 0:
                sell = min(shortfall * sf, eq.amount_mm * hc)
                reactions["sell_equity"] = sell
                shortfall -= sell

        # 7. Redeem MMF
        if shortfall > 0 and network:
            oef_targets = network.get_redemption_targets(self.name)
            if oef_targets:
                redeem = min(shortfall * 0.15, self.total_mm * 0.03)
                reactions["redeem_mmf"] = redeem

        return reactions
