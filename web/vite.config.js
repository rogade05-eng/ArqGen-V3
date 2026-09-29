import { defineConfig } from 'vite';

export default defineConfig({
  base: './',
  server: { host: '0.0.0.0', strictPort: true, allowedHosts: true,
    watch: { ignored: ['**/src-tauri/**'] }, fs: { allow: ['..'] } },
  preview: { host: '0.0.0.0', allowedHosts: true },
  build: { outDir: '../dist/web', emptyOutDir: true },
});
