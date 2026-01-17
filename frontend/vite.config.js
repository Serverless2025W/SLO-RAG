import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const VM_IP = '192.168.2.4';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/minio': {
        target: `http://${VM_IP}:9000`,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/minio/, ''),
      },
      '/openfaas': {
        target: `http://${VM_IP}:8080`,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/openfaas/, ''),
      },
      '/qdrant': {
        target: `http://${VM_IP}:6333`,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/qdrant/, ''),
      },
    },
  },
})
