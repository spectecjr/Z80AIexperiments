"""End-to-end M3: plan -> HL-mode code -> emulator -> reference compare."""

import random

import pytest

from codesprite.codegen.draw import DrawContext, generate_draw
from codesprite.codegen.navigate import Navigator
from codesprite.ir import Mode, Piece, Plan, Reloc
from codesprite.optimize.baseline import baseline_plan
from codesprite.screen import Screen
from codesprite.sprite import Sprite
from codesprite.verify import VerificationError, verify_draw
from codesprite.z80 import isa


def compile_sprite(sprite, x=0, y=0, phase=None, screen=None, **kw):
    screen = screen or Screen(0x8000)
    phase = (x % 2) if phase is None else phase
    packed = sprite.pack(phase)
    plan = baseline_plan(packed, **kw)
    plan.validate(packed)
    context = DrawContext(screen, x=x, y=y, reloc=Reloc.NONE)
    program = generate_draw(plan, context)
    return packed, program, context


# -- navigation -------------------------------------------------------------


def test_navigator_picks_inc_l_for_one_step():
    nav = Navigator(Reloc.NONE)
    ops = nav.move(0x8000, 0x8001)
    assert [op.text() for op in ops] == ["INC L"]


def test_navigator_row_step_costs_no_more_than_ld_l():
    nav = Navigator(Reloc.NONE)
    ops = nav.move(0x8000, 0x8080)  # row 0 -> row 1
    assert sum(op.tstates for op in ops) <= 8


def test_navigator_uses_patch_free_moves_when_patching():
    nav = Navigator(Reloc.PATCH)
    assert [op.text() for op in nav.move(0x8000, 0x8080)] == ["SET 7,L"]
    assert [op.text() for op in nav.move(0x8080, 0x8100)] == ["INC H", "RES 7,L"]


def test_navigator_register_mode_never_emits_absolute_loads():
    nav = Navigator(Reloc.REGISTER)
    for target in (0x8001, 0x8080, 0x8100, 0x8123):
        ops = nav.move(0x8000, target)
        assert all(not isinstance(op, isa.LdPairImm) for op in ops)
        assert all(not isinstance(op, isa.LdRegImm) for op in ops)


def test_navigator_register_mode_requires_known_pointer():
    with pytest.raises(ValueError):
        Navigator(Reloc.REGISTER).move(None, 0x8000)


def test_navigator_no_move_needed():
    assert Navigator(Reloc.NONE).move(0x8000, 0x8000) == []


# -- drawing ----------------------------------------------------------------


def test_single_opaque_pixel_pair():
    sprite = Sprite([[1, 2]])
    packed, program, ctx = compile_sprite(sprite, x=0, y=0)
    result = verify_draw(program, packed, ctx.screen, 0, 0, expected_tstates=program.tstates)
    assert result.tstates == program.tstates


def test_solid_block_draws_and_costs_are_exact():
    sprite = Sprite([[3] * 8 for _ in range(4)])
    packed, program, ctx = compile_sprite(sprite, x=0, y=0)
    verify_draw(program, packed, ctx.screen, 0, 0, expected_tstates=program.tstates)


def test_half_transparent_bytes_preserve_background():
    # Odd phase makes both edge bytes half-transparent.
    sprite = Sprite([[5, 6, 7, 8]])
    packed, program, ctx = compile_sprite(sprite, x=1, y=0)
    assert packed.half_count == 2
    verify_draw(program, packed, ctx.screen, 1, 0, expected_tstates=program.tstates)


def test_transparent_holes_are_not_written():
    sprite = Sprite(
        [
            [1, 1, None, None, 1, 1],
            [None, None, None, None, None, None],
            [2, None, None, None, None, 2],
        ]
    )
    packed, program, ctx = compile_sprite(sprite, x=0, y=0)
    result = verify_draw(program, packed, ctx.screen, 0, 0)
    # Row 1 is entirely transparent, so nothing in it may be written.
    row1 = range(ctx.screen.addr_byte(1, 0), ctx.screen.addr_byte(1, 128))
    assert not [a for a in result.writes if a in row1]


