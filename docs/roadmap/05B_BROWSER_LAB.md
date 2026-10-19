# Chunk 05B — Interactive research web application

Build a polished, usable local laboratory around the tested backend. Keep the interface accessible and honest about what is measured.

## Scope
- Scaffold React + TypeScript + Vite and install compatible stable PixiJS. Use a canvas-based world with food pellets, organism heading/color, pan/zoom, optional trails, selection, and responsive layout.
- UI sections: Live World, Run Analytics, Experiment Comparison, Lineage Explorer. Controls: run, pause, one step, seed/config, reset, playback speed, export. Include organism detail inspector with phenotype/genome/parent/children and neural action/sensor values when available.
- Create charts using chosen charting library with real data from API or stored runs, clearly label units, sample sizes, conditions, and seeded run IDs. Do not create fake 'science' metrics in live charts.
- Handle API disconnected/reconnecting, invalid input, runs ending due to extinction, >1000 agents with frame coalescing, and browser refresh without mutating the authoritative run.
- Add quickstart, screenshot/demo instructions, and a manual E2E checklist. Add simple UI tests if feasible without major tooling overhead.

## Tests / review
- Browser can pause and single-step; reconnect reads true current state; selecting an organism doesn't modify the simulation; controls validate ranges; compare two runs; outputs match backend; basic responsive and keyboard usability.

## Learning
Explain frontend vs backend, API contracts, state synchronization, Canvas/WebGL, and plotting scientific evidence versus decorative visualization.

## Acceptance
Local UI supports complete observer workflow and does not affect seeded numerical results. Stop and point to `06A_PREDATOR_PREY.md`.
