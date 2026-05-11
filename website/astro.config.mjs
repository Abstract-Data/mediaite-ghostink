import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import abstractData from '@abstractdata/starlight-theme';
import starlightLinksValidator from 'starlight-links-validator';

// https://astro.build/config
export default defineConfig({
  site: 'https://abstract-data.github.io',
  base: '/mediaite-ghostink',
  trailingSlash: 'always',

  integrations: [
    starlight({
      title: 'mediaite-ghostink',
      description:
        'Hybrid forensic pipeline investigating AI writing adoption at Mediaite.com — operator and developer documentation.',

      lastUpdated: true,

      // Project-level SocialIcons override that renders TWO <VersionPicker>
      // instances (one for `/api`, one for `/cli`) — Option C versioning.
      // See `src/components/SocialIcons.astro` for the rationale.
      components: {
        SocialIcons: './src/components/SocialIcons.astro',
      },

      editLink: {
        baseUrl: 'https://github.com/Abstract-Data/mediaite-ghostink/edit/main/',
      },

      social: [
        {
          icon: 'github',
          label: 'GitHub',
          href: 'https://github.com/Abstract-Data/mediaite-ghostink',
        },
      ],

      sidebar: [
        {
          label: 'Get started',
          items: [
            { label: 'Welcome', slug: 'index' },
            { label: 'Quickstart', slug: 'getting-started' },
          ],
        },
        {
          label: 'Operator docs',
          autogenerate: { directory: 'synced' },
          collapsed: true,
        },
        {
          label: 'CLI reference',
          autogenerate: { directory: 'cli' },
          collapsed: true,
        },
        {
          label: 'Python API',
          autogenerate: { directory: 'api' },
          collapsed: true,
        },
        {
          label: 'Decision records',
          autogenerate: { directory: 'adr' },
          collapsed: true,
        },
        {
          label: 'Forensic report',
          // Use index.html so Vite dev resolves the Quarto output (public/report/)
          // the same way static hosts do; /report/ alone 404s in dev.
          link: '/report/index.html',
          attrs: { target: '_blank', rel: 'noopener' },
          badge: { text: 'Quarto', variant: 'tip' },
        },
      ],

      plugins: [
        abstractData({
          motion: 'calm',
          credit: 'auto',
        }),
        starlightLinksValidator({
          // The Quarto-rendered report at /report/ ships as static assets
          // in public/report/ — not Markdown content — so exclude it from
          // the validator (which only inspects content/docs/ Markdown).
          exclude: ['/report/**', '/mediaite-ghostink/report/**'],
        }),
      ],
    }),
  ],
});
