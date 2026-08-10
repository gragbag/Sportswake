import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.tsx";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {/* basename comes from vite's `base`, so the router and the asset URLs
        can never drift apart. Today that is "/app/"; when React replaces the
        server-rendered pages at "/", changing vite.config.ts moves both. */}
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
