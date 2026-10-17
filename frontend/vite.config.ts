import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // WARDEN_API lets a second dev copy (e.g. :8001) run next to one on :8000.
    proxy: { "/api": process.env.WARDEN_API ?? "http://127.0.0.1:8000" },
  },
});
