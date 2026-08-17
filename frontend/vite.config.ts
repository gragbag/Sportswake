import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Tailwind v4 is a Vite plugin -- no tailwind.config.js, no PostCSS step.
// Configuration lives in src/index.css via @theme.
export default defineConfig({
  plugins: [react(), tailwindcss()],

  // The brief IS the site now, so the app serves from the root and FastAPI
  // mounts it there. Also becomes import.meta.env.BASE_URL, which the router
  // uses as its basename, so the two can never disagree -- moving the app
  // again is a change to this one line.
  base: "/",

  // Read the repo-root .env instead of frontend/.env, so there is one env
  // file for the whole project. Only VITE_-prefixed variables are exposed to
  // browser code -- DATABASE_URL and GROQ_API_KEY are loaded but never
  // bundled. The corollary is a rule: never prefix a secret with VITE_.
  envDir: "..",

  server: {
    // Dev only. The FastAPI app runs separately on 8000; proxying /api keeps
    // the browser on one origin so there is no CORS to configure.
    //   terminal 1:  make api
    //   terminal 2:  make web
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },

  build: {
    // FastAPI serves this directory in production, so the whole thing ships
    // as one Render service on one URL.
    outDir: "dist",
    emptyOutDir: true,
  },
});
