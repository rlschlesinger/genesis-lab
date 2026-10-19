// Connects the store to a run's stream while a run is being watched. The connection itself
// (and its reconnection rules) lives in connection.ts; this hook only starts and stops it.

import { useEffect } from "react";

import { useLabStore } from "../store/labStore";
import { StreamConnection } from "./connection";

export function useRunStream(fps = 15): void {
  // Restart only when the user picks a run. When a run is reset, the connection follows the
  // new run by itself and updates runId; restarting here would open a second socket.
  const subscription = useLabStore((s) => s.subscription);

  useEffect(() => {
    const store = useLabStore.getState();
    if (store.runId === null) return;
    const connection = new StreamConnection(
      store.runId,
      {
        onHello: store.receiveHello,
        onSnapshot: store.receiveSnapshot,
        onStatus: store.setStatus,
        onRunReplaced: store.runReplaced,
      },
      { fps },
    );
    connection.start();
    return () => connection.close();
  }, [subscription, fps]);
}
