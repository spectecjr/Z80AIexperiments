"""Erase, save and restore."""

import pytest

from codesprite.codegen.copy import generate_copy, scratch_size, spans_of
from codesprite.codegen.draw import DrawContext, generate_draw
from codesprite.codegen.erase import erase_sprite
from codesprite.ir import Reloc
from codesprite.optimize.baseline import baseline_plan
from codesprite.screen import SCREEN_BYTES, Screen
from codesprite.sprite import MASK_BOTH, Sprite
from codesprite.verify import (
    CODE_ORIGIN,
    STACK_TOP,
    noise_image,
    reference_screen,
    run_program,
    verify_draw,
)

SCREEN = Screen(0x8000)
SCRATCH = 0xE000


def draw_program(packed, x=0, y=0, reloc=Reloc.NONE, label="t"):
    plan = baseline_plan(packed, mode="auto")
    ctx = DrawContext(SCREEN, x=x, y=y, reloc=reloc, label=label)
    return generate_draw(plan, ctx), ctx


# -- erase ------------------------------------------------------------------


def test_erase_cells_covers_exactly_the_sprite():
    sprite = Sprite([[1, 2, None], [None, 3, 4]])
    packed = sprite.pack(0)
    erase = erase_sprite(packed, colour=0, shape="cells")
    assert {(c.row, c.col) for c in erase.cells} == {
        (c.row, c.col) for c in packed.cells
    }
    for cell, original in zip(erase.cells, packed.cells):
        assert cell.mask == original.mask


def test_erase_rows_fills_each_span():
    sprite = Sprite([[1, None, None, None, None, 2]])
    packed = sprite.pack(0)
    erase = erase_sprite(packed, colour=5, shape="rows")
    assert [c.col for c in erase.cells] == [0, 1, 2]
    assert all(c.mask == MASK_BOTH and c.value == 0x55 for c in erase.cells)


def test_erase_bbox_covers_every_row():
    sprite = Sprite([[1, 1], [None, None], [1, 1]])
    packed = sprite.pack(0)
    erase = erase_sprite(packed, colour=0, shape="bbox")
    assert sorted({c.row for c in erase.cells}) == [0, 1, 2]


def test_erase_draws_the_colour_and_keeps_neighbours():
    sprite = Sprite([[7, 7, 7, 7]])
    packed = sprite.pack(1)  # half-owned bytes at both ends
    erase = erase_sprite(packed, colour=2, shape="cells")
    program, ctx = draw_program(erase, x=1)
    verify_draw(program, erase, SCREEN, 1, 0, expected_tstates=program.tstates)


@pytest.mark.parametrize("shape", ["cells", "rows", "bbox"])
def test_erase_shapes_all_generate_and_verify(shape):
    sprite = Sprite([[3, None, 4, 5], [None, 6, None, 7], [8, 8, 8, 8]])
    packed = sprite.pack(0)
    erase = erase_sprite(packed, colour=0, shape=shape)
    program, ctx = draw_program(erase)
    verify_draw(program, erase, SCREEN, 0, 0, expected_tstates=program.tstates)


def test_erase_rejects_bad_input():
    packed = Sprite([[1]]).pack(0)
    with pytest.raises(ValueError):
        erase_sprite(packed, colour=16)
    with pytest.raises(ValueError):
        erase_sprite(packed, colour=0, shape="nonsense")


# -- save / restore ---------------------------------------------------------


def test_spans_are_dense_in_scratch():
    sprite = Sprite([[1, 1, 1, 1], [None, None, 2, 2], [3, 3, 3, 3]])
    packed = sprite.pack(0)
    spans = spans_of(packed)
    assert [(s.row, s.first_col, s.length, s.offset) for s in spans] == [
        (0, 0, 2, 0),
        (1, 1, 1, 2),
        (2, 0, 2, 3),
    ]
    assert scratch_size(packed) == 5


