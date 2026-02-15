# Bank B0 Buffer Calibration: Regulatory Framework Mapping

## The Formula

```python
self.liquidity.B0 = boe_val * 0.3 + cet1_val * 0.15 - wf_val * 0.1
```

B0 represents the bank's **actually available liquidity buffer** — not total assets, but what the bank can freely deploy under stress. Each term reflects a realistic availability fraction derived from UK/Basel regulatory constraints.

---

## `boe_val * 0.3` — BoE Facility Eligible (30% available)

**Regulatory context: LCR HQLA and BoE Sterling Monetary Framework**

Under the LCR (Liquidity Coverage Ratio), banks must hold High Quality Liquid Assets (HQLA) to cover 30-day net cash outflows. HQLA is tiered:

- **Level 1** (gilts, central bank reserves): counted at 100% face value, no haircut, no cap
- **Level 2A** (covered bonds, some corporates): 15% haircut, capped at 40% of HQLA
- **Level 2B** (equities, lower-rated corporates): 50% haircut, capped at 15% of HQLA

The "BoE Facility Eligible" item in the model represents the bank's total pool of collateral eligible for the BoE's lending facilities (Indexed Long-Term Repo, Discount Window Facility, Contingent Term Repo Facility). In practice:

- A large chunk of this pool is **already pre-positioned** as Level 1 HQLA for LCR compliance and cannot be freely deployed
- Another portion is **encumbered** — pledged as collateral for derivatives margin, repo transactions, or covered bond programmes
- The BoE's own haircuts on less liquid collateral (e.g., raw loans eligible for DWF) can be 20-40%

**30% represents**: the residual unencumbered, uncommitted fraction after LCR requirements, existing repo collateral commitments, and BoE haircuts. The PRA's PS11/23 guidance on encumbrance suggests UK banks typically have 50-70% of eligible assets encumbered, leaving 30-50% free.

---

## `cet1_val * 0.15` — CET1 Capital Buffer (15% available)

**Regulatory context: Basel III capital stack and PRA buffers**

A UK bank's CET1 requirement is layered:

| Layer | Typical % of RWA |
|-------|-----------------|
| Pillar 1 minimum | 4.5% |
| Pillar 2A (firm-specific) | 1-3% |
| Capital Conservation Buffer | 2.5% |
| Countercyclical Buffer (CCyB) | 0-2% (UK currently 2%) |
| G-SIB / O-SII surcharge | 1-3.5% |
| PRA Buffer (Pillar 2B, confidential) | ~1-2% |
| **Total requirement** | **~12-16%** |

If a bank reports CET1 of, say, 14% of RWA but the combined requirement is 12%, the **free headroom is only 2%** — about 15% of the reported CET1 figure.

Why only 15%:

- Breaching the combined buffer triggers **Maximum Distributable Amount (MDA) restrictions** — the bank can't pay dividends, bonuses, or AT1 coupons
- The PRA buffer (Pillar 2B) is not publicly disclosed but the PRA will intensify supervision if the bank dips into it
- Market confidence evaporates well before the hard minimum — a bank trading near its buffer boundary faces wholesale funding withdrawal (which compounds the problem)

**15% represents**: the fraction of reported CET1 that is genuinely *headroom* above all binding constraints, consistent with most UK banks having 100-200bps of true free capital above all stacked buffers.

---

## `- wf_val * 0.1` — Wholesale Funding Runoff (10% drain)

**Regulatory context: LCR outflow assumptions and PRA SS24/15**

The LCR prescribes outflow rates for different liability types over a 30-day stress window:

| Funding type | LCR runoff rate |
|-------------|----------------|
| Stable retail deposits | 5% |
| Less stable retail | 10% |
| Operational deposits (financial) | 25% |
| Non-operational unsecured wholesale | 40-100% |
| Secured funding (not with central bank) | 0-100% |

The model uses **10% for the first few days** of a 10-day scenario, which maps to:

- ~25% of unsecured wholesale funding at 40% runoff = 10% of total wholesale
- This is conservative (real 10-day runoff could be higher) but recognises that most wholesale funding has contractual maturities beyond 10 days
- The PRA's Internal Liquidity Adequacy Assessment Process (ILAAP) requires banks to model bespoke runoff rates; 10% of total wholesale is a reasonable blended mid-point for the short horizon

