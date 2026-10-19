import { describe, expect, it } from "vitest";

import snapshot from "./__fixtures__/snapshot.json";
import { ProtocolError, parseServerMessage } from "./parse";

const text = (value: unknown) => JSON.stringify(value);

describe("parseServerMessage refuses what the lab can't trust", () => {
  it.each([
    ["not JSON", "{oops", "isn't JSON"],
    ["no type", text({ version: 1 }), "has no type"],
    ["an unknown type", text({ type: "surprise" }), 'unknown message type "surprise"'],
    ["another protocol version", text({ ...snapshot, version: 2 }), "snapshot version 2"],
    [
      "a column with the wrong length",
      text({ ...snapshot, organisms: { ...snapshot.organisms, x: [1] } }),
      'column "x"',
    ],
    ["food positions that don't pair up", text({ ...snapshot, food: { x: [1, 2], y: [1] } }), "food"],
  ])("%s", (_case, message, reason) => {
    expect(() => parseServerMessage(message)).toThrow(ProtocolError);
    expect(() => parseServerMessage(message)).toThrow(reason);
  });

  it("accepts a real snapshot unchanged", () => {
    expect(parseServerMessage(text(snapshot))).toEqual(snapshot);
  });
});
