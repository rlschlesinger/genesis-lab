"""`genesis inspect`: replay a run to one tick and show one organism's decision, step by step.

Nothing is stored about individual decisions while a run is recorded (it would be huge), but
nothing needs to be: a run is fully determined by its config and seed (the determinism
invariant), so replaying it reproduces every tick exactly, on the same platform. The
inspector replays to the start of the chosen tick, lets the simulation take that tick, and
reads the decision record the simulation kept for it (``Simulation.last_decision``). For
neural organisms that record holds the controller's whole computation, so what is printed is
what the simulation used, by construction (D-044).

Two checks make a replay trustworthy:

- the replayed tick's counts (population, births, deaths, meals) are compared with the
  recorded ticks.csv row, when that tick was recorded;
- a run recorded on a different platform is flagged: last-bit differences in floating point
  (D-027) can make a replay drift from the original over many ticks.
"""

from __future__ import annotations

import csv
import json
import math
import platform
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from genesis.core.config import SimulationConfig
from genesis.core.simulation import Simulation, TickSummary
from genesis.intelligence.brain_inputs import input_names
from genesis.intelligence.neural import OUTPUT_NAMES, Brain

CHECKED_COUNTS = ("population", "births", "deaths", "food_eaten")


class InspectError(ValueError):
    """The requested organism or tick can't be inspected (with the reason)."""


@dataclass(frozen=True)
class BodyState:
    x: float
    y: float
    heading: float
    energy: float


@dataclass(frozen=True)
class Inspection:
    tick: int
    organism_id: int
    controller: str
    generation: int
    founder_id: int
    age: int
    max_turn: float
    speed: float
    before: BodyState
    after: BodyState
    alive_after: bool
    ate: bool
    # What it sensed.
    food_seen: bool
    food_distance: float
    food_bearing: float
    # What it did, as applied by movement (clipped to the body's limits).
    turn: float
    throttle: float
    # Neural organisms only.
    brain: Brain | None
    inputs: np.ndarray | None  # (7,) as passed to the network
    hidden_sum: np.ndarray | None  # (6,)
    hidden: np.ndarray | None  # (6,)
    output_sum: np.ndarray | None  # (2,)
    outputs: np.ndarray | None  # (2,)
    # Replay checks.
    recorded_match: bool | None  # None: this tick wasn't recorded (sampling) or no ticks.csv
    platform_note: str | None


def replay_to(config: SimulationConfig, tick: int) -> Simulation:
    """A simulation that has completed ticks 0 .. tick-1: about to take tick ``tick``."""
    if tick < 0:
        raise InspectError("tick must be 0 or more")
    if tick >= config.run.max_ticks:
        raise InspectError(
            f"the run has {config.run.max_ticks} ticks (0 to {config.run.max_ticks - 1})"
        )
    sim = Simulation(config)
    while sim.tick < tick:
        if sim.finished:
            raise InspectError(f"the population went extinct at tick {sim.tick - 1}")
        sim.step()
    return sim


def inspect_tick(
    config: SimulationConfig,
    tick: int,
    organism_id: int,
    recorded_ticks: dict[int, dict] | None = None,
    recorded_platform: tuple[str, str] | None = None,
) -> Inspection:
    """Replay to ``tick``, take it, and return organism ``organism_id``'s decision."""
    sim = replay_to(config, tick)
    ids = [o.id for o in sim.organisms]
    if organism_id not in ids:
        raise InspectError(_not_alive_reason(sim, organism_id, tick, ids))
    k = ids.index(organism_id)
    org = sim.organisms[k]
    before = BodyState(org.x, org.y, org.heading, org.energy)

    summary = sim.step()
    decision = sim.last_decision
    obs = decision.observations
    max_turn = float(decision.max_turn[k])
    turn = float(np.clip(decision.actions.turn[k], -max_turn, max_turn))
    throttle = float(np.clip(decision.actions.throttle[k], 0.0, 1.0))
    ate = any(e.kind == "meal" and e.organism_id == organism_id for e in sim.events_this_tick)
    thought = decision.thought
    act = thought.activations.row(k) if thought is not None else None

    return Inspection(
        tick=tick,
        organism_id=organism_id,
        controller=config.organisms.controller,
        generation=org.generation,
        founder_id=org.founder_id,
        age=org.age - (1 if org.alive else 0),  # age at the start of the tick
        max_turn=max_turn,
        speed=org.traits.speed,
        before=before,
        after=BodyState(org.x, org.y, org.heading, org.energy),
        alive_after=org.alive,
        ate=ate,
        food_seen=bool(obs.food_found[k]),
        food_distance=float(obs.food_distance[k]),
        food_bearing=float(obs.food_bearing[k]),
        turn=turn,
        throttle=throttle,
        brain=org.brain,
        inputs=None if thought is None else thought.inputs[k],
        hidden_sum=None if act is None else act.hidden_sum,
        hidden=None if act is None else act.hidden,
        output_sum=None if act is None else act.output_sum,
        outputs=None if act is None else act.outputs,
        recorded_match=_matches_record(summary, recorded_ticks),
        platform_note=_platform_note(recorded_platform),
    )


