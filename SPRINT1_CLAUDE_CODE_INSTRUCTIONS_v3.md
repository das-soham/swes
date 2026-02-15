# CLAUDE CODE AGENT: Sprint 1 Build Instructions (v2)
# SWES Private Markets Stress Lens — SWES 1 Channel Pack (Fast Channel)
# HETEROGENEOUS MULTI-AGENT NETWORK MODEL

---

## CRITICAL DESIGN CONTEXT — READ BEFORE CODING

This is a **market-price-driven, time-stepped, network-based system-wide stress simulator** with **60-75 heterogeneous agents** connected by bilateral relationships.

### How stress propagates:

1. Market prices move (gilt yields spike, credit spreads widen, equity falls)
2. This causes **immediate mark-to-market losses** on portfolios
3. Which triggers **margin calls** (VM + IM increases) flowing through **bilateral relationships**
4. Which creates **liquidity needs** (agents need cash/collateral NOW)
5. Agents respond **behaviourally** — but differently based on their size, strategy, and risk tolerance
6. These actions flow through the **network** — a bank tightening repo affects only ITS connected hedge funds
7. Collective actions impact **market-level** prices (aggregate selling pressure)
8. Which feeds back to step 1 → **amplification spiral**

### Why heterogeneity matters:

The SWES 1 finding that ">1/3 of NBFIs expecting repo would be refused by all SWES banks" ONLY exists because different banks made different decisions. With one archetypal bank, there's no distribution of willingness. Similarly, LDI funds with thin yield buffers were forced sellers on Day 1 while those with 300bps buffers absorbed the shock. The cascade emerges from **dispersion**, not averages.

### Network topology:

```
10-15 Banks (hub nodes, degree 8-10)
    ↕ bilateral repo/PB/clearing relationships
30-40 Hedge Funds (spoke nodes, degree 2-3)

8-12 LDI/Pension Funds ←→ Banks (clearing member relationships)
                        ←→ OEFs/MMFs (redemption relationships)

5-8 Insurers ←→ Banks (derivatives clearing, repo)

5-8 OEFs/MMFs ←→ all NBFIs (redemption source)
```

Each hedge fund has active relationships with 2-3 banks.
Each bank has active relationships with 8-10 hedge funds.
Relationships are randomly assigned at setup with degree constraints.

### PRA's Three Transmission Channels:

1. **Drivers of liquidity needs:** VM calls, IM increases, collateral revaluation, fund redemptions
2. **Actions in response + liquidity available:** Asset sales, repo demand, bank intermediation willingness
3. **Deleveraging / rebalancing:** VaR-limit-driven deleveraging, mandate rebalancing, precautionary risk-off

### Sprint 1 scope:

- SWES 1 channel pack (fast channel, 10 business days)
- 60-75 heterogeneous agents across 5 types
- Bilateral relationship network with degree constraints
- Market-price-driven scenario with day-by-day paths
- Van den End three-stage mechanics at each time step
- Network-propagated feedback (not broadcast)
- System-wide feedback toggle as core demo feature

### NOT in Sprint 1:

- Slow channel (GDP → EBITDA → defaults)
- Private credit / PE / AAM agents
- Sentiment accumulator
- SWES 2 channel pack

---

## PROJECT STRUCTURE

```
swes/
├── app.py                          # Streamlit entry point
├── config.py                       # Constants, enums, defaults
├── market.py                       # Market state: prices, depth, feedback
├── network.py                      # Relationship graph + bilateral flow routing
├── agent_factory.py                # Parameterised generation of 60-75 agents
├── agents/
│   ├── __init__.py
│   ├── base.py                     # Base Agent class (Van den End mechanics)
│   ├── bank.py                     # Bank agent (intermediary, repo, MM)
│   ├── hedge_fund.py               # Hedge fund agent (strategy-specific)
│   ├── ldi_pension.py              # LDI / pension fund agent
│   ├── insurer.py                  # Insurer agent
│   └── oef_mmf.py                  # OEF / MMF agent (redemption-driven)
├── engine/
│   ├── __init__.py
│   ├── simulation.py               # Time-stepped simulation loop
│   └── feedback.py                 # Stage 3: network-propagated feedback
├── visualisation.py                # All Plotly charts
├── data/
│   ├── scenario_swes1.json         # Day-by-day market variable paths
│   ├── agent_distributions.json    # Parameter distributions for factory
│   └── network_config.json         # Degree constraints and topology rules
├── requirements.txt
└── README.md
```

