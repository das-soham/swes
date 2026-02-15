"""Diagnostic: inspect B0, B1, B2, B3 values per agent type per day."""

import pandas as pd
from agent_factory import generate_all_agents
from network import RelationshipNetwork
from engine.simulation import run_simulation


def main():
    agents = generate_all_agents()
    network = RelationshipNetwork()
    network.build_network(agents)
    results = run_simulation(agents, network)

    df = pd.DataFrame(results["daily_agents"])

    for atype in ["bank"]:
        print(f"\n{'='*60}")
        print(f"  {atype.upper()}")
        print(f"{'='*60}")
        adf = df[df["agent_type"] == atype]

        for day in sorted(adf["day"].unique()):
            ddf = adf[adf["day"] == day]
            print(f"\n  Day {day+1}:")
            print(f"    B0   mean={ddf['B0'].mean():>10.1f}  min={ddf['B0'].min():>10.1f}  max={ddf['B0'].max():>10.1f}")
            print(f"    B1   mean={ddf['B1'].mean():>10.1f}  min={ddf['B1'].min():>10.1f}  max={ddf['B1'].max():>10.1f}")
            print(f"    B2   mean={ddf['B2'].mean():>10.1f}  min={ddf['B2'].min():>10.1f}  max={ddf['B2'].max():>10.1f}")
            print(f"    B3   mean={ddf['B3'].mean():>10.1f}  min={ddf['B3'].min():>10.1f}  max={ddf['B3'].max():>10.1f}")
            print(f"    E1   mean={ddf['E1'].mean():>10.1f}  min={ddf['E1'].min():>10.1f}  max={ddf['E1'].max():>10.1f}")
            b3_b0 = ddf["B3"] / ddf["B0"].replace(0, float("nan"))
            print(f"    B3/B0 mean={b3_b0.mean():>8.3f}  min={b3_b0.min():>8.3f}  max={b3_b0.max():>8.3f}")
            print(f"    reacted: {ddf['has_reacted'].sum()} / {len(ddf)}")


if __name__ == "__main__":
    main()
