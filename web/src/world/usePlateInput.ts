// Pointer, wheel and keyboard on the plate: drag to pan, wheel to zoom about the cursor,
// click to select, double-click to fit the whole world. Keyboard: + and - zoom, arrows pan,
// 0 fits, ] and [ step through organisms by ID, Escape clears the selection.
//
// A press that moves less than CLICK_SLOP pixels is a click (select); more is a drag (pan).

import { type KeyboardEvent, type PointerEvent, type RefObject, useMemo, useRef } from "react";

import { useLabStore } from "../store/labStore";
import { stepSelection } from "./hitTest";
import type { PlateRenderer } from "./renderer";

const CLICK_SLOP = 4;
const KEY_ZOOM = 1.25;
const KEY_PAN = 40; // screen pixels

export function usePlateInput(renderer: RefObject<PlateRenderer | null>) {
  const drag = useRef<{ x: number; y: number; moved: number } | null>(null);

  return useMemo(() => {
    const local = (e: { clientX: number; clientY: number; currentTarget: Element }) => {
      const box = e.currentTarget.getBoundingClientRect();
      return { x: e.clientX - box.left, y: e.clientY - box.top };
    };
    return {
      onPointerDown(e: PointerEvent<HTMLDivElement>) {
        e.currentTarget.setPointerCapture(e.pointerId);
        drag.current = { x: e.clientX, y: e.clientY, moved: 0 };
      },
      onPointerMove(e: PointerEvent<HTMLDivElement>) {
        const d = drag.current;
        if (!d) return;
        const dx = e.clientX - d.x;
        const dy = e.clientY - d.y;
        d.moved += Math.abs(dx) + Math.abs(dy);
        d.x = e.clientX;
        d.y = e.clientY;
        if (d.moved > CLICK_SLOP) renderer.current?.pan(dx, dy);
      },
      onPointerUp(e: PointerEvent<HTMLDivElement>) {
        const d = drag.current;
        drag.current = null;
        if (d && d.moved <= CLICK_SLOP && renderer.current) {
          useLabStore.getState().selectOrganism(renderer.current.pick(local(e)));
        }
      },
      onPointerCancel() {
        drag.current = null;
      },
      onDoubleClick() {
        renderer.current?.resetView();
      },
      onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
        const r = renderer.current;
        if (!r) return;
        const store = useLabStore.getState();
        const actions: Record<string, () => void> = {
          "+": () => r.zoom(KEY_ZOOM),
          "=": () => r.zoom(KEY_ZOOM),
          "-": () => r.zoom(1 / KEY_ZOOM),
          "0": () => r.resetView(),
          ArrowLeft: () => r.pan(KEY_PAN, 0),
          ArrowRight: () => r.pan(-KEY_PAN, 0),
          ArrowUp: () => r.pan(0, KEY_PAN),
          ArrowDown: () => r.pan(0, -KEY_PAN),
          "]": () => store.selectOrganism(stepSelection(r.organismIds, store.selectedOrganism, 1)),
          "[": () => store.selectOrganism(stepSelection(r.organismIds, store.selectedOrganism, -1)),
          Escape: () => store.selectOrganism(null),
        };
        const action = actions[e.key];
        if (action) {
          e.preventDefault();
          action();
        }
      },
    };
  }, [renderer]);
}

/** Zoom with the wheel, about the cursor. Attached by hand: React's wheel listeners are
 *  "passive" and can't stop the page scrolling at the same time. */
export function attachWheelZoom(element: HTMLElement, renderer: RefObject<PlateRenderer | null>) {
  const onWheel = (e: WheelEvent) => {
    e.preventDefault();
    const box = element.getBoundingClientRect();
    renderer.current?.zoom(Math.exp(-e.deltaY * 0.0015), {
      x: e.clientX - box.left,
      y: e.clientY - box.top,
    });
  };
  element.addEventListener("wheel", onWheel, { passive: false });
  return () => element.removeEventListener("wheel", onWheel);
}
