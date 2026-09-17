# The write-ups: chequer8.html, chequer9.html, chequer10.html

**The illustrated version of the design notes**, one per demo that got one,
checked in beside the notes themselves. Each is a single self-contained HTML
file — no build, no dependencies, styles inline — that reads the GIFs out of
`demo/`, so opening one in a browser from a clone works.

| | |
|---|---|
| `chequer10.html` | three compiled trees on a moving board, what the map holds, and where a 50 Hz music tick fits |
| `chequer9.html` | the horizon that moves, the four colour board, and the palette that had to go |
| `chequer8.html` | the two layer desert on a board that stays put |

They are also published as private pages on claude.ai, and this is the copy
of record: the published one is this file, and the images beside it are the
ones in `demo/`.

**What goes in one.** The same thing the design notes have, in the order a
reader wants rather than the order it was built in: what it is, what the
frame costs measured piece by piece, and then the two or three decisions
that are actually interesting — with the one that was wrong first, because
that is the part that is worth reading. `chequer9.html` leads on the board
that does not tilt; `chequer10.html` on a scaled sprite being eight sprites.

The numbers in them are the numbers in `reports/`, and they are stale the
moment a routine changes. When one does: re-run the test, re-read the
report, fix the page, and republish it to the same URL.
