# SWES Private Markets Stress Lens

A heterogeneous multi-agent network model for simulating the Bank of England's System-Wide Exploratory Scenario (SWES 1). The model implements the Van den End (2012) three-stage liquidity stress test framework across 70 interconnected financial agents, with bilateral network-propagated contagion and endogenous market feedback.

## Overview

The model simulates a 10 business-day stress scenario (the "Fast Channel") across five types of UK financial market participants:

| Agent Type | Count | Description |
|---|---|---|
| Banks | 12 | Dealer banks acting as repo providers, market makers, and liquidity hubs |
| Hedge Funds | 35 | Five strategy types: macro rates, relative value, credit L/S, equity L/S, multi-strategy |
| LDI / Pension | 10 | Liability-driven investment funds with leveraged gilt/swap positions |
| Insurers | 6 | Life/general insurers with derivative hedges and dirty CSA mechanics |
| OEF / MMF | 7 | Open-ended funds / money market funds facing redemption pressure |

Agents are connected via a bilateral relationship network where banks act as hubs. Stress propagates through both network-routed channels (repo tightening, counterparty risk) and broadcast channels (selling pressure into market prices).

## Van den End Three-Stage Framework

Each simulation day follows the Van den End (2012) liquidity stress test:

```
Stage 1: Exogenous Shock
  B0 (initial buffer) - E1 (shock: MTM + margin calls + redemptions) = B1 (post-shock buffer)

Stage 2: Behavioural Reactions
  If E1/B0 > effective_theta: agent reacts (seek repo, sell assets, draw facilities)
  effective_theta = theta * (1 + buffer_usability)   [Farmer et al. 2020]
  B1 + reactions = B2 (post-reaction buffer)

Stage 3: Systemic Feedback (N iterations per day)
  B2 - E2 (feedback: counterparty losses, market impact, crowding) = B3 (final buffer)
```

**Key metric:** Amplification Ratio = (B0 - B3) / (B0 - B1) measures how much second-round effects amplify the initial shock.

## Project Structure

```
swes/
+-- app.py                    # Streamlit dashboard entry point
+-- config.py                 # All centralised hyperparameters
+-- market.py                 # MarketState: exogenous scenario + endogenous feedback
+-- network.py                # Bilateral relationship network (NetworkX)
+-- agent_factory.py          # Factory: generates 70 agents from distributions
+-- visualisation.py          # Plotly charts for the dashboard
+-- agents/
|   +-- base.py               # BaseAgent ABC with Van den End mechanics
|   +-- bank.py               # BankAgent: repo provider, market maker
|   +-- hedge_fund.py         # HedgeFundAgent: 5 strategy subtypes
|   +-- ldi_pension.py        # LDIPensionAgent: leveraged gilt/swap
|   +-- insurer.py            # InsurerAgent: hedge ratio, dirty CSA
|   +-- oef_mmf.py            # OEFMMFAgent: redemption-driven
+-- engine/
|   +-- simulation.py         # Main 10-day simulation loop
|   +-- feedback.py           # Stage 3: bilateral + market-level feedback
+-- data/
|   +-- scenario_swes1.json   # SWES 1 market variable paths (10 days)
|   +-- agent_distributions.json  # Agent population parameters
+-- tests/
|   +-- calibrate_check.py    # Quick calibration validation script
|   +-- diag_buffers.py       # Buffer diagnostic (B0/B1/B2/B3 per type per day)
|   +-- test_validation.py    # Unit tests
```

## Quickstart

### Prerequisites

- Python 3.10+
- pip

### Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run the Dashboard

```bash
streamlit run app.py
```

### Run Calibration Check

```bash
python tests/calibrate_check.py
```

### Run Buffer Diagnostics

```bash
python tests/diag_buffers.py
```

## Configuration

All hyperparameters are centralised in `config.py`.

### `REACTION_PARAMS`

Controls asset sale caps per agent type. Each entry is a tuple `(shortfall_alloc_pct, holding_cap_pct)`:
- **shortfall_alloc_pct**: fraction of the shortfall allocated to this sale action
- **holding_cap_pct**: maximum fraction of the holding that can be sold per day

The actual sale amount is `min(shortfall * shortfall_alloc_pct, holding * holding_cap_pct)`.

### `BUFFER_PARAMS`

Initial liquidity buffer (B0) multipliers per agent type. B0 is computed as a weighted sum of eligible balance sheet items, floored at a fraction of total size.

### `BUFFER_USABILITY`

Buffer usability parameter ranges per agent type (Farmer et al. 2020). Controls the effective reaction threshold:

- `u = 0.0`: buffers treated as hard floor (procyclical — reacts immediately)
- `u = 1.0`: buffers fully usable (absorbs losses down to regulatory minimum)
- `effective_theta = theta * (1 + u)`

Higher buffer usability means agents tolerate more stress before reacting, reducing systemic amplification. The BoE's SWES explicitly investigated willingness to use buffers as a key driver of system-wide outcomes.

### `FEEDBACK_PARAMS`

Stage 3 feedback coefficients:
- `bank_counterparty_loss_coeff`: scales bilateral counterparty impact on banks from stressed hedge funds
- `bank_repo_refusal_stress_threshold`: E1/B0 ratio at which a bank's repo willingness drops to zero (linear decay)

### `agent_distributions.json`

Defines the population characteristics: AUM ranges, strategy distributions, leverage ranges, balance sheet compositions, sensitivity profiles, and behavioural parameters (theta, buffer usability, risk appetite, repo dependence).

### `scenario_swes1.json`

The 10-day market variable paths for the SWES 1 scenario, including gilt yields, credit spreads, equity, FX, repo haircuts, basis, and VIX.