def inspect_run_folder(run_dir: str | Path, tick: int, organism_id: int) -> Inspection:
    """``inspect_tick`` for a recorded run: config from run.json, checked against ticks.csv."""
    run_dir = Path(run_dir)
    meta = json.loads((run_dir / "run.json").read_text())
    try:
        config = SimulationConfig.model_validate(meta["config"])
    except ValueError as exc:
        raise InspectError(f"this run's config can't be loaded by the current code: {exc}") from exc
    recorded: dict[int, dict] | None = None
    if (run_dir / "ticks.csv").exists():
        with (run_dir / "ticks.csv").open(newline="") as f:
            recorded = {int(r["tick"]): r for r in csv.DictReader(f)}
    env = meta.get("environment") or {}
    where = (env.get("platform"), env.get("machine"))
    return inspect_tick(config, tick, organism_id, recorded, where if all(where) else None)


def _matches_record(summary: TickSummary, recorded: dict[int, dict] | None) -> bool | None:
    if recorded is None or summary.tick not in recorded:
        return None
    row = recorded[summary.tick]
    return all(int(row[c]) == getattr(summary, c) for c in CHECKED_COUNTS)


def os_family(platform_string: str) -> str:
    """``macOS-27.0.1-arm64-arm-64bit`` -> ``macOS``: the operating system without its version.

    run.json records ``platform.platform()``; comparing whole strings would flag a run made
    before a minor OS update as "another platform". D-027 groups platforms the same way: by
    operating system and machine.
    """
    return platform_string.split("-", 1)[0]


def _platform_note(recorded: tuple[str, str] | None) -> str | None:
    if recorded is None:
        return None
    recorded_os, recorded_machine = os_family(recorded[0]), recorded[1]
    here_os, here_machine = os_family(platform.platform()), platform.machine()
    if (recorded_os, recorded_machine) == (here_os, here_machine):
        return None
    return (
        f"recorded on {recorded_os} {recorded_machine}, replayed on {here_os} {here_machine}: "
        "floating-point last bits may differ (D-027), so a long replay can drift"
    )


def _not_alive_reason(sim: Simulation, organism_id: int, tick: int, ids: list[int]) -> str:
    if any(o.id == organism_id for o in (*sim.predators, *sim.dead_predators)):
        # Predators take IDs after the prey founders (D-057) and keep their own decision
        # record; this command walks through prey decisions. Say so, rather than "not alive".
        return (
            f"organism {organism_id} is a predator; genesis inspect replays prey decisions only "
            "(the lab's specimen panel shows a predator's latest decision)"
        )
    dead = next((o for o in sim.dead if o.id == organism_id), None)
    if dead is not None:
        # Founders act from tick 0; a newborn first acts the tick after its birth.
        first = dead.birth_tick if dead.parent_id is None else dead.birth_tick + 1
        return (
            f"organism {organism_id} died at tick {dead.death_tick} ({dead.death_cause}); "
            f"choose a tick from {first} to {dead.death_tick}"
        )
    if organism_id >= sim._next_id:  # IDs are handed out in order: not born yet
        return f"organism {organism_id} is born after tick {tick - 1}; choose a later tick"
    example = ", ".join(map(str, ids[:8])) or "none"
    return f"organism {organism_id} is not alive at tick {tick}; alive then: {example} ..."


