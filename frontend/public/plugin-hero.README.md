# Landing-page hero image

`app/page.tsx` → `components/PluginHero.tsx` loads **`/plugin-hero.png`** from this
folder as the first image on the dashboard.

Export the Claude artifact (https://claude.ai/code/artifact/894675fb-011f-47e6-ae17-e3ec2697cada)
as a PNG (or SVG — then change the `src` in `PluginHero.tsx`) and save it here as
`plugin-hero.png`. Recommended ~1200×800 or wider; it's rendered with `object-cover`
so exact dimensions don't matter. Until the file exists the hero shows a navy panel.
