// Checking stream messages at runtime. TypeScript types disappear when the code runs, so a
// message from a newer or older server, or a damaged one, would otherwise be trusted silently.
// These checks are cheap (a few comparisons per message, not per organism) and turn a
// mismatch into a clear error the interface can show.

import { SNAPSHOT_VERSION, type ServerMessage, type Snapshot } from "./types";

export class ProtocolError extends Error {
  override name = "ProtocolError";
}

const COLUMNS = ["id", "x", "y", "heading", "energy", "fullness", "generation", "founder"] as const;

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function parseServerMessage(text: string): ServerMessage {
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    throw new ProtocolError("the server sent something that isn't JSON");
  }
  if (!isObject(data) || typeof data.type !== "string") {
    throw new ProtocolError("message has no type");
  }
  switch (data.type) {
    case "hello":
    case "snapshot":
      if (data.version !== SNAPSHOT_VERSION) {
        throw new ProtocolError(
          `the server speaks snapshot version ${String(data.version)}; this lab understands ${SNAPSHOT_VERSION}`,
        );
      }
      if (data.type === "snapshot") checkSnapshot(data);
      return data as unknown as ServerMessage;
    case "gone":
      return data as unknown as ServerMessage;
    default:
      throw new ProtocolError(`unknown message type "${data.type}"`);
  }
}

function checkSnapshot(data: Record<string, unknown>): void {
  const organisms = data.organisms;
  const food = data.food;
  if (!isObject(organisms) || !isObject(food) || typeof data.population !== "number") {
    throw new ProtocolError("snapshot is missing organisms, food or population");
  }
  checkColumns(organisms, data.population, "organism");
  const predators = data.predators;
  if (predators !== null) {
    if (!isObject(predators) || !Array.isArray(predators.id)) {
      throw new ProtocolError("snapshot predators are neither null nor columns");
    }
    checkColumns(predators, predators.id.length, "predator");
  }
  if (!Array.isArray(data.captures)) throw new ProtocolError("snapshot captures are missing");
  if (!Array.isArray(food.x) || !Array.isArray(food.y) || food.x.length !== food.y.length) {
    throw new ProtocolError("food positions are incomplete");
  }
}

function checkColumns(columns: Record<string, unknown>, length: number, what: string): void {
  for (const column of COLUMNS) {
    const values = columns[column];
    if (!Array.isArray(values) || values.length !== length) {
      throw new ProtocolError(`${what} column "${column}" doesn't have one value per ${what}`);
    }
  }
}

export function isSnapshot(message: ServerMessage): message is Snapshot {
  return message.type === "snapshot";
}
