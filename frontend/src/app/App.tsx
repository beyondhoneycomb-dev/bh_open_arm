// Composition root: config and the one realtime client over the browser router over the route
// tree. BrowserRouter gives clean paths (/connection, ...); the backend serves index.html as the
// SPA fallback for deep links.
//
// The realtime provider sits OUTSIDE the router. `CTR-WS@v2` D-2 permits exactly one realtime
// socket, and a provider inside the router would be rebuilt whenever navigation replaced the
// tree beneath it — one socket per screen change, each of them another stop path.

import { BrowserRouter } from "react-router-dom";

import { createDefaultWsClient } from "../ws/defaults";
import { AppRoutes } from "./AppRoutes";
import { ConfigProvider } from "./ConfigContext";
import { RealtimeProvider, type RealtimeLifecycle } from "./RealtimeContext";
import "./shell.css";

interface AppProps {
  // How the realtime client is built. Injected on the same terms as `ConfigProvider`'s
  // `fetchImpl`: the default reaches a real WebSocket and a real Worker, which no test lane may
  // do, and a host wanting another role or session supplies it at the one place a client is made.
  createRealtimeClient?: () => RealtimeLifecycle;
}

export function App({ createRealtimeClient = createDefaultWsClient }: AppProps = {}) {
  return (
    <ConfigProvider>
      <RealtimeProvider createClient={createRealtimeClient}>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </RealtimeProvider>
    </ConfigProvider>
  );
}
