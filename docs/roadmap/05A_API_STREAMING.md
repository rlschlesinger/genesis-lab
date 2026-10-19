# Chunk 05A — Backend API and bounded live streaming

Expose the existing Python simulation without moving its rules into the browser.

## Scope
- Build FastAPI service with validated endpoints to create a run, read config, pause, resume, single-step, reset by seed, fetch summary, fetch organism details, list saved runs, and export a run.
- Add WebSocket stream of **read-only** snapshots at controlled rate independent of simulation tick rate. Define typed, versioned payload contract. Server should decimate/coalesce snapshots for slow consumers; never block simulation on UI frame rate.
- Implement explicit run state (idle/running/paused/completed/failed) and safe control coordination; bound input values, file paths, and memory queue sizes.
- Support API-controlled deterministic stepping, but do not assume wall-clock playback is deterministic. Simulation sequence must remain seed/config dependent, not number of WebSocket clients.
- Add endpoint docs in `docs/API.md` and one curl/Python usage script.

## Tests
- Create/step/pause/resume/reset, invalid config validation, existence and shape of read-only snapshots, two clients observing same authoritative state, disconnected clients, no unbounded queue growth, state digest equal to headless run after N ticks.

## Learning
Explain client/server, JSON schemas, asynchronous I/O, WebSocket vs HTTP, concurrency hazards, and why state should have one authority.

## Acceptance
A documented API can control a seeded simulation headlessly and send snapshots. Stop and point to `05B_BROWSER_LAB.md`.
