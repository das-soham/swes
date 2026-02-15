"""Quick calibration check — run after fixes to verify asset sales vs SWES 1."""

from agent_factory import generate_all_agents
from network import RelationshipNetwork
from engine.simulation import run_simulation


def main():
    agents = generate_all_agents()
    network = RelationshipNetwork()
    network.build_network(agents)
    results = run_simulation(agents, network)

    s = results["summary"]
    print("=== Post-fix calibration check ===")
    print(f"Total margin calls:  {s['total_margin_calls_mm']:>10.0f} mm")
    print(f"Total asset sales:   {s['total_asset_sales_mm']:>10.0f} mm")
    print(f"NBFI gilt sales:     {s['nbfi_gilt_sales_mm']:>10.0f} mm")
    print(f"Total repo demand:   {s['total_repo_demand_mm']:>10.0f} mm")
    print(f"Final repo avail:    {s['final_repo_avail']:>10.2%}")
    print(f"Agents reacted:      {s['agents_reacted']:>5} / {s['total_agents']}")

    # Gilt sales by agent type
    from collections import defaultdict
    gilt_by_type = defaultdict(float)
    for a in agents:
        gilt_by_type[a.agent_type] += a.cumulative_gilt_sales_mm
    print()
    print("Gilt sales by agent type:")
    for atype in sorted(gilt_by_type):
        print(f"  {atype:<15} {gilt_by_type[atype]:>10.0f} mm")
    print(f"  {'TOTAL':<15} {sum(gilt_by_type.values()):>10.0f} mm")
    print()

    # Repo refusal rate
    hfs = [a for a in agents if a.agent_type == "hedge_fund"]
    hfs_seeking = [h for h in hfs if getattr(h, "has_ever_sought_repo", False)]
    hfs_refused = [h for h in hfs if getattr(h, "repo_refused_by_all", False)]
    total_seeking = len(hfs_seeking)
    refused = len(hfs_refused)
    rate = refused / max(total_seeking, 1)
    print(f"HFs seeking repo:    {total_seeking:>5}")
    print(f"HFs refused by all:  {refused:>5}")
    print(f"Repo refusal rate:   {rate:>10.1%}")
    print()
    print("SWES 1 targets:")
    print(f"  Margin calls:      ~94,000 mm")
    print(f"  NBFI gilt sales:    ~4,700 mm")
    print(f"  Repo refusal rate:     ~33%")


if __name__ == "__main__":
    main()
