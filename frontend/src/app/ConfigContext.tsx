// Shared runtime-config state for the whole SPA. Config is cross-cutting shell
// state (layout, theme, presets), so it lives in one Context read by every
// screen rather than a per-component hook that would fetch it many times. The
// canon is the backend; this holds the in-memory copy and the REST get/set path,
// and never persists to localStorage (CG-G-00e).

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { fetchConfig, saveSubobject, type FetchLike } from "../config/client";
import {
  defaultConfig,
  type ConfigSubobjectKey,
  type RuntimeConfig,
} from "../config/schema";

export type ConfigStatus = "loading" | "ready" | "error";

export interface ConfigContextValue {
  config: RuntimeConfig;
  status: ConfigStatus;
  // Subobjects the last load/save replaced with defaults because the backend
  // returned them malformed (CG-G-00d). Empty on a clean round-trip.
  defaulted: ConfigSubobjectKey[];
  reload: () => Promise<void>;
  save: <K extends ConfigSubobjectKey>(key: K, value: RuntimeConfig[K]) => Promise<void>;
}

const ConfigContext = createContext<ConfigContextValue | null>(null);

interface ConfigProviderProps {
  children: ReactNode;
  // Injectable for tests; defaults to the global fetch in the browser.
  fetchImpl?: FetchLike;
}

export function ConfigProvider({ children, fetchImpl }: ConfigProviderProps) {
  const [config, setConfig] = useState<RuntimeConfig>(defaultConfig);
  const [status, setStatus] = useState<ConfigStatus>("loading");
  const [defaulted, setDefaulted] = useState<ConfigSubobjectKey[]>([]);
  const fetchRef = useRef<FetchLike | undefined>(fetchImpl);
  fetchRef.current = fetchImpl;

  const reload = useCallback(async () => {
    setStatus("loading");
    try {
      const parsed = await fetchConfig(fetchRef.current ?? fetch);
      setConfig(parsed.config);
      setDefaulted(parsed.defaulted);
      setStatus("ready");
    } catch {
      setStatus("error");
    }
  }, []);

  const save = useCallback(
    async <K extends ConfigSubobjectKey>(key: K, value: RuntimeConfig[K]) => {
      const parsed = await saveSubobject(key, value, fetchRef.current ?? fetch);
      setConfig(parsed.config);
      setDefaulted(parsed.defaulted);
    },
    [],
  );

  useEffect(() => {
    void reload();
  }, [reload]);

  const value = useMemo<ConfigContextValue>(
    () => ({ config, status, defaulted, reload, save }),
    [config, status, defaulted, reload, save],
  );

  return <ConfigContext.Provider value={value}>{children}</ConfigContext.Provider>;
}

export function useConfig(): ConfigContextValue {
  const value = useContext(ConfigContext);
  if (!value) {
    throw new Error("useConfig must be used within a ConfigProvider");
  }
  return value;
}
