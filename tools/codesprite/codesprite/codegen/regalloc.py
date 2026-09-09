"""Caching sprite constants in registers, with Belady eviction.

The plan fixes the order in which cells are written, so the whole future
is known when a register has to be freed: evict whatever is needed
farthest away (Belady's optimal policy for a fixed reference string).

Two caches exist:

* an 8-bit cache over B, C, D, E (and optionally H, L, A) so that a
  repeated pixel byte costs ``LD (HL),r`` (7T) instead of
  ``LD (HL),n`` (10T);
* a 16-bit cache over BC, DE, HL and their alternates, so that stack
  writes cost a bare ``PUSH rr`` (11T for two bytes).

Admission is cost-aware: loading a register costs 7T (byte) or 10T
(pair), so a value is only cached when the remaining uses pay that back.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..z80 import isa
from .state import MachineState

LOAD_BYTE_COST = 7  # LD r,n
LOAD_PAIR_COST = 10  # LD rr,nn
LOAD_PAIR_HALF_COST = 7  # LD r,n when the other half already matches
USE_BYTE_SAVING = 3  # LD (HL),n (10T) - LD (HL),r (7T)
EXX_COST = 4


@dataclass
class ByteCache:
    """Keeps frequently used pixel bytes in registers."""

    registers: tuple[str, ...] = ("B", "C", "D", "E")
    future: list[int] = field(default_factory=list)  # remaining byte requests
    position: int = 0

    def next_use(self, value: int, after: int) -> int:
        """Index of the next request for ``value`` at or after ``after``."""
        for index in range(after, len(self.future)):
            if self.future[index] == value:
                return index
        return len(self.future) + 1  # never used again

    def remaining_uses(self, value: int, after: int) -> int:
        return sum(1 for v in self.future[after:] if v == value)

    def find(self, state: MachineState, value: int) -> str | None:
        """A register already holding ``value``, if any."""
        for reg in self.registers:
            if state.get(reg) == value:
                return reg
        return None

    def choose_victim(self, state: MachineState, after: int) -> str:
        """Register whose current value is needed farthest in the future."""
        best, best_distance = self.registers[0], -1
        for reg in self.registers:
            held = state.get(reg)
            distance = (
                len(self.future) + 2 if held is None else self.next_use(held, after)
            )
            if distance > best_distance:
                best, best_distance = reg, distance
        return best

    def should_admit(self, state: MachineState, value: int, after: int) -> bool:
        """Is caching ``value`` worth the load, given what it would evict?"""
        uses = self.remaining_uses(value, after)
        if uses * USE_BYTE_SAVING <= LOAD_BYTE_COST:
            return False
        victim = self.choose_victim(state, after)
        held = state.get(victim)
        if held is None:
            return True
        # Only evict something used less often than the newcomer.
        return self.next_use(held, after) > self.next_use(value, after)


@dataclass
class PairCache:
    """Keeps 16-bit push values in register pairs, using both banks."""

    pairs: tuple[str, ...] = ("BC", "DE", "HL")
    use_alternate: bool = True
    future: list[int] = field(default_factory=list)
    position: int = 0

    def next_use(self, value: int, after: int) -> int:
        for index in range(after, len(self.future)):
            if self.future[index] == value:
                return index
        return len(self.future) + 1

    def find(self, state: MachineState, value: int) -> tuple[str, bool] | None:
        """Find ``value`` in a pair; returns (pair, in_alternate_bank)."""
        for pair in self.pairs:
            if state.get_pair(pair) == value:
                return pair, state.exx
        if self.use_alternate:
            probe = state.copy()
            probe.toggle_exx()
            for pair in self.pairs:
                if probe.get_pair(pair) == value:
                    return pair, probe.exx
        return None

    def choose_victim(self, state: MachineState, after: int) -> str:
        best, best_distance = self.pairs[0], -1
        for pair in self.pairs:
            held = state.get_pair(pair)
            distance = (
                len(self.future) + 2 if held is None else self.next_use(held, after)
            )
            if distance > best_distance:
                best, best_distance = pair, distance
        return best

    @staticmethod
    def load_ops(pair: str, value: int, state: MachineState) -> list[isa.Op]:
        """Load ``value`` into ``pair``, using half loads where possible."""
        from .state import PAIR_HALVES

        high, low = (value >> 8) & 0xFF, value & 0xFF
        hi_reg, lo_reg = PAIR_HALVES[pair]
        have_hi, have_lo = state.get(hi_reg), state.get(lo_reg)
        if have_hi == high and have_lo == low:
            return []
        if have_hi == high:
            return [isa.LdRegImm(lo_reg, low)]
        if have_lo == low:
            return [isa.LdRegImm(hi_reg, high)]
        return [isa.LdPairImm(pair, value)]
