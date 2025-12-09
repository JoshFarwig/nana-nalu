# gameplan

## envisioned tech stack + notes

react.JS, w/ TS since its the one front-end lang / framework I've worked with before,
plus robust map ecosystem as of now.

bundling w/ vite and react-router or something else makes the most sense as of now.
don't need the comprehensive features of next.js, nor state managers.
consider SSR native to react with newer versions. use with TS.

MUST consider how to setup proper PWA / mobile friendly setup.

MapLibre + OpenFreeMap. use something like cartoDB dark-matter / positron or
Stamen maps. use Mapunik to edit styles specific to nana-nalu. think dark, light,
and maybe terrain would be more than enough.

shadcn ui + tailwind css for styles etc.

since I only really need marker creation and don't plan to show forecasting in areas,
leaftlet makes the most sense for the MVP. shadcn ui has a community plugin for leaflet
as well. can use openfreemap for vector tiling w/ leaflet for best of both worlds. if
I change gears and want to render map tiles, may need to go maplibre gl js instead.

leaflet makes most sense though to just get something up and running.
