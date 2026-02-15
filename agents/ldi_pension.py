"""LDI / pension fund agent — leverage, yield buffers, recapitalisation."""

from typing import Dict, List
from agents.base import BaseAgent, BalanceSheetItem
from config import REACTION_PARAMS, BUFFER_PARAMS


class LDIPensionAgent(BaseAgent):

    def __init__(self, config: Dict):
        name = config["name"]
        theta = config["theta"]
        bs = config["balance_sheet"]
        aum_mm = (bs["gilt_holdings_mm"] + bs["il_gilt_holdings_mm"] +
                  bs["corp_bond_holdings_mm"] + bs["cash_and_mmf_mm"])
        super().__init__(name=name, agent_type="ldi_pension", theta=theta, size_factor=aum_mm)

        self.yield_buffer_bps = config["yield_buffer_bps"]
        self.ldi_leverage_ratio = bs["ldi_leverage_ratio"]
        self.aum_mm = aum_mm

        # Recapitalisation
        recap = config["recapitalisation"]
        self.recap_available_mm = recap["pension_scheme_can_recapitalise_mm"]
        self.recap_speed_days = recap["recapitalisation_speed_days"]
        self.is_pooled = recap["pre_agreed_waterfall"]
        self.recap_used_mm = 0.0

        self.balance_sheet = [
            BalanceSheetItem("Gilt Holdings", bs["gilt_holdings_mm"], "liquid_asset",
                             {"gilt_10y_yield": -0.0006, "gilt_30y_yield": -0.0009},
                             is_collateral_eligible=True, is_reaction_instrument=True),
            BalanceSheetItem("IL Gilt Holdings", bs["il_gilt_holdings_mm"], "liquid_asset",
                             {"il_gilt_yield": -0.0007},
                             is_collateral_eligible=True, is_reaction_instrument=True),
            BalanceSheetItem("Corporate Bond Holdings", bs["corp_bond_holdings_mm"], "liquid_asset",
                             {"ig_corp_spread": -0.0004},
                             is_collateral_eligible=True, is_reaction_instrument=True),
            BalanceSheetItem("Cash & MMF", bs["cash_and_mmf_mm"], "liquid_asset",
                             {}),
            BalanceSheetItem("Derivatives Exposure", bs["derivatives_exposure_notional_mm"], "off_bs",
                             {"gilt_10y_yield": -0.0003, "sonia_swap": -0.0003, "gilt_30y_yield": -0.0004}),
            BalanceSheetItem("Unencumbered Collateral", bs["unencumbered_collateral_mm"], "liquid_asset",
                             {},
                             is_collateral_eligible=True),
            BalanceSheetItem("Margin Posted", bs["margin_posted_mm"], "illiquid_asset",
                             {}),
        ]

        self.yield_buffer_consumed_pct = 0.0

    def compute_initial_buffer(self) -> float:
        """LDI buffer = cash/MMF + fraction of unencumbered collateral."""
        bp = BUFFER_PARAMS["ldi_pension"]
        cash = self.get_item("Cash & MMF")
        uec = self.get_item("Unencumbered Collateral")
        cash_val = cash.amount_mm if cash else 0.0
        uec_val = uec.amount_mm if uec else 0.0
        self.liquidity.B0 = cash_val * bp["cash_mult"] + uec_val * bp["unencumbered_collateral_mult"]
        self.liquidity.B0 = max(self.liquidity.B0, self.aum_mm * bp["floor_pct_of_aum"])
        return self.liquidity.B0

    def compute_mtm_impact(self, market, day_delta: Dict[str, float]) -> float:
        total_mtm = 0.0
        for item in self.balance_sheet:
            for var, sens in item.sensitivity_map.items():
                delta = day_delta.get(var, 0.0)
                impact = item.amount_mm * sens * delta
                total_mtm += abs(impact)
        # Leverage amplifies impact
        total_mtm *= self.ldi_leverage_ratio * 0.5
        return total_mtm

    def compute_margin_calls(self, market) -> float:
        deriv = self.get_item("Derivatives Exposure")
        if not deriv:
            return 0.0

        # VM from rate moves on derivatives (use max of gilt moves, not sum)
        gilt_move = max(abs(market.gilt_10y_yield_chg_bps), abs(market.gilt_30y_yield_chg_bps))
        vm = deriv.amount_mm * gilt_move * 0.0001 * 0.04

        # IM increase from volatility
        stress = market.vix_level / 15.0
        im_increase = deriv.amount_mm * max(0, stress - 1.0) * 0.003

        # Yield buffer consumption: once buffer consumed, margin calls escalate
        cumulative_gilt_move = abs(market.gilt_10y_yield_chg_bps)
        self.yield_buffer_consumed_pct = min(1.0, cumulative_gilt_move / self.yield_buffer_bps)

        if self.yield_buffer_consumed_pct >= 1.0:
            # Buffer breached — full margin calls hit
            excess = cumulative_gilt_move - self.yield_buffer_bps
            additional = deriv.amount_mm * excess * 0.0001 * 0.06
            vm += additional

        return vm + im_increase

    def compute_redemptions(self, market, network, agents: List) -> float:
        # LDI funds redeem from connected OEFs/MMFs to meet margin calls
        # This creates outflows FROM OEFs
        if network and self.yield_buffer_consumed_pct > 0.7:
            oef_targets = network.get_redemption_targets(self.name)
            cash_mmf = self.get_item("Cash & MMF")
            if oef_targets and cash_mmf and cash_mmf.amount_mm > 0:
                # Redeem proportional to stress
                redeem = cash_mmf.amount_mm * self.yield_buffer_consumed_pct * 0.3
                return redeem
        return 0.0

    def compute_reactions(self, market, network=None, agents=None) -> Dict[str, float]:
        reactions = {}
        caps = REACTION_PARAMS["ldi_pension"]
        shortfall = max(0, -self.liquidity.B1) + self.liquidity.E1 * 0.1

        # 1. Use unencumbered collateral
        uec = self.get_item("Unencumbered Collateral")
        if uec and uec.amount_mm > 0:
            use = min(shortfall * 0.4, uec.amount_mm * 0.5)
            reactions["post_collateral"] = use
            shortfall -= use

        # 2. Recapitalisation from pension scheme (speed depends on pooled/segregated)
        if shortfall > 0 and self.recap_available_mm > self.recap_used_mm:
            daily_recap = (self.recap_available_mm - self.recap_used_mm) / max(self.recap_speed_days, 1)
            recap_use = min(shortfall * 0.3, daily_recap)
            reactions["recapitalisation"] = recap_use
            self.recap_used_mm += recap_use
            shortfall -= recap_use

        # 3. Seek repo from connected banks (primary funding channel)
        if shortfall > 0 and network:
            clearing_banks = network.get_clearing_banks(self.name)
            agent_map = {a.name: a for a in agents} if agents else {}
            repo_obtained = 0.0
            repo_ask = shortfall * caps["repo_ask_pct"]
            for bank_name in clearing_banks:
                ask_per_bank = repo_ask / max(len(clearing_banks), 1)
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

        # 5. Sell IL gilts (last resort)
        if shortfall > 0:
            sf, hc = caps["sell_il_gilt"]
            il = self.get_item("IL Gilt Holdings")
            if il and il.amount_mm > 0:
                sell = min(shortfall * sf, il.amount_mm * hc)
                reactions["sell_gilt_il"] = sell
                shortfall -= sell

        # 6. Sell corporate bonds (last resort)
        if shortfall > 0:
            sf, hc = caps["sell_corp"]
            corp = self.get_item("Corporate Bond Holdings")
            if corp and corp.amount_mm > 0:
                sell = min(shortfall * sf, corp.amount_mm * hc)
                reactions["sell_corp_bonds"] = sell
                shortfall -= sell

        # 7. Redeem MMF/OEF holdings
        if shortfall > 0 and network:
            oef_targets = network.get_redemption_targets(self.name)
            if oef_targets:
                redeem = min(shortfall * 0.2, self.aum_mm * 0.05)
                reactions["redeem_mmf"] = redeem

        return reactions
