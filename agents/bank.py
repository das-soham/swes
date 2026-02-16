"""Bank agent — intermediary, repo provider, market maker."""

from typing import Dict, List
from agents.base import BaseAgent, BalanceSheetItem
from config import REACTION_PARAMS, BUFFER_PARAMS, FEEDBACK_PARAMS


class BankAgent(BaseAgent):

    def __init__(self, config: Dict):
        name = config["name"]
        theta = config["theta"]
        total_bs_mm = config["total_bs_mm"]
        super().__init__(name=name, agent_type="bank", theta=theta, size_factor=total_bs_mm,
                         buffer_usability=config.get("buffer_usability", 0.0))

        self.tier = config["tier"]
        self.risk_appetite = config["risk_appetite"]
        self.total_bs_mm = total_bs_mm

        # Market-making capacity
        mm = config["market_making_capacity"]
        self.gilt_mm_appetite_mm = mm["gilt_appetite_mm"]
        self.corp_mm_appetite_mm = mm["corp_bond_appetite_mm"]
        self.mm_appetite_consumed_pct = mm["appetite_consumed_pct"]

        # Repo provision
        rp = config["repo_provision"]
        self.repo_capacity_mm = rp["total_capacity_mm"]
        self.willingness_to_roll_pct = rp["willingness_to_roll_pct"]
        self.willingness_to_extend_new_pct = rp["willingness_to_extend_new_pct"]
        self.haircut_sensitivity = rp["haircut_sensitivity"]

        # Build balance sheet
        bs = config["balance_sheet"]
        self.balance_sheet = [
            BalanceSheetItem("Gilt Holdings", bs["gilt_holdings_mm"], "liquid_asset",
                             {"gilt_10y_yield": -0.00045, "gilt_30y_yield": -0.00065},
                             is_collateral_eligible=True, is_reaction_instrument=True),
            BalanceSheetItem("Corporate Bond Holdings", bs["corp_bond_holdings_mm"], "liquid_asset",
                             {"ig_corp_spread": -0.0004, "hy_corp_spread": -0.0002},
                             is_collateral_eligible=True, is_reaction_instrument=True),
            BalanceSheetItem("Equity Portfolio", bs["equity_portfolio_mm"], "liquid_asset",
                             {"equity": 0.01},
                             is_reaction_instrument=True),
            BalanceSheetItem("Repo Lending", bs["repo_lending_mm"], "liquid_asset",
                             {},
                             is_collateral_eligible=False),
            BalanceSheetItem("Derivative Assets", bs["derivative_assets_mm"], "illiquid_asset",
                             {"gilt_10y_yield": -0.0002, "sonia_swap": -0.0002}),
            BalanceSheetItem("BoE Facility Eligible", bs["boe_facility_eligible_mm"], "liquid_asset",
                             {},
                             is_collateral_eligible=True),
            BalanceSheetItem("Wholesale Funding", bs["wholesale_funding_mm"], "liability",
                             {}),
            BalanceSheetItem("CET1 Buffer", bs["cet1_buffer_mm"], "equity",
                             {}),
        ]

        # Track daily capacity history
        self.daily_capacity_history: List[float] = []
        self.corp_appetite_consumed_pct: float = 0.0
        self.daily_corp_capacity_history: List[float] = []
        self.daily_combined_capacity_history: List[float] = []

    def compute_initial_buffer(self) -> float:
        """Bank buffer = BoE eligible + CET1 headroom - wholesale funding runoff risk."""
        bp = BUFFER_PARAMS["bank"]
        boe = self.get_item("BoE Facility Eligible")
        cet1 = self.get_item("CET1 Buffer")
        wf = self.get_item("Wholesale Funding")
        boe_val = boe.amount_mm if boe else 0.0
        cet1_val = cet1.amount_mm if cet1 else 0.0
        wf_val = wf.amount_mm if wf else 0.0
        self.liquidity.B0 = (boe_val * bp["boe_eligible_mult"]
                             + cet1_val * bp["cet1_mult"]
                             - wf_val * bp["wholesale_funding_runoff_mult"])
        self.liquidity.B0 = max(self.liquidity.B0, self.total_bs_mm * bp["floor_pct_of_bs"])
        return self.liquidity.B0

    def compute_mtm_impact(self, market, day_delta: Dict[str, float]) -> float:
        total_mtm = 0.0
        for item in self.balance_sheet:
            for var, sens in item.sensitivity_map.items():
                delta = day_delta.get(var, 0.0)
                impact = item.amount_mm * sens * delta
                total_mtm += abs(impact)
        return total_mtm

    def compute_margin_calls(self, market) -> float:
        deriv = self.get_item("Derivative Assets")
        if not deriv:
            return 0.0
        stress = market.vix_level / 15.0
        vm = deriv.amount_mm * abs(market.gilt_10y_yield_chg_bps) * 0.0001 * 0.05
        im_increase = deriv.amount_mm * (stress - 1.0) * 0.005 if stress > 1.0 else 0.0
        return vm + im_increase

    def compute_redemptions(self, market, network, agents: List) -> float:
        # Banks don't face fund redemptions but face wholesale funding pressure
        wf = self.get_item("Wholesale Funding")
        if not wf:
            return 0.0
        stress = market.vix_level / 15.0
        if stress > 2.0:
            return wf.amount_mm * (stress - 2.0) * 0.02
        return 0.0

    def compute_reactions(self, market, network=None, agents=None) -> Dict[str, float]:
        reactions = {}
        shortfall = max(0, -self.liquidity.B1)

        # 1. Access BoE facilities (preferred)
        boe = self.get_item("BoE Facility Eligible")
        if boe and boe.amount_mm > 0:
            boe_draw = min(shortfall * 0.3, boe.amount_mm * 0.5)
            reactions["boe_facility"] = boe_draw
            shortfall -= boe_draw

        # 2. Reduce repo lending (tighten for counterparties)
        if shortfall > 0:
            repo = self.get_item("Repo Lending")
            if repo and repo.amount_mm > 0:
                repo_cut = min(shortfall * 0.3, repo.amount_mm * (1.0 - self.risk_appetite) * 0.3)
                reactions["reduce_repo_lending"] = repo_cut
                shortfall -= repo_cut

        # 3. Sell gilts (last resort)
        if shortfall > 0:
            sf, hc = REACTION_PARAMS["bank"]["sell_gilt"]
            gilt = self.get_item("Gilt Holdings")
            if gilt and gilt.amount_mm > 0:
                gilt_sell = min(shortfall * sf, gilt.amount_mm * hc)
                reactions["sell_gilt"] = gilt_sell
                shortfall -= gilt_sell

        # 4. Sell corporate bonds (last resort)
        if shortfall > 0:
            sf, hc = REACTION_PARAMS["bank"]["sell_corp"]
            corp = self.get_item("Corporate Bond Holdings")
            if corp and corp.amount_mm > 0:
                corp_sell = min(shortfall * sf, corp.amount_mm * hc)
                reactions["sell_corp_bonds"] = corp_sell

        return reactions

    def assess_repo_request(self, requesting_agent_name: str, amount: float, network) -> float:
        """
        Check if requesting agent is connected to this bank via the network.
        Returns amount willing to provide (0 if no relationship or bank too stressed).
        """
        if network is None:
            return 0.0

        # Check if requester is connected
        connected_hfs = network.get_connected_hfs(self.name)
        connected_ldis = network.get_connected_ldis(self.name)
        connected_insurers = [i for b, i in network.bank_insurer_edges if b == self.name]
        all_connected = connected_hfs + connected_ldis + connected_insurers

        if requesting_agent_name not in all_connected:
            return 0.0  # No relationship — refuse

        # Bank stress-based willingness: linear decay from 1.0 at no stress to 0.0 at threshold
        threshold = FEEDBACK_PARAMS["bank_repo_refusal_stress_threshold"]
        stress_ratio = self.liquidity.E1 / max(self.liquidity.B0, 1.0)
        stress_scaling = max(0.0, 1.0 - stress_ratio / threshold)

        available = self.repo_capacity_mm * self.willingness_to_extend_new_pct
        return min(amount, available * self.risk_appetite * stress_scaling)

    def absorb_selling_pressure(self, amount_mm: float) -> float:
        """Use this bank's gilt market-making capacity to absorb selling pressure."""
        remaining_appetite = self.gilt_mm_appetite_mm * (1.0 - self.mm_appetite_consumed_pct)
        absorbed = min(amount_mm, remaining_appetite * self.risk_appetite)
        if self.gilt_mm_appetite_mm > 0:
            self.mm_appetite_consumed_pct += absorbed / self.gilt_mm_appetite_mm
            self.mm_appetite_consumed_pct = min(1.0, self.mm_appetite_consumed_pct)
        return absorbed

    def absorb_corp_selling_pressure(self, amount_mm: float) -> float:
        """Use this bank's corp bond market-making capacity to absorb selling pressure."""
        remaining_appetite = self.corp_mm_appetite_mm * (1.0 - self.corp_appetite_consumed_pct)
        absorbed = min(amount_mm, remaining_appetite * self.risk_appetite)
        if self.corp_mm_appetite_mm > 0:
            self.corp_appetite_consumed_pct += absorbed / self.corp_mm_appetite_mm
            self.corp_appetite_consumed_pct = min(1.0, self.corp_appetite_consumed_pct)
        return absorbed

    def tighten_repo_for_counterparties(self, network) -> None:
        """
        When reacting, reduce willingness to extend new repo.
        Degree of tightening depends on risk_appetite.
        """
        tightening = (1.0 - self.risk_appetite) * 0.3
        self.willingness_to_extend_new_pct = max(
            0.0, self.willingness_to_extend_new_pct - tightening
        )
        self.willingness_to_roll_pct = max(
            0.5, self.willingness_to_roll_pct - tightening * 0.5
        )

    def register_actions_to_market(self, market) -> None:
        super().register_actions_to_market(market)

    def post_registration_update(self, gilt_to_absorb: float, corp_to_absorb: float) -> None:
        """Called after ALL agents have registered, with this bank's share of selling."""
        self.absorb_selling_pressure(gilt_to_absorb)
        self.absorb_corp_selling_pressure(corp_to_absorb)
        if self.has_reacted:
            self.tighten_repo_for_counterparties(None)
        self.daily_capacity_history.append(self.mm_appetite_consumed_pct)
        self.daily_corp_capacity_history.append(self.corp_appetite_consumed_pct)
        # Combined: weighted by total capacity
        total_cap = self.gilt_mm_appetite_mm + self.corp_mm_appetite_mm
        if total_cap > 0:
            gilt_used = self.mm_appetite_consumed_pct * self.gilt_mm_appetite_mm
            corp_used = self.corp_appetite_consumed_pct * self.corp_mm_appetite_mm
            self.daily_combined_capacity_history.append((gilt_used + corp_used) / total_cap)
        else:
            self.daily_combined_capacity_history.append(0.0)
