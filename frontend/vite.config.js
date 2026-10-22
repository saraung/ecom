import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode }) => {
  if (mode === 'production') {
    const env = loadEnv(mode, process.cwd(), '')
    const apiUrl = process.env.VITE_API_URL || env.VITE_API_URL

    // A production build without an API origin silently bakes in the localhost
    // fallback, and every request 404s against the static host. Fail the build
    // instead so the misconfiguration is caught before deployment.
    if (!apiUrl) {
      throw new Error(
        'VITE_API_URL is required for production builds. Set it to the ' +
          'public API origin, e.g. https://api.example.com/api/v1.'
      )
    }
  }

  return {
    plugins: [
      react(),
      tailwindcss(),
    ],

    server: {
      port: 5175,
      host: true,

      // @ecom/shared is installed from ../packages/shared (file: dependency),
      // so the dev server must be allowed to read the sibling package.
      fs: {
        allow: ['..'],
      },
    },

    preview: {
      port: 5175,
      host: true,
    },
  }
})
