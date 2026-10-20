// The camera: which part of the world the plate shows, and how big.
//
// World coordinates have their origin at the bottom-left and y pointing up (the simulation's
// convention); the screen's origin is top-left with y pointing down. Everything here converts
// between the two, so no other code has to remember the flip.
//
// A camera is a world point at the centre of the view and a zoom (1 = the whole world fits).
// It can never show anything outside the world: the centre is clamped so the view's edges
// stay inside it. Pure functions, tested without a screen.

export interface Size {
  width: number;
  height: number;
}

export interface Point {
  x: number;
  y: number;
}

export interface Camera {
  centre: Point; // world units
  zoom: number; // 1 = whole world visible
}

export const MIN_ZOOM = 1;
export const MAX_ZOOM = 12;

/** Screen pixels per world unit. */
export function pixelsPerUnit(camera: Camera, world: Size, view: Size): number {
  return Math.min(view.width / world.width, view.height / world.height) * camera.zoom;
}

export function wholeWorld(world: Size): Camera {
  return { centre: { x: world.width / 2, y: world.height / 2 }, zoom: 1 };
}

export function worldToScreen(p: Point, camera: Camera, world: Size, view: Size): Point {
  const k = pixelsPerUnit(camera, world, view);
  return {
    x: (p.x - camera.centre.x) * k + view.width / 2,
    y: (camera.centre.y - p.y) * k + view.height / 2,
  };
}

export function screenToWorld(p: Point, camera: Camera, world: Size, view: Size): Point {
  const k = pixelsPerUnit(camera, world, view);
  return {
    x: (p.x - view.width / 2) / k + camera.centre.x,
    y: camera.centre.y - (p.y - view.height / 2) / k,
  };
}

/** Keep the view inside the world (at zoom 1 that means centred). */
export function clamp(camera: Camera, world: Size, view: Size): Camera {
  const zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, camera.zoom));
  const k = pixelsPerUnit({ ...camera, zoom }, world, view);
  const halfW = Math.min(view.width / 2 / k, world.width / 2);
  const halfH = Math.min(view.height / 2 / k, world.height / 2);
  return {
    zoom,
    centre: {
      x: Math.min(world.width - halfW, Math.max(halfW, camera.centre.x)),
      y: Math.min(world.height - halfH, Math.max(halfH, camera.centre.y)),
    },
  };
}

/** Zoom by ``factor`` keeping the world point under ``screenPoint`` where it is (as maps do). */
export function zoomAt(camera: Camera, factor: number, screenPoint: Point, world: Size, view: Size): Camera {
  const anchor = screenToWorld(screenPoint, camera, world, view);
  const zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, camera.zoom * factor));
  const k = pixelsPerUnit({ ...camera, zoom }, world, view);
  const centre = {
    x: anchor.x - (screenPoint.x - view.width / 2) / k,
    y: anchor.y + (screenPoint.y - view.height / 2) / k,
  };
  return clamp({ centre, zoom }, world, view);
}

/** Move the view by a screen-pixel drag (the world follows the pointer). */
export function panBy(camera: Camera, dx: number, dy: number, world: Size, view: Size): Camera {
  const k = pixelsPerUnit(camera, world, view);
  return clamp(
    { ...camera, centre: { x: camera.centre.x - dx / k, y: camera.centre.y + dy / k } },
    world,
    view,
  );
}
