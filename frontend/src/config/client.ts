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

// PATCH one subobject. Only the named subobject is sent; the backend applies its
// own atomic write and blast-radius isolation and returns the new whole config,
// which is re-parsed the same way as a GET.
export async function saveSubobject<K extends ConfigSubobjectKey>(
  key: K,
  value: RuntimeConfig[K],
  fetchImpl: FetchLike = fetch,
): Promise<ParsedConfig> {
  const response = await fetchImpl(CONFIG_ENDPOINT, {
    method: "PATCH",
    headers: JSON_HEADERS,
    body: JSON.stringify({ [key]: value }),
  });
  return parseConfig(await readJson(response));
}
