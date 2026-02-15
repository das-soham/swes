"""Base Agent class with Van den End three-stage mechanics."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from abc import ABC, abstractmethod
import numpy as np


@dataclass
class LiquidityPosition:
    B0: float = 0.0
    B1: float = 0.0
    B2: float = 0.0
    B3: float = 0.0
    E1: float = 0.0
    E2: float = 0.0


@dataclass
class BalanceSheetItem:
    name: str
    amount_mm: float
    category: str                      # 'liquid_asset', 'illiquid_asset', 'liability', 'equity', 'off_bs'
    sensitivity_map: Dict[str, float] = field(default_factory=dict)
    is_collateral_eligible: bool = False
    is_reaction_instrument: bool = False
    current_haircut_pct: float = 0.0


class BaseAgent(ABC):

    def __init__(self, name: str, agent_type: str, theta: float, size_factor: float = 1.0):
        self.name = name
        self.agent_type = agent_type
        self.theta = theta
        self.size_factor = size_factor    # Used by network for weighted assignment
        self.balance_sheet: List[BalanceSheetItem] = []
        self.liquidity = LiquidityPosition()
        self.has_reacted = False
        self.reactions: Dict[str, float] = {}
        self.daily_history: List[Dict] = []
        self.cumulative_margin_calls_mm: float = 0.0
        self.cumulative_asset_sales_mm: float = 0.0
        self.cumulative_gilt_sales_mm: float = 0.0
        self.cumulative_repo_demand_mm: float = 0.0
        self.cumulative_redemptions_mm: float = 0.0

    def get_item(self, name: str) -> Optional[BalanceSheetItem]:
        for item in self.balance_sheet:
            if item.name == name:
                return item
        return None

    def compute_initial_buffer(self) -> float:
        liquid = sum(i.amount_mm for i in self.balance_sheet if i.category == 'liquid_asset')
        liab = sum(i.amount_mm for i in self.balance_sheet if i.category == 'liability')
        self.liquidity.B0 = liquid - liab
        return self.liquidity.B0

    @abstractmethod
    def compute_mtm_impact(self, market, day_delta: Dict[str, float]) -> float:
        pass

    @abstractmethod
    def compute_margin_calls(self, market) -> float:
        pass

    @abstractmethod
    def compute_redemptions(self, market, network, agents: List) -> float:
        """Now takes network parameter to route redemptions through bilateral links."""
        pass

    def compute_stage1(self, market, day_delta, network=None, agents=None) -> float:
        mtm = self.compute_mtm_impact(market, day_delta)
        margin = self.compute_margin_calls(market)
        redemptions = self.compute_redemptions(market, network, agents or [])
        self.liquidity.E1 = mtm + margin + redemptions
        self.liquidity.B1 = self.liquidity.B0 - self.liquidity.E1
        self.cumulative_margin_calls_mm += margin
        self.cumulative_redemptions_mm += redemptions
        return self.liquidity.E1

    def should_react(self) -> bool:
        if self.liquidity.B0 <= 0:
            return False
        return (self.liquidity.E1 / self.liquidity.B0) > self.theta

    @abstractmethod
    def compute_reactions(self, market, network=None, agents=None) -> Dict[str, float]:
        """Now takes network to route bilateral actions (e.g., which bank to seek repo from)."""
        pass

    def compute_stage2(self, market, network=None, agents=None) -> None:
        if not self.should_react():
            self.has_reacted = False
            self.reactions = {}
            self.liquidity.B2 = self.liquidity.B1
            return
        self.has_reacted = True
        self.reactions = self.compute_reactions(market, network, agents)
        mitigation = 0.0
        for action, amount in self.reactions.items():
            if action.startswith("sell_"):
                realisation = max(0.5, 1.0 - market.gilt_bid_ask_spread_bps / 100.0)
                mitigation += amount * realisation
            elif "repo" in action:
                mitigation += amount * market.repo_market_availability_pct
            elif "boe" in action:
                mitigation += amount * 0.95
            elif "redeem" in action:
                mitigation += amount * 0.90
            else:
                mitigation += amount * 0.80
        self.liquidity.B2 = self.liquidity.B1 + mitigation
        for action, amount in self.reactions.items():
            if "sell" in action:
                self.cumulative_asset_sales_mm += amount
                if "gilt" in action:
                    self.cumulative_gilt_sales_mm += amount
            if "repo" in action:
                self.cumulative_repo_demand_mm += amount

    def apply_stage3(self, e2: float) -> None:
        self.liquidity.E2 += e2
        self.liquidity.B3 = self.liquidity.B2 - self.liquidity.E2

    def register_actions_to_market(self, market) -> None:
        for action, amount in self.reactions.items():
            if "gilt" in action and "sell" in action:
                market.endogenous_gilt_selling_mm += amount
            elif "corp" in action and "sell" in action:
                market.endogenous_corp_selling_mm += amount
            elif "repo" in action:
                market.endogenous_repo_demand_mm += amount

    def daily_snapshot(self) -> Dict:
        return {
            "agent": self.name,
            "agent_type": self.agent_type,
            "size_factor": self.size_factor,
            "B0": self.liquidity.B0, "B1": self.liquidity.B1,
            "B2": self.liquidity.B2, "B3": self.liquidity.B3,
            "E1": self.liquidity.E1, "E2": self.liquidity.E2,
            "has_reacted": self.has_reacted,
            "cum_margin": self.cumulative_margin_calls_mm,
            "cum_sales": self.cumulative_asset_sales_mm,
            "cum_repo": self.cumulative_repo_demand_mm,
        }

    def reset_daily(self) -> None:
        self.liquidity.E1 = 0.0
        self.liquidity.E2 = 0.0
        self.has_reacted = False
        self.reactions = {}