**The subtraction matters** because wholesale funding runoff *drains* the liquidity buffer. It's not an asset the bank can deploy — it's a liability that demands cash when it runs.

---

## How It All Fits Together

The formula is a simplified, single-number version of:

> **Net Liquidity Buffer = Deployable HQLA (after encumbrance and haircuts) + Capital Headroom (above all stacked requirements) - Expected Wholesale Runoff**

This mirrors the structure of the LCR itself:

```
LCR = HQLA / Net Cash Outflows >= 100%
```

B0 is the numerator minus a portion of the denominator, giving the **net available buffer**. This ensures that the stress-to-buffer ratio (`E1/B0`) used in the Van den End `should_react()` threshold check produces meaningful reactions — banks with thin genuine headroom react earlier than those with ample free liquidity.

### Floor: `max(..., self.total_bs_mm * 0.002)`

A minimum of 0.2% of total balance sheet prevents B0 from going to zero or negative (which would break the `E1/B0 > theta` division and cause all banks to trivially "react"). This floor represents the absolute minimum operational liquidity a bank maintains.

---

# Bank Sensitivity Maps: MTM Impact Calculation

## The MTM Formula

```python
# agents/bank.py, lines 76-78
for var, sens in item.sensitivity_map.items():
    delta = day_delta.get(var, 0.0)
    impact = item.amount_mm * sens * delta
```

- `item.amount_mm` — position size in millions
- `sens` — sensitivity: the fractional price change per 1 unit move in the market variable
- `delta` — how much the market variable moved **this day** (today's value minus yesterday's)
- `abs(impact)` is taken because we're computing a **loss** (unsigned drain on liquidity)

---

## Item-by-Item Breakdown

### 1. Gilt Holdings

```python
{"gilt_10y_yield": -0.00045, "gilt_30y_yield": -0.00065}
```

For every 1 bps rise in gilt yields, the bank's gilt portfolio loses value.

- **`-0.00045` per bps on 10Y gilts** — This is a modified duration proxy. A 10Y gilt has ~8-9 years modified duration. Price change per 1bps = duration * 0.01% = 8.5 * 0.0001 = 0.00085. The 0.00045 is roughly half of that, reflecting that banks hold a **mix of maturities** (not just 10Y), and some positions may be hedged.
- **`-0.00065` per bps on 30Y gilts** — Higher because 30Y gilts have longer duration (~18-20 years). 0.00065 reflects the bank's longer-dated gilt allocation.
- **Negative sign** — yields up = bond price down = loss.

**Example:** Bank holds 15,000mm in gilts. Day 1 gilt_10y moves +40bps:
`15,000 * (-0.00045) * 40 = -270mm` -> abs = 270mm MTM loss.

### 2. Corporate Bond Holdings

```python
{"ig_corp_spread": -0.0004, "hy_corp_spread": -0.0002}
```

- **`-0.0004` per bps of IG spread widening** — Investment-grade corp bonds have spread duration ~5-7 years. The 0.0004 reflects a blended IG portfolio.
- **`-0.0002` per bps of HY spread widening** — Lower coefficient because banks typically hold less HY, and HY bonds have shorter duration (higher coupon, earlier expected default/call). Also, the HY spread moves are much larger (270bps vs 130bps), so a smaller sensitivity still produces significant losses.
- **Negative** — spreads widen = bond price falls.

### 3. Equity Portfolio

```python
{"equity": 0.01}
```

- **`0.01` per 1% equity market move** — A 1% decline in the equity index produces a 1% loss on the equity portfolio. The `0.01` converts the percentage move (scenario gives equity as `-3.0`, `-5.5`, etc.) into a fraction.
- **Positive sign** because the scenario variable is already negative (equity declines are negative). The formula takes `abs(impact)`, so the sign doesn't matter for the MTM calculation — but conceptually, a negative equity move * positive sensitivity = negative P&L, and `abs()` converts that to a positive loss figure.

### 4. Repo Lending

```python
{}  # Empty sensitivity map
```

**No market sensitivity.** Repo lending is collateralised and marked daily. The bank's repo book doesn't take direct MTM losses from market moves — the collateral haircuts absorb that (captured separately in haircut variables). Repo lending risk is **counterparty/funding** risk, handled in `compute_redemptions()` and stage 3 feedback, not in MTM.

