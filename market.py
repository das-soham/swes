"""Market state: prices, depth, feedback."""

import json
from typing import Dict


def load_scenario(path: str = "data/scenario_swes1.json") -> Dict:
    with open(path) as f:
        return json.load(f)


def get_scenario_day(scenario: Dict, day: int) -> Dict[str, float]:
    paths = scenario["variable_paths"]
    return {var: vals[day] for var, vals in paths.items()}


class MarketState:
    """
    Tracks current market conditions: exogenous scenario moves + endogenous feedback.

    Exogenous: scenario-driven day-by-day paths (gilt yields, spreads, equity, etc.)
    Endogenous: agent selling pressure feeds back into prices via market depth.
    """

    def __init__(self):
        # Current cumulative scenario values (bps or %)
        self.gilt_10y_yield_chg_bps: float = 0.0
        self.gilt_30y_yield_chg_bps: float = 0.0
        self.il_gilt_yield_chg_bps: float = 0.0
        self.ust_10y_yield_chg_bps: float = 0.0
        self.ig_corp_spread_chg_bps: float = 0.0
        self.hy_corp_spread_chg_bps: float = 0.0
        self.equity_chg_pct: float = 0.0
        self.sonia_swap_chg_bps: float = 0.0
        self.fx_gbpusd_chg_pct: float = 0.0
        self.repo_haircut_gilt_chg_pct: float = 0.0
        self.repo_haircut_corp_chg_pct: float = 0.0
        self.bond_futures_basis_chg_bps: float = 0.0
        self.vix_level: float = 15.0

        # Market functioning indicators
        self.gilt_bid_ask_spread_bps: float = 2.0  # Normal ~2bps
        self.corp_bid_ask_spread_bps: float = 5.0  # Normal ~5bps
        self.repo_market_availability_pct: float = 1.0  # 1.0 = fully available
        self.market_depth_gilt_mm: float = 5000.0  # Total gilt market-making capacity
        self.market_depth_corp_mm: float = 2000.0

        # Endogenous pressure accumulators (reset each day)
        self.endogenous_gilt_selling_mm: float = 0.0
        self.endogenous_corp_selling_mm: float = 0.0
        self.endogenous_repo_demand_mm: float = 0.0

        # Endogenous additional price impacts
        self.endogenous_gilt_yield_add_bps: float = 0.0
        self.endogenous_ig_spread_add_bps: float = 0.0
        self.endogenous_equity_add_pct: float = 0.0

        self.day: int = 0

    def apply_exogenous_scenario(self, day_values: Dict[str, float]) -> None:
        """Apply the scenario-driven market moves for this day."""
        self.gilt_10y_yield_chg_bps = day_values.get("gilt_10y_yield", 0.0)
        self.gilt_30y_yield_chg_bps = day_values.get("gilt_30y_yield", 0.0)
        self.il_gilt_yield_chg_bps = day_values.get("il_gilt_yield", 0.0)
        self.ust_10y_yield_chg_bps = day_values.get("ust_10y_yield", 0.0)
        self.ig_corp_spread_chg_bps = day_values.get("ig_corp_spread", 0.0)
        self.hy_corp_spread_chg_bps = day_values.get("hy_corp_spread", 0.0)
        self.equity_chg_pct = day_values.get("equity", 0.0)
        self.sonia_swap_chg_bps = day_values.get("sonia_swap", 0.0)
        self.fx_gbpusd_chg_pct = day_values.get("fx_gbpusd", 0.0)
        self.repo_haircut_gilt_chg_pct = day_values.get("repo_haircut_gilt", 0.0)
        self.repo_haircut_corp_chg_pct = day_values.get("repo_haircut_corp", 0.0)
        self.bond_futures_basis_chg_bps = day_values.get("bond_futures_basis", 0.0)
        self.vix_level = day_values.get("vix", 15.0)

        # Reset endogenous accumulators each day
        self.endogenous_gilt_selling_mm = 0.0
        self.endogenous_corp_selling_mm = 0.0
        self.endogenous_repo_demand_mm = 0.0
        self.endogenous_gilt_yield_add_bps = 0.0
        self.endogenous_ig_spread_add_bps = 0.0
        self.endogenous_equity_add_pct = 0.0

        # Update market functioning based on scenario severity
        stress_intensity = self.vix_level / 15.0
        self.gilt_bid_ask_spread_bps = 2.0 * stress_intensity
        self.corp_bid_ask_spread_bps = 5.0 * stress_intensity
        self.repo_market_availability_pct = max(0.5, 1.0 - (stress_intensity - 1.0) * 0.15)

    def apply_endogenous_feedback(self) -> None:
        """
        Convert aggregate agent selling pressure into additional price impacts.
        This is the market-level (broadcast) feedback loop.
        """
        # Gilt selling → additional yield rise
        if self.market_depth_gilt_mm > 0:
            gilt_price_impact = (self.endogenous_gilt_selling_mm / self.market_depth_gilt_mm) * 20.0
            self.endogenous_gilt_yield_add_bps += gilt_price_impact
            self.gilt_10y_yield_chg_bps += gilt_price_impact * 0.5
            self.gilt_30y_yield_chg_bps += gilt_price_impact * 0.7

        # Corp selling → additional spread widening
        if self.market_depth_corp_mm > 0:
            corp_price_impact = (self.endogenous_corp_selling_mm / self.market_depth_corp_mm) * 30.0
            self.endogenous_ig_spread_add_bps += corp_price_impact
            self.ig_corp_spread_chg_bps += corp_price_impact * 0.6
            self.hy_corp_spread_chg_bps += corp_price_impact * 1.2

        # Repo demand → reduced availability
        total_repo_capacity = 50000.0  # Approximate system repo capacity in mm
        if total_repo_capacity > 0:
            repo_pressure = self.endogenous_repo_demand_mm / total_repo_capacity
            self.repo_market_availability_pct = max(
                0.5, self.repo_market_availability_pct - repo_pressure * 0.25
            )

        # Bid-ask spreads widen with selling pressure
        self.gilt_bid_ask_spread_bps += self.endogenous_gilt_selling_mm * 0.001
        self.corp_bid_ask_spread_bps += self.endogenous_corp_selling_mm * 0.002

        # Market depth degrades under pressure (dealers pull back)
        stress = self.vix_level / 15.0
        self.market_depth_gilt_mm = max(1000.0, 5000.0 / stress)
        self.market_depth_corp_mm = max(500.0, 2000.0 / stress)

    def get_variable(self, var_name: str) -> float:
        """Get current value of a market variable by name."""
        mapping = {
            "gilt_10y_yield": self.gilt_10y_yield_chg_bps,
            "gilt_30y_yield": self.gilt_30y_yield_chg_bps,
            "il_gilt_yield": self.il_gilt_yield_chg_bps,
            "ust_10y_yield": self.ust_10y_yield_chg_bps,
            "ig_corp_spread": self.ig_corp_spread_chg_bps,
            "hy_corp_spread": self.hy_corp_spread_chg_bps,
            "equity": self.equity_chg_pct,
            "sonia_swap": self.sonia_swap_chg_bps,
            "fx_gbpusd": self.fx_gbpusd_chg_pct,
            "repo_haircut_gilt": self.repo_haircut_gilt_chg_pct,
            "repo_haircut_corp": self.repo_haircut_corp_chg_pct,
            "bond_futures_basis": self.bond_futures_basis_chg_bps,
            "vix": self.vix_level,
        }
        return mapping.get(var_name, 0.0)

    def snapshot(self) -> Dict:
        """Return current market state as a dictionary."""
        return {
            "day": self.day,
            "gilt_10y_yield_chg_bps": self.gilt_10y_yield_chg_bps,
            "gilt_30y_yield_chg_bps": self.gilt_30y_yield_chg_bps,
            "il_gilt_yield_chg_bps": self.il_gilt_yield_chg_bps,
            "ust_10y_yield_chg_bps": self.ust_10y_yield_chg_bps,
            "ig_corp_spread_chg_bps": self.ig_corp_spread_chg_bps,
            "hy_corp_spread_chg_bps": self.hy_corp_spread_chg_bps,
            "equity_chg_pct": self.equity_chg_pct,
            "sonia_swap_chg_bps": self.sonia_swap_chg_bps,
            "fx_gbpusd_chg_pct": self.fx_gbpusd_chg_pct,
            "repo_haircut_gilt_chg_pct": self.repo_haircut_gilt_chg_pct,
            "repo_haircut_corp_chg_pct": self.repo_haircut_corp_chg_pct,
            "bond_futures_basis_chg_bps": self.bond_futures_basis_chg_bps,
            "vix_level": self.vix_level,
            "gilt_bid_ask_spread_bps": self.gilt_bid_ask_spread_bps,
            "corp_bid_ask_spread_bps": self.corp_bid_ask_spread_bps,
            "repo_market_availability_pct": self.repo_market_availability_pct,
            "market_depth_gilt_mm": self.market_depth_gilt_mm,
            "market_depth_corp_mm": self.market_depth_corp_mm,
            "endogenous_gilt_selling_mm": self.endogenous_gilt_selling_mm,
            "endogenous_corp_selling_mm": self.endogenous_corp_selling_mm,
            "endogenous_repo_demand_mm": self.endogenous_repo_demand_mm,
            "endogenous_gilt_yield_add_bps": self.endogenous_gilt_yield_add_bps,
            "endogenous_ig_spread_add_bps": self.endogenous_ig_spread_add_bps,
        }
