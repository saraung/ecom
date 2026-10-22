import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],

  server: {
    port: 5175,
    host: true,
    allowedHosts: true,

    // @ecom/shared is installed from ../packages/shared (file: dependency),
    // so the dev server must be allowed to read the sibling package.
    fs: {
      allow: ['..'],
    },

    // HMR over ngrok must use the public hostname over wss, otherwise
    // the dev client falls back to localhost ws which fails behind
    // ngrok and leaves stale chunks / import errors in the console.
    // Set NGROK_HOST=deliverer-powdering-affiliate.ngrok-free.dev when
    // serving dev through ngrok.
    hmr: {
      host: process.env.NGROK_HOST || undefined,
      protocol: process.env.NGROK_HOST ? 'wss' : undefined,
      clientPort: process.env.NGROK_HOST ? 443 : undefined,
    },
    origin: process.env.NGROK_HOST
      ? `https://${process.env.NGROK_HOST}`
      : undefined,

    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        ws: true,
      },
    },
  },
  preview: {
    port: 5175,
    host: true,
    allowedHosts: true,
  },
})