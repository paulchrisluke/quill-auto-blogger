import { defineConfig } from 'vitest/config';
import path from 'path';

// Resolve root directory from config file location
const root = path.resolve(__dirname, '.');

export default defineConfig({
  test: {
    environment: 'node',
    globals: true,
    setupFiles: [path.resolve(root, 'tests/setup.ts')],
  },
  resolve: {
    alias: {
      '@': root,
    },
  },
});
