import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'  // 👈 Add this

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),  // 👈 Add this for v4
  ],
  server: {
    port: 3001,
    host: true,
    // @ecom/shared is installed from ../packages/shared (file: dependency),
    // so the dev server must be allowed to read the sibling package.
    fs: {
      allow: ['..'],
    },
    // Allow any ngrok tunnel (*.ngrok-free.dev, *.ngrok.io). `true`
    // disables the Host check (Vite 6+). Keep it so ngrok hostnames
    // are never blocked with "Blocked request. This host ...".
    allowedHosts: true,
    // HMR over ngrok must use the public hostname over wss, otherwise
    // the dev client falls back to localhost ws which fails behind
    // ngrok and leaves stale chunks / import errors in the console.
    // NOTE: replace with your current tunnel hostname after `ngrok http 3001`.
    hmr: {
      host: process.env.NGROK_HOST || undefined,
      protocol: process.env.NGROK_HOST ? 'wss' : undefined,
      clientPort: process.env.NGROK_HOST ? 443 : undefined,
    },
    origin: process.env.NGROK_HOST
      ? `https://${process.env.NGROK_HOST}`
      : undefined,

    // Dev-only: proxy /api to the local backend so the page and the API
    // share ONE public origin. Without this, a page loaded over ngrok
    // (https://*.ngrok-free.dev) calling http://localhost:8001 is blocked
    // by Chrome Private Network Access ("loopback address space") — the
    // request never reaches the backend no matter what CORS you set.
    // Same pattern as frontend/vite.config.js (port 5175).
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        ws: true,
      },
    },
  },
  preview: {
    port: 3001,
    host: true,
    allowedHosts: true,
  },
})
