// REST config client (FR-GUI-004). The browser does get/set over HTTP only; the
// canon is the backend runtime_config.json. Nothing here reads or writes
// localStorage/sessionStorage — persisting config in the browser would create a
// second canon (CG-G-00e). The fetch implementation is injectable so the shell
// tests exercise get/set and blast-radius isolation without a live backend.

import { CONFIG_ENDPOINT } from "./endpoints";
import { parseConfig, type ConfigSubobjectKey, type ParsedConfig, type RuntimeConfig } from "./schema";

export type FetchLike = typeof fetch;

const JSON_HEADERS: Readonly<Record<string, string>> = {
  "Content-Type": "application/json",
};

async function readJson(response: Response): Promise<unknown> {
  if (!response.ok) {
    throw new ConfigRequestError(response.status, response.statusText);
  }
  return response.json();
}

export class ConfigRequestError extends Error {
  readonly status: number;

  constructor(status: number, statusText: string) {
    super(`config request failed: ${status} ${statusText}`);
    this.name = "ConfigRequestError";
    this.status = status;
  }
}

// GET the whole config. The response is parsed with blast-radius isolation, so a
// backend that returns one corrupt subobject still yields a usable config.
export async function fetchConfig(fetchImpl: FetchLike = fetch): Promise<ParsedConfig> {
  const response = await fetchImpl(CONFIG_ENDPOINT, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  return parseConfig(await readJson(response));
}

// PUT one subobject to its own path: the subobject IS the body, and the backend
// replaces that one and leaves the others alone, so a malformed endEffector can
// never wipe layout. What the write responds with is the backend's choice and is
// not read — the canon is re-read whole with a GET, which is the same parse a
// fresh load does. One extra round trip on an operator action, and no guess about
// a body shape this side does not own.
export async function saveSubobject<K extends ConfigSubobjectKey>(
  key: K,
  value: RuntimeConfig[K],
  fetchImpl: FetchLike = fetch,
): Promise<ParsedConfig> {
  const response = await fetchImpl(`${CONFIG_ENDPOINT}/${key}`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(value),
  });
  if (!response.ok) {
    throw new ConfigRequestError(response.status, response.statusText);
  }
  return fetchConfig(fetchImpl);
}
