import { useLabStore } from "../store/labStore";

/** The plate in words, for screen readers (the canvas itself is hidden from them). Updated
 *  only when the tick's hundreds change or the selection changes, so it doesn't chatter. */
export function PlateSummary() {
  const population = useLabStore((s) => s.snapshot?.population ?? 0);
  const predators = useLabStore((s) => s.snapshot?.predators?.id.length ?? null);
  const food = useLabStore((s) => s.snapshot?.food.x.length ?? 0);
  const hundreds = useLabStore((s) => Math.floor((s.snapshot?.tick ?? 0) / 100) * 100);
  const selected = useLabStore((s) => s.selectedOrganism);
  // Name the species from the picture itself, so the word is right before any detail arrives.
  const selectedIsPredator = useLabStore(
    (s) => s.selectedOrganism !== null && (s.snapshot?.predators?.id.includes(s.selectedOrganism) ?? false),
  );
  const word = predators === null ? "Organism" : selectedIsPredator ? "Predator" : "Prey";
  return (
    <p className="visually-hidden">
      Around tick {hundreds}:{" "}
      {predators === null
        ? `${population} organisms`
        : `${population} prey, ${predators} ${predators === 1 ? "predator" : "predators"}`}{" "}
      and{" "}
      {food} food items.
      {selected !== null && ` ${word} ${selected} is selected.`}
    </p>
  );
}
