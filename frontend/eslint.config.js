// ESLint 10 flat config with the rules that have teeth (playbook 2.3, 6.4,
// 6.6, 6.7, 8.3). Every custom rule below names the section it enforces.
import nextPlugin from '@next/eslint-plugin-next';
import reactPlugin from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import tseslint from 'typescript-eslint';

// 6.4: the numbered font scale is gone. Any legacy or one-off size in a
// string literal, template literal or cva variant fails the build.
const LEGACY_FONT_SIZE = /(^|[\s"'`:!])text-(xs|sm|base|lg|xl|\dxl|\[[^\]]*px\])(?=$|[\s"'`])/;

const COPY_PROPS = new Set(['aria-label', 'aria-description', 'aria-placeholder', 'aria-roledescription', 'aria-valuetext', 'placeholder', 'title', 'alt', 'label']);

const bleqq = {
  rules: {
    // 6.7: no raw pill markup outside Pill.tsx.
    'no-raw-pill': {
      meta: { type: 'problem', docs: { description: 'Pills only through <Pill> (playbook 6.7)' }, schema: [] },
      create(context) {
        if (/[\\/]components[\\/]ui[\\/]Pill\.tsx$/.test(context.filename)) return {};
        return {
          JSXOpeningElement(node) {
            for (const attr of node.attributes) {
              if (attr.type !== 'JSXAttribute' || attr.name.type !== 'JSXIdentifier') continue;
              const name = attr.name.name;
              if (name === 'data-pill') {
                context.report({ node: attr, message: 'Raw pill markup: render <Pill tone=…> instead (playbook 6.7).' });
              }
              if (name === 'className' && attr.value && attr.value.type === 'Literal' && /pill/i.test(String(attr.value.value))) {
                context.report({ node: attr, message: 'A "pill" class outside Pill.tsx: render <Pill tone=…> instead (playbook 6.7).' });
              }
            }
          },
        };
      },
    },
    // 6.5: no user-facing string in a component. jsx-no-literals covers JSX
    // text; this covers the props that carry copy (aria-label, placeholder,
    // title, alt, label).
    'no-literal-copy-props': {
      meta: { type: 'problem', docs: { description: 'Copy-bearing props must come from the message catalog (playbook 6.5)' }, schema: [] },
      create(context) {
        return {
          JSXAttribute(node) {
            if (node.name.type !== 'JSXIdentifier' || !COPY_PROPS.has(node.name.name) || !node.value) return;
            const v = node.value;
            const literal =
              (v.type === 'Literal' && typeof v.value === 'string') ||
              (v.type === 'JSXExpressionContainer' &&
                ((v.expression.type === 'Literal' && typeof v.expression.value === 'string') ||
                  (v.expression.type === 'TemplateLiteral' && v.expression.quasis.some((q) => q.value.raw.trim().length > 0))));
            if (literal) {
              context.report({ node, message: `"${node.name.name}" carries copy: use t('…') from the message catalog (playbook 6.5).` });
            }
          },
        };
      },
    },
  },
};

const LEGACY_FONT_MESSAGE = 'Numbered or one-off font size. Use the named scale: text-hero, text-display, text-title, text-body, text-meta or .microlabel (playbook 6.4).';

export default tseslint.config(
  {
    ignores: ['node_modules/**', '.next/**', 'out/**', 'coverage/**', 'playwright-report/**', 'test-results/**', 'next-env.d.ts', 'src/types/api.generated.ts'],
  },
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx,js,mjs}'],
    plugins: { '@next/next': nextPlugin, react: reactPlugin, 'react-hooks': reactHooks, bleqq },
    rules: {
      ...nextPlugin.configs.recommended.rules,
      ...reactHooks.configs.flat.recommended.rules,
      // 6.6: never console.log; the logger is the one exception (override below).
      'no-console': 'error',
      // 6.4: legacy font sizes, in string literals, template literals and cva variants.
      'no-restricted-syntax': [
        'error',
        { selector: `Literal[value=${LEGACY_FONT_SIZE.toString()}]`, message: LEGACY_FONT_MESSAGE },
        { selector: `TemplateElement[value.raw=${LEGACY_FONT_SIZE.toString()}]`, message: LEGACY_FONT_MESSAGE },
      ],
      'bleqq/no-raw-pill': 'error',
      '@typescript-eslint/consistent-type-imports': ['error', { fixStyle: 'inline-type-imports' }],
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
    },
  },
  {
    // 6.5: no string literal in JSX text. `ignoreProps: true` because the
    // plugin would otherwise flag every className, href and type prop (and
    // every string literal in a .tsx file); copy-bearing props are covered
    // by bleqq/no-literal-copy-props instead.
    files: ['src/**/*.tsx'],
    ignores: ['src/**/*.test.tsx'],
    rules: {
      'react/jsx-no-literals': ['error', { noStrings: true, ignoreProps: true, noAttributeStrings: false, allowedStrings: [] }],
      'bleqq/no-literal-copy-props': 'error',
    },
  },
  {
    // 6.7: pill-tones is imported only where tones are mapped, never in a screen.
    files: ['src/**/*.{ts,tsx}'],
    ignores: ['src/components/ui/**', 'src/features/**/*-presentation.ts', 'src/features/shared/**', 'src/**/*.test.{ts,tsx}'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['**/pill-tones', '**/pill-tones.ts', '@/components/ui/pill-tones'],
              message: 'Tones are chosen by slot or kind in a *-presentation.ts, never in a screen (playbook 6.7).',
            },
          ],
        },
      ],
    },
  },
  {
    // 8.3: every E2E spec imports `test` from support/api-guard.
    files: ['tests/e2e/**/*.spec.ts'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          paths: [
            {
              name: '@playwright/test',
              importNames: ['test'],
              message: "Import { test } from './support/api-guard' so undeclared API failures fail the journey (playbook 8.3).",
            },
          ],
        },
      ],
    },
  },
  {
    files: ['src/shared/utils/logger.ts'],
    rules: { 'no-console': 'off' },
  },
  {
    files: ['scripts/**/*.mjs', 'tests/e2e/support/**/*.ts'],
    rules: { 'no-console': 'off' },
  },
);
