// Draws the plate with PixiJS (WebGL/WebGPU). The only code in the lab that touches the GPU.
//
// Everything is placed in *world* coordinates inside one container whose transform is the
// camera, including a flip (scale y = -1), so organisms sit at their simulated positions and
// turn by their simulated headings with no conversions elsewhere. Organisms and food are
// sprites stamped from shared textures and reused frame to frame (a pool), which keeps
// thousands of them cheap. Colours come from the CSS tokens (tokens.css), never from here;
// sizes and timings from species.ts.
//
// Each organism is two sprites (6.5): its interior, drawn as full as its energy allows, and
// its membrane on top, which also shows the species' shape. Prey are crystal-violet ovals
// with a tail at the back; predators are larger safranin cells with a notch at the front,
// their mouth.
//
// Display only: nothing here can reach the server. Selecting reports an ID to the caller.

import { Application, Container, Graphics, Sprite, type Texture } from "pixi.js";

import type { OrganismColumns, Snapshot } from "../api/types";
import {
  type Camera,
  type Point,
  type Size,
  clamp,
  panBy,
  pixelsPerUnit,
  screenToWorld,
  wholeWorld,
  zoomAt,
} from "./camera";
import { nearestOrganism } from "./hitTest";
import { SNAP_DISTANCE, blend, progress, type Pose } from "./interpolate";
import { BODIES, type SpeciesName, interiorAlpha, markLook, newCaptures } from "./species";
import { TrailBook } from "./trails";

/** The grid's spacing in world units: a founder's sight range (see Plate.tsx). */
const GRATICULE_UNITS = 20;
const TEXTURE_RADIUS = 32; // pixels of a body's radius in the generated textures
const FOOD_UNITS = 0.8;
const PICK_PX = 10; // a click this close (screen pixels) to an organism selects it

export interface Palette {
  prey: number;
  predator: number;
  food: number;
  selected: number;
  graticule: number;
}

/** Read the palette from the CSS tokens, so tokens.css stays the only place colours live. */
export function paletteFromCss(element: Element = document.documentElement): Palette {
  const colour = (name: string) => {
    // A token may name another (--prey: var(--violet)); a probe element resolves it.
    const probe = document.createElement("span");
    probe.style.color = `var(${name})`;
    element.appendChild(probe);
    const [r, g, b] = getComputedStyle(probe).color.match(/\d+/g)!.map(Number);
    probe.remove();
    return ((r! << 16) | (g! << 8) | b!) >>> 0;
  };
  return {
    prey: colour("--prey"),
    predator: colour("--predator"),
    food: colour("--iodine"),
    selected: colour("--selected"),
    graticule: colour("--graticule"),
  };
}

/** A texture and the point in it that sits on the organism's position. */
interface Stamp {
  texture: Texture;
  anchor: Point;
}

/** One species on the plate: where it was drawn, its target picture, and its sprites. */
interface Group {
  name: SpeciesName;
  from: Map<number, Pose>;
  shown: Map<number, Pose>;
  fullness: Map<number, number>;
  interiors: Container;
  membranes: Container;
  interior: Stamp;
  membrane: Stamp;
}

interface Mark {
  x: number;
  y: number;
  bornMs: number;
}

export class PlateRenderer {
  private camera: Camera;
  private view: Size;
  private readonly scene = new Container();
  private readonly grid = new Graphics();
  private readonly trailLines = new Graphics();
  private readonly foodLayer = new Container();
  private readonly markLines = new Graphics();
  private readonly ring = new Graphics();
  private readonly trails = new TrailBook();
  private readonly foodTexture: Texture;
  private readonly groups: Record<SpeciesName, Group>;

  private target: Snapshot | null = null;
  private arrivedAt = 0;
  private intervalMs = 66;
  private selected: number | null = null;
  private showTrails = false;
  private cameraDirty = true;
  private readonly reducedMotion: boolean;
  private marks: Mark[] = [];
  /** The newest capture tick already marked (or skipped); -1 before the first picture. */
  private markedUpTo = -1;

