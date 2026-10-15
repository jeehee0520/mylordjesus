import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// GitHub Pages 프로젝트 사이트: https://jeehee0520.github.io/mylordjesus/
export default defineConfig({
  base: '/mylordjesus/',
  plugins: [react()],
  test: { environment: 'node', include: ['tests/**/*.test.ts'] },
});
