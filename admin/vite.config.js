import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],

  server: {
    port: 3001,
    host: true,

    // @ecom/shared is installed from ../packages/shared (file: dependency),
    // so the dev server must be allowed to read the sibling package.
    fs: {
      allow: ['..'],
    },
  },

  preview: {
    port: 3001,
    host: true,
  },
})
