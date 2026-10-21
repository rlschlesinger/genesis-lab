import type { OrganismDetail } from "../api/types";
import { useOrganismDetail } from "../hooks/useOrganismDetail";
import { useLabStore } from "../store/labStore";
import { BrainDiagram } from "./BrainDiagram";
import styles from "./SpecimenPanel.module.css";

const GENE_LABELS: Record<string, string> = {
  speed: "speed",
  sense_range: "sense range",
  max_turn: "max turn",
  metabolic_rate: "metabolism",
  reproduction_threshold: "reproduces at",
  neutral_marker: "neutral marker",
};

function number(value: number, digits = 3): string {
  return Number(value.toPrecision(digits)).toLocaleString("en");
}

/** One organism under examination: who it is, its body, its genes, and its brain. */
export function SpecimenPanel() {
  const selected = useLabStore((s) => s.selectedOrganism);
  const twoSpecies = useLabStore((s) => s.snapshot?.predators != null);
  const { detail, error } = useOrganismDetail();
  // In a world with predators, say which kind; otherwise every organism is simply one.
  const kind = !twoSpecies || detail === null ? "Organism" : detail.species === "predator" ? "Predator" : "Prey";

  return (
    <aside className={styles.specimen} aria-label="Selected organism">
      <h2 className={styles.title}>{selected === null ? "No specimen" : `${kind} ${selected}`}</h2>
      {selected === null && (
        <p className={styles.hint}>
          Select an organism on the plate to see its genome, its family and what its brain is
          deciding.
        </p>
      )}
      {selected !== null && error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
      {selected !== null && detail && <Specimen detail={detail} />}
    </aside>
  );
}

function Specimen({ detail: d }: { detail: OrganismDetail }) {
  const select = useLabStore((s) => s.selectOrganism);
  const children = d.children;
  return (
    <>
      <p className={styles.status}>
        {d.alive
          ? `Alive, ${d.age.toLocaleString("en")} ticks old`
          : `Died on tick ${d.death_tick?.toLocaleString("en")} (${(d.death_cause ?? "").replaceAll("_", " ")})`}
      </p>

      <dl className={styles.facts}>
        <div>
          <dt>Energy</dt>
          <dd className="num">{number(d.energy)}</dd>
        </div>
        <div>
          <dt>{d.species === "predator" ? "Prey caught" : "Meals"}</dt>
          <dd className="num">{d.species === "predator" ? d.prey_eaten : d.food_eaten}</dd>
        </div>
        <div>
          <dt>Generation</dt>
          <dd className="num">{d.generation}</dd>
        </div>
        <div>
          <dt>Founder</dt>
          <dd className="num">{d.founder_id}</dd>
        </div>
        <div>
          <dt>Parent</dt>
          <dd>
            {d.parent_id === null ? (
              "a founder"
            ) : (
              <button type="button" className={`num ${styles.link}`} onClick={() => select(d.parent_id)}>
                {d.parent_id}
              </button>
            )}
          </dd>
        </div>
        <div>
          <dt>Offspring</dt>
          <dd className="num">{children.length}</dd>
        </div>
      </dl>
      {children.length > 0 && (
        <p className={styles.children}>
          Children:{" "}
          {children.slice(0, 12).map((id) => (
            <button key={id} type="button" className={`num ${styles.link}`} onClick={() => select(id)}>
              {id}
            </button>
          ))}
          {children.length > 12 && ` and ${children.length - 12} more`}
        </p>
      )}

      {d.thought && d.brain_weights ? (
        <section className={styles.section}>
          <h3 className={styles.heading}>Brain, latest decision</h3>
          <BrainDiagram thought={d.thought} weights={d.brain_weights} species={d.species} />
        </section>
      ) : (
        <p className={styles.hint}>
          {d.brain_weights
            ? "No decision to show: it hasn't acted yet, or it has died."
            : "No brain: a rule decides for this organism."}
        </p>
      )}

      <section className={styles.section}>
        <h3 className={styles.heading}>Genome</h3>
        <dl className={styles.genome}>
          {Object.entries(d.genome).map(([gene, value]) => (
            <div key={gene}>
              <dt>{GENE_LABELS[gene] ?? gene}</dt>
              <dd className="num">{number(value)}</dd>
            </div>
          ))}
        </dl>
      </section>
    </>
  );
}
