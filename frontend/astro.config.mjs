// @ts-check
import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  output: 'static',
  // login.astro -> login.html (Caddy: try_files {path} {path}.html)
  build: { format: 'file' },
  vite: {
    plugins: [tailwindcss()],
    server: {
      // En desarrollo, /api se redirige al backend local.
      proxy: { '/api': 'http://127.0.0.1:8000' },
    },
  },
});
