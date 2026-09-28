# Store listing

Paste these into App Store Connect and the Google Play Console. Character
limits are noted next to each field; every draft below fits.

Audio features are behind the Coming soon flag in this release, so nothing
here mentions recordings, live listening or graded run-throughs. Add them to
the descriptions when `VITE_AUDIO_FEATURES=on` ships.

## Names

| Field | Limit | Text |
|---|---|---|
| App name (both stores) | 30 | `Pedagogue: Piano Practice` |
| Subtitle (App Store) | 30 | `Your repertoire, mapped` |
| Promotional text (App Store) | 170 | `Every piece you play becomes a star. Pedagogue shows what to practise today, why a passage is hard, and which piece to learn next.` |

If `Pedagogue: Piano Practice` is already taken on either store, use
`Pedagogue – Piano Repertoire`.

## Short description (Google Play, 80 characters)

```
Track your piano repertoire, practise smarter and watch your sky of pieces grow.
```

## Full description (both stores, 4,000 characters)

```
Pedagogue is a practice companion for pianists who want to know what to work on next and why.

Add the pieces you play and Pedagogue builds a picture of you as a pianist: your repertoire, your strongest and weakest techniques, and how hard each piece really is for your hands.

YOUR REPERTOIRE AS A CONSTELLATION
Every piece becomes a star. Size shows difficulty, colour shows the era, and lines join pieces that share a composer, a technique or a style. Tap any star to open the piece, tap a line to read why two pieces belong together, and share your sky as an image.

KNOW EACH PIECE PROPERLY
Every catalogue piece comes with context: what it depicts, its history, and its hardest passages marked by bar number, each with a practical cue for how to work on it. Real score excerpts show the technique in question, with piano playback.

PRACTISE WITH A PLAN
• Today shows the piece to work on next and anything fading from your fingers
• Practice sessions track minutes per piece, and a load guard warns before you overdo it
• The weakness forge turns your weakest techniques into targeted drills
• Fresh eight-bar sight-reading exercises, never the same twice
• A polyrhythm trainer for three against two and beyond
• Practice plans that move you through a piece step by step

FIND YOUR NEXT PIECE
Pedagogue maps which pieces prepare you for which. Choose a dream piece and see the stepping stones that lead to it, then add the whole route to your repertoire in one tap.

STAY MOTIVATED
• Daily streaks and a practice reminder at the time you choose
• XP, levels and achievements that appear as figures in your sky
• Spend gold earned by practising on star colours, glows and nebulas in the Observatory
• A daily sight-reading roulette and weekly practice leaderboards with friends, only if you opt in

WORKS WHERE YOU PRACTISE
Your repertoire and piece pages open without a connection. Notes you write offline are sent as soon as you are back online. Upload scores as PDF, MusicXML or MIDI straight from your phone.

YOUR DATA STAYS YOURS
No ads and no tracking. Download your practice history at any time, and delete your account and everything in it from Settings.

Pedagogue is free to use.
```

## Keywords (App Store, 100 characters)

```
piano,practice,repertoire,sight reading,pianist,sheet music,technique,classical,music theory,log
```

## Category and rating

| Field | App Store | Google Play |
|---|---|---|
| Primary category | Music | Music & Audio |
| Secondary category | Education | (tags) Education, Productivity |
| Age rating | 4+ (answer No to every content question; friends and leaderboards show display names only, with no messaging) | Everyone, after the IARC questionnaire (see `MOBILE_RELEASE.md`) |

## Screenshots

Capture each at the sizes below with the demo account (see
`MOBILE_RELEASE.md`, "Demo account"), which has a repertoire, streak and
achievements already set up.

- App Store: 6.9-inch iPhone, 1320 × 2868 portrait (required). The app is set
  to iPhone only, so no iPad screenshots are needed.
- Google Play: phone, 1080 × 1920 or larger portrait, at least 2, up to 8.
- Google Play also needs a 1024 × 500 feature graphic: the planet logo from
  `frontend/assets/logo.svg` on the navy `#0a1120`, with the app name beside it.

| # | Screen | What to show | Caption |
|---|---|---|---|
| 1 | Constellation | The full sky with the legend visible, the demo repertoire's stars and connecting lines, zoomed so several stars are labelled. | Your repertoire as a sky of stars |
| 2 | Today | The greeting, the Next up card with its tempo bar, the streak and the Also in progress list. | Know what to practise today |
| 3 | A piece page (Fur Elise in the demo account) | The summary bar and the Hardest sections panel with bar numbers and practice cues. | Every hard passage, marked by bar |
| 4 | Progress, prerequisites | A dream piece with its stepping-stone route drawn as a flowchart. | See the route to your next piece |
| 5 | Practice | A running session with minutes logged and the load guard meter, or a generated sight-reading exercise on screen. | Practise with a plan, not a guess |
| 6 | Observatory | The wallet, level bar and a row of cosmetics, with one equipped and previewed in the sky. | Earn your way to a brighter sky |

Tips for clean captures on Windows without a Mac:

1. Run the website locally (`npm run dev`) or open the deployed site in
   Chrome, sign in as the demo account, and open DevTools (F12).
2. Toggle the device toolbar (Ctrl+Shift+M), choose "Edit…" and add a device
   of 440 × 956 at device pixel ratio 3 (gives 1320 × 2868) and one of
   412 × 915 at ratio 2.625 (gives about 1080 × 2400).
3. Use the DevTools menu (⋮) → "Capture screenshot" for each screen.
4. Store rules require screenshots to show the app itself, so capture from
   the app (TestFlight or an Android test build) if you can. DevTools
   captures of the same web code are identical in content, but they have no
   phone status bar.
