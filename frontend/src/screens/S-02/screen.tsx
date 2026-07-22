// S-02 screen entry point (the seam WP-G-00 discovers via import.meta.glob). The
// screen owns two routes — /connection and /home-zero (13 §2.6) — mounted by the
// same component; this default export reads the active path and renders the
// matching view of ConnectionScreen. It supplies the offline default source (the
// WP is AI-offline); the shell later injects a backend-derived source.

import { useLocation } from "react-router-dom";

import "./screen.css";
import { ConnectionScreen, type ConnectionRoute } from "./ConnectionScreen";
import { HOME_ZERO_ROUTE } from "./constants";

export default function S02ConnectionScreen() {
  const location = useLocation();
  const route: ConnectionRoute =
    location.pathname === HOME_ZERO_ROUTE ? HOME_ZERO_ROUTE : "/connection";
  return <ConnectionScreen route={route} />;
}