@pytest.mark.parametrize("x", [0, 1, 2, 3, 40, 41, 200, 253])
@pytest.mark.parametrize("y", [0, 1, 2, 3, 95, 189])
def test_positions_and_parities(x, y):
    sprite = Sprite([[9, 8, 7], [6, None, 5]])
    packed, program, ctx = compile_sprite(sprite, x=x, y=y)
    verify_draw(program, packed, ctx.screen, x, y, expected_tstates=program.tstates)


@pytest.mark.parametrize("seed", range(8))
def test_random_sprites(seed):
    rng = random.Random(seed)
    w = rng.randrange(1, 17)
    h = rng.randrange(1, 17)
    pixels = [
        [None if rng.random() < 0.35 else rng.randrange(16) for _ in range(w)]
        for _ in range(h)
    ]
    if all(v is None for row in pixels for v in row):
        pixels[0][0] = 1
    sprite = Sprite(pixels)
    x = rng.randrange(0, 256 - w)
    y = rng.randrange(0, 192 - h)
    packed, program, ctx = compile_sprite(sprite, x=x, y=y)
    verify_draw(program, packed, ctx.screen, x, y, seed=seed, expected_tstates=program.tstates)


def test_serpentine_and_rowmajor_agree_on_pixels_and_differ_on_cost():
    sprite = Sprite([[1] * 8 for _ in range(8)])
    packed = sprite.pack(0)
    ctx = DrawContext(Screen(0x8000), x=0, y=0, reloc=Reloc.NONE)
    serp = generate_draw(baseline_plan(packed, serpentine=True), ctx)
    rows = generate_draw(baseline_plan(packed, serpentine=False), ctx)
    verify_draw(serp, packed, ctx.screen, 0, 0, expected_tstates=serp.tstates)
    verify_draw(rows, packed, ctx.screen, 0, 0, expected_tstates=rows.tstates)
    assert serp.tstates <= rows.tstates


def test_plan_validation_catches_missing_cells():
    sprite = Sprite([[1, 2, 3, 4]])
    packed = sprite.pack(0)
    plan = Plan((Piece(0, packed.cells[:1], Mode.HL),))
    with pytest.raises(ValueError):
        plan.validate(packed)


def test_verify_detects_wrong_code():
    """A deliberately broken program must fail verification, not pass it."""
    sprite = Sprite([[1, 2]])
    packed, program, ctx = compile_sprite(sprite, x=0, y=0)
    program.ops[-1] = isa.LdHlImm(0x00)  # wrong pixel data
    with pytest.raises(VerificationError):
        verify_draw(program, packed, ctx.screen, 0, 0)


def test_verify_detects_stray_write():
    sprite = Sprite([[1, 2]])
    packed, program, ctx = compile_sprite(sprite, x=0, y=0)
    program.ops.insert(0, isa.LdPairImm("HL", 0x7000))
    program.ops.insert(1, isa.LdHlImm(0xFF))
    program.origins.insert(0, None)
    program.origins.insert(1, None)
    with pytest.raises(VerificationError):
        verify_draw(program, packed, ctx.screen, 0, 0)


def test_16x16_opaque_sprite_hl_mode_baseline_cost():
    """Records the HL-mode cost that stack mode has to beat in M4."""
    sprite = Sprite([[7] * 16 for _ in range(16)])
    packed, program, ctx = compile_sprite(sprite, x=0, y=0)
    verify_draw(program, packed, ctx.screen, 0, 0, expected_tstates=program.tstates)
    per_byte = program.tstates / len(packed.cells)
    # With the byte cache a repeated pixel byte costs LD (HL),r (7T) plus an
    # INC L (4T): ~11.6T/byte.  Stack mode has to beat that.
    assert 11.0 <= per_byte < 12.5, f"unexpected HL-mode cost {per_byte:.2f}T/byte"
