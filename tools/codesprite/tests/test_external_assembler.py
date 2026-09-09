"""Cross-check our encoder against a real Z80 assembler when one exists.

sjasmplus is the shipping target but has no distribution package; pasmo
and z80asm do, and any of them validates the instruction encodings, which
is the part that can silently go wrong.  These tests skip when none is
installed, so the suite still runs on a bare machine.
"""

import pytest

from codesprite.codegen.draw import DrawContext, generate_draw
from codesprite.emit.external import compare_with_assembler, find_assembler
from codesprite.ir import Mode, Program, Reloc
from codesprite.optimize.baseline import baseline_plan
from codesprite.screen import Screen
from codesprite.sprite import Sprite
from codesprite.z80 import isa

SCREEN = Screen(0x8000)

pytestmark = pytest.mark.skipif(
    find_assembler() is None, reason="no Z80 assembler installed"
)


def test_every_emitted_instruction_matches_the_assembler():
    from tests.test_emit_roundtrip import EVERY_OP

    program = Program()
    for op in EVERY_OP:
        program.add(op)
    difference = compare_with_assembler(program)
    if difference is not None:
        ours, theirs = difference
        pytest.fail(
            "encoder disagrees with the assembler:\n"
            f"  ours  : {ours.hex(' ')}\n"
            f"  theirs: {theirs.hex(' ')}"
        )


@pytest.mark.parametrize("mode", ["hl", "stack", "ix"])
@pytest.mark.parametrize("reloc", [Reloc.NONE, Reloc.REGISTER])
def test_generated_sprites_match_the_assembler(mode, reloc):
    sprite = Sprite([[1, 2, 3, 4, None, 5], [6, 7, 8, 9, 10, 11], [None, 3, 3, None, 4, 4]])
    packed = sprite.pack(0)
    modes = {"hl": Mode.HL, "stack": Mode.STACK, "ix": Mode.IX}
    plan = baseline_plan(packed, mode=modes[mode])
    context = DrawContext(SCREEN, reloc=reloc, label="t")
    program = generate_draw(plan, context)
    assert compare_with_assembler(program) is None


def test_patched_module_including_self_modifying_stores():
    from codesprite.codegen.setpos import (
        collect_sites,
        generate_setpos,
        label_patch_sites,
    )

    sprite = Sprite([[7] * 12 for _ in range(6)])
    packed = sprite.pack(0)
    context = DrawContext(SCREEN, reloc=Reloc.PATCH, label="t")
    draw = label_patch_sites(generate_draw(baseline_plan(packed, mode="auto"), context))
    setpos = generate_setpos(collect_sites(draw), parity=0)

    combined = Program()
    combined.ops.extend(draw.ops)
    combined.origins.extend(draw.origins)
    combined.ops.extend(setpos.ops)
    combined.origins.extend(setpos.origins)
    # The setpos stores name labels inside the draw body, so this also checks
    # that the two routines agree about where the patch sites are.
    assert compare_with_assembler(combined) is None


def test_list_form_matches_the_assembler():
    from codesprite.codegen.forms import generate_list

    sprite = Sprite([[5] * 8 for _ in range(4)])
    packed = sprite.pack(0)
    context = DrawContext(SCREEN, reloc=Reloc.REGISTER, label="t")
    listing = generate_list(baseline_plan(packed, mode="auto"), context, label="t")
    assert compare_with_assembler(listing.program) is None
