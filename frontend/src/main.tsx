import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.tsx";
import { AuthProvider } from "./lib/AuthProvider";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {/* basename comes from vite's `base`, so the router and the asset URLs
        can never drift apart. Today that is "/app/"; when React replaces the
        server-rendered pages at "/", changing vite.config.ts moves both. */}
    {/* AuthProvider inside the router so auth-aware components can navigate,
        and outside <App /> so the header and every route share one session. */}
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
