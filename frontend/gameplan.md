# gameplan

## envisioned tech stack + notes

react.JS, w/ TS since its the one front-end lang / framework I've worked with before,
plus robust map ecosystem as of now.

bundling w/ vite and react-router or something else makes the most sense as of now.
don't need the comprehensive features of next.js, nor state managers.
consider SSR native to react with newer versions. use with TS.

MUST consider how to setup proper PWA / mobile friendly setup.

MapLibre + OpenFreeMap. use something like cartoDB dark-matter (using this first) / positron or
Stamen maps. use Mapunik to edit styles specific to nana-nalu. think dark, light,
and maybe terrain would be more than enough.

Dark maps for MVP, build out light mode option though and toggling with state, but stick with dark for MVP

shadcn ui + tailwind css for styles etc.

can use openfreemap for vector tiling w/ leaflet for best of both worlds.
use mapcn -> maplibre interface with shadcn ui esque components

tanstack query for handling the forecast data
