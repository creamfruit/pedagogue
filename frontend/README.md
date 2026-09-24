# Piano Pedagogue — frontend

Vite + vanilla JS progressive web app. No framework, no build-time magic beyond Vite
itself: plain ES modules, a small hash-free router over the History API, and a thin
fetch client wrapping the FastAPI backend.

## Setup

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open http://localhost:5173 with the backend running on port 8000.

In development Vite proxies `/api` and `/health` straight to the backend, so the browser
sees one origin and CORS never enters the picture. In production the client calls
`VITE_API_URL` directly, so set that to wherever the API is deployed.

```bash
npm run build
npm run preview
```

The service worker only registers in a production build. Use `npm run preview` to
exercise offline behaviour; `npm run dev` deliberately leaves it off so you are never
debugging a stale cache.

## Layout

```
frontend/
├── index.html            app shell: topbar, nav, view outlet, toast host, update bar
├── vite.config.js        dev proxy + Workbox (vite-plugin-pwa) configuration
├── public/icons/         generated PWA icons and favicon
└── src/
    ├── main.js           boot sequence, route table, auth guard, chrome wiring
    ├── router.js         History API router with params, guards and view teardown
    ├── styles.css        the whole design system, one file, CSS custom properties
    ├── api/client.js     fetch wrapper, token storage, typed endpoint methods
    ├── lib/store.js      auth state and subscriptions
    ├── lib/dom.js        el() builder and shared UI fragments
    ├── lib/toast.js      transient notifications
    ├── lib/drift.js      the suspended-in-space physics force and throw handling
    ├── components/       shared rich fragments (piece overview, link summary)
    └── views/            one module per route
```

## The router

`route(pattern, handler, options)` registers a view. Patterns take `:params`
(`/repertoire/:id`). A handler receives `(outlet, { params, query, pathname })` and may
return a cleanup function, which runs before the next view mounts — the constellation
uses this to stop its force simulation and drop its resize listener.

`setGuard` runs before every navigation. Ours redirects unauthenticated visitors to
`/login` and bounces authenticated ones away from the auth pages. Any `<a data-link>`
is intercepted, so navigation never reloads the document.

## The API client

`src/api/client.js` is the only place that knows about HTTP. It attaches the bearer
token, normalises FastAPI's several error shapes into a readable `detail` string, and
throws `ApiError` with `status`, `isAuth`, `isConflict` and `isOffline` helpers. A 401
clears the token and fires the `onUnauthorized` listeners, which sign the user out and
redirect once, from one place.

`pollSubmission(id)` implements the upload handshake: the POST returns `202` with a
`poll_url`, and this polls until the status settles on `done` or `failed`.

`liveSocketUrl(targetBpm)` builds the WebSocket URL for the live-listening coach,
upgrading the scheme and carrying the token as a query parameter, since browsers cannot
set headers on a WebSocket handshake.

## Offline behaviour

Workbox precaches the shell and assets. Runtime caching is split by how stale the data
may safely be:

| Route | Strategy | Why |
|---|---|---|
| `/api/v1/catalog/*` | StaleWhileRevalidate | The catalog barely changes; instant is better than fresh |
| `/api/v1/repertoire`, `/progression`, `/onboarding` | NetworkFirst, 5s timeout | Yours and changing, but worth showing stale rather than nothing |
| Google Fonts | CacheFirst | Immutable once fetched |

`navigateFallback` serves `index.html` for any navigation, with `/api` and `/health`
denylisted so requests are never swallowed by the shell. Updates use `registerType:
"prompt"`: a new service worker waits and the update bar appears rather than the page
reloading under the user mid-practice.

Verified in a headless browser: after one visit, a full reload with the network cut
still renders the shell, and a deep link to `/constellation` is served from the
precache.

## The constellation

`views/constellation.js` renders to Canvas rather than SVG, because a node per piece
plus a link per relationship gets heavy in the DOM quickly. `d3-force` computes the
layout with a custom `forceDrift` force on top, the canvas draws it, and hit testing is
a distance check against each node's radius. A star's drawn size and its physical mass
both scale with difficulty, so heavy pieces glide further when thrown. Each link type
gets its own colour and its own legend toggle:

- composer — amber
- technique — coral
- era / genre — rose

Filtering is pure JS, so toggling never refetches.

Three separate gestures share the canvas, resolved in `pointerdown` in this order:

1. Press on a star — drag and throw it; releasing without moving opens the piece.
2. Press on a connector — opens the connection summary below the canvas and lights the
   line. `linkAt()` is a point-to-segment distance test with a 7px slack in world units,
   so the target stays the same size on screen at any zoom.
3. Press on empty sky — pans the view. Scroll zooms around the cursor.

Cosmetics from the Observatory are read out of the loadout and applied at draw time:
star colour mode, glow spread, nebula layers and connector width, alpha and dash.

## Rich piece overviews

`components/overview.js` exports two builders used in more than one place.
`pieceOverview(data)` renders everything `GET /catalog/pieces/{id}/overview` returns:
the metadata grid, the character strip, the written context, the hardest sections with
their bar numbers and practice cues, the technique breakdown with mechanics and common
faults, the composer panel and the physical load profile. `linkSummaryPanel(data)`
renders `GET /catalog/links/{a}/{b}` — the headline, the explanation, the shared
techniques with each piece's weighting, and the marked passages where they appear.

Both take plain API payloads and return a detached node, so a view appends one without
owning any of the markup.

## Adding a view

```js
import { el } from "../lib/dom.js";
import { api } from "../api/client.js";

export async function myView(outlet, context) {
  const data = await api.get("/something");
  outlet.append(el("h1", {}, data.title));
  return () => {
    /* optional cleanup */
  };
}
```

Then register it in `main.js` with `route("/my-path", myView)` and add a nav link in
`index.html`.

## What is not built yet

The entry detail page is a stub: submissions upload, practice plans, drills,
sight-reading and readiness scoring all have working API methods in the client but no UI
yet. The live-listening view is likewise wired in the client (`liveSocketUrl`) but has
no screen. Those are the next slice.