---

## STEP 0: SETUP

Create `requirements.txt`:
```
streamlit>=1.30.0
plotly>=5.18.0
pandas>=2.0.0
numpy>=1.24.0
scipy>=1.11.0
networkx>=3.1
```

---

## STEP 1: Create `config.py`

```python
"""Global configuration, constants, enums."""

from enum import Enum

class AgentType(Enum):
    BANK = "bank"
    LDI_PENSION = "ldi_pension"
    HEDGE_FUND = "hedge_fund"
    INSURER = "insurer"
    OEF_MMF = "oef_mmf"

class HedgeFundStrategy(Enum):
    LONG_SHORT_EQUITY = "long_short_equity"
    MACRO_RATES = "macro_rates"
    RELATIVE_VALUE = "relative_value"       # Basis trades — directly hit by SWES
    CREDIT_LONG_SHORT = "credit_long_short"
    MULTI_STRATEGY = "multi_strategy"

class MarketVariable(Enum):
    GILT_10Y_YIELD = "gilt_10y_yield"
    GILT_30Y_YIELD = "gilt_30y_yield"
    IL_GILT_YIELD = "il_gilt_yield"
    UST_10Y_YIELD = "ust_10y_yield"
    IG_CORP_SPREAD = "ig_corp_spread"
    HY_CORP_SPREAD = "hy_corp_spread"
    EQUITY = "equity"
    SONIA_SWAP = "sonia_swap"
    FX_GBPUSD = "fx_gbpusd"
    REPO_HAIRCUT_GILT = "repo_haircut_gilt"
    REPO_HAIRCUT_CORP = "repo_haircut_corp"
    BOND_FUTURES_BASIS = "bond_futures_basis"
    VIX = "vix"

# Agent population counts
AGENT_COUNTS = {
    AgentType.BANK: 12,
    AgentType.HEDGE_FUND: 35,
    AgentType.LDI_PENSION: 10,
    AgentType.INSURER: 6,
    AgentType.OEF_MMF: 7,
}
# Total: 70 agents

# Network degree constraints
NETWORK_RULES = {
    "hf_bank_degree": (2, 3),       # Each HF connected to 2-3 banks
    "bank_hf_degree": (8, 12),      # Each bank connected to 8-12 HFs
    "ldi_bank_degree": (1, 2),      # Each LDI clears through 1-2 banks
    "insurer_bank_degree": (1, 3),  # Each insurer has 1-3 bank relationships
    "oef_all_degree": (0, 0),       # OEFs don't have bilateral bank relationships
                                     # but ARE redeemed FROM by all other NBFIs
}

# Van den End defaults
VDE_DEFAULTS = {
    "bank_theta_range": (0.35, 0.45),
    "ldi_theta_range": (0.25, 0.35),
    "hedge_fund_theta_range": (0.20, 0.30),
    "insurer_theta_range": (0.40, 0.50),
    "oef_theta_range": (0.15, 0.25),
}

SIMULATION_DAYS = 10
FEEDBACK_ITERATIONS_PER_DAY = 3

# SWES 1 calibration anchors
SWES1_ANCHORS = {
    "total_nbfi_margin_calls_bn": 94.0,
    "ldi_recapitalisation_bn": 16.5,
    "nbfi_gilt_sales_bn": 4.7,
    "bank_gilt_capacity_consumed_pct": 0.70,
    "additional_long_gilt_exhaust_bn": 0.5,
    "nbfi_repo_refusal_pct": 0.33,
}
```

---

## STEP 2: Create `data/scenario_swes1.json`

Same as previous version — day-by-day cumulative market variable paths over 10 business days. Calibrated to SWES 1 published parameters.

