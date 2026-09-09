"""M4: stack mode, IX mode, register caching and the relocation modes."""

import random

import pytest

from codesprite.codegen.draw import DrawContext, generate_draw
from codesprite.ir import Mode, Piece, Plan, Reloc
from codesprite.optimize.baseline import baseline_plan, choose_mode
from codesprite.screen import Screen
from codesprite.sprite import Sprite
from codesprite.verify import verify_draw
from codesprite.z80 import isa

SCREEN = Screen(0x8000)


def build(sprite, *, mode="auto", x=0, y=0, reloc=Reloc.NONE, **kw):
    packed = sprite.pack(x % 2)
    plan = baseline_plan(packed, mode=mode, **kw)
    plan.validate(packed)
    context = DrawContext(SCREEN, x=x, y=y, reloc=reloc, label="t")
    return packed, generate_draw(plan, context), context


def check(sprite, *, mode="auto", x=0, y=0, reloc=Reloc.NONE, seed=0, **kw):
    packed, program, ctx = build(sprite, mode=mode, x=x, y=y, reloc=reloc, **kw)
    registers = None
    if reloc is Reloc.REGISTER:
        address = SCREEN.addr_byte(y, x // 2)
        registers = {"h": address >> 8, "l": address & 0xFF}
    result = verify_draw(
        program,
        packed,
        SCREEN,
        x,
        y,
        seed=seed,
        registers=registers,
        expected_tstates=program.tstates,
    )
    return packed, program, result


# -- stack mode -------------------------------------------------------------


def test_stack_mode_used_for_long_runs():
    piece_cells = Sprite([[1] * 8]).pack(0).cells
    assert choose_mode(Piece(0, piece_cells)) is Mode.STACK
    short = Sprite([[1] * 2]).pack(0).cells
    assert choose_mode(Piece(0, short)) is Mode.HL


def test_stack_mode_draws_correctly():
    sprite = Sprite([[3] * 16 for _ in range(4)])
    check(sprite)


def test_stack_mode_beats_hl_mode_on_a_solid_sprite():
    sprite = Sprite([[7] * 16 for _ in range(16)])
    _packed, stack_program, _ = build(sprite, mode="auto")
    _packed2, hl_program, _ = build(sprite, mode=Mode.HL)
    assert stack_program.tstates < hl_program.tstates
    per_byte = stack_program.tstates / len(sprite.pack(0).cells)
    assert per_byte < 8.0, f"stack mode should be well under 8T/byte, got {per_byte:.2f}"


def test_stack_mode_saves_and_restores_sp():
    sprite = Sprite([[5] * 16 for _ in range(2)])
    _packed, program, _ = build(sprite)
    texts = [op.text() for op in program.ops]
    assert any(t.startswith("LD (") and t.endswith("),SP") for t in texts)
    assert "DI" in texts and "EI" in texts
    # verify_draw asserts SP is back where it started.
    check(sprite)


def test_stack_mode_without_interrupt_guard():
    sprite = Sprite([[5] * 16 for _ in range(2)])
    packed = sprite.pack(0)
    plan = baseline_plan(packed, mode="auto")
    ctx = DrawContext(SCREEN, reloc=Reloc.NONE, interrupts="raw", label="t")
    program = generate_draw(plan, ctx)
    texts = [op.text() for op in program.ops]
    assert "DI" not in texts and "EI" not in texts
    verify_draw(program, packed, SCREEN, 0, 0, expected_tstates=program.tstates)


def test_odd_length_run_writes_its_leftover_byte():
    sprite = Sprite([[2] * 7])  # 7 pixels -> 4 byte cells, last one half
    packed, program, _ = check(sprite)
    assert len(packed.cells) == 4


def test_stack_run_with_half_transparent_edges():
    sprite = Sprite([[6] * 12])
    check(sprite, x=1)  # odd x makes both ends half-transparent


def test_mixed_modes_in_one_sprite():
    sprite = Sprite(
        [
            [1] * 16,  # long run -> stack
            [None, None, 2, None, None] + [None] * 11,  # scattered -> HL
            [3] * 16,
        ]
    )
    check(sprite)


# -- IX mode ----------------------------------------------------------------


def test_ix_mode_draws_correctly():
    # Full byte pairs, so the opaque LD (IX+d),n path is exercised.
    sprite = Sprite([[1, 2, None, None, 3, 4], [None, None, 5, 6, None, None]])
    packed = sprite.pack(0)
    plan = Plan(
        tuple(p.with_mode(Mode.IX) for p in baseline_plan(packed, mode=Mode.HL).pieces)
    )
    ctx = DrawContext(SCREEN, reloc=Reloc.NONE, label="t")
    program = generate_draw(plan, ctx)
    verify_draw(program, packed, SCREEN, 0, 0, expected_tstates=program.tstates)
    assert any(isinstance(op, isa.LdIndexImm) for op in program.ops)


def test_ix_mode_handles_half_transparent_cells():
    sprite = Sprite([[4, 5, 6]])
    packed = sprite.pack(1)  # produces half cells at both ends
    plan = Plan(
        tuple(p.with_mode(Mode.IX) for p in baseline_plan(packed, mode=Mode.HL).pieces)
    )
    ctx = DrawContext(SCREEN, x=1, reloc=Reloc.NONE, label="t")
    program = generate_draw(plan, ctx)
    verify_draw(program, packed, SCREEN, 1, 0, expected_tstates=program.tstates)


# -- register caching -------------------------------------------------------


def test_byte_cache_reuses_a_register_for_a_repeated_value():
    sprite = Sprite([[9, 9, 9, 9, 9, 9]])
    _packed, program, _ = build(sprite, mode=Mode.HL)
    assert any(isinstance(op, isa.LdHlReg) for op in program.ops)
    immediates = sum(1 for op in program.ops if isinstance(op, isa.LdHlImm))
    assert immediates <= 1


def test_byte_cache_not_used_for_single_use_values():
    sprite = Sprite([[1, 2, 3, 4, 5, 6, 7, 8]])
    _packed, program, _ = build(sprite, mode=Mode.HL)
    # Every byte differs, so caching would cost more than it saves.
    assert not any(isinstance(op, isa.LdHlReg) for op in program.ops)


def test_pair_cache_reuses_pairs_across_rows():
    sprite = Sprite([[4] * 16 for _ in range(8)])
    _packed, program, _ = build(sprite)
    loads = sum(1 for op in program.ops if isinstance(op, isa.LdPairImm))
    pushes = sum(1 for op in program.ops if isinstance(op, isa.Push))
    assert pushes == 32  # 8 rows x 8 byte cells / 2 bytes per push
    assert loads <= 2, f"identical rows should not reload pairs ({loads} loads)"


def test_alternate_bank_holds_extra_values():
    # Eight distinct pair values per row is more than the three main-bank
    # pairs hold, so the alternate bank has to carry the rest.
    sprite = Sprite([[1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8] for _ in range(6)])
    _packed, program, _ = check(sprite)
    assert any(op.text() == "EXX" for op in program.ops)


def test_alternate_bank_costs_less_than_reloading():
    sprite = Sprite([[1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8] for _ in range(6)])
    packed = sprite.pack(0)
    plan = baseline_plan(packed, mode="auto")
    ctx = DrawContext(SCREEN, reloc=Reloc.NONE, label="t")
    with_alt = generate_draw(plan, ctx, use_alternate=True)
    without = generate_draw(plan, ctx, use_alternate=False)
    assert with_alt.tstates < without.tstates


def test_alternate_bank_can_be_disabled():
    sprite = Sprite([[1, 1, 2, 2, 3, 3, 4, 4] for _ in range(4)])
    packed = sprite.pack(0)
    plan = baseline_plan(packed, mode="auto")
    ctx = DrawContext(SCREEN, reloc=Reloc.NONE, label="t")
    program = generate_draw(plan, ctx, use_alternate=False)
    assert not any(op.text() == "EXX" for op in program.ops)
    verify_draw(program, packed, SCREEN, 0, 0, expected_tstates=program.tstates)


# -- relocation modes -------------------------------------------------------


def test_register_relocation_draws_from_hl():
    sprite = Sprite([[8] * 12 for _ in range(6)])
    _packed, program, _ = check(sprite, x=20, y=30, reloc=Reloc.REGISTER)
    for op in program.ops:
        assert not isinstance(op, isa.LdPairImm) or op.pair != "HL"
        assert not isinstance(op, isa.LdSpImm) or op.imm == 0  # only the SP restore


def test_register_relocation_works_at_any_position():
    sprite = Sprite([[2, 3, 4, 5], [6, None, 7, 8]])
    for x, y in ((0, 0), (2, 1), (40, 60), (100, 101), (248, 189)):
        check(sprite, x=x - (x % 2), y=y, reloc=Reloc.REGISTER)


def test_patch_relocation_marks_immediates():
    sprite = Sprite([[1] * 8 for _ in range(4)])
    packed = sprite.pack(0)
    plan = baseline_plan(packed, mode="auto")
    ctx = DrawContext(SCREEN, x=10, y=10, reloc=Reloc.PATCH, label="t")
    program = generate_draw(plan, ctx)
    assert program.patch_count > 0
    for op in program.ops:
        for patch in op.patches:
            assert patch.kind in (isa.PatchKind.L, isa.PatchKind.H)
            assert 0 <= patch.row < sprite.height
    # A patched build still has to draw correctly at its compiled position.
    verify_draw(program, packed, SCREEN, 10, 10, expected_tstates=program.tstates)


def test_patch_relocation_prefers_patch_free_navigation():
    """Patch weighting should push row steps onto SET/RES rather than LD L,n."""
    sprite = Sprite([[1] * 4 for _ in range(8)])
    packed = sprite.pack(0)
    plan = baseline_plan(packed, mode=Mode.HL)
    none_program = generate_draw(
        plan, DrawContext(SCREEN, reloc=Reloc.NONE, label="t")
    )
    patch_program = generate_draw(
        plan, DrawContext(SCREEN, reloc=Reloc.PATCH, label="t")
    )
    # Without patch weighting the generator is free to re-seat the pointer
    # with LD L,n; under patching it must prefer SET/RES 7,L and INC H, so
    # only the initial LD HL,nn should carry patch points.
    assert none_program.patch_count == 0  # nothing is patchable in that mode
    assert patch_program.patch_count == 2, [
        (op.text(), len(op.patches)) for op in patch_program.ops if op.patches
    ]


# -- randomised cross-checks ------------------------------------------------


@pytest.mark.parametrize("seed", range(12))
def test_random_sprites_all_modes(seed):
    rng = random.Random(1000 + seed)
    w, h = rng.randrange(1, 25), rng.randrange(1, 25)
    density = rng.choice([0.0, 0.2, 0.5])
    palette_size = rng.choice([1, 2, 16])
    pixels = [
        [
            None if rng.random() < density else rng.randrange(palette_size)
            for _ in range(w)
        ]
        for _ in range(h)
    ]
    if all(v is None for row in pixels for v in row):
        pixels[0][0] = 1
    sprite = Sprite(pixels)
    x = rng.randrange(0, 256 - w)
    y = rng.randrange(0, 192 - h)
    mode = rng.choice(["auto", Mode.HL, Mode.STACK, Mode.IX])
    reloc = rng.choice([Reloc.NONE, Reloc.REGISTER])
    if reloc is Reloc.REGISTER:
        x -= x % 2  # keep the phase the caller's HL implies
    check(sprite, mode=mode, x=x, y=y, reloc=reloc, seed=seed)


@pytest.mark.parametrize("mode", ["auto", Mode.HL, Mode.STACK, Mode.IX])
def test_every_mode_draws_the_ship_example(mode):
    sprite = Sprite(
        [
            [None, None, 1, 1, None, None],
            [None, 1, 2, 2, 1, None],
            [1, 2, 3, 3, 2, 1],
            [None, 1, None, None, 1, None],
        ]
    )
    for x in (0, 1):
        check(sprite, mode=mode, x=x, y=7)
