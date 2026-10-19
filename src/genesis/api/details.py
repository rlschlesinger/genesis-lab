"""One organism in detail: identity, family, genome, body, and (with a brain) its latest
decision exactly as the simulation computed it (D-050).

The simulation keeps the latest tick's decision record (``Simulation.last_decision``): one
row per organism that decided, in ID order, but without the IDs themselves. They follow
from the tick order (docs/architecture.md): on tick T, the organisms that decided are the
founders and everyone born before T, minus anyone who died before T. Deaths happen after
deciding, so an organism that died *on* tick T still decided on it. Newborns of tick T
didn't. The count is checked against the record, so a mistake in this rule fails loudly
instead of showing one organism another's thoughts.
"""

from __future__ import annotations

from dataclasses import asdict

import numpy as np

from genesis.api.runs import LiveRun, RunNotFound
from genesis.api.schemas import BrainThought, OrganismDetail
from genesis.core.organism import Organism
from genesis.core.simulation import Simulation
from genesis.intelligence.brain_inputs import INPUT_NAMES, parameter_names


def deciders(sim: Simulation) -> list[int]:
    """IDs of the organisms that decided on the latest tick, in decision-record order."""
    tick = sim.tick - 1
    everyone = [*sim.organisms, *sim.dead]
    ids = sorted(
        o.id
        for o in everyone
        if (o.parent_id is None or o.birth_tick < tick)
        and (o.death_tick is None or o.death_tick >= tick)
    )
    return ids


def find(sim: Simulation, organism_id: int) -> Organism:
    for org in (*sim.organisms, *sim.dead):
        if org.id == organism_id:
            return org
    raise RunNotFound(f"no organism {organism_id} in this run (yet)")


def thought(sim: Simulation, organism_id: int) -> BrainThought | None:
    decision = sim.last_decision
    if decision is None or decision.thought is None:
        return None
    ids = deciders(sim)
    if len(ids) != len(decision.observations):
        raise RuntimeError(
            f"decision record has {len(decision.observations)} rows but {len(ids)} organisms "
            "decided: the rule in details.deciders is wrong"
        )
    try:
        k = ids.index(organism_id)
    except ValueError:
        return None  # born on the latest tick, or dead before it
    t = decision.thought
    act = t.activations.row(k)
    max_turn = float(decision.max_turn[k])
    return BrainThought(
        tick=sim.tick - 1,
        input_names=list(INPUT_NAMES),
        inputs=t.inputs[k].tolist(),
        hidden_sum=act.hidden_sum.tolist(),
        hidden=act.hidden.tolist(),
        output_sum=act.output_sum.tolist(),
        outputs=act.outputs.tolist(),
        turn=float(np.clip(t.actions.turn[k], -max_turn, max_turn)),
        throttle=float(np.clip(t.actions.throttle[k], 0.0, 1.0)),
    )


def organism_detail(run: LiveRun, organism_id: int) -> OrganismDetail:
    sim = run.sim
    org = find(sim, organism_id)
    children = sorted(o.id for o in (*sim.organisms, *sim.dead) if o.parent_id == organism_id)
    weights = None
    if org.brain is not None:
        weights = dict(zip(parameter_names(), org.brain.to_vector().tolist(), strict=True))
    return OrganismDetail(
        id=org.id,
        alive=org.alive,
        parent_id=org.parent_id,
        founder_id=org.founder_id,
        generation=org.generation,
        birth_tick=org.birth_tick,
        death_tick=org.death_tick,
        death_cause=None if org.death_cause is None else str(org.death_cause),
        age=org.age,
        energy=org.energy,
        x=org.x,
        y=org.y,
        heading=org.heading,
        food_eaten=org.food_eaten,
        offspring_count=org.offspring_count,
        children=children,
        genome=org.genome.as_dict(),
        traits=asdict(org.traits),
        brain_weights=weights,
        thought=thought(sim, organism_id),
    )