```json
{
  "description": "SWES 1 hypothetical scenario: sudden crystallisation of geopolitical tensions",
  "horizon_days": 10,
  "narrative_events": {
    "day_1": "Geopolitical shock triggers sharp repricing of risk-free rates globally",
    "day_3": "Default of mid-sized relative value hedge fund elevates counterparty credit risk",
    "day_5": "Single-notch sovereign downgrades (UK and others) + corporate downgrades",
    "day_7": "Sovereign wealth funds announce reduction in advanced-economy debt holdings",
    "day_10": "Uncertainty persists; expectation of longer-term economic fundamental shocks"
  },
  "variable_paths": {
    "gilt_10y_yield": [40, 65, 80, 88, 95, 100, 105, 108, 112, 115],
    "gilt_30y_yield": [50, 78, 95, 105, 112, 118, 122, 125, 128, 130],
    "il_gilt_yield": [35, 58, 72, 80, 86, 90, 94, 97, 100, 103],
    "ust_10y_yield": [25, 42, 55, 62, 68, 72, 75, 78, 80, 82],
    "ig_corp_spread": [45, 72, 90, 100, 108, 115, 120, 124, 127, 130],
    "hy_corp_spread": [80, 130, 170, 200, 220, 235, 248, 258, 265, 270],
    "equity": [-3.0, -5.5, -8.0, -10.0, -11.5, -12.5, -13.5, -14.0, -14.5, -15.0],
    "sonia_swap": [30, 50, 65, 75, 82, 88, 92, 95, 98, 100],
    "fx_gbpusd": [-1.5, -2.8, -4.0, -5.0, -5.5, -6.0, -6.3, -6.5, -6.7, -7.0],
    "repo_haircut_gilt": [0.5, 1.2, 2.0, 2.5, 3.0, 3.3, 3.5, 3.7, 3.8, 4.0],
    "repo_haircut_corp": [1.0, 2.5, 4.0, 5.5, 6.5, 7.5, 8.0, 8.5, 9.0, 9.5],
    "bond_futures_basis": [3, 7, 12, 16, 19, 22, 24, 26, 27, 28],
    "vix": [22, 30, 38, 42, 44, 45, 44, 43, 42, 41]
  }
}
```

---

## STEP 3: Create `data/agent_distributions.json`

This defines the **parameter distributions** from which the factory generates heterogeneous agents. Each agent type has size ranges, behavioural parameter ranges, and strategy-specific settings.

