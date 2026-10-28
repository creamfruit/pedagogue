# Difficulty calibration

Model `harvest-difficulty-1`, fitted on 38 harvested pieces that are also on the reference ladder.

| Piece | Ladder | Computed | Error |
|---|---:|---:|---:|
| Burgmüller: La Bergeronnette | 10.0 | 26.0 | +16.0 |
| Chopin: Prelude: Op. 28, No. 7 | 10.0 | 19.8 | +9.8 |
| Satie: Gymnopédie No. 1 | 12.0 | 12.1 | +0.1 |
| Chopin: Prelude: Op. 28, No. 4 ('Suffocation') | 15.0 | 33.0 | +18.0 |
| Chopin: Prelude: Op. 28, No. 20 | 25.0 | 20.2 | -4.8 |
| Schumann: Kinderscenen - Traümerei | 25.0 | 26.9 | +1.9 |
| Beethoven: Für Elise | 30.0 | 32.2 | +2.2 |
| Joplin: The Entertainer | 35.0 | 53.7 | +18.7 |
| Beethoven: Sonata No. 8 “Pathétique” (2nd Movement: Adagio cantabile) | 35.0 | 46.3 | +11.3 |
| Schumann: Kinderscenen - Glückes genug | 35.0 | 36.3 | +1.3 |
| Chopin: Prelude: Op. 28, No. 15 | 38.0 | 36.5 | -1.5 |
| Liszt: Consolation, S.172 No.3 | 38.0 | 47.3 | +9.3 |
| Mozart: Fantasy in D minor | 38.0 | 44.6 | +6.6 |
| Debussy: Première Arabesque | 40.0 | 42.6 | +2.6 |
| Mozart: Sonate Opus KV 331 - Rondo Alla Turca | 42.0 | 35.7 | -6.3 |
| Joplin: Maple Leaf Rag | 45.0 | 55.4 | +10.4 |
| Chopin: Valse Op. 64, No. 1 ('Minute Waltz') | 45.0 | 42.9 | -2.1 |
| Mozart: Sonate Opus KV 331 - Variation 3 | 45.0 | 51.8 | +6.8 |
| Scriabin: Etude | 45.0 | 41.3 | -3.7 |
| Grieg: Troldtog (March of the Dwarfs) | 45.0 | 46.4 | +1.4 |
| Debussy: Suite Bergamasque: Clair de Lune | 48.0 | 49.2 | +1.2 |
| Beethoven: Sonata No. 8 “Pathétique” (3rd Movement: Rondo) | 50.0 | 39.2 | -10.8 |
| Brahms: 2. Intermezzo | 52.0 | 43.6 | -8.4 |
| Beethoven: Sonata No. 8 “Pathétique” (1st Movement: Grave, Allegro molto e con b | 58.0 | 60.9 | +2.9 |
| Grieg: Wedding-day at Troldhaugen | 58.0 | 61.8 | +3.8 |
| Chopin: Fantaisie-Impromptu | 62.0 | 62.8 | +0.8 |
| Beethoven: Sonata No. 17 (1st Movement: Largo - Allegro) | 64.0 | 56.4 | -7.6 |
| Chopin: Etüde f-moll | 65.0 | 54.2 | -10.8 |
| Chopin: Etüde c-moll | 66.0 | 66.9 | +0.9 |
| Chopin: Etüde As-Dur | 68.0 | 69.5 | +1.5 |
| Tchaikovsky: Doumka | 70.0 | 76.4 | +6.4 |
| Chopin: Etüde f-moll | 70.0 | 50.9 | -19.1 |
| Chopin: Etüde Ges-Dur | 75.0 | 74.0 | -1.0 |
| Chopin: Ballade number 4 | 85.0 | 71.3 | -13.7 |
| Beethoven: Sonata No. 23 “Appassionata” (3rd Movement: Allegro, ma non troppo -  | 86.0 | 66.6 | -19.4 |
| Beethoven: Sonata No. 32 (1st Movement) | 88.0 | 67.3 | -20.7 |
| Chopin: Etüde a-moll | 90.0 | 48.4 | -41.6 |
| Chopin: Etüde C-Dur | 90.0 | 43.9 | -46.1 |

- Pieces compared: 38
- RMSE in sample: 13.8; leave-one-out RMSE: 16.1
- Mean absolute error: 9.3; bias: -2.2
- Rank correlation with the ladder (Spearman): 0.79
- Terms the fit dropped: octave_runs, octave_share, polyphony

## Anchors

| Anchor | Target | Ladder | Computed | In the harvested corpus |
|---|---:|---:|---:|---|
| Für Elise (Beethoven) | 30 | 30.0 | 32.2 | yes: Beethoven: Für Elise |
| Ballade No. 1 (Chopin) | 70 | 70.0 | n/a | no |
| La Campanella (Liszt) | 90 | 90.0 | n/a | no |
| Islamey (Balakirev) | 98 | 98.0 | n/a | no |
