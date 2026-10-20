import { useLabStore } from "../store/labStore";

/** The plate in words, for screen readers (the canvas itself is hidden from them). Updated
 *  only when the tick's hundreds change or the selection changes, so it doesn't chatter. */
export function PlateSummary() {
  const population = useLabStore((s) => s.snapshot?.population ?? 0);
  const food = useLabStore((s) => s.snapshot?.food.x.length ?? 0);
  const hundreds = useLabStore((s) => Math.floor((s.snapshot?.tick ?? 0) / 100) * 100);
  const selected = useLabStore((s) => s.selectedOrganism);
  return (
    <p className="visually-hidden">
      Around tick {hundreds}: {population} organisms and {food} food items.
      {selected !== null && ` Organism ${selected} is selected.`}
    </p>
  );
}
