import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import path from 'path';
import Icons from 'unplugin-icons/vite'; // <--- 1. ADD THIS IMPORT

export default defineConfig({
  plugins: [
    vue(),
    // 2. ADD THIS PLUGIN BLOCK
    Icons({
      compiler: 'vue3',
      autoInstall: true
    })
  ],
  base: '/assets/van_sale/frontend/',
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 8080,
    proxy: {
      '^/(app|api|assets|files|private)': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: {
    outDir: '../van_sale/public/frontend',
    emptyOutDir: true,
    target: 'es2015',
    sourcemap: true,
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]',
      },
    },
  },
});
