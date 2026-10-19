import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // Listen on the local network too, so http://<your-pc-ip>:5173 opens on iPhone/iPad
    host: true,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