### 5. Derivative Assets

```python
{"gilt_10y_yield": -0.0002, "sonia_swap": -0.0002}
```

- **`-0.0002` per bps on gilt 10Y / SONIA swap** — Lower sensitivity than the gilt portfolio because:
  1. Derivatives are **partially hedged** (many are hedging instruments themselves)
  2. The bank's derivative book has **two-way risk** (some positions gain, some lose), so net sensitivity is lower
  3. The 0.0002 represents the **residual unhedged** delta on the derivative book
- **Both gilt and SONIA** — bank derivative books typically have interest rate swap exposure (SONIA) and government bond futures/options (gilt yield).

### 6. BoE Facility Eligible

```python
{}  # Empty sensitivity map
```

**No MTM sensitivity.** This represents assets *available to be pledged* to the BoE. Their market value changes don't directly impact the bank's liquidity — they're held as a reserve capacity. The value change is already captured in the underlying gilt/bond holdings above. Including sensitivity here would double-count.

### 7. Wholesale Funding

```python
{}  # Empty sensitivity map
```

**No MTM sensitivity.** Liabilities don't have mark-to-market in this model — they represent contractual obligations at par. Wholesale funding risk (runoff) is handled in `compute_redemptions()`, not MTM.

### 8. CET1 Buffer

```python
{}  # Empty sensitivity map
```

**No MTM sensitivity.** Capital is an accounting concept, not a traded position. CET1 is eroded by *losses* (which flow through from the MTM-sensitive items above), but it doesn't have its own market sensitivity.

---

## Summary Table

| Item | Sensitivity Map | Why |
|------|----------------|-----|
| Gilt Holdings | gilt_10y: -0.00045, gilt_30y: -0.00065 | Duration-based MTM loss on rate rises |
| Corp Bonds | ig_spread: -0.0004, hy_spread: -0.0002 | Spread duration loss on credit widening |
| Equity | equity: 0.01 | Direct beta-1 equity exposure |
| Repo Lending | `{}` | Collateralised, no direct MTM |
| Derivative Assets | gilt_10y: -0.0002, sonia: -0.0002 | Residual unhedged rate delta |
| BoE Eligible | `{}` | Reserve capacity, would double-count |
| Wholesale Funding | `{}` | Liability at par, runoff handled separately |
| CET1 Buffer | `{}` | Capital eroded by losses, not a position |

---

# NBFI Classification and Liquidity Response Waterfalls

## Who is NBFI?

In the codebase, **NBFI = everyone except banks**. From `network.py:88`:

```python
all_nbfis = hfs + ldis + insurers
```

And from `test_validation.py:151`, NBFI margin calls are computed by dropping banks:

```python
nbfi = by_type.drop("bank", errors="ignore").sum()
```

**NBFI includes all 4 non-bank agent types:**

| Agent Type | Count | Examples |
|-----------|-------|---------|
| Hedge Funds | 35 | RV, macro, L/S equity, credit, multi-strat |
| LDI / Pension | 10 | Pooled and segregated schemes |
| Insurers | 6 | Life/annuity insurers with varying hedge ratios |
| OEF / MMF | 7 | Gilt-focused, credit-focused, mixed, MMF-only |

OEFs are an edge case — they're NBFI but sit on both sides: they're *sources* of liquidity (other NBFIs redeem from them) and also *victims* of stress (they face redemption pressure and must sell to meet it).

---

## How Do NBFIs Meet Margin Calls Without Selling Assets?

Each NBFI type has a **reaction waterfall** — an ordered list of actions tried before resorting to asset sales. The waterfall is in each agent's `compute_reactions()`.

### Hedge Funds (`agents/hedge_fund.py:144-215`)

| Priority | Action | Key name | Is asset sale? |
|----------|--------|----------|---------------|
| 1 | Seek repo from connected banks | `seek_repo` | No — borrowing secured against existing positions |
| 2 | Strategy-specific asset sales | `sell_gilt`, `sell_corp_bonds`, `sell_equity` | **Yes** |
| 3 | Redeem from MMF/OEF holdings | `redeem_mmf` | No — cashing out existing fund investments |

