"""Score a plan by generating its code and measuring it.

The cost model *is* the code generator: a plan is evaluated by generating
the real instructions and adding up their T-states, so a plan can never
look cheaper than it turns out to be.  That makes the search safe -
whatever it picks is what will be emitted - at the price of a full
generation per evaluation, which the budget absorbs.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..codegen.draw import DrawContext, generate_draw
from ..ir import Mode, Plan, Program
from ..sprite import PackedSprite
from .baseline import baseline_plan


@dataclass(frozen=True)
class Cost:
    """What a plan costs once generated."""

    tstates: int
    size: int
    patches: int

    def score(self, *, patch_weight: float = 0.0, size_weight: float = 0.0) -> float:
        return self.tstates + patch_weight * self.patches + size_weight * self.size


def evaluate(plan: Plan, context: DrawContext, **kwargs) -> tuple[Cost, Program]:
    """Generate ``plan`` and report what it costs."""
    program = generate_draw(plan, context, **kwargs)
    return Cost(program.tstates, program.size, program.patch_count), program


def candidate_plans(packed: PackedSprite, *, max_gap: int = 1) -> list[Plan]:
    """A small spread of plans worth trying before any real search.

    The modes trade against each other in ways that depend on the sprite:
    stack writes are the cheapest per byte but cost a pair load and, in
    this generator, give up the byte cache; HL writes with a cached byte
    are close behind on sprites that repeat a colour; IX suits scattered
    cells.  Generating all of them and keeping the cheapest is both fast
    and honest, and it is what the annealer refines in M6.
    """
    plans = []
    for mode in ("auto", Mode.HL, Mode.STACK, Mode.IX):
        for serpentine in (True, False):
            plans.append(
                baseline_plan(
                    packed, max_gap=max_gap, serpentine=serpentine, mode=mode
                )
            )
    return plans


def best_plan(
    packed: PackedSprite,
    context: DrawContext,
    *,
    max_gap: int = 1,
    patch_weight: float = 0.0,
    size_weight: float = 0.0,
    plans: list[Plan] | None = None,
    **kwargs,
) -> tuple[Plan, Cost, Program]:
    """Generate every candidate plan and return the cheapest."""
    best: tuple[Plan, Cost, Program] | None = None
    for plan in plans or candidate_plans(packed, max_gap=max_gap):
        cost, program = evaluate(plan, context, **kwargs)
        score = cost.score(patch_weight=patch_weight, size_weight=size_weight)
        if best is None or score < best[1].score(
            patch_weight=patch_weight, size_weight=size_weight
        ):
            best = (plan, cost, program)
    assert best is not None
    return best
