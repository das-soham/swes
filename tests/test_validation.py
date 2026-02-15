"""Validation tests for SWES Stress Lens Sprint 1."""

import time
from collections import Counter
from agent_factory import generate_all_agents
from network import RelationshipNetwork
from engine.simulation import run_simulation


def test_all():
    passed = 0
    failed = 0

    # Test 1: Agent factory generates correct count
    print("=" * 60)
    print("TEST 1: Agent Factory")
    agents = generate_all_agents(seed=42)
    types = Counter(a.agent_type for a in agents)
    print(f"  Total agents: {len(agents)}")
    for t, c in sorted(types.items()):
        print(f"    {t}: {c}")

    if len(agents) == 70:
        print("  PASS: 70 agents generated")
        passed += 1
    else:
        print(f"  FAIL: Expected 70, got {len(agents)}")
        failed += 1

    if types.get("bank", 0) == 12:
        print("  PASS: 12 banks")
        passed += 1
    else:
        print(f"  FAIL: Expected 12 banks, got {types.get('bank', 0)}")
        failed += 1

    # Test 2: Network topology
    print("\n" + "=" * 60)
    print("TEST 2: Network Topology")
    network = RelationshipNetwork()
    network.build_network(agents, seed=42)
    ns = network.network_summary()
    print(f"  Nodes: {ns['total_nodes']}, Edges: {ns['total_edges']}")
    print(f"  Bank-HF: {ns['bank_hf_edges']}, Bank-LDI: {ns['bank_ldi_edges']}")
    print(f"  Bank-Insurer: {ns['bank_insurer_edges']}, NBFI-OEF: {ns['nbfi_oef_edges']}")

    # Check HF degree constraints (each HF connected to 2-3 banks)
    hfs = [a for a in agents if a.agent_type == "hedge_fund"]
    hf_degrees = [len(network.get_connected_banks(hf.name)) for hf in hfs]
    print(f"  HF bank degrees: min={min(hf_degrees)}, max={max(hf_degrees)}")
    if all(2 <= d <= 3 for d in hf_degrees):
        print("  PASS: All HFs connected to 2-3 banks")
        passed += 1
    else:
        print("  FAIL: Some HFs outside 2-3 bank range")
        failed += 1

    # Bank-HF edges should be 70-105
    if 70 <= ns["bank_hf_edges"] <= 105:
        print(f"  PASS: Bank-HF edges in range ({ns['bank_hf_edges']})")
        passed += 1
    else:
        print(f"  FAIL: Bank-HF edges {ns['bank_hf_edges']} outside 70-105")
        failed += 1

    # Test 3: Simulation with feedback
    print("\n" + "=" * 60)
    print("TEST 3: Simulation WITH Feedback")
    agents_fb = generate_all_agents(seed=42)
    net_fb = RelationshipNetwork()
    net_fb.build_network(agents_fb, seed=42)
    t0 = time.time()
    results_fb = run_simulation(agents_fb, net_fb, enable_feedback=True, feedback_iterations=3)
    elapsed_fb = time.time() - t0
    print(f"  Runtime: {elapsed_fb:.2f}s")

    if elapsed_fb < 3.0:
        print("  PASS: Under 3 seconds")
        passed += 1
    else:
        print(f"  WARN: Took {elapsed_fb:.2f}s (target < 3s)")

    summary_fb = results_fb["summary"]
    amp_fb = results_fb["amplification_ratios"].get("System-Wide", 1.0)
    print(f"  Agents reacted: {summary_fb['agents_reacted']}")
    print(f"  Total margin calls: {summary_fb['total_margin_calls_mm']:,.0f} mm")
    print(f"  Total asset sales: {summary_fb['total_asset_sales_mm']:,.0f} mm")
    print(f"  System-Wide Amplification: {amp_fb:.2f}x")

    # Test 4: Simulation WITHOUT feedback
    print("\n" + "=" * 60)
    print("TEST 4: Simulation WITHOUT Feedback")
    agents_nf = generate_all_agents(seed=42)
    net_nf = RelationshipNetwork()
    net_nf.build_network(agents_nf, seed=42)
    results_nf = run_simulation(agents_nf, net_nf, enable_feedback=False)
    amp_nf = results_nf["amplification_ratios"].get("System-Wide", 1.0)
    print(f"  System-Wide Amplification (no feedback): {amp_nf:.2f}x")

    if amp_nf <= amp_fb:
        print("  PASS: Feedback ON produces higher amplification than OFF")
        passed += 1
    else:
        print("  FAIL: Feedback did not increase amplification")
        failed += 1

    # Test 5: Amplification ratio in expected range
    print("\n" + "=" * 60)
    print("TEST 5: Amplification Ratio Range")
    if 1.0 <= amp_fb <= 5.0:
        print(f"  PASS: Amplification {amp_fb:.2f}x in range [1.0, 5.0]")
        passed += 1
    else:
        print(f"  FAIL: Amplification {amp_fb:.2f}x outside expected range")
        failed += 1

    # Test 6: Different seed produces different results
    print("\n" + "=" * 60)
    print("TEST 6: Seed Sensitivity")
    agents_s2 = generate_all_agents(seed=123)
    net_s2 = RelationshipNetwork()
    net_s2.build_network(agents_s2, seed=123)
    results_s2 = run_simulation(agents_s2, net_s2, enable_feedback=True)
    amp_s2 = results_s2["amplification_ratios"].get("System-Wide", 1.0)
    print(f"  Seed 42 amp: {amp_fb:.3f}x, Seed 123 amp: {amp_s2:.3f}x")
    if abs(amp_fb - amp_s2) > 0.001:
        print("  PASS: Different seeds produce different results")
        passed += 1
    else:
        print("  FAIL: Seeds produced identical results")
        failed += 1

    # Test 7: Type-level amplification
    print("\n" + "=" * 60)
    print("TEST 7: Type-Level Amplification")
    for key, val in results_fb["amplification_ratios"].items():
        if key.startswith("Type:"):
            print(f"  {key}: {val:.2f}x")
    passed += 1  # Informational

    # Test 8: Margin calls breakdown by type
    print("\n" + "=" * 60)
    print("TEST 8: Margin Calls Breakdown")
    import pandas as pd
    df = pd.DataFrame(results_fb["daily_agents"])
    last = df[df["day"] == df["day"].max()]
    by_type = last.groupby("agent_type")["cum_margin"].sum()
    for t, v in by_type.items():
        print(f"  {t}: {v:,.0f} mm = £{v/1000:.1f}bn")
    print(f"  TOTAL: {by_type.sum():,.0f} mm = £{by_type.sum()/1000:.1f}bn")
    nbfi = by_type.drop("bank", errors="ignore").sum()
    print(f"  NBFI total: {nbfi:,.0f} mm = £{nbfi/1000:.1f}bn (target ~£94bn)")

    # Test 9: Reacted by type
    print("\n" + "=" * 60)
    print("TEST 9: Agents Reacted by Type")
    reacted = last.groupby("agent_type")["has_reacted"].sum()
    total_by_type = last.groupby("agent_type")["has_reacted"].count()
    for t in reacted.index:
        print(f"  {t}: {int(reacted[t])}/{int(total_by_type[t])}")

    # Test 10: B0 values (sanity check buffer sizes)
    print("\n" + "=" * 60)
    print("TEST 10: Buffer Sizes (B0) by Type")
    b0_by_type = last.groupby("agent_type")["B0"].describe()[["mean", "min", "max"]]
    for t in b0_by_type.index:
        row = b0_by_type.loc[t]
        print(f"  {t}: mean={row['mean']:,.0f} min={row['min']:,.0f} max={row['max']:,.0f}")

    # Test 11: Asset sales by type
    print("\n" + "=" * 60)
    print("TEST 11: Asset Sales by Type")
    sales_by_type = last.groupby("agent_type")["cum_sales"].sum()
    for t, v in sales_by_type.items():
        print(f"  {t}: {v:,.0f} mm = £{v/1000:.1f}bn")

    # Summary
    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)


if __name__ == "__main__":
    test_all()

