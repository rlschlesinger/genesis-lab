import { ChangeRun } from "./ChangeRun";
import { RunLabel } from "./RunLabel";
import { StatusLine } from "./StatusLine";
import styles from "./Masthead.module.css";
import { ViewTabs } from "./ViewTabs";

export function Masthead() {
  return (
    <header className={styles.masthead}>
      <a className={styles.skip} href="#main">
        Skip to the lab
      </a>
      <h1 className={styles.wordmark}>Genesis Lab</h1>
      <ViewTabs />
      <div className={styles.run}>
        <RunLabel />
        <StatusLine />
        <ChangeRun />
      </div>
    </header>
  );
}