# --- Text output ---------------------------------------------------------------------------


def _deg(radians: float) -> str:
    side = "left" if radians > 0 else "right" if radians < 0 else "straight"
    return f"{abs(math.degrees(radians)):.1f}° {side}"


def format_inspection(i: Inspection, weights: bool = False) -> str:
    """A readable account of one decision: sensed -> inputs -> hidden -> outputs -> result."""
    lines = [
        f"Organism {i.organism_id}, tick {i.tick} ({i.controller.replace('_', ' ')} controller)",
        f"  generation {i.generation}, founder {i.founder_id}, age {i.age}",
    ]
    if i.recorded_match is True:
        lines.append("  replay check: this tick's counts match ticks.csv")
    elif i.recorded_match is False:
        lines.append("  WARNING: this tick's counts differ from ticks.csv: the replay has diverged")
    if i.platform_note:
        lines.append(f"  note: {i.platform_note}")

    lines += ["", "Sensed"]
    if i.food_seen:
        lines.append(f"  nearest food {i.food_distance:.2f} units away, {_deg(i.food_bearing)}")
    else:
        lines.append("  no food in sight")
    lines.append(f"  energy {i.before.energy:.2f} EU")

    if i.inputs is not None:
        lines += ["", "1. Inputs (each in [-1, 1])"]
        lines += [
            f"  {name:<18} {value:+.3f}"
            for name, value in zip(input_names(len(i.inputs)), i.inputs, strict=True)
        ]
        lines += ["", "2. Hidden layer: weighted sum + bias, then tanh"]
        lines.append(f"  {'unit':<6}{'sum':>9}{'tanh':>9}")
        for h, (z, a) in enumerate(zip(i.hidden_sum, i.hidden, strict=True)):
            lines.append(f"  {h:<6}{z:>+9.3f}{a:>+9.3f}")
        turn_raw, throttle_raw = i.outputs
        lines += [
            "",
            "3. Outputs",
            f"  {OUTPUT_NAMES[0]:<9} sum {i.output_sum[0]:+.3f} -> tanh {turn_raw:+.3f}"
            f" x max_turn {i.max_turn:.3f} = {i.turn:+.3f} rad ({_deg(i.turn)})",
            f"  {OUTPUT_NAMES[1]:<9} sum {i.output_sum[1]:+.3f} -> sigmoid {throttle_raw:.3f}"
            f" x speed {i.speed:.2f} = up to {throttle_raw * i.speed:.3f} units",
        ]
    else:
        lines += [
            "",
            "Decision (rule-based: no brain)",
            f"  turn {i.turn:+.3f} rad ({_deg(i.turn)}), throttle {i.throttle:.3f}",
        ]

    b, a = i.before, i.after
    lines += [
        "",
        "Result" if i.inputs is None else "4. Result",
        f"  heading   {math.degrees(b.heading):7.1f}° -> {math.degrees(a.heading):7.1f}°",
        f"  position  ({b.x:.2f}, {b.y:.2f}) -> ({a.x:.2f}, {a.y:.2f}),"
        f" moved {math.hypot(a.x - b.x, a.y - b.y):.3f} units",
        f"  energy    {b.energy:.2f} -> {a.energy:.2f} EU" + (" (ate)" if i.ate else ""),
    ]
    if not i.alive_after:
        lines.append("  died this tick")

    if weights and i.brain is not None:
        lines += ["", "Weights: hidden layer (rows: units; columns: inputs)"]
        header = "".join(f"{name[:9]:>10}" for name in input_names(i.brain.shape[0]))
        lines.append(f"  {'unit':<5}{header}{'bias':>8}")
        for h in range(i.brain.w_hidden.shape[0]):
            row = "".join(f"{w:>+10.2f}" for w in i.brain.w_hidden[h])
            lines.append(f"  {h:<5}{row}{i.brain.b_hidden[h]:>+8.2f}")
        lines += ["", "Weights: outputs (columns: hidden units)"]
        for o, name in enumerate(OUTPUT_NAMES):
            row = "".join(f"{w:>+8.2f}" for w in i.brain.w_output[o])
            lines.append(f"  {name:<9}{row}   bias {i.brain.b_output[o]:+.2f}")
    return "\n".join(lines)
