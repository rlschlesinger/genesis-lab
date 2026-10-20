# The browser lab

Watch seeded simulations live, control them, examine any organism's brain, chart a run as it goes, compare finished runs and trace families. The Python server runs the simulation; the browser only shows it and asks for things, so a run behaves exactly as it would headless (same config and seed, same history, checked by digest).

## Start

Once, after cloning (needs [Node](https://nodejs.org) 22):

```bash
cd web && npm ci && npm run build && cd ..
```

Then, whenever you want the lab:

```bash
uv run genesis lab --open        # http://127.0.0.1:8765, opens your browser
```

One process serves the lab and its API; Ctrl+C stops it. Live runs are kept in memory and end when it stops: **Save run** keeps one as a normal run folder in `data/runs/live/`, loaded into the data lake.

Working on the lab's code instead? Run `uv run genesis serve` and, in a second terminal, `cd web && npm run dev` (http://127.0.0.1:5173, reloading as you edit).

## The four views

| View | What it's for |
|---|---|
| **World** | Start a run (configuration and seed), run, pause, step 1/10/100 ticks, change speed, reset, save. Drag and zoom the plate; click an organism to examine it in the specimen panel: its body, family, genome and, with a brain, its latest decision drawn as a network. |
| **Analytics** | The watched run over time: population and food; births, deaths and meals; mean energy; behaviour. Each chart says its unit and what one point covers. |
| **Compare** | Two finished runs from the data lake (every experiment's, and runs you saved): what differs in their settings, then their charts overlaid (A violet, B iodine and dashed). |
| **Lineage** | The selected organism's line of descent back to its founder, and its descendants; click any organism to move there. |

The address keeps the watched run (`?run=…`), so a refresh, bookmark or link returns to it while the server is running.

## Keyboard

On the plate (click it or Tab to it first):

| Key | Does |
|---|---|
| `]` / `[` | Select the next / previous organism by ID |
| `Escape` | Clear the selection |
| `+` / `-` | Zoom in / out |
| Arrow keys | Move the view |
| `0` | Fit the whole world |

Everything else is buttons, fields and links in reading order; a "Skip to the lab" link is the first stop for keyboard users.

## Making a demo or a screenshot

1. `uv run genesis lab --open`, start `neural` with seed 1, and set the speed to 200 ticks/s for a minute so brains have evolved.
2. Pause. Tick **Trails**, zoom in on a busy area, and select an organism that's seeing food (`]` until "food seen" reads 1.00).
3. Use your system's screenshot tool (macOS: Shift-Cmd-4, then Space, then click the window). For a recording, Shift-Cmd-5. The same seed always gives the same run, so a demo can be repeated exactly.

## When something's wrong

| You see | Why, and what to do |
|---|---|
| "Can't reach the Genesis Lab API" | The server isn't running: `uv run genesis lab`. |
| "Connection lost. Trying again in … s" | The server stopped or restarted; the lab keeps trying (0.5 → 8 s). |
| "This run isn't on the server" / "no longer exists" | Live runs end with the server. Start it again (same config and seed recreate it exactly) or choose another. |
| "4 live runs already (the limit is 4); remove one first" | **Change run**, then **Remove** one you're done with. |
| Compare says there's no data lake | Ingest runs first: `uv run genesis lake ingest data/runs data/experiments`. |
| `genesis lab` says the lab hasn't been built | `cd web && npm ci && npm run build`. |

Checked by hand before each release: [e2e-checklist.md](e2e-checklist.md). How it's built: [API.md](API.md), [ui-design.md](ui-design.md), [architecture.md](architecture.md).