HFs try **repo first** (line 149). The amount they seek depends on their `repo_dep_mult` (ranges from 0.2 for L/S equity to 1.0 for relative value). Repo is routed through the network — only connected banks are asked. If `market.repo_market_availability_pct` is low (market stress), repo obtained shrinks, and the HF is forced into asset sales at step 2.

### LDI / Pension (`agents/ldi_pension.py:109-163`)

| Priority | Action | Key name | Is asset sale? |
|----------|--------|----------|---------------|
| 1 | Post unencumbered collateral | `post_collateral` | No — pledging existing assets without selling |
| 2 | Pension scheme recapitalisation | `recapitalisation` | No — fresh cash injection from sponsor |
| 3 | Sell gilts | `sell_gilt` | **Yes** |
| 4 | Sell IL gilts | `sell_gilt_il` | **Yes** |
| 5 | Sell corporate bonds | `sell_corp_bonds` | **Yes** |
| 6 | Seek repo | `seek_repo` | No — borrowing |
| 7 | Redeem MMF holdings | `redeem_mmf` | No — cashing out fund investments |

The two key non-sale mechanisms:

- **Post collateral** (line 113): Uses the "Unencumbered Collateral" pool — assets already held that can be pledged to CCPs/counterparties to meet VM/IM calls without being sold. This is the fastest response.
- **Recapitalisation** (line 120): The pension scheme sponsor injects fresh cash. Speed depends on `recap_speed_days` — pooled funds get Day 1 recap via pre-agreed waterfall, segregated funds take 1-5 days (trustee decision needed). This maps directly to the SWES 1 finding of 16.5bn in LDI recapitalisation.

### Insurers (`agents/insurer.py:100-153`)

| Priority | Action | Key name | Is asset sale? |
|----------|--------|----------|---------------|
| 1 | Draw committed repo lines | `draw_repo_line` | No — pre-arranged borrowing facility |
| 2 | Draw revolving credit facility | `draw_rcf` | No — pre-arranged bank credit line |
| 3 | Sell gilts | `sell_gilt` | **Yes** |
| 4 | Sell corporate bonds | `sell_corp_bonds` | **Yes** |
| 5 | Sell equity | `sell_equity` | **Yes** |
| 6 | Seek repo from banks | `seek_repo` | No — borrowing |
| 7 | Redeem MMF | `redeem_mmf` | No — cashing out |

Insurers have **two dedicated pre-arranged facilities** before any asset sales:

- **Committed repo lines** (line 104): Pre-negotiated with banks, so the bank is contractually obligated to lend (unlike discretionary repo for HFs). These are drawn at 50% of available capacity.
- **RCF** (line 112): Revolving credit facilities — unsecured bank credit lines. These exist precisely for this purpose.

### OEF / MMF (`agents/oef_mmf.py:117-149`)

| Priority | Action | Key name | Is asset sale? |
|----------|--------|----------|---------------|
| 1 | Use cash buffer | `use_cash_buffer` | No — spending existing cash reserves |
| 2 | Sell gilts | `sell_gilt` | **Yes** |
| 3 | Sell corporate bonds | `sell_corp_bonds` | **Yes** |
| 4 | Swing pricing / gates | `swing_pricing` | No — reducing outflows rather than sourcing inflows |

OEFs have the **fewest non-sale options** — essentially just their cash buffer. If redemptions exceed the cash buffer, they're forced sellers. At extreme stress (>15% of AUM redeemed), they apply swing pricing or gates to slow outflows.

---

## How Stage 2 Treats Sale vs Non-Sale Actions

In `base.py:100-118`, the mitigation effectiveness differs by action type:

```python
if action.startswith("sell_"):     # realisation rate (50-100%, degrades with bid-ask spread)
elif "repo" in action:             # market.repo_market_availability_pct (degrades under stress)
elif "boe" in action:              # 95% (near-certain, central bank backstop)
elif "redeem" in action:           # 90% (slight haircut for redemption timing)
else:                              # 80% (collateral posting, recap, RCF, etc.)
```

**Non-sale actions degrade less under stress.** BoE facilities are 95% reliable even in crisis. Collateral posting and recapitalisation are 80%. But asset sales can drop to 50% realisation when bid-ask spreads blow out, and repo availability can drop to 20-30%. This is why the waterfall ordering matters — agents exhaust reliable sources first, then resort to increasingly costly market-dependent actions.
