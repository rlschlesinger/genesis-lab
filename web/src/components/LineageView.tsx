import type { LineageNode } from "../api/types";
import { useLineage } from "../hooks/useLineage";
import { useLabStore } from "../store/labStore";
import styles from "./LineageView.module.css";
import { SpecimenPanel } from "./SpecimenPanel";

function life(node: LineageNode): string {
  const born = `born tick ${node.birth_tick.toLocaleString("en")}`;
  return node.alive ? `${born}, alive` : `${born}, died tick ${node.death_tick?.toLocaleString("en")}`;
}

function NodeButton({ node, current }: { node: LineageNode; current: boolean }) {
  const select = useLabStore((s) => s.selectOrganism);
  return (
    <button
      type="button"
      className={styles.node}
      data-alive={node.alive}
      aria-current={current ? "true" : undefined}
      onClick={() => select(node.id)}
    >
      <span className="num">{node.id}</span>
      <span className={styles.nodeMeta}>
        generation <span className="num">{node.generation}</span>, {life(node)}
      </span>
    </button>
  );
}

function Descendants({ node }: { node: LineageNode }) {
  if (node.children.length === 0 && node.hidden_children === 0) return null;
  return (
    <ul className={styles.children}>
      {node.children.map((child) => (
        <li key={child.id}>
          <NodeButton node={child} current={false} />
          <Descendants node={child} />
        </li>
      ))}
      {node.hidden_children > 0 && (
        <li className={styles.hidden}>
          and <span className="num">{node.hidden_children}</span> more{" "}
          {node.hidden_children === 1 ? "child" : "children"} (select one shown to go deeper)
        </li>
      )}
    </ul>
  );
}

/** The selected organism's family: its line back to its founder, and the family below it.
 *  Every organism is a button: selecting it re-centres the view and the specimen panel. */
export function LineageView() {
  const runId = useLabStore((s) => s.runId);
  const selected = useLabStore((s) => s.selectedOrganism);
  const { lineage, error } = useLineage();

  if (runId === null || selected === null) {
    return (
      <p className={styles.empty}>
        Select an organism on the World view to trace its family here.
      </p>
    );
  }
  return (
    <div className={styles.lineage}>
      <div className={styles.tree}>
        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}
        {lineage && (
          <>
            <p className={styles.summary}>
              Founder <span className="num">{lineage.founder_id}</span>'s family:{" "}
              <span className="num">{lineage.founder_family.toLocaleString("en")}</span> born,{" "}
              <span className="num">{lineage.founder_family_alive.toLocaleString("en")}</span> alive now.
              Organism <span className="num">{lineage.organism.id}</span> has{" "}
              <span className="num">{lineage.descendants.toLocaleString("en")}</span>{" "}
              {lineage.descendants === 1 ? "descendant" : "descendants"}.
            </p>
            <section aria-label="Ancestors">
              <h2 className={styles.heading}>Line of descent</h2>
              {lineage.ancestors.length === 0 ? (
                <p className={styles.note}>A founder: it has no ancestors in this run.</p>
              ) : (
                <ol className={styles.line}>
                  {lineage.ancestors.map((a) => (
                    <li key={a.id}>
                      <NodeButton node={a} current={false} />
                    </li>
                  ))}
                </ol>
              )}
            </section>
            <section aria-label="Descendants">
              <h2 className={styles.heading}>Organism and descendants</h2>
              <div className={styles.root}>
                <NodeButton node={lineage.organism} current />
                <Descendants node={lineage.organism} />
              </div>
              <p className={styles.note}>Three generations down, up to twelve children each.</p>
            </section>
          </>
        )}
      </div>
      <SpecimenPanel />
    </div>
  );
}