  private constructor(
    private readonly app: Application,
    private readonly world: Size,
    private readonly palette: Palette,
  ) {
    this.view = { width: app.screen.width, height: app.screen.height };
    this.camera = wholeWorld(world);
    this.reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    this.foodTexture = this.stamp(new Graphics().circle(0, 0, TEXTURE_RADIUS).fill(palette.food)).texture;
    this.groups = {
      prey: this.group("prey", this.preyShape(false), this.preyShape(true)),
      predator: this.group("predator", this.predatorShape(false), this.predatorShape(true)),
    };
    const { prey, predator } = this.groups;
    this.scene.addChild(
      this.grid, this.trailLines, this.foodLayer, this.markLines,
      prey.interiors, prey.membranes, predator.interiors, predator.membranes, this.ring,
    );
    app.stage.addChild(this.scene);
    app.ticker.add(() => this.frame());
  }

  /** Create a renderer filling ``host``. Pixi starts asynchronously (it picks WebGPU or WebGL). */
  static async create(host: HTMLElement, world: Size, palette: Palette): Promise<PlateRenderer> {
    const app = new Application();
    await app.init({
      resizeTo: host,
      backgroundAlpha: 0,
      antialias: true,
      autoDensity: true,
      resolution: window.devicePixelRatio || 1,
    });
    app.canvas.setAttribute("aria-hidden", "true"); // described in words by the plate instead
    host.appendChild(app.canvas);
    return new PlateRenderer(app, world, palette);
  }

  destroy(): void {
    this.app.destroy(true, { children: true, texture: true });
  }

  // --- What to show -------------------------------------------------------------------------

  showSnapshot(snapshot: Snapshot): void {
    const now = performance.now();
    if (this.target !== null && snapshot.tick < this.target.tick) {
      // A new run on a plate of the same size (a reset): nothing from the old one carries over.
      this.marks = [];
      this.markedUpTo = -1;
      this.trails.clear();
    }
    if (this.target !== null) {
      // The gap between pictures sets how long a glide takes (smoothed, within limits).
      const gap = now - this.arrivedAt;
      this.intervalMs = Math.min(500, Math.max(33, 0.8 * this.intervalMs + 0.2 * gap));
    }
    for (const group of Object.values(this.groups)) {
      group.from = group.shown; // glide from wherever things are drawn right now
      group.fullness = fullnessById(this.columns(snapshot, group.name));
    }
    this.target = snapshot;
    this.arrivedAt = now;
    this.takeCaptures(snapshot, now);
    this.drawFood(snapshot);
    const predators = snapshot.predators;
    if (predators) this.trails.record(snapshot.organisms, predators);
    else this.trails.record(snapshot.organisms);
    if (this.showTrails) this.drawTrails();
  }

  setSelected(id: number | null): void {
    this.selected = id;
  }

  setTrails(on: boolean): void {
    this.showTrails = on;
    if (on) this.drawTrails();
    else this.trailLines.clear();
  }

  // --- Camera -------------------------------------------------------------------------------

  resetView(): void {
    this.setCamera(wholeWorld(this.world));
  }

  zoom(factor: number, at?: Point): void {
    const point = at ?? { x: this.view.width / 2, y: this.view.height / 2 };
    this.setCamera(zoomAt(this.camera, factor, point, this.world, this.view));
  }

  pan(dx: number, dy: number): void {
    this.setCamera(panBy(this.camera, dx, dy, this.world, this.view));
  }

  /** The organism (of either species) under a screen point, if any. */
  pick(at: Point): number | null {
    const worldPoint = screenToWorld(at, this.camera, this.world, this.view);
    const everyone = new Map([...this.groups.prey.shown, ...this.groups.predator.shown]);
    return nearestOrganism(everyone, worldPoint, PICK_PX / this.k());
  }

  get organismIds(): number[] {
    if (!this.target) return [];
    return [...this.target.organisms.id, ...(this.target.predators?.id ?? [])];
  }

  // --- Drawing ------------------------------------------------------------------------------

  private columns(snapshot: Snapshot, name: SpeciesName): OrganismColumns | null {
    return name === "prey" ? snapshot.organisms : snapshot.predators;
  }

  private setCamera(camera: Camera): void {
    this.camera = camera;
    this.cameraDirty = true;
  }

