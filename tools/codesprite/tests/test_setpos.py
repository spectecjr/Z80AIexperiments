"""The position patcher: a routine compiled at one place must draw at another."""

import random

import pytest

from codesprite.codegen.draw import DrawContext, generate_draw
from codesprite.codegen.setpos import (
    collect_sites,
    generate_setpos,
    label_patch_sites,
    setpos_registers,
)
from codesprite.ir import Reloc
from codesprite.optimize.baseline import baseline_plan
from codesprite.screen import Screen
from codesprite.sprite import Sprite
from codesprite.verify import VerificationError, verify_patched

SCREEN = Screen(0x8000)


def build_patched(sprite, compiled_at, mode="auto"):
    x0, y0 = compiled_at
    packed = sprite.pack(x0 % 2)
    plan = baseline_plan(packed, mode=mode)
    ctx = DrawContext(SCREEN, x=x0, y=y0, reloc=Reloc.PATCH, label="t")
    draw = label_patch_sites(generate_draw(plan, ctx))
    setpos = generate_setpos(collect_sites(draw), parity=y0 % 2)
    return packed, draw, setpos


def test_setpos_registers_match_the_address_formula():
    for x, y in ((0, 0), (10, 5), (254, 191), (40, 60)):
        regs = setpos_registers(x, y, 0x8000)
        parity = y & 1
        # Even sprite rows use C, odd rows use B; both plus the column.
        assert (regs["d"] << 8 | regs["c"]) == SCREEN.addr_byte(y, x // 2)
        assert regs["b"] == regs["c"] ^ 0x80


@pytest.mark.parametrize(
    "compiled_at, target",
    [
        ((0, 0), (0, 0)),
        ((0, 0), (40, 60)),
        ((0, 0), (100, 100)),
        ((40, 60), (0, 0)),
        ((10, 10), (200, 180)),
        ((0, 2), (60, 100)),
        ((1, 1), (101, 101)),
        ((1, 3), (55, 187)),
    ],
)
def test_patched_sprite_moves(compiled_at, target):
    sprite = Sprite([[1, 2, 3, 4], [5, None, 6, 7], [8, 9, None, None]])
    packed, draw, setpos = build_patched(sprite, compiled_at)
    verify_patched(draw, setpos, packed, SCREEN, compiled_at, target)


def test_patched_stack_mode_moves():
    sprite = Sprite([[7] * 16 for _ in range(8)])
    packed, draw, setpos = build_patched(sprite, (0, 0))
    verify_patched(draw, setpos, packed, SCREEN, (0, 0), (60, 80))


def test_parity_mismatch_is_rejected():
    sprite = Sprite([[1, 2]])
    packed, draw, setpos = build_patched(sprite, (0, 0))
    with pytest.raises(VerificationError):
        verify_patched(draw, setpos, packed, SCREEN, (0, 0), (0, 1))
    with pytest.raises(VerificationError):
        verify_patched(draw, setpos, packed, SCREEN, (0, 0), (1, 0))


def test_setpos_is_cheap_relative_to_drawing():
    sprite = Sprite([[3] * 16 for _ in range(16)])
    packed, draw, setpos = build_patched(sprite, (0, 0))
    assert setpos.tstates < draw.tstates // 2
    verify_patched(draw, setpos, packed, SCREEN, (0, 0), (40, 40))


def test_setpos_groups_stores_by_source():
    """Consecutive sites sharing a source and constant must not reload A."""
    sprite = Sprite([[1] * 8 for _ in range(8)])
    packed, draw, setpos = build_patched(sprite, (0, 0))
    sites = collect_sites(draw)
    loads = sum(1 for op in setpos.ops if op.text().startswith("LD A,"))
    stores = sum(1 for op in setpos.ops if op.text().endswith("),A"))
    assert stores == len(sites)
    assert loads <= stores


@pytest.mark.parametrize("seed", range(6))
def test_random_patched_sprites(seed):
    rng = random.Random(2000 + seed)
    w, h = rng.randrange(1, 20), rng.randrange(1, 20)
    pixels = [
        [None if rng.random() < 0.3 else rng.randrange(16) for _ in range(w)]
        for _ in range(h)
    ]
    if all(v is None for row in pixels for v in row):
        pixels[0][0] = 3
    sprite = Sprite(pixels)
    x0, y0 = rng.randrange(0, 40), rng.randrange(0, 40)
    packed, draw, setpos = build_patched(sprite, (x0, y0))
    x1 = rng.randrange(0, 256 - w)
    y1 = rng.randrange(0, 192 - h)
    x1 -= (x1 % 2) - (x0 % 2)
    y1 -= (y1 % 2) - (y0 % 2)
    x1 = max(0, min(x1, 255 - w))
    y1 = max(0, min(y1, 191 - h))
    if (x1 % 2, y1 % 2) != (x0 % 2, y0 % 2):
        pytest.skip("could not keep parity within bounds")
    verify_patched(draw, setpos, packed, SCREEN, (x0, y0), (x1, y1), seed=seed)