```json
{
  "bank": {
    "count": 12,
    "size_distribution": {
      "description": "Total balance sheet in £bn. Mix of large, medium, small.",
      "tiers": [
        {"label": "G-SIB", "count": 3, "total_bs_bn_range": [300, 500], "gilt_mm_appetite_range": [4000, 8000]},
        {"label": "Large domestic", "count": 4, "total_bs_bn_range": [100, 300], "gilt_mm_appetite_range": [1500, 4000]},
        {"label": "Mid-tier / foreign sub", "count": 5, "total_bs_bn_range": [30, 100], "gilt_mm_appetite_range": [300, 1500]}
      ]
    },
    "behavioural_params": {
      "repo_willingness_roll_range": [0.70, 0.95],
      "repo_willingness_new_range": [0.05, 0.35],
      "risk_appetite": {
        "description": "How aggressively the bank warehouses risk. Affects MM capacity and repo generosity.",
        "range": [0.3, 1.0],
        "note": "0.3 = very conservative (tightens early), 1.0 = aggressive (absorbs more)"
      },
      "leverage_ratio_headroom_pct_range": [0.5, 2.5],
      "theta_range": [0.35, 0.45]
    },
    "balance_sheet_composition": {
      "gilt_holdings_pct_of_bs": [0.02, 0.06],
      "corp_bond_pct_of_bs": [0.005, 0.02],
      "repo_lending_pct_of_bs": [0.03, 0.08],
      "derivative_assets_pct_of_bs": [0.01, 0.04],
      "boe_eligible_pct_of_bs": [0.04, 0.10],
      "wholesale_funding_pct_of_bs": [0.05, 0.12],
      "cet1_pct_of_rwa": [0.12, 0.16]
    }
  },

  "hedge_fund": {
    "count": 35,
    "size_distribution": {
      "description": "AUM in £bn.",
      "tiers": [
        {"label": "Large", "count": 5, "aum_bn_range": [10, 25]},
        {"label": "Medium", "count": 15, "aum_bn_range": [2, 10]},
        {"label": "Small", "count": 15, "aum_bn_range": [0.5, 2]}
      ]
    },
    "strategy_distribution": {
      "long_short_equity": 8,
      "macro_rates": 7,
      "relative_value": 6,
      "credit_long_short": 7,
      "multi_strategy": 7
    },
    "strategy_profiles": {
      "long_short_equity": {
        "primary_sensitivities": ["equity"],
        "secondary_sensitivities": ["ig_corp_spread"],
        "gross_leverage_range": [1.5, 3.0],
        "gilt_exposure_pct": [0.0, 0.05],
        "equity_exposure_pct": [0.5, 0.9],
        "corp_bond_exposure_pct": [0.05, 0.2],
        "repo_dependence": "low"
      },
      "macro_rates": {
        "primary_sensitivities": ["gilt_10y_yield", "gilt_30y_yield", "ust_10y_yield", "sonia_swap"],
        "secondary_sensitivities": ["fx_gbpusd"],
        "gross_leverage_range": [3.0, 6.0],
        "gilt_exposure_pct": [0.3, 0.6],
        "equity_exposure_pct": [0.0, 0.1],
        "derivatives_notional_multiple": [3.0, 8.0],
        "repo_dependence": "high"
      },
      "relative_value": {
        "primary_sensitivities": ["bond_futures_basis", "gilt_10y_yield"],
        "secondary_sensitivities": ["sonia_swap"],
        "gross_leverage_range": [5.0, 10.0],
        "gilt_exposure_pct": [0.4, 0.7],
        "basis_trade_pct": [0.3, 0.5],
        "repo_dependence": "very_high",
        "note": "Basis trades are DIRECTLY hit by SWES scenario basis widening. Day 3 narrative: RV HF default."
      },
      "credit_long_short": {
        "primary_sensitivities": ["ig_corp_spread", "hy_corp_spread"],
        "secondary_sensitivities": ["equity"],
        "gross_leverage_range": [2.0, 4.0],
        "corp_bond_exposure_pct": [0.5, 0.8],
        "gilt_exposure_pct": [0.0, 0.1],
        "repo_dependence": "medium"
      },
      "multi_strategy": {
        "primary_sensitivities": ["gilt_10y_yield", "ig_corp_spread", "equity"],
        "secondary_sensitivities": ["fx_gbpusd", "bond_futures_basis"],
        "gross_leverage_range": [3.0, 6.0],
        "gilt_exposure_pct": [0.1, 0.3],
        "equity_exposure_pct": [0.1, 0.3],
        "corp_bond_exposure_pct": [0.1, 0.3],
        "repo_dependence": "high"
      }
    },
    "behavioural_params": {
      "var_utilisation_range": [0.55, 0.90],
      "deleverage_trigger_var_pct": 0.90,
      "volatility_scaling": true,
      "theta_range": [0.20, 0.30]
    }
  },

  "ldi_pension": {
    "count": 10,
    "heterogeneity_dimensions": {
      "leverage_ratio_range": [2.0, 4.0],
      "yield_buffer_bps_range": [180, 350],
      "aum_bn_range": [0.5, 15.0],
      "recapitalisation_speed_days_range": [1, 5],
      "recap_available_pct_of_aum_range": [0.05, 0.20],
      "pooled_vs_segregated": {
        "pooled_pct": 0.40,
        "segregated_pct": 0.60,
        "note": "Pooled = faster recap, pre-agreed waterfall. Segregated = slower, trustee decisions."
      },
      "theta_range": [0.25, 0.35]
    },
    "balance_sheet_composition": {
      "gilt_pct_of_aum": [0.25, 0.45],
      "il_gilt_pct_of_aum": [0.10, 0.25],
      "corp_bond_pct_of_aum": [0.05, 0.15],
      "cash_mmf_pct_of_aum": [0.05, 0.15],
      "derivatives_notional_multiple_of_aum": [2.0, 5.0],
      "unencumbered_collateral_pct_of_aum": [0.10, 0.25]
    }
  },

  "insurer": {
    "count": 6,
    "heterogeneity_dimensions": {
      "total_assets_bn_range": [20, 150],
      "hedge_ratio_range": [0.50, 0.95],
      "dirty_csa_pct_range": [0.0, 0.70],
      "corp_bond_allocation_pct_range": [0.30, 0.60],
      "bpa_exposure_pct_range": [0.0, 0.30],
      "theta_range": [0.40, 0.50]
    },
    "balance_sheet_composition": {
      "gilt_pct": [0.15, 0.35],
      "corp_bond_pct": [0.30, 0.60],
      "equity_pct": [0.05, 0.15],
      "cash_liquid_pct": [0.05, 0.12],
      "derivatives_notional_multiple": [1.5, 4.0],
      "committed_repo_pct": [0.05, 0.15],
      "rcf_pct": [0.02, 0.06]
    }
  },

  "oef_mmf": {
    "count": 7,
    "heterogeneity_dimensions": {
      "total_aum_bn_range": [2, 30],
      "strategy": ["gilt_focused", "credit_focused", "mixed", "mmf_only"],
      "strategy_distribution": {"gilt_focused": 2, "credit_focused": 2, "mixed": 2, "mmf_only": 1},
      "pension_investor_pct_range": [0.20, 0.80],
      "insurer_investor_pct_range": [0.05, 0.30],
      "cash_buffer_pct_range": [0.10, 0.30],
      "theta_range": [0.15, 0.25]
    },
    "strategy_compositions": {
      "gilt_focused": {"gilt_pct": [0.60, 0.80], "corp_pct": [0.05, 0.15], "abs_pct": [0.0, 0.05]},
      "credit_focused": {"gilt_pct": [0.10, 0.20], "corp_pct": [0.50, 0.70], "abs_pct": [0.10, 0.20]},
      "mixed": {"gilt_pct": [0.25, 0.40], "corp_pct": [0.25, 0.40], "abs_pct": [0.05, 0.15]},
      "mmf_only": {"gilt_pct": [0.20, 0.30], "corp_pct": [0.10, 0.20], "abs_pct": [0.0, 0.05], "cash_pct": [0.50, 0.70]}
    }
  }
}
```

