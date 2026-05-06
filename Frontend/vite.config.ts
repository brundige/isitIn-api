import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

const BASE = "/is-it-in/";

export default defineConfig({
  base: BASE,
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: [
        "favicon.svg",
        "apple-touch-icon.png",
        "icon-192.png",
        "icon-512.png",
        "icon-maskable-512.png",
      ],
      manifest: {
        name: "Is It In?",
        short_name: "IsItIn",
        description: "Whitewater conditions and forecasts at a glance.",
        theme_color: "#0d1514",
        background_color: "#0d1514",
        display: "standalone",
        orientation: "portrait",
        start_url: BASE,
        scope: BASE,
        id: BASE,
        icons: [
          { src: `${BASE}icon-192.png`, sizes: "192x192", type: "image/png" },
          { src: `${BASE}icon-512.png`, sizes: "512x512", type: "image/png" },
          {
            src: `${BASE}icon-maskable-512.png`,
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,png,ico}"],
        // Deep-link refreshes inside the SPA must fall back to index.html.
        navigateFallback: `${BASE}index.html`,
        // Don't intercept navigations to anything outside the PWA scope —
        // the API (and the bare-domain root) shouldn't be hijacked.
        navigateFallbackDenylist: [/^\/(?!is-it-in\/)/],
        runtimeCaching: [
          {
            // API lives on a different origin (api.brundigital.io); match by host.
            urlPattern: ({ url }) =>
              url.hostname === "api.brundigital.io" && url.pathname.startsWith("/rivers"),
            handler: "NetworkFirst",
            options: {
              cacheName: "api-rivers",
              networkTimeoutSeconds: 5,
              expiration: { maxEntries: 50, maxAgeSeconds: 60 * 30 },
            },
          },
        ],
      },
    }),
  ],
  server: { host: true, port: 5173 },
});
