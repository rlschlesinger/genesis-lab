import styles from "./EmptyView.module.css";

/** A view with nothing to show yet: say what would fill it. */
export function EmptyView({ message }: { message: string }) {
  return <p className={styles.empty}>{message}</p>;
}
