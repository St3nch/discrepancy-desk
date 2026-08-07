import { defineConfig } from "vite";

export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      "/api": {
        // Desk default is 8000; if another process holds it, start uvicorn on 8001
        // and set VITE_API_PROXY_TARGET. F-51: wrong process on 8000 yields HTML.
        target: process.env.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