---

## STEP 4: Create `network.py`

This is a **new module** — the relationship graph connecting agents bilaterally.

```python
"""
Bilateral relationship network between agents.
Defines who transacts with whom, enabling network-propagated contagion.
"""

import networkx as nx
import numpy as np
from typing import List, Dict, Tuple
from agents.base import BaseAgent
from config import AgentType, NETWORK_RULES


class RelationshipNetwork:
    """
    Bipartite-ish network with banks as hubs.

    Relationships define:
    - Which HFs use which banks as prime brokers / repo counterparties
    - Which LDI funds clear through which banks
    - Which insurers have derivatives/repo relationships with which banks
    - Which OEFs/MMFs are redeemed from by which NBFIs

    When Bank #3 tightens repo, ONLY hedge funds connected to Bank #3 are affected.
    When HF #17 fails, ONLY its 2-3 connected banks take a counterparty hit.
    """

    def __init__(self):
        self.graph = nx.Graph()
        self.bank_hf_edges: List[Tuple[str, str]] = []
        self.bank_ldi_edges: List[Tuple[str, str]] = []
        self.bank_insurer_edges: List[Tuple[str, str]] = []
        self.nbfi_oef_edges: List[Tuple[str, str]] = []  # Who redeems from which OEF

    def build_network(self, agents: List[BaseAgent], seed: int = 42) -> None:
        """
        Build the relationship graph with degree constraints.

        Rules:
        - Each HF connected to 2-3 banks (randomly assigned)
        - Each bank connected to 8-12 HFs (emerges from HF assignments)
        - Each LDI fund connected to 1-2 banks (clearing members)
        - Each insurer connected to 1-3 banks
        - OEFs don't have direct bank relationships but are redeemed FROM by all NBFIs
          (redemption links assigned based on investor base composition)
        """
        rng = np.random.default_rng(seed)

        banks = [a for a in agents if a.agent_type == AgentType.BANK.value]
        hfs = [a for a in agents if a.agent_type == AgentType.HEDGE_FUND.value]
        ldis = [a for a in agents if a.agent_type == AgentType.LDI_PENSION.value]
        insurers = [a for a in agents if a.agent_type == AgentType.INSURER.value]
        oefs = [a for a in agents if a.agent_type == AgentType.OEF_MMF.value]

        # Add all agents as nodes
        for a in agents:
            self.graph.add_node(a.name, agent_type=a.agent_type)

        # ── HF ↔ Bank relationships ──
        # Each HF picks 2-3 banks, weighted by bank size (larger banks more likely)
        bank_sizes = np.array([a.size_factor for a in banks])
        bank_probs = bank_sizes / bank_sizes.sum()

        for hf in hfs:
            n_banks = rng.integers(2, 4)  # 2 or 3
            chosen_banks = rng.choice(banks, size=n_banks, replace=False, p=bank_probs)
            for bank in chosen_banks:
                self.graph.add_edge(hf.name, bank.name, rel_type="prime_brokerage")
                self.bank_hf_edges.append((bank.name, hf.name))

        # ── LDI ↔ Bank relationships ──
        for ldi in ldis:
            n_banks = rng.integers(1, 3)  # 1 or 2
            chosen = rng.choice(banks, size=n_banks, replace=False, p=bank_probs)
            for bank in chosen:
                self.graph.add_edge(ldi.name, bank.name, rel_type="clearing_member")
                self.bank_ldi_edges.append((bank.name, ldi.name))

        # ── Insurer ↔ Bank relationships ──
        for ins in insurers:
            n_banks = rng.integers(1, 4)  # 1 to 3
            chosen = rng.choice(banks, size=min(n_banks, len(banks)), replace=False, p=bank_probs)
            for bank in chosen:
                self.graph.add_edge(ins.name, bank.name, rel_type="derivatives_repo")
                self.bank_insurer_edges.append((bank.name, ins.name))

        # ── NBFI → OEF/MMF redemption relationships ──
        # Each NBFI that holds MMF/OEF positions has redemption links to specific OEFs
        all_nbfis = hfs + ldis + insurers
        for nbfi in all_nbfis:
            # Each NBFI redeems from 1-3 OEFs (weighted by OEF size)
            if oefs:
                oef_sizes = np.array([a.size_factor for a in oefs])
                oef_probs = oef_sizes / oef_sizes.sum()
                n_oefs = rng.integers(1, min(4, len(oefs) + 1))
                chosen = rng.choice(oefs, size=n_oefs, replace=False, p=oef_probs)
                for oef in chosen:
                    self.graph.add_edge(nbfi.name, oef.name, rel_type="redemption")
                    self.nbfi_oef_edges.append((nbfi.name, oef.name))

    def get_connected_hfs(self, bank_name: str) -> List[str]:
        """Get all hedge funds connected to a specific bank."""
        return [hf for bank, hf in self.bank_hf_edges if bank == bank_name]

    def get_connected_banks(self, hf_name: str) -> List[str]:
        """Get all banks connected to a specific hedge fund."""
        return [bank for bank, hf in self.bank_hf_edges if hf == hf_name]

    def get_connected_ldis(self, bank_name: str) -> List[str]:
        """Get all LDI funds clearing through a specific bank."""
        return [ldi for bank, ldi in self.bank_ldi_edges if bank == bank_name]

    def get_clearing_banks(self, ldi_name: str) -> List[str]:
        """Get all banks that an LDI fund clears through."""
        return [bank for bank, ldi in self.bank_ldi_edges if ldi == ldi_name]

    def get_oef_redeemers(self, oef_name: str) -> List[str]:
        """Get all NBFIs that have redemption relationships with an OEF."""
        return [nbfi for nbfi, oef in self.nbfi_oef_edges if oef == oef_name]

    def get_redemption_targets(self, nbfi_name: str) -> List[str]:
        """Get all OEFs that an NBFI can redeem from."""
        return [oef for nbfi, oef in self.nbfi_oef_edges if nbfi == nbfi_name]

    def get_bank_degree(self, bank_name: str) -> Dict[str, int]:
        """Get the number of each type of counterparty for a bank."""
        return {
            "hedge_funds": len(self.get_connected_hfs(bank_name)),
            "ldi_funds": len(self.get_connected_ldis(bank_name)),
            "insurers": len([i for b, i in self.bank_insurer_edges if b == bank_name]),
        }

    def network_summary(self) -> Dict:
        """Summary statistics of the network."""
        return {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "bank_hf_edges": len(self.bank_hf_edges),
            "bank_ldi_edges": len(self.bank_ldi_edges),
            "bank_insurer_edges": len(self.bank_insurer_edges),
            "nbfi_oef_edges": len(self.nbfi_oef_edges),
        }
```

