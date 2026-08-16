import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5178, // 前端开发服务器端口
    strictPort: true, // 端口被占用时报错而非自动换号
    // 开发环境代理：前端请求 /api 转发到后端 FastAPI（8016 端口）
    proxy: {
      '/api': {
        target: 'http://localhost:8016',
        changeOrigin: true,
      },
    },
  },
})
