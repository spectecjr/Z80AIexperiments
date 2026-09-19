"""Moving the HL screen pointer between cells as cheaply as possible.

The navigator is where the mode 4 address layout pays off.  Because a row
is 128 bytes, two rows share a 256-byte page and the row parity is bit 7
of L, so most moves need no address immediate at all:

    same row, next byte      INC L                       4T, patch-free
    even row -> row below    SET 7,L                     8T, patch-free
    odd row  -> row below    INC H : RES 7,L            12T, patch-free
    two rows down            INC H                       4T, patch-free
    arbitrary, same page     LD L,n                      7T, one patch
    arbitrary                LD HL,nn                   10T, two patches

Which of these is *cheapest* depends on the relocation mode: with
``Reloc.NONE`` an ``LD L,n`` (7T) beats ``SET 7,L`` (8T), but under
``Reloc.PATCH`` the immediate costs a patch at setpos time, and under
``Reloc.REGISTER`` an absolute immediate is not available at all.  The
navigator therefore scores candidates with a patch weight and returns the
best sequence.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..ir import Reloc
from ..z80 import isa

# Cost, in T-states, charged per patch point when relocation is by patching.
# One patch is a `LD (nn),A` (13T) in setpos, sometimes preceded by an
# `LD A,r`/`ADD A,n`; 13 is the floor and the annealer refines the trade
# through --moves-per-draw.
PATCH_COST = 13


@dataclass
class Candidate:
    ops: list[isa.Op]
    patches: int

    @property
    def tstates(self) -> int:
        return sum(op.tstates for op in self.ops)

    @property
    def size(self) -> int:
        return sum(op.size for op in self.ops)

    def score(self, patch_weight: float) -> tuple[float, int]:
        return (self.tstates + patch_weight * self.patches, self.size)


class Navigator:
    """Emits pointer moves for one relocation mode.

    ``row_of`` maps an absolute address back to the sprite row it belongs
    to, so patch points can record which row's register supplies the byte.
    """

    def __init__(
        self,
        reloc: Reloc = Reloc.NONE,
        *,
        patch_weight: float = PATCH_COST,
        max_inc_run: int = 8,
    ) -> None:
        self.reloc = reloc
        self.patch_weight = patch_weight if reloc is Reloc.PATCH else 0.0
        self.max_inc_run = max_inc_run

    # -- candidate generation ---------------------------------------------
    def _candidates(
        self, current: int | None, target: int, row: int, col: int
    ) -> list[Candidate]:
        out: list[Candidate] = []
        absolute_ok = self.reloc is not Reloc.REGISTER

        if absolute_ok:
            out.append(
                Candidate(
                    [
                        isa.LdPairImm(
                            "HL",
                            target,
                            patch_lo=isa.Patch(isa.PatchKind.L, row, col)
                            if self.reloc is Reloc.PATCH
                            else None,
                            patch_hi=isa.Patch(isa.PatchKind.H, row, col)
                            if self.reloc is Reloc.PATCH
                            else None,
                        )
                    ],
                    patches=2 if self.reloc is Reloc.PATCH else 0,
                )
            )

        if current is None:
            if not out:
                raise ValueError(
                    "register relocation needs a known starting pointer; "
                    "the caller must supply HL"
                )
            return out

        cur_h, cur_l = current >> 8, current & 0xFF
        tgt_h, tgt_l = target >> 8, target & 0xFF

        if current == target:
            out.append(Candidate([], patches=0))
            return out

        # Same page: L-only moves.
        if cur_h == tgt_h:
            if absolute_ok:
                out.append(
                    Candidate(
                        [
                            isa.LdRegImm(
                                "L",
                                tgt_l,
                                patch=isa.Patch(isa.PatchKind.L, row, col)
                                if self.reloc is Reloc.PATCH
                                else None,
                            )
                        ],
                        patches=1 if self.reloc is Reloc.PATCH else 0,
                    )
                )
            delta = tgt_l - cur_l
            # INC L / DEC L chains, only while L does not wrap (H must not move).
            if 0 < delta <= self.max_inc_run:
                out.append(Candidate([isa.IncDec8("L")] * delta, patches=0))
            elif -self.max_inc_run <= delta < 0:
                out.append(Candidate([isa.IncDec8("L", down=True)] * -delta, patches=0))
            # Row step within a page: SET 7,L / RES 7,L.
            if tgt_l == (cur_l | 0x80) and not cur_l & 0x80:
                out.append(Candidate([isa.BitOp(7, "L")], patches=0))
            if tgt_l == (cur_l & 0x7F) and cur_l & 0x80:
                out.append(Candidate([isa.BitOp(7, "L", set_=False)], patches=0))
            # A + n through the accumulator: relocation-safe arithmetic.
            out.append(
                Candidate(
                    [
                        isa.LdRegReg("A", "L"),
                        isa.AluImm("ADD", delta & 0xFF),
                        isa.LdRegReg("L", "A"),
                    ],
                    patches=0,
                )
            )

        # H moves.
        h_delta = (tgt_h - cur_h) & 0xFF
        if h_delta in (1, 2) and tgt_l == cur_l:
            out.append(Candidate([isa.IncDec8("H")] * h_delta, patches=0))
        if h_delta == 1 and tgt_l == (cur_l & 0x7F) and cur_l & 0x80:
            # Odd row to the row below: INC H : RES 7,L.
            out.append(
                Candidate([isa.IncDec8("H"), isa.BitOp(7, "L", set_=False)], patches=0)
            )
        if h_delta == 1 and absolute_ok:
            out.append(
                Candidate(
                    [
                        isa.IncDec8("H"),
                        isa.LdRegImm(
                            "L",
                            tgt_l,
                            patch=isa.Patch(isa.PatchKind.L, row, col)
                            if self.reloc is Reloc.PATCH
                            else None,
                        ),
                    ],
                    patches=1 if self.reloc is Reloc.PATCH else 0,
                )
            )
        if h_delta == 1 and tgt_l == (cur_l | 0x80) and not cur_l & 0x80:
            out.append(Candidate([isa.IncDec8("H"), isa.BitOp(7, "L")], patches=0))

        # General fallback: set each half of the pointer by arithmetic.  H and
        # L are independent here because both are computed from the target
        # rather than by a 16-bit add, so a carry out of L cannot corrupt H.
        # This is what makes register relocation complete for any move.
        general: list[isa.Op] = []
        if tgt_l != cur_l:
            general += [
                isa.LdRegReg("A", "L"),
                isa.AluImm("ADD", (tgt_l - cur_l) & 0xFF),
                isa.LdRegReg("L", "A"),
            ]
        if h_delta:
            if h_delta <= 3:
                general += [isa.IncDec8("H")] * h_delta
            elif h_delta >= 0xFD:
                general += [isa.IncDec8("H", down=True)] * (0x100 - h_delta)
            else:
                general += [
                    isa.LdRegReg("A", "H"),
                    isa.AluImm("ADD", h_delta),
                    isa.LdRegReg("H", "A"),
                ]
        if general:
            out.append(Candidate(general, patches=0))

        return out

    def move(
        self, current: int | None, target: int, row: int = 0, col: int = 0
    ) -> list[isa.Op]:
        """Cheapest instruction sequence taking HL from ``current`` to ``target``."""
        candidates = self._candidates(current, target, row, col)
        best = min(candidates, key=lambda c: c.score(self.patch_weight))
        return best.ops

    def cost(self, current: int | None, target: int, row: int = 0, col: int = 0) -> float:
        candidates = self._candidates(current, target, row, col)
        return min(c.score(self.patch_weight)[0] for c in candidates)
