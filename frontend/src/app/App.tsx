// Composition root: config provider over the browser router over the route tree.
// BrowserRouter gives clean paths (/connection, ...); the backend serves
// index.html as the SPA fallback for deep links.

import { BrowserRouter } from "react-router-dom";

import { ConfigProvider } from "./ConfigContext";
import { AppRoutes } from "./AppRoutes";
import "./shell.css";

export function App() {
  return (
    <ConfigProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </ConfigProvider>
  );
}
