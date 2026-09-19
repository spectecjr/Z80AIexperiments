"""The list form: one register setup, many draws."""

import pytest

from codesprite.codegen.draw import DrawContext, generate_draw
from codesprite.codegen.forms import generate_list
from codesprite.ir import Mode, Reloc
from codesprite.optimize.baseline import baseline_plan
from codesprite.screen import Screen
from codesprite.sprite import Sprite
from codesprite.verify import VerificationError, verify_list
from codesprite.z80 import isa

SCREEN = Screen(0x8000)


def build_list(sprite, *, mode="auto", phase=0, parity=0, **kw):
    packed = sprite.pack(phase)
    plan = baseline_plan(packed, mode=mode)
    ctx = DrawContext(SCREEN, x=phase, y=parity, reloc=Reloc.REGISTER, label="t")
    return packed, generate_list(plan, ctx, label="t", **kw)


def test_list_draws_every_item():
    sprite = Sprite([[1, 2, 3, 4], [5, 6, None, 8]])
    packed, listing = build_list(sprite)
    verify_list(
        listing.program, packed, SCREEN, [(0, 0), (20, 40), (100, 100), (200, 150)]
    )


def test_list_uses_the_stack_protocol():
    sprite = Sprite([[1, 2]])
    _packed, listing = build_list(sprite)
    texts = [op.text() for op in listing.program.ops]
    assert "POP HL" in texts
    assert any(t.startswith("DJNZ") or t.startswith("JP NZ") for t in texts)


def test_list_hoists_constant_loads_out_of_the_loop():
    """Identical tiles must not reload their push pairs every iteration."""
    sprite = Sprite([[7] * 16 for _ in range(8)])
    _packed, listing = build_list(sprite)
    ops = listing.program.ops
    loop_at = next(
        i for i, op in enumerate(ops) if isinstance(op, isa.Label)
    )
    in_loop = ops[loop_at:]
    assert not [op for op in in_loop if isinstance(op, isa.LdPairImm)], (
        "pair loads should be hoisted into the prologue"
    )
    assert [op for op in ops[:loop_at] if isinstance(op, isa.LdPairImm)]


def test_list_beats_repeated_single_calls():
    """The list form wins by paying setup once and skipping CALL/RET."""
    sprite = Sprite([[4] * 16 for _ in range(8)])
    packed, listing = build_list(sprite)
    ctx = DrawContext(SCREEN, reloc=Reloc.REGISTER, label="t")
    single = generate_draw(baseline_plan(packed, mode="auto"), ctx)
    call_overhead = isa.Call("x").tstates + isa.Simple("RET").tstates
    for count in (4, 16):
        as_list = listing.prologue_tstates + count * listing.item_tstates
        as_calls = count * (single.tstates + call_overhead)
        assert as_list < as_calls, (count, as_list, as_calls)
    verify_list(listing.program, packed, SCREEN, [(0, 0), (32, 0), (64, 0)])


def test_list_of_one_item_still_works():
    sprite = Sprite([[9, 9, 9, 9]])
    packed, listing = build_list(sprite)
    verify_list(listing.program, packed, SCREEN, [(50, 50)])


def test_long_body_uses_dec_b_and_jp():
    sprite = Sprite([[c % 16 for c in range(64)] for _ in range(16)])
    _packed, listing = build_list(sprite)
    texts = [op.text() for op in listing.program.ops]
    assert any(t.startswith("JP NZ") for t in texts)
    assert not any(t.startswith("DJNZ") for t in texts)


def test_long_body_list_draws_correctly():
    sprite = Sprite([[c % 16 for c in range(40)] for _ in range(12)])
    packed, listing = build_list(sprite)
    verify_list(listing.program, packed, SCREEN, [(0, 0), (100, 60)])


def test_stack_body_restores_the_list_pointer():
    sprite = Sprite([[6] * 16 for _ in range(4)])
    packed, listing = build_list(sprite, mode=Mode.STACK)
    texts = [op.text() for op in listing.program.ops]
    assert any(t.endswith("),SP") for t in texts)
    # verify_list asserts SP ends exactly where the items ran out.
    verify_list(listing.program, packed, SCREEN, [(0, 0), (60, 20), (120, 40)])


def test_hl_only_body_has_no_sp_juggling():
    sprite = Sprite([[1, None, 2]])
    _packed, listing = build_list(sprite, mode=Mode.HL)
    texts = [op.text() for op in listing.program.ops]
    assert not any(t.endswith("),SP") for t in texts)
    assert "DI" not in texts


def test_odd_phase_list():
    sprite = Sprite([[3, 4, 5, 6]])
    packed, listing = build_list(sprite, phase=1)
    verify_list(listing.program, packed, SCREEN, [(1, 0), (41, 0), (101, 100)])


def test_odd_parity_list():
    sprite = Sprite([[3, 4], [5, 6]])
    packed, listing = build_list(sprite, parity=1)
    verify_list(listing.program, packed, SCREEN, [(0, 1), (40, 41), (100, 101)])


def test_mismatched_parity_is_rejected():
    sprite = Sprite([[1, 2]])
    packed, listing = build_list(sprite)
    with pytest.raises(VerificationError):
        verify_list(listing.program, packed, SCREEN, [(0, 0), (0, 1)])


def test_list_form_requires_register_relocation():
    sprite = Sprite([[1, 2]])
    packed = sprite.pack(0)
    plan = baseline_plan(packed, mode="auto")
    ctx = DrawContext(SCREEN, reloc=Reloc.NONE, label="t")
    with pytest.raises(ValueError):
        generate_list(plan, ctx, label="t")
