// What each connection state is called on screen.
import type { LabState } from "../store/labStore";

export const STATUS_TEXT: Record<LabState["status"], string> = {
  idle: "Not watching a run",
  connecting: "Connecting",
  live: "Live",
  reconnecting: "Reconnecting",
  gone: "This run no longer exists",
  error: "Can't read this run's stream",
  closed: "Stopped watching",
};
