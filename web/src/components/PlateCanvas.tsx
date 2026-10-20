import { useEffect, useRef } from "react";

import type { World } from "../store/labStore";
import { useLabStore } from "../store/labStore";
import { attachWheelZoom, usePlateInput } from "../world/usePlateInput";
// Type only: the renderer (and PixiJS with it) is loaded when a plate is first shown, so the
// picker and the rest of the lab don't wait for the graphics library.
import type { PlateRenderer } from "../world/renderer";
import styles from "./PlateCanvas.module.css";

/** The live plate: a PixiJS canvas fed by the store. Selecting an organism only changes
 *  the store's selection; nothing here can reach the simulation. */
export function PlateCanvas({ world }: { world: World }) {
  const host = useRef<HTMLDivElement>(null);
  const renderer = useRef<PlateRenderer | null>(null);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let cancelled = false;
    let unsubscribe = () => {};
    // Pixi starts asynchronously; React (StrictMode in development) may unmount first.
    import("../world/renderer")
      .then(({ PlateRenderer, paletteFromCss }) => PlateRenderer.create(element, world, paletteFromCss()))
      .then((created) => {
      if (cancelled) {
        created.destroy();
        return;
      }
      renderer.current = created;
      const state = useLabStore.getState();
      if (state.snapshot) created.showSnapshot(state.snapshot);
      created.setSelected(state.selectedOrganism);
      created.setTrails(state.showTrails);
      // Follow the store without re-rendering React on every picture.
      unsubscribe = useLabStore.subscribe((next, prev) => {
        if (next.snapshot !== prev.snapshot && next.snapshot) created.showSnapshot(next.snapshot);
        if (next.selectedOrganism !== prev.selectedOrganism) created.setSelected(next.selectedOrganism);
        if (next.showTrails !== prev.showTrails) created.setTrails(next.showTrails);
      });
    });
    return () => {
      cancelled = true;
      unsubscribe();
      renderer.current?.destroy();
      renderer.current = null;
    };
  }, [world]);

  useEffect(() => (host.current ? attachWheelZoom(host.current, renderer) : undefined), []);
  const handlers = usePlateInput(renderer);

  return (
    <div
      ref={host}
      className={styles.canvas}
      tabIndex={0}
      role="application"
      aria-roledescription="culture plate"
      aria-label="The world. Drag to move, scroll or press plus and minus to zoom, 0 to fit. Click an organism, or press ] and [, to examine it."
      {...handlers}
    />
  );
}
