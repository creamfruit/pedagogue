import { defineConfig, loadEnv } from "vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.VITE_API_URL || "http://localhost:8000";

  return {
    server: {
      port: 5173,
      proxy: {
        "/api": { target: apiTarget, changeOrigin: true },
        "/health": { target: apiTarget, changeOrigin: true },
      },
    },
    build: {
      outDir: "dist",
      sourcemap: true,
    },
    plugins: [
      VitePWA({
        registerType: "prompt",
        injectRegister: null,
        includeAssets: ["icons/favicon.svg", "icons/apple-touch-icon.png"],
        manifest: {
          name: "Piano Pedagogue",
          short_name: "Pedagogue",
          description: "Your repertoire, your weaknesses, your route to the next piece.",
          theme_color: "#08090a",
          background_color: "#08090a",
          display: "standalone",
          orientation: "any",
          start_url: "/",
          scope: "/",
          categories: ["education", "music", "productivity"],
          icons: [
            { src: "icons/icon-192.png", sizes: "192x192", type: "image/png" },
            { src: "icons/icon-512.png", sizes: "512x512", type: "image/png" },
            {
              src: "icons/icon-512-maskable.png",
              sizes: "512x512",
              type: "image/png",
              purpose: "maskable",
            },
          ],
        },
        workbox: {
          globPatterns: ["**/*.{js,css,html,svg,png,woff2}"],
          navigateFallback: "index.html",
          navigateFallbackDenylist: [/^\/api/, /^\/health/],
          cleanupOutdatedCaches: true,
          clientsClaim: true,
          runtimeCaching: [
            {
              urlPattern: ({ url }) => url.pathname.startsWith("/api/v1/catalog"),
              handler: "StaleWhileRevalidate",
              options: {
                cacheName: "catalog",
                expiration: { maxEntries: 200, maxAgeSeconds: 60 * 60 * 24 * 30 },
                cacheableResponse: { statuses: [0, 200] },
              },
            },
            {
              urlPattern: ({ url }) =>
                url.pathname.startsWith("/api/v1/repertoire") ||
                url.pathname.startsWith("/api/v1/progression") ||
                url.pathname.startsWith("/api/v1/onboarding"),
              handler: "NetworkFirst",
              options: {
                cacheName: "app-data",
                networkTimeoutSeconds: 5,
                expiration: { maxEntries: 120, maxAgeSeconds: 60 * 60 * 24 },
                cacheableResponse: { statuses: [0, 200] },
              },
            },
            {
              urlPattern: ({ url }) => url.origin === "https://fonts.googleapis.com",
              handler: "StaleWhileRevalidate",
              options: { cacheName: "google-fonts-stylesheets" },
            },
            {
              urlPattern: ({ url }) => url.origin === "https://fonts.gstatic.com",
              handler: "CacheFirst",
              options: {
                cacheName: "google-fonts-webfonts",
                expiration: { maxEntries: 20, maxAgeSeconds: 60 * 60 * 24 * 365 },
                cacheableResponse: { statuses: [0, 200] },
              },
            },
          ],
        },
        devOptions: { enabled: false, type: "module" },
      }),
    ],
  };
});
