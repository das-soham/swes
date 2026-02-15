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
