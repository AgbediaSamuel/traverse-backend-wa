
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react-swc';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    extensions: ['.js', '.jsx', '.ts', '.tsx', '.json'],
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  // Set base path for when served behind nginx proxy at /template/
  // This can be overridden via VITE_BASE_URL env var
  base: process.env.VITE_BASE_URL || '/',
  build: {
    target: 'esnext',
    outDir: 'build',
  },
  server: {
    port: 5174,
    host: '0.0.0.0', // Allow external connections (for ngrok)
    strictPort: false,
    hmr: {
      host: 'localhost', // HMR should use localhost
      port: 5174,
    },
    // Disable host checking for development
    watch: {
      usePolling: false,
    },
  },
  // For production builds behind proxy
  preview: {
    port: 5174,
    host: '0.0.0.0',
  },
});