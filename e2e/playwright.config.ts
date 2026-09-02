import { defineConfig, devices } from '@playwright/test'
import { TARGETS } from './urls'
import path from 'path'

export default defineConfig({
  testDir: './specs',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 2,
  retries: 0,
  globalSetup: require.resolve('./global-setup.ts'),
  reporter: [
    ['list'],
    ['json', { outputFile: 'artifacts/results.json' }],
    ['html', { outputFolder: 'artifacts/html', open: 'never' }],
  ],
  use: {
    ignoreHTTPSErrors: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    actionTimeout: 20_000,
    navigationTimeout: 60_000,
  },
  projects: [
    {
      name: 'platform',
      testMatch: /platform-.*\.spec\.ts/,
      use: { ...devices['Desktop Chrome'], baseURL: TARGETS.platform.base,
             storageState: path.join(__dirname, '.auth/platform.json') },
    },
    {
      name: 'klara',
      testMatch: /klara-.*\.spec\.ts/,
      use: { ...devices['Desktop Chrome'], baseURL: TARGETS.klara.base,
             storageState: path.join(__dirname, '.auth/klara.json') },
    },
    {
      name: 'agency',
      testMatch: /agency-.*\.spec\.ts/,
      use: { ...devices['Desktop Chrome'], baseURL: TARGETS.agency.base,
             storageState: path.join(__dirname, '.auth/agency.json') },
    },
  ],
})
