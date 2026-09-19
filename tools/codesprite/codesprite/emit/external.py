"""Check generated code against a real external assembler.

The emulator proves the bytes behave; the parser proves the text says what
the bytes say.  Neither proves a *third party* reads the text the same way.
Assembling with a real assembler and comparing the result byte for byte
closes that last gap.

sjasmplus is the shipping target, but any Z80 assembler validates the
instruction encodings, which is what can silently go wrong.  ``pasmo`` is
used when present because it installs from a distribution package.
Directives and label syntax differ between assemblers, so only the
instruction stream is compared: labels are rewritten to a neutral form and
metadata lines are dropped.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from ..ir import Program
from ..z80 import isa
from .parse import strip_line

ASSEMBLERS = ("sjasmplus", "pasmo", "z80asm")


def find_assembler(preferred: str | None = None) -> str | None:
    """Path to an available assembler, or None."""
    names = (preferred,) if preferred else ASSEMBLERS
    for name in names:
        if name and shutil.which(name):
            return shutil.which(name)
    return None


def _pasmo_source(program: Program, origin: int) -> str:
    """Render a program as assembler-neutral source.

    Local labels (``.p0``) become plain identifiers, and the
    self-modifying operands that name them keep pointing at the same byte.
    """
    lines = [f"        org ${origin:04X}"]
    for op in program.ops:
        if isinstance(op, isa.Comment):
            continue
        if isinstance(op, isa.Label):
            lines.append(f"{op.name.lstrip('.').replace('.', '_')}:")
            continue
        text = op.text()
        # Rewrite "(.p0+1)" and "(name+1)" operands to the neutral label.
        if "(" in text and ")" in text and any(
            isinstance(op, kind)
            for kind in (isa.LdMemA, isa.LdMemSp, isa.LdAMem, isa.LdMemPair, isa.LdPairMem)
        ):
            inner = text[text.index("(") + 1 : text.rindex(")")]
            if not inner.startswith("$"):
                neutral = inner.lstrip(".").replace(".", "_")
                text = text.replace(f"({inner})", f"({neutral})")
        if isinstance(op, (isa.Djnz, isa.Jump, isa.JumpCond, isa.Call)):
            text = text.replace(op.label, op.label.lstrip(".").replace(".", "_"))
        lines.append(f"        {text}")
    return "\n".join(lines) + "\n"


def assemble_externally(
    program: Program, origin: int = 0x4000, assembler: str | None = None
) -> bytes | None:
    """Assemble ``program`` with an external assembler, or None if absent."""
    tool = find_assembler(assembler)
    if tool is None:
        return None
    name = Path(tool).name
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "check.asm"
        binary = Path(directory) / "check.bin"
        source.write_text(_pasmo_source(program, origin))
        if name == "pasmo":
            command = [tool, "--bin", str(source), str(binary)]
        elif name == "sjasmplus":
            command = [tool, f"--raw={binary}", str(source)]
        else:  # z80asm
            command = [tool, "-o", str(binary), str(source)]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"{name} rejected the generated source:\n"
                f"{result.stdout}\n{result.stderr}"
            )
        return binary.read_bytes()


def compare_with_assembler(
    program: Program, origin: int = 0x4000, assembler: str | None = None
) -> tuple[bytes, bytes] | None:
    """Return (ours, theirs) when they differ, None when they agree.

    Returns None too when no assembler is installed, so callers can treat
    "no assembler" and "agrees" alike and skip.
    """
    theirs = assemble_externally(program, origin, assembler)
    if theirs is None:
        return None
    ours, _labels = program.assemble(origin)
    return None if ours == theirs else (ours, theirs)