  private k(): number {
    return pixelsPerUnit(this.camera, this.world, this.view);
  }

  private frame(): void {
    const screen = this.app.screen;
    if (screen.width !== this.view.width || screen.height !== this.view.height) {
      this.view = { width: screen.width, height: screen.height };
      this.camera = clamp(this.camera, this.world, this.view);
      this.cameraDirty = true;
    }
    if (this.cameraDirty) this.applyCamera();
    if (this.target === null) return;
    const now = performance.now();
    const t = progress(now - this.arrivedAt, this.intervalMs, this.reducedMotion);
    for (const group of Object.values(this.groups)) {
      const next = this.columns(this.target, group.name);
      group.shown = next ? blend(group.from, next, t) : new Map();
      this.drawGroup(group);
    }
    this.drawMarks(now);
    this.drawRing();
  }

  private applyCamera(): void {
    const k = this.k();
    this.scene.scale.set(k, -k); // world y up, screen y down
    this.scene.position.set(
      this.view.width / 2 - this.camera.centre.x * k,
      this.view.height / 2 + this.camera.centre.y * k,
    );
    this.drawGrid(k);
    if (this.showTrails) this.drawTrails();
    this.cameraDirty = false;
  }

  private drawGrid(k: number): void {
    const { width, height } = this.world;
    this.grid.clear();
    for (let x = 0; x <= width + 1e-9; x += GRATICULE_UNITS) this.grid.moveTo(x, 0).lineTo(x, height);
    for (let y = 0; y <= height + 1e-9; y += GRATICULE_UNITS) this.grid.moveTo(0, y).lineTo(width, y);
    this.grid.stroke({ width: 1 / k, color: this.palette.graticule }); // a 1-pixel hairline
  }

  private radius(name: SpeciesName): number {
    const body = BODIES[name];
    return Math.max(body.units, body.minPx / this.k());
  }

  private drawGroup(group: Group): void {
    const n = group.shown.size;
    const interiors = this.pool(group.interiors, n, group.interior);
    const membranes = this.pool(group.membranes, n, group.membrane);
    const scale = this.radius(group.name) / TEXTURE_RADIUS;
    let i = 0;
    for (const [id, pose] of group.shown) {
      const inside = interiors[i]!;
      const outline = membranes[i++]!;
      for (const sprite of [inside, outline]) {
        sprite.position.set(pose.x, pose.y);
        sprite.rotation = pose.heading;
        sprite.scale.set(scale);
      }
      inside.alpha = interiorAlpha(group.fullness.get(id) ?? 1);
    }
  }

  private drawFood(snapshot: Snapshot): void {
    const { x, y } = snapshot.food;
    const sprites = this.pool(this.foodLayer, x.length, { texture: this.foodTexture, anchor: { x: 0.5, y: 0.5 } });
    const scale = FOOD_UNITS / TEXTURE_RADIUS;
    for (let i = 0; i < x.length; i++) {
      sprites[i]!.position.set(x[i]!, y[i]!);
      sprites[i]!.scale.set(scale);
    }
  }

  /** Mark captures newer than any already marked. The first picture of a run only sets the
   *  starting point: captures from before the viewer arrived aren't replayed. */
  private takeCaptures(snapshot: Snapshot, now: number): void {
    if (this.markedUpTo >= 0) {
      for (const c of newCaptures(snapshot.captures, this.markedUpTo)) {
        this.marks.push({ x: c.x, y: c.y, bornMs: now });
      }
    }
    const newest = snapshot.captures.reduce((m, c) => Math.max(m, c.tick), 0);
    this.markedUpTo = Math.max(this.markedUpTo, newest);
  }

  private drawMarks(now: number): void {
    this.markLines.clear();
    if (this.marks.length === 0) return;
    const k = this.k();
    this.marks = this.marks.filter((mark) => {
      const look = markLook(now - mark.bornMs, this.reducedMotion);
      if (look === null) return false;
      this.markLines
        .circle(mark.x, mark.y, Math.max(look.radius, 6 / k))
        .stroke({ width: 1.5 / k, color: this.palette.predator, alpha: look.alpha });
      return true;
    });
  }

