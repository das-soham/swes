
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

# Buffer usability parameter (Farmer et al. 2020)
# u = 0%: buffers treated as hard floor (procyclical — reacts immediately)
# u = 100%: buffers fully usable (absorbs losses down to regulatory minimum)
# Key SWES insight: BoE explicitly asks about willingness to use buffers.
# Post-2022 FPC guidance pushed for greater buffer usability.
BUFFER_USABILITY = {
    "bank_u_range": (0.30, 0.70),
    "ldi_pension_u_range": (0.20, 0.50),
    "hedge_fund_u_range": (0.10, 0.30),
    "insurer_u_range": (0.40, 0.70),
    "oef_mmf_u_range": (0.10, 0.20),
}

# Reaction parameters: repo ask fractions and asset sale caps per agent type.
# Each sale entry is (shortfall_alloc_pct, holding_cap_pct).
REACTION_PARAMS = {
    "bank": {
        "repo_ask_pct": None,
        "sell_gilt": (0.10, 0.20),
        "sell_corp": (0.08, 0.02),
    },
    "ldi_pension": {
        "repo_ask_pct": 0.85,
        "sell_gilt": (0.15, 0.15),
        "sell_il_gilt": (0.08, 0.02),
        "sell_corp": (0.05, 0.015),
    },
    "hedge_fund": {
        "repo_ask_pct": 0.85,
        "sell_gilt": (0.10, 0.10),
        "sell_corp": (0.10, 0.025),
        "sell_equity": (0.10, 0.025),
        "sell_basis_unwind": (0.10, 0.04),
        "multi_strategy": (0.05, 0.03),
    },
    "insurer": {
        "repo_ask_pct": 0.80,
        "sell_gilt": (0.15, 0.10),
        "sell_corp": (0.08, 0.02),
        "sell_equity": (0.05, 0.025),
    },
    "oef_mmf": {
        "repo_ask_pct": None,
        "sell_gilt": (0.10, 0.20),
        "sell_corp": (0.08, 0.02),
    },
}

# Initial liquidity buffer (B0) multipliers per agent type.
# B0 = weighted sum of eligible items, floored at a fraction of total size.
BUFFER_PARAMS = {
    "bank": {
        "boe_eligible_mult": 0.15,           # was 0.3
        "cet1_mult": 0.08,                   # was 0.15
        "wholesale_funding_runoff_mult": 0.10,
        "floor_pct_of_bs": 0.002,
    },
    "ldi_pension": {
        "cash_mult": 1.0,
        "unencumbered_collateral_mult": 0.3,
        "floor_pct_of_aum": 0.005,
    },
    "hedge_fund": {
        "cash_mult": 1.0,
        "floor_pct_of_aum": 0.005,
    },
    "insurer": {
        "cash_mult": 0.5,
        "committed_repo_mult": 0.2,
        "rcf_mult": 0.2,
        "floor_pct_of_assets": 0.002,
    },
    "oef_mmf": {
        "cash_mult": 0.5,
        "floor_pct_of_aum": 0.01,
    },
}

SIMULATION_DAYS = 10
FEEDBACK_ITERATIONS_PER_DAY = 3

# Stage 3 feedback coefficients
FEEDBACK_PARAMS = {
    # Bank counterparty loss from a stressed HF, scaled by bilateral repo exposure.
    # Impact = hf_stress * bilateral_exposure * coeff * vix_stress_factor
    "bank_counterparty_loss_coeff": 0.005,

    # Bank repo refusal: when a bank's stress ratio (E1/B0) reaches this threshold,
    # willingness to extend new repo drops to 0 (full refusal).
    # Linear decay from full willingness at stress=0 to zero at stress=threshold.
    # Lower value → banks refuse earlier → higher refusal rate.
    "bank_repo_refusal_stress_threshold": 0.266353,
}

# SWES 1 calibration anchors
SWES1_ANCHORS = {
    "total_nbfi_margin_calls_bn": 94.0,
    "ldi_recapitalisation_bn": 16.5,
    "nbfi_gilt_sales_bn": 4.7,
    "bank_gilt_capacity_consumed_pct": 0.70,
    "additional_long_gilt_exhaust_bn": 0.5,
    "nbfi_repo_refusal_pct": 0.33,
}