def round_trip(sprite, x=0, y=0, reloc=Reloc.NONE, seed=0):
    """save -> draw -> restore must return the screen to its start."""
    packed = sprite.pack(x % 2)
    ctx = DrawContext(SCREEN, x=x, y=y, reloc=reloc, label="t")
    save = generate_copy(packed, ctx, SCRATCH, to_screen=False)
    draw = generate_draw(baseline_plan(packed, mode="auto"), ctx)
    restore = generate_copy(packed, ctx, SCRATCH, to_screen=True)

    memory = noise_image(seed, SCREEN)
    original = bytes(memory[SCREEN.base : SCREEN.base + SCREEN_BYTES])
    expected_drawn = reference_screen(memory, packed, SCREEN, x, y)

    registers = None
    if reloc is Reloc.REGISTER:
        address = SCREEN.addr_byte(y, x // 2)
        registers = {"h": address >> 8, "l": address & 0xFF}

    cpu, _t, _range = run_program(save, memory, registers=registers)
    cpu2, _t2, _r2 = run_program(draw, cpu.memory, registers=registers)
    drawn = bytes(cpu2.memory[SCREEN.base : SCREEN.base + SCREEN_BYTES])
    assert drawn == bytes(expected_drawn[SCREEN.base : SCREEN.base + SCREEN_BYTES])

    cpu3, _t3, _r3 = run_program(restore, cpu2.memory, registers=registers)
    assert bytes(cpu3.memory[SCREEN.base : SCREEN.base + SCREEN_BYTES]) == original


def test_save_draw_restore_round_trip():
    round_trip(Sprite([[1, 2, 3, 4], [5, None, 6, 7], [8, 9, 10, 11]]))


def test_round_trip_with_half_transparent_edges():
    round_trip(Sprite([[1, 2, 3]]), x=1)


def test_round_trip_at_an_offset_position():
    round_trip(Sprite([[4] * 8 for _ in range(4)]), x=40, y=60)


def test_round_trip_with_register_relocation():
    round_trip(Sprite([[4] * 8 for _ in range(4)]), x=20, y=30, reloc=Reloc.REGISTER)


@pytest.mark.parametrize("seed", range(4))
def test_round_trip_random(seed):
    import random

    rng = random.Random(seed)
    w, h = rng.randrange(1, 17), rng.randrange(1, 17)
    pixels = [
        [None if rng.random() < 0.3 else rng.randrange(16) for _ in range(w)]
        for _ in range(h)
    ]
    if all(v is None for row in pixels for v in row):
        pixels[0][0] = 1
    x = rng.randrange(0, 256 - w)
    y = rng.randrange(0, 192 - h)
    round_trip(Sprite(pixels), x=x, y=y, seed=seed)


def test_bounce_is_chosen_for_long_spans_and_is_cheaper():
    sprite = Sprite([[1] * 64 for _ in range(4)])
    packed = sprite.pack(0)
    ctx = DrawContext(SCREEN, reloc=Reloc.NONE, label="t")
    chosen = generate_copy(packed, ctx, SCRATCH, to_screen=False)
    ldi_only = generate_copy(packed, ctx, SCRATCH, to_screen=False, allow_bounce=False)
    assert chosen.tstates < ldi_only.tstates
    per_byte = chosen.tstates / scratch_size(packed)
    assert per_byte < 16.0, f"bounce should beat 16T/byte, got {per_byte:.1f}"


def test_restore_from_back_buffer():
    """restore_bb reads a clean copy of the screen at a fixed offset."""
    sprite = Sprite([[6] * 8 for _ in range(4)])
    packed = sprite.pack(0)
    ctx = DrawContext(SCREEN, x=10, y=20, reloc=Reloc.NONE, label="t")
    backbuffer = 0x2000
    delta = (backbuffer - SCREEN.base) & 0xFFFF
    restore = generate_copy(
        packed, ctx, SCRATCH, to_screen=True, source_delta=delta, allow_bounce=False
    )

    memory = noise_image(0, SCREEN)
    for offset in range(SCREEN_BYTES):
        memory[backbuffer + offset] = (offset * 7) & 0xFF
    draw = generate_draw(baseline_plan(packed, mode="auto"), ctx)
    cpu, _t, _r = run_program(draw, memory)
    cpu2, _t2, _r2 = run_program(restore, cpu.memory)

    for span in spans_of(packed):
        for index in range(span.length):
            address = SCREEN.addr_byte(20 + span.row, 10 // 2 + span.first_col + index)
            assert cpu2.memory[address] == cpu2.memory[(address + delta) & 0xFFFF]


# -- caller-supplied scratchpads --------------------------------------------


def _run_with_registers(program, memory, **registers):
    from codesprite.verify import run_program

    cpu, _t, _r = run_program(program, memory, registers=registers)
    return cpu


def test_one_routine_serves_several_instances_with_their_own_scratch():
    """The point of a passed-in scratchpad: two sprites, one save routine,
    two independent backgrounds, restored in either order."""
    sprite = Sprite([[6] * 8 for _ in range(4)])
    packed = sprite.pack(0)
    ctx_a = DrawContext(SCREEN, x=0, y=0, reloc=Reloc.REGISTER, label="t")
    ctx_b = DrawContext(SCREEN, x=40, y=60, reloc=Reloc.REGISTER, label="t")

    save = generate_copy(packed, ctx_a, 0, to_screen=False, scratch_in_de=True)
    restore = generate_copy(packed, ctx_a, 0, to_screen=True, scratch_in_de=True)
    draw = generate_draw(baseline_plan(packed, mode="auto"), ctx_a)
    draw_b = generate_draw(baseline_plan(packed, mode="auto"), ctx_b)

    memory = noise_image(0, SCREEN)
    original = bytes(memory[SCREEN.base : SCREEN.base + SCREEN_BYTES])

    scratch_a, scratch_b = 0x6000, 0x6100

    def anchor(x, y):
        address = SCREEN.addr_byte(y, x // 2)
        return {"h": address >> 8, "l": address & 0xFF}

    # Save both backgrounds into separate pads, then draw over both.
    cpu = _run_with_registers(save, memory, **anchor(0, 0), d=scratch_a >> 8,
                              e=scratch_a & 0xFF)
    cpu = _run_with_registers(save, cpu.memory, **anchor(40, 60),
                              d=scratch_b >> 8, e=scratch_b & 0xFF)
    cpu = _run_with_registers(draw, cpu.memory, **anchor(0, 0))
    cpu = _run_with_registers(draw_b, cpu.memory, **anchor(40, 60))
    assert bytes(cpu.memory[SCREEN.base : SCREEN.base + SCREEN_BYTES]) != original

    # Restore in the opposite order; both pads must still be intact.
    cpu = _run_with_registers(restore, cpu.memory, **anchor(40, 60),
                              d=scratch_b >> 8, e=scratch_b & 0xFF)
    cpu = _run_with_registers(restore, cpu.memory, **anchor(0, 0),
                              d=scratch_a >> 8, e=scratch_a & 0xFF)
    assert bytes(cpu.memory[SCREEN.base : SCREEN.base + SCREEN_BYTES]) == original


def test_passed_in_scratch_costs_no_more_than_a_baked_one():
    sprite = Sprite([[3] * 12 for _ in range(6)])
    packed = sprite.pack(0)
    ctx = DrawContext(SCREEN, reloc=Reloc.NONE, label="t")
    fixed = generate_copy(packed, ctx, SCRATCH, to_screen=False, allow_bounce=False)
    passed = generate_copy(
        packed, ctx, SCRATCH, to_screen=False, allow_bounce=False, scratch_in_de=True
    )
    assert passed.tstates <= fixed.tstates
    assert passed.size < fixed.size  # one fewer immediate load


@pytest.mark.parametrize("reloc", [Reloc.NONE, Reloc.PATCH, Reloc.REGISTER])
def test_passed_in_scratch_round_trips_in_every_relocation_mode(reloc):
    sprite = Sprite([[9, 8, 7, None, 6], [5, 4, 3, 2, 1]])
    packed = sprite.pack(0)
    ctx = DrawContext(SCREEN, x=20, y=30, reloc=reloc, label="t")
    save = generate_copy(packed, ctx, 0, to_screen=False, scratch_in_de=True)
    restore = generate_copy(packed, ctx, 0, to_screen=True, scratch_in_de=True)
    draw = generate_draw(baseline_plan(packed, mode="auto"), ctx)

    memory = noise_image(3, SCREEN)
    original = bytes(memory[SCREEN.base : SCREEN.base + SCREEN_BYTES])
    address = SCREEN.addr_byte(30, 20 // 2)
    anchor = {"h": address >> 8, "l": address & 0xFF}
    pad = {"d": 0x60, "e": 0x00}

    cpu = _run_with_registers(save, memory, **anchor, **pad)
    cpu = _run_with_registers(draw, cpu.memory, **anchor)
    assert bytes(cpu.memory[SCREEN.base : SCREEN.base + SCREEN_BYTES]) != original
    cpu = _run_with_registers(restore, cpu.memory, **anchor, **pad)
    assert bytes(cpu.memory[SCREEN.base : SCREEN.base + SCREEN_BYTES]) == original