  private drawRing(): void {
    this.ring.clear();
    if (this.selected === null) return;
    for (const group of Object.values(this.groups)) {
      const pose = group.shown.get(this.selected);
      if (!pose) continue;
      const k = this.k();
      this.ring.circle(pose.x, pose.y, this.radius(group.name) * 1.6 + 4 / k);
      this.ring.stroke({ width: 2 / k, color: this.palette.selected });
      return;
    }
  }

  private drawTrails(): void {
    const k = this.k();
    this.trailLines.clear();
    for (const [, points] of this.trails.entries()) {
      for (let i = 0; i < points.length; i++) {
        const p = points[i]!;
        const prev = points[i - 1];
        if (!prev || Math.hypot(p.x - prev.x, p.y - prev.y) > SNAP_DISTANCE) this.trailLines.moveTo(p.x, p.y);
        else this.trailLines.lineTo(p.x, p.y);
      }
    }
    this.trailLines.stroke({ width: 1.2 / k, color: this.palette.prey, alpha: 0.28 });
  }

  /** Exactly ``count`` sprites in ``layer``: reuse, add or remove as needed. */
  private pool(layer: Container, count: number, stamp: Stamp): Sprite[] {
    while (layer.children.length < count) {
      const sprite = new Sprite(stamp.texture);
      sprite.anchor.set(stamp.anchor.x, stamp.anchor.y);
      layer.addChild(sprite);
    }
    while (layer.children.length > count) layer.removeChildAt(layer.children.length - 1).destroy();
    return layer.children as Sprite[];
  }

  // --- Shapes -------------------------------------------------------------------------------

  private group(name: SpeciesName, interior: Graphics, membrane: Graphics): Group {
    return {
      name,
      from: new Map(),
      shown: new Map(),
      fullness: new Map(),
      interiors: new Container(),
      membranes: new Container(),
      interior: this.stamp(interior),
      membrane: this.stamp(membrane),
    };
  }

  /** Bake a drawing into a texture, remembering where its origin (the organism's position)
   *  lies in it: a tail or a stroke makes the drawing lopsided, so the centre isn't 0.5. */
  private stamp(g: Graphics): Stamp {
    const bounds = g.getLocalBounds();
    const texture = this.app.renderer.generateTexture({ target: g, resolution: 2 });
    const anchor = { x: -bounds.minX / bounds.width, y: -bounds.minY / bounds.height };
    g.destroy();
    return { texture, anchor };
  }

  /** Prey: an oval pointing along +x (its heading), with a short tail trailing behind. */
  private preyShape(membrane: boolean): Graphics {
    const r = TEXTURE_RADIUS;
    const colour = this.palette.prey;
    const g = new Graphics().ellipse(0, 0, r, r * 0.68);
    if (!membrane) return g.fill(colour);
    g.stroke({ width: r * 0.16, color: colour });
    g.moveTo(-r * 0.95, 0).quadraticCurveTo(-r * 1.45, r * 0.32, -r * 1.9, r * 0.06);
    return g.stroke({ width: r * 0.14, color: colour, cap: "round" });
  }

  /** Predator: a rounder, larger cell with a notch at the front, its mouth. The outline is
   *  a circle whose radius dips smoothly where it faces (angle 0, the heading). */
  private predatorShape(membrane: boolean): Graphics {
    const r = TEXTURE_RADIUS;
    const colour = this.palette.predator;
    const points: number[] = [];
    const steps = 72;
    for (let i = 0; i < steps; i++) {
      const a = -Math.PI + (2 * Math.PI * i) / steps;
      const dip = 1 - 0.38 * Math.exp(-((a / 0.42) ** 2));
      points.push(Math.cos(a) * r * dip, Math.sin(a) * r * dip);
    }
    const g = new Graphics().poly(points, true);
    return membrane ? g.stroke({ width: r * 0.2, color: colour, join: "round" }) : g.fill(colour);
  }
}

function fullnessById(columns: OrganismColumns | null): Map<number, number> {
  const out = new Map<number, number>();
  if (!columns) return out;
  for (let i = 0; i < columns.id.length; i++) out.set(columns.id[i]!, columns.fullness[i]!);
  return out;
}