---

## STEP 5: Create `agent_factory.py`

This generates all 60-75 agents from the parameter distributions with controlled randomness.

```python
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
                "recapitalisation_speed_days": 1 if is_pooled else rng.integers(*hd["recapitalisation_speed_days_range"]),
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
```

---

## STEP 6: Create `agents/base.py`

Same as previous version, but add a `size_factor` attribute used by the network for degree-weighted assignment.

```python
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
    def compute_reactions(self, market, network=None) -> Dict[str, float]:
        """Now takes network to route bilateral actions (e.g., which bank to seek repo from)."""
        pass

    def compute_stage2(self, market, network=None) -> None:
        if not self.should_react():
            self.has_reacted = False
            self.reactions = {}
            self.liquidity.B2 = self.liquidity.B1
            return
        self.has_reacted = True
        self.reactions = self.compute_reactions(market, network)
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
            if "repo" in action:
                self.cumulative_repo_demand_mm += amount

    def apply_stage3(self, e2: float) -> None:
        self.liquidity.E2 = e2
        self.liquidity.B3 = self.liquidity.B2 - e2

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
```

---

## STEP 7: Create Agent Subclasses

The agent subclasses (`agents/bank.py`, `agents/ldi_pension.py`, `agents/hedge_fund.py`, `agents/insurer.py`, `agents/oef_mmf.py`) follow the same structure as the previous version but with these critical changes:

### All agents:
- Constructor takes a config dict from the factory (not hardcoded values)
- `size_factor` is set from the config (total BS for banks, AUM for funds)
- All abstract methods now accept `network` parameter

### `agents/bank.py` additions:
- `assess_repo_request(requesting_agent, amount, network)` — checks if the requesting agent is actually connected to this bank via the network. If not connected, returns 0 (no relationship).
- `absorb_selling_pressure()` — uses this bank's specific `gilt_appetite_mm` and `risk_appetite` from config
- `tighten_repo_for_counterparties(network)` — when reacting, reduces `willingness_to_extend_new_pct` for all connected counterparties. The tightening degree depends on the bank's `risk_appetite` parameter.

### `agents/hedge_fund.py` additions:
- Strategy-specific sensitivity maps: a `relative_value` HF has high sensitivity to `bond_futures_basis`, a `long_short_equity` HF has high sensitivity to `equity`, etc.
- Strategy-specific reaction logic: RV funds deleverage by unwinding basis trades (sell gilts, buy futures), macro funds cut rates positions, credit funds sell corporate bonds
- `compute_reactions(market, network)` — when seeking repo, the HF asks ONLY its connected banks (via `network.get_connected_banks(self.name)`). If all connected banks refuse, the HF is forced to sell assets instead (fire sale).

### `agents/ldi_pension.py` additions:
- `yield_buffer_bps` from config determines how quickly margin calls consume the buffer
- `recapitalisation_speed_days` and `is_pooled` affect reaction waterfall speed
- `compute_redemptions()` now routes redemptions through network — redeems from OEFs it's connected to

### `agents/oef_mmf.py` additions:
- `compute_redemptions(market, network, agents)` — computes inflows from redemptions by checking which NBFIs are connected via `network.get_oef_redeemers(self.name)` and how stressed those NBFIs are. Higher NBFI stress → higher redemption demands on this OEF.

---

## STEP 8: Create `engine/simulation.py`

Same time-stepped loop as before, but now passes the network to all agent methods.

```python
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
            agent.compute_stage2(market, network)

        # Register to market
        for agent in agents:
            agent.register_actions_to_market(market)

        # Stage 3 — network-propagated feedback
        if enable_feedback:
            for _ in range(feedback_iterations):
                market.apply_endogenous_feedback()
                compute_stage3_feedback(agents, market, network)
                for agent in agents:
                    if agent.has_reacted:
                        agent.register_actions_to_market(market)
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
    return {
        "total_agents": len(agents),
        "agents_reacted": sum(1 for a in agents if a.has_reacted),
        "total_margin_calls_mm": sum(a.cumulative_margin_calls_mm for a in agents),
        "total_asset_sales_mm": sum(a.cumulative_asset_sales_mm for a in agents),
        "total_repo_demand_mm": sum(a.cumulative_repo_demand_mm for a in agents),
        "final_gilt_yield": market.gilt_10y_yield_chg_bps,
        "final_ig_spread": market.ig_corp_spread_chg_bps,
        "final_repo_avail": market.repo_market_availability_pct,
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
```

---

## STEP 9: Create `engine/feedback.py`

Updated to propagate feedback through the network, not broadcast.

```python
"""Stage 3: Network-propagated second-round feedback."""

import numpy as np
from typing import List
from agents.base import BaseAgent
from network import RelationshipNetwork


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
    2. Market-level (broadcast): selling pressure → price impact → MTM for all
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
                    # Bank has tightened → this HF faces repo/funding stress
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
                    # HF deleveraging → counterparty risk + reduced repo usage
                    hf_stress = hf.liquidity.E1 / max(hf.liquidity.B0, 1)
                    counterparty_impact = hf_stress * target.size_factor * 0.001 * s
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
```

---

## STEP 10: Create `market.py`

Same as previous version. No changes needed — the market state aggregates all agent selling pressure regardless of network topology. The network affects *bilateral* flows; the market affects *everyone*.

(Use the market.py from the previous version of this document verbatim.)

---

## STEP 11: Create `visualisation.py`

All previous charts plus these new ones for the network model:

1. **`plot_network_graph(network, agents)`** — NetworkX visualisation showing the bipartite bank-HF graph. Colour nodes by agent type. Size nodes by `size_factor`. Highlight stressed nodes (has_reacted) in red. Show which bilateral links are under strain.

