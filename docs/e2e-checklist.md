# Browser lab: manual end-to-end checklist

Automated tests cover the API (Python, including a real-server WebSocket test), the lab's logic (Vitest) and the contract between them (fixtures checked from both sides). They can't see the screen. Walk through this list before a release, in Chrome, with `uv run genesis lab`. Each line says what to do and what must happen.

**Status (2026-10-20, 5.10):** every item was checked in Chrome by scripted interaction during 5.5–5.10, **except the items marked "not yet checked by hand"**: most need a real mouse or a system setting, and were exercised only through keyboard equivalents or unit tests. Tick them on the first hands-on pass.

## Start and watch

- [ ] Fresh tab, no run: the picker shows the three configurations, each described in words; "Runs on the server" says none yet.
- [ ] **Start run** (neural, seed 1): the plate appears, square, with a grid; status "Live"; tick 0, 30 alive, "idle".
- [ ] **Step 1**, **10**, **100**: the tick moves by exactly that; the run stays paused.
- [ ] **Run**: Pause replaces Run; Step and Save fade (can't be used); organisms glide smoothly.
- [ ] Speed slider to the right end: "As fast as possible"; to the left: 1 tick/s. Ticks follow.
- [ ] **Pause**, then **Save run**: one line says where it was saved, "identical to the live run" and "added to the data lake".

## The plate

- [ ] Drag moves the view; the scroll wheel zooms about the pointer (the page doesn't scroll); double-click fits the world. *(not yet checked by hand; zoom-about-a-point is unit-tested)*
- [ ] Click an organism: a safranin ring; the panel shows it. Click empty space: selection clears. *(not yet checked by hand; picking is unit-tested and keyboard selection was checked)*
- [ ] Keyboard only: Tab to the plate, `]` selects, `+` zooms, arrows move, `0` fits, Escape clears.
- [ ] **Trails** on: faint violet paths; off: gone. *(on checked; off not yet checked by hand)*
- [ ] Selecting and inspecting never changes the run (also tested: tests/api/test_details.py).

## Two species (6.5)

- [ ] Start `predators`, seed 3, at 8 ticks/s: pink predators (larger, a notch at the front) and violet prey (ovals with a tail); under the plate "N prey, M predators", the predator count in pink.
- [ ] A capture: a thin pink ring appears where it happened and fades in about a second (with reduce motion: appears and disappears without fading).
- [ ] Select a predator: the panel says "Predator N" and "Prey caught"; a prey in the same world says "Prey N". A neural world without predators still says "Organism N".
- [ ] Analytics: "Prey and predators", "Strikes and captures" (strikes dashed), and the phase plot from the open circle (start) to the filled one (now).

## The specimen panel

- [ ] Status, energy, meals, generation, founder; a parent or child number selects that organism.
- [ ] Neural organism seeing food: the brain diagram, a sentence ("turned … left at …% throttle"), seven inputs as numbers.
- [ ] Rule-based organism: "No brain: a rule decides for this organism." *(not yet checked by hand)*

## Analytics, Compare, Lineage

- [ ] Analytics while running: four charts grow about once a second; legends show the latest values; each caption says what a point covers.
- [ ] Compare: E007, A "evolved, seed 7100", B "seeker, seed 7100": "What differs" lists exactly `brain.founder_weights` and `organisms.controller`; four overlaid charts.
- [ ] Lineage with an organism selected: line of descent from its founder; descendants in birth order; clicking any organism moves there.

## When things go wrong

- [ ] Stop the server with the lab open: "Connection lost. Trying again in 0.5 s", then 1, 2, 4 s.
- [ ] Start it again: "This run no longer exists" with "Start neural, seed 1 again" (which works) and "Choose another run"; no run controls shown.
- [ ] Open `/?run=nonsense`: the plate explains the run isn't on the server and offers "Choose a run".
- [ ] A world with no food (API: `{"config": "default", "changes": {"food.initial_count": 0, "food.regrowth_per_tick": 0, "organisms.initial_energy": 2}}`), run it: "Extinct: the last organisms died on tick …"; only Reset and Save remain.
- [ ] Five runs: the fifth is refused in place: "4 live runs already (the limit is 4); remove one first", next to the Remove buttons.
- [ ] Refresh the page while watching: the same run comes back.

## Layout and access

- [ ] 1360 × 860: the page doesn't scroll on the World view; plate and stage bar line up.
- [ ] 390 × 844 (phone): no sideways scrolling on any view; panels stack under the plate.
- [ ] Lighthouse accessibility: 100 on the picker and on a live run with an organism selected.
- [ ] System setting "reduce motion": organisms move without gliding. *(not yet checked by hand; the rule is unit-tested)*
