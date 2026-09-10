"""Distant thunder alone, deeper: the same engine, a different score.

storm.z80s plays two layers of noise, each a list of segments. What
they sound like is entirely in the score, and this one spends both
layers on the thunder instead of one on rain:

    layer 0   THE BODY. The clock sweeps 150 Hz down to 62 Hz, and at
              62 Hz the noise has nothing above 31 Hz in it. That is
              the bottom of what the chip can do: a tone generator will
              not go below 30.6 Hz, so a mode 3 noise clock will not go
              below 61 Hz, so 30 Hz is the floor of any rumble it can
              make. This layer sits on it.

    layer 1   THE GRAVEL, 420 Hz down to 132 Hz, and gone sooner. Real
              thunder loses its top end with distance and with time -
              the air absorbs high frequencies over a mile far more
              than low ones - so the upper layer decays faster than the
              body underneath it. That difference is most of what makes
              it read as far away rather than merely quiet.

Two generators also means two uncorrelated noise streams, so the rumble
is dense rather than one modulated hiss, and the rolls in each layer
fall in different places - which is what stops it sounding designed.
"""
import storm as S

# frames, clock Hz at the start and end, level 0..1 at the start and end
BODY = [
    (25, 150, 140, 0.00, 0.45),         # it arrives from a long way off
    (30, 140, 132, 0.45, 0.70),
    (35, 132, 124, 0.70, 1.00),         # the weight of it
    (40, 124, 116, 1.00, 0.72),
    (45, 116, 108, 0.72, 0.92),         # and then it rolls
    (45, 108, 100, 0.92, 0.55),
    (55, 100,  93, 0.55, 0.74),
    (55,  93,  86, 0.74, 0.40),
    (60,  86,  80, 0.40, 0.52),
    (65,  80,  74, 0.52, 0.22),
    (70,  74,  68, 0.22, 0.28),
    (75,  68,  62, 0.28, 0.00),         # down to the chip's floor
]

GRAVEL = [
    (25, 420, 380, 0.00, 0.38),
    (35, 380, 330, 0.38, 0.60),
    (40, 330, 290, 0.60, 0.33),
    (45, 290, 255, 0.33, 0.46),
    (50, 255, 225, 0.46, 0.24),
    (60, 225, 200, 0.24, 0.29),
    (70, 200, 178, 0.29, 0.11),
    (80, 178, 160, 0.11, 0.14),
    (90, 160, 145, 0.14, 0.04),
    (105, 145, 132, 0.04, 0.00),
]

L0 = S.compile_score(BODY)
L1 = S.compile_score(GRAVEL)
INIT = S.INIT
FRAMES = sum(s[0] for s in BODY)
assert FRAMES == sum(s[0] for s in GRAVEL), "the layers must end together"


class Thunder(S.Storm):
    def __init__(self):
        S.Storm.__init__(self, L0, L1)
