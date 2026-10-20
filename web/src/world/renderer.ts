// Draws the plate with PixiJS (WebGL/WebGPU). The only code in the lab that touches the GPU.
//
// Everything is placed in *world* coordinates inside one container whose transform is the
// camera, including a flip (scale y = -1), so organisms sit at their simulated positions and
// turn by their simulated headings with no conversions elsewhere. Organisms and food are
// sprites stamped from shared textures and reused frame to frame (a pool), which keeps
// thousands of them cheap. Colours come from the CSS tokens (tokens.css), never from here.
//
// Display only: nothing here can reach the server. Selecting reports an ID to the caller.

import { Application, Container, Graphics, Sprite, type Texture } from "pixi.js";

import type { Snapshot } from "../api/types";
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
import { TrailBook } from "./trails";

/** The grid's spacing in world units: a founder's sight range (see Plate.tsx). */
const GRATICULE_UNITS = 20;
const TEXTURE_RADIUS = 32; // pixels in the generated textures, scaled down to world size
const MIN_ORGANISM_PX = 3.5; // never smaller than this on screen, however far out
const ORGANISM_UNITS = 1.3; // drawn radius in world units when zoomed in
const FOOD_UNITS = 0.8;
const PICK_PX = 10; // a click this close (screen pixels) to an organism selects it

export interface Palette {
  organism: number;
  food: number;
  selected: number;
  graticule: number;
  notch: number;
}

/** Read the palette from the CSS tokens, so tokens.css stays the only place colours live. */
export function paletteFromCss(element: Element = document.documentElement): Palette {
  const style = getComputedStyle(element);
  const colour = (name: string) => Number.parseInt(style.getPropertyValue(name).trim().slice(1), 16);
  return {
    organism: colour("--violet"),
    food: colour("--iodine"),
    selected: colour("--safranin"),
    graticule: colour("--graticule"),
    notch: colour("--field"),
  };
}

export class PlateRenderer {
  private camera: Camera;
  private view: Size;
  private readonly scene = new Container();
  private readonly grid = new Graphics();
  private readonly trailLines = new Graphics();
  private readonly foodLayer = new Container();
  private readonly organismLayer = new Container();
  private readonly ring = new Graphics();
  private readonly trails = new TrailBook();
  private organismTexture!: Texture;
  private foodTexture!: Texture;

  private from = new Map<number, Pose>();
  private target: Snapshot | null = null;
  private arrivedAt = 0;
  private intervalMs = 66;
  private shown = new Map<number, Pose>();
  private selected: number | null = null;
  private showTrails = false;
  private cameraDirty = true;
  private readonly reducedMotion: boolean;

  private constructor(
    private readonly app: Application,
    private readonly world: Size,
    private readonly palette: Palette,
  ) {
    this.view = { width: app.screen.width, height: app.screen.height };
    this.camera = wholeWorld(world);
    this.reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    this.organismTexture = this.makeOrganismTexture();
    this.foodTexture = this.makeDiscTexture(palette.food);
    this.scene.addChild(this.grid, this.trailLines, this.foodLayer, this.organismLayer, this.ring);
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
    if (this.target !== null) {
      // The gap between pictures sets how long a glide takes (smoothed, within limits).
      const gap = now - this.arrivedAt;
      this.intervalMs = Math.min(500, Math.max(33, 0.8 * this.intervalMs + 0.2 * gap));
    }
    this.from = this.shown; // glide from wherever things are drawn right now
    this.target = snapshot;
    this.arrivedAt = now;
    this.drawFood(snapshot);
    this.trails.record(snapshot.organisms);
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

  /** The organism under a screen point (relative to the canvas), if any. */
  pick(at: Point): number | null {
    const worldPoint = screenToWorld(at, this.camera, this.world, this.view);
    return nearestOrganism(this.shown, worldPoint, PICK_PX / this.k());
  }

  get organismIds(): number[] {
    return this.target ? [...this.target.organisms.id] : [];
  }

  // --- Drawing ------------------------------------------------------------------------------

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
    const t = progress(performance.now() - this.arrivedAt, this.intervalMs, this.reducedMotion);
    this.shown = blend(this.from, this.target.organisms, t);
    this.drawOrganisms();
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

  private organismRadius(): number {
    return Math.max(ORGANISM_UNITS, MIN_ORGANISM_PX / this.k());
  }

  private drawOrganisms(): void {
    const sprites = this.pool(this.organismLayer, this.shown.size, this.organismTexture);
    const scale = this.organismRadius() / TEXTURE_RADIUS;
    let i = 0;
    for (const pose of this.shown.values()) {
      const sprite = sprites[i++]!;
      sprite.position.set(pose.x, pose.y);
      sprite.rotation = pose.heading;
      sprite.scale.set(scale);
    }
  }

  private drawFood(snapshot: Snapshot): void {
    const { x, y } = snapshot.food;
    const sprites = this.pool(this.foodLayer, x.length, this.foodTexture);
    const scale = FOOD_UNITS / TEXTURE_RADIUS;
    for (let i = 0; i < x.length; i++) {
      sprites[i]!.position.set(x[i]!, y[i]!);
      sprites[i]!.scale.set(scale);
    }
  }

  private drawRing(): void {
    this.ring.clear();
    const pose = this.selected === null ? undefined : this.shown.get(this.selected);
    if (!pose) return; // not selected, or no longer alive
    const k = this.k();
    this.ring.circle(pose.x, pose.y, this.organismRadius() + 5 / k);
    this.ring.stroke({ width: 2 / k, color: this.palette.selected });
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
    this.trailLines.stroke({ width: 1.2 / k, color: this.palette.organism, alpha: 0.28 });
  }

  /** Exactly ``count`` sprites in ``layer``: reuse, add or remove as needed. */
  private pool(layer: Container, count: number, texture: Texture): Sprite[] {
    while (layer.children.length < count) {
      const sprite = new Sprite(texture);
      sprite.anchor.set(0.5);
      layer.addChild(sprite);
    }
    while (layer.children.length > count) layer.removeChildAt(layer.children.length - 1).destroy();
    return layer.children as Sprite[];
  }

  private makeDiscTexture(colour: number): Texture {
    const g = new Graphics().circle(0, 0, TEXTURE_RADIUS).fill(colour);
    const texture = this.app.renderer.generateTexture({ target: g, resolution: 2 });
    g.destroy();
    return texture;
  }

  /** A crystal-violet disc with a pale notch toward +x: the organism's heading. */
  private makeOrganismTexture(): Texture {
    const r = TEXTURE_RADIUS;
    const g = new Graphics()
      .circle(0, 0, r)
      .fill(this.palette.organism)
      .poly([r * 0.15, -r * 0.28, r * 0.95, 0, r * 0.15, r * 0.28])
      .fill(this.palette.notch);
    const texture = this.app.renderer.generateTexture({ target: g, resolution: 2 });
    g.destroy();
    return texture;
  }
}