## Agent Reaction Waterfalls

Each agent type follows a priority-ordered waterfall when reacting to stress:

**Banks:** BoE facilities > Reduce repo lending > Sell gilts > Sell corporate bonds

**Hedge Funds:** Seek repo from connected banks > Strategy-specific asset sales > Redeem from MMFs/OEFs

**LDI / Pension:** Post additional collateral > Sponsor recapitalisation > Seek repo > Sell gilts > Sell IL gilts > Sell corporate bonds > Redeem from MMFs

**Insurers:** Draw committed repo lines > Draw RCF > Seek repo > Sell gilts > Sell corporate bonds > Sell equity > Redeem from MMFs

**OEF / MMF:** Use cash buffer > Sell gilts > Sell corporate bonds > Swing pricing/gates

Repo is prioritised before asset sales for all NBFI agent types. Banks assess each repo request based on their own stress level and willingness parameters.

## Network Topology

- Each hedge fund is connected to 2-3 banks (prime brokerage)
- Each LDI fund clears through 1-2 banks
- Each insurer has 1-3 bank relationships
- All NBFIs have 1-3 redemption links to OEFs/MMFs
- Bank selection is weighted by bank size (larger banks attract more counterparties)

## Feedback Mechanisms

Stage 3 feedback operates on two layers:

1. **Bilateral (network-routed):** Bank repo tightening affects only connected HFs. HF deleveraging creates counterparty risk only for connected banks. NBFI stress triggers redemptions only from connected OEFs.

2. **Market-level (broadcast):** Aggregate selling pressure feeds back into gilt yields, credit spreads, and repo availability. All agents with exposure are affected.

Additional feedback channels: reputation risk (Van den End eq. 7) and crowding penalties when many agents of the same type react with the same instruments.

## Bank Market-Making Capacity

Dealer banks absorb NBFI selling pressure through their market-making function. Capacity is tracked separately for gilt and corporate bond markets:

- After all agents register their daily selling actions, banks absorb proportionally to their remaining capacity
- Each bank's share = `remaining_capacity / total_remaining_across_all_banks`
- Absorption is capped by `remaining * risk_appetite` (willingness constraint)
- Capacity is cumulative — once consumed, it does not replenish during the scenario
- The dashboard includes heatmaps for gilt-only and combined (gilt + corp) capacity utilisation

Capacity ranges are calibrated as daily flow capacity (not total inventory), consistent with the SWES 1 finding of ~70% dealer capacity consumed.

## Calibration Targets (SWES 1)

| Metric | SWES 1 Published | Description |
|---|---|---|
| Total NBFI margin calls | ~94bn | Sum of VM + IM across all NBFIs |
| NBFI gilt sales | ~4.7bn | Net gilt disposals by non-bank agents |
| Repo refusal rate | ~33% | Fraction of HFs refused by all connected banks |
| LDI recapitalisation | ~16.5bn | Sponsor capital calls by LDI funds |
| Bank gilt capacity consumed | ~70% | Fraction of dealer market-making capacity used |

## Dashboard Tabs

1. **Market Evolution** - 10-day paths for all market variables + scenario narrative
2. **Agent Buffers** - Liquidity buffer trajectories (B3/B0) with min/max bands, waterfall chart, amplification gauge, time series, and day-filterable bar chart
3. **System Dynamics** - Margin calls by agent type, stress flow Sankey diagram
4. **Network View** - Relationship network graph, outcome distributions, repo refusal rate, bank capacity heatmaps (gilt-only and combined gilt + corp)
5. **SWES Comparison** - Model output vs SWES 1 published findings, calibration anchors

### Sidebar Controls

- **Feedback toggle and iterations** - Enable/disable Stage 3 feedback and control iteration depth
- **Buffer Usability slider** - Override bank buffer usability (Farmer et al. 2020) to demonstrate the impact of buffer willingness on systemic amplification
- **Random seed** - Change network topology and agent parameter draws

## Key Design Decisions

- **Centralised configuration:** All tunable parameters live in `config.py` or `agent_distributions.json`. No magic numbers in agent code.
- **Network-aware reactions:** NBFI repo requests are routed to connected banks via `assess_repo_request()`, not drawn from a global pool.
- **Stress-based repo refusal:** Banks' willingness to extend repo decays linearly with their own stress ratio (E1/B0), reaching zero at a configurable threshold.
- **Buffer usability:** Farmer et al. (2020) parameter modulates the Van den End reaction threshold — agents with higher buffer usability tolerate more stress before reacting, reducing procyclical behaviour.
- **Two-pass market registration:** All agents register selling pressure first, then banks absorb proportionally to remaining capacity. This ensures banks see the full daily selling total regardless of agent ordering.
- **Cumulative tracking:** Gilt sales, margin calls, repo demand, refusal flags, and bank MM capacity consumption accumulate across all 10 days.
- **Feedback accumulation:** Stage 3 E2 accumulates across feedback iterations within a day (`+=` not `=`), making the feedback iterations slider meaningful.

## References

- Van den End, J.W. (2012). "Liquidity Stress-Tester: Do Basel III and Unconventional Monetary Policy Work?" *Applied Financial Economics*, 22(15), 1233-1257.
- Farmer, J.D. et al. (2020). "Foundations of system-wide financial stress testing with heterogeneous institutions." *Bank of England Staff Working Paper No. 861.*
- Bank of England (2024). System-Wide Exploratory Scenario: Final Report.

## License

This project is provided for educational and research purposes only. It is not intended for use in production risk management or regulatory compliance. The model outputs are illustrative and should not be interpreted as financial advice.

Copyright (c) 2025 Soham Das. All rights reserved.

## Author

Soham Das, CFA
