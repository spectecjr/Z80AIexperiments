"""Tracking what the Z80 holds while code is being generated.

The generator always knows, symbolically, what every register contains:
either a known constant, the screen pointer, or "unknown".  That is what
lets it skip a reload (``LD (HL),C`` instead of ``LD (HL),n``) or a
pointer move, and it is checked by the emulator afterwards, so a wrong
belief here shows up as a failed verification rather than a silent bug.
"""

from __future__ import annotations

from dataclasses import dataclass, field

BYTE_REGISTERS = ("A", "B", "C", "D", "E", "H", "L")
PAIR_REGISTERS = ("BC", "DE", "HL")
PAIR_HALVES = {"BC": ("B", "C"), "DE": ("D", "E"), "HL": ("H", "L")}


@dataclass
class MachineState:
    """Known register contents, per bank, plus the pointer and SP."""

    # Main bank byte registers; None means unknown.
    main: dict[str, int | None] = field(
        default_factory=lambda: {r: None for r in BYTE_REGISTERS}
    )
    # Alternate bank (BC', DE', HL'); A' is not used by the generator.
    alt: dict[str, int | None] = field(
        default_factory=lambda: {r: None for r in ("B", "C", "D", "E", "H", "L")}
    )
    exx: bool = False  # True when the alternate bank is selected
    pointer: int | None = None  # value of HL when it holds a screen address
    sp: int | None = None  # value of SP when it is known
    index: dict[str, int | None] = field(
        default_factory=lambda: {"IX": None, "IY": None}
    )

    # -- bank access -------------------------------------------------------
    @property
    def active(self) -> dict[str, int | None]:
        """The byte registers currently visible (main or alternate bank)."""
        return self.alt if self.exx else self.main

    def get(self, reg: str) -> int | None:
        if reg == "A":  # A is not banked in the way the generator uses it
            return self.main["A"]
        return self.active.get(reg)

    def set(self, reg: str, value: int | None) -> None:
        if reg == "A":
            self.main["A"] = None if value is None else value & 0xFF
            return
        self.active[reg] = None if value is None else value & 0xFF

    def get_pair(self, pair: str) -> int | None:
        if pair in ("IX", "IY"):
            return self.index[pair]
        hi, lo = PAIR_HALVES[pair]
        high, low = self.get(hi), self.get(lo)
        if high is None or low is None:
            return None
        return (high << 8) | low

    def set_pair(self, pair: str, value: int | None) -> None:
        if pair in ("IX", "IY"):
            self.index[pair] = None if value is None else value & 0xFFFF
            return
        hi, lo = PAIR_HALVES[pair]
        if value is None:
            self.set(hi, None)
            self.set(lo, None)
        else:
            self.set(hi, (value >> 8) & 0xFF)
            self.set(lo, value & 0xFF)

    # -- pointer -----------------------------------------------------------
    def set_pointer(self, address: int | None) -> None:
        """Record that HL holds a screen address (in the current bank)."""
        self.pointer = address
        self.set_pair("HL", address)

    def invalidate_pointer(self) -> None:
        self.pointer = None
        self.set_pair("HL", None)

    def toggle_exx(self) -> None:
        self.exx = not self.exx
        # HL changes meaning with the bank, so the pointer belief is only
        # valid in the bank that established it.
        self.pointer = self.get_pair("HL")

    def copy(self) -> "MachineState":
        return MachineState(
            main=dict(self.main),
            alt=dict(self.alt),
            exx=self.exx,
            pointer=self.pointer,
            sp=self.sp,
            index=dict(self.index),
        )
