import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  const proxyTarget =
    process.env.VITE_DEV_API_PROXY || env.VITE_DEV_API_PROXY || "http://127.0.0.1:8001";
  return {
    plugins: [react()],
    server: {
      proxy: {
        "/tasks": proxyTarget,
      },
    },
  };
});
