"""An organism's family in a live run: ancestors back to its founder, descendants below (D-055).

Every organism records its parent (``parent_id``), so the family is a tree. Ancestors are a
simple walk up. Descendants can number thousands (a founder whose family took over the world),
so the tree is cut to ``depth`` generations and ``breadth`` children per organism, each cut
saying how many it hides; ``descendants`` counts the whole family below the organism. Built
from the simulation's own lists on request; nothing is stored.
"""

from __future__ import annotations

from collections import defaultdict

from genesis.core.organism import Organism
from genesis.core.simulation import Simulation


def _node(org: Organism) -> dict:
    return {
        "id": org.id,
        "generation": org.generation,
        "birth_tick": org.birth_tick,
        "death_tick": org.death_tick,
        "alive": org.alive,
        "offspring_count": org.offspring_count,
    }


def lineage(sim: Simulation, organism_id: int, depth: int = 3, breadth: int = 12) -> dict:
    # Sorted by ID, which is birth order: the living list comes first and the dead list second,
    # so without sorting, living children would be listed before older, dead siblings.
    everyone = {o.id: o for o in sorted((*sim.organisms, *sim.dead), key=lambda o: o.id)}
    if organism_id not in everyone:
        raise KeyError(f"no organism {organism_id} in this run (yet)")
    children: dict[int, list[int]] = defaultdict(list)
    for org in everyone.values():  # ID order, so each list of children is in birth order
        if org.parent_id is not None:
            children[org.parent_id].append(org.id)

    ancestors = []
    current = everyone[organism_id]
    while current.parent_id is not None:
        current = everyone[current.parent_id]
        ancestors.append(_node(current))
    ancestors.reverse()  # founder first

    def tree(oid: int, level: int) -> dict:
        node = _node(everyone[oid])
        kids = children[oid]
        node["children"] = [tree(k, level + 1) for k in kids[:breadth]] if level < depth else []
        node["hidden_children"] = len(kids) - len(node["children"])
        return node

    founder = everyone[organism_id] if not ancestors else everyone[ancestors[0]["id"]]
    family = [founder.id, *_all_below(founder.id, children)]
    return {
        "organism": tree(organism_id, 0),
        "ancestors": ancestors,
        "descendants": sum(1 for _ in _all_below(organism_id, children)),
        "founder_id": founder.id,
        "founder_family": len(family),
        "founder_family_alive": sum(1 for oid in family if everyone[oid].alive),
    }


def _all_below(oid: int, children: dict[int, list[int]]):
    stack = list(children[oid])
    while stack:
        current = stack.pop()
        yield current
        stack.extend(children[current])
