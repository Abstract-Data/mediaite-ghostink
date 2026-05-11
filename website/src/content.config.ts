import { defineCollection, z } from 'astro:content';
import { docsLoader } from '@astrojs/starlight/loaders';
import { docsSchema } from '@astrojs/starlight/schema';

/**
 * Type-safe frontmatter for the docs collection.
 *
 * `docsSchema({ extend })` lets you add custom fields on top of Starlight's
 * built-in ones (`title`, `description`, `sidebar`, `draft`, `pagefind`, …).
 * The fields below are scaffolding — keep, replace, or extend them to match
 * how your team actually tags content. Errors in frontmatter fail the build
 * with helpful Zod messages, so this catches issues at PR time instead of
 * after deploy.
 *
 * Common fields teams add:
 *   - `category`: a grouping label for filterable views or future analytics
 *   - `audience`: who this page is written for
 *   - `lastReviewed`: when a maintainer last vetted the content (good for
 *     surfacing "this page is over a year old" warnings)
 */
export const collections = {
  docs: defineCollection({
    loader: docsLoader(),
    schema: docsSchema({
      extend: z.object({
        // ── User-authored fields ───────────────────────────────────
        category: z.string().optional(),
        audience: z
          .enum(['user', 'contributor', 'maintainer'])
          .optional(),
        lastReviewed: z.coerce.date().optional(),

        // ── Theme-managed fields ───────────────────────────────────
        // Written by the autodoc orchestrators (build-python-docs.mjs /
        // build-ts-docs.mjs) onto every page emitted under a `versions[]`
        // tag. The bundled <VersionPicker> reads them via
        // getCollection('docs') so the autodoc JSON stays the canonical
        // source of truth — no duplicating the version list in your
        // override component. Don't hand-edit these.
        version: z.string().optional(),
        versionLabel: z.string().optional(),
        versionDefault: z.boolean().optional(),
      }),
    }),
  }),
};
