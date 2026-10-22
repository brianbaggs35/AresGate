import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript'
import prettier from 'eslint-config-prettier'
import playwright from 'eslint-plugin-playwright'
import pluginVue from 'eslint-plugin-vue'

export default defineConfigWithVueTs(
  { name: 'aresgate/files', files: ['**/*.{ts,mts,vue}'] },
  {
    name: 'aresgate/ignores',
    ignores: ['dist/**', 'coverage/**', 'e2e-results/**', 'node_modules/**'],
  },
  pluginVue.configs['flat/recommended'],
  vueTsConfigs.strictTypeChecked,
  {
    name: 'aresgate/rules',
    rules: {
      'vue/multi-word-component-names': ['error', { ignores: ['App'] }],
      'vue/block-lang': ['error', { script: { lang: 'ts' } }],
      'vue/component-api-style': ['error', ['script-setup']],
      '@typescript-eslint/restrict-template-expressions': ['error', { allowNumber: true }],
    },
  },
  {
    name: 'aresgate/tests',
    files: ['src/**/*.spec.ts', 'src/test/**', 'e2e/**'],
    rules: {
      '@typescript-eslint/no-non-null-assertion': 'off',
      '@typescript-eslint/no-empty-function': 'off',
    },
  },
  {
    ...playwright.configs['flat/recommended'],
    name: 'aresgate/e2e',
    files: ['e2e/**'],
    settings: {
      // Specs use the fixtures from e2e/support, which extend Playwright's test and expect.
      playwright: { globalAliases: { test: ['test'], expect: ['expect'] } },
    },
    rules: {
      ...playwright.configs['flat/recommended'].rules,
      'playwright/expect-expect': [
        'error',
        { assertFunctionNames: ['expect', 'expectAccessible', 'expectTheme'] },
      ],
    },
  },
  prettier,
)