2. **`plot_agent_distribution(daily_agents)`** — Histogram/violin plot showing the DISTRIBUTION of buffer outcomes across agents of the same type. E.g., "Hedge Fund buffer decline: min -80%, median -35%, max -5%". This distribution IS the insight — it shows that some HFs survive and others blow up, depending on their strategy, leverage, and bank relationships.

3. **`plot_type_amplification(amp_ratios)`** — Grouped bar chart showing amplification ratio by agent TYPE (not individual). Banks vs HFs vs LDI vs Insurers vs OEFs.

4. **`plot_repo_refusal_rate(agents, network)`** — Compute and display: "What % of HFs seeking repo were refused by ALL their connected banks?" — directly comparable to SWES 1 finding of >1/3.

5. **`plot_bank_capacity_heatmap(agents)`** — Heatmap showing each bank's market-making capacity utilisation over the 10 days. Shows which banks exhaust capacity first.

6. All previous charts (market evolution, agent buffers timeseries, waterfall, gauge, margin calls, Sankey) remain.

---

## STEP 12: Create `app.py`

Same Streamlit structure as before but with these additions:

```python
# ── Load and setup ──
from agent_factory import generate_all_agents
from network import RelationshipNetwork

@st.cache_resource
def setup():
    agents = generate_all_agents(seed=42)
    network = RelationshipNetwork()
    network.build_network(agents, seed=42)
    return agents, network

agents, network = setup()

# ── Sidebar additions ──
with st.sidebar:
    # ... existing controls ...
    st.markdown("---")
    st.header("🌐 Network")
    st.write(f"Agents: {len(agents)}")
    ns = network.network_summary()
    st.write(f"Relationships: {ns['total_edges']}")
    st.write(f"Bank↔HF: {ns['bank_hf_edges']}")
    random_seed = st.number_input("Random Seed", value=42, step=1,
                                   help="Change seed to see different network topologies")

# ── New Tab: Network View ──
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Market Evolution",
    "🏦 Agent Buffers",
    "🔄 System Dynamics",
    "🌐 Network View",      # NEW
    "📋 SWES Comparison",
])

with tab4:
    st.header("Relationship Network")
    st.plotly_chart(plot_network_graph(network, agents), use_container_width=True)

    st.subheader("Outcome Distributions by Agent Type")
    st.plotly_chart(plot_agent_distribution(results["daily_agents"]), use_container_width=True)

    st.subheader("Repo Refusal Rate")
    st.plotly_chart(plot_repo_refusal_rate(agents, network), use_container_width=True)

    st.subheader("Bank Capacity Heatmap")
    st.plotly_chart(plot_bank_capacity_heatmap(agents), use_container_width=True)
```

---

## VALIDATION CHECKLIST

1. `streamlit run app.py` starts without errors
2. Agent factory generates 70 agents (12 banks + 35 HFs + 10 LDI + 6 insurers + 7 OEFs)
3. Network has ~70-105 bank-HF edges (35 HFs × 2-3 banks each)
4. Each HF connected to exactly 2-3 banks; each bank connected to 8-12 HFs
5. Market Evolution tab shows 10-day paths that diverge when feedback ON
6. Agent Buffers tab shows heterogeneous outcomes WITHIN agent types (distribution, not single line)
7. System-Wide Feedback toggle visibly changes all charts
8. Amplification ratio: 1.0x when OFF, 1.5-3.0x when ON
9. Repo refusal rate approximately ~30% (comparable to SWES 1 finding of >1/3)
10. Aggregate margin calls in the ballpark of £94bn (order of magnitude, not exact)
11. Bank MM capacity reaches ~70% consumed during scenario
12. Network view clearly shows which bilateral links are under strain
13. Distribution plots show meaningful dispersion (not all HFs same outcome)
14. Full simulation runs in < 3 seconds (70 agents × 10 days × 3 iterations)
15. Changing random seed produces different (but plausible) network topology and outcomes

## ARCHITECTURE NOTES FOR SPRINT 2

Sprint 2 adds:
- New agent types (AAM, CLO vehicle, private credit fund) via new subclasses
- SWES 2 channel pack with slow channel (monthly steps for credit deterioration)
- Sentiment accumulator with configurable thresholds
- Fast-slow channel coupling (defaults trigger repricing, funding freeze blocks refinancing)
- Network extended: AAM↔Bank (lending), AAM↔Pension (LP relationship)
- Market state extended with private market variables (lev loan spreads, PE NAV, CLO OC)

Sprint 1 architecture should require ONLY extension, not refactoring.
