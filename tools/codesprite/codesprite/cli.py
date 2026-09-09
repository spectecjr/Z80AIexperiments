"""Command line front end: ``codesprite compile | inspect | sizes``."""

from __future__ import annotations

import argparse
import hashlib
import shlex
import sys
from pathlib import Path

from .codegen.copy import generate_copy, scratch_size
from .codegen.draw import DrawContext, generate_draw
from .codegen.erase import SHAPES, erase_sprite
from .codegen.forms import generate_list
from .codegen.setpos import collect_sites, generate_setpos, label_patch_sites
from .emit.report import Report, VariantRow, manifest
from .emit.sjasm import ModuleInfo, render, uses_stack
from .ir import Mode, Reloc
from .optimize.baseline import baseline_plan
from .optimize.evaluate import best_plan
from .screen import MemoryLayout, Screen
from .sprite import PackedSprite, Sprite, load_sprite
from .verify import verify_draw, verify_list, verify_patched


def _auto_int(text: str) -> int:
    return int(text, 0)


def _rect(text: str) -> tuple[int, int, int, int]:
    parts = [int(p, 0) for p in text.replace(",", " ").split()]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("rect must be x,y,w,h")
    return tuple(parts)  # type: ignore[return-value]


def lower_bound(packed: PackedSprite) -> int:
    """Cheapest conceivable cost: the write instructions alone.

    Stack writes move two bytes for 11T, so an opaque byte cannot cost less
    than 5.5T; a half-transparent byte needs a read-modify-write, whose
    floor is 22T with mask and data in registers.  Pointer movement, loop
    overhead and register loading are all excluded, so this is a true (if
    loose) lower bound rather than an estimate.
    """
    return round(packed.opaque_count * 5.5 + packed.half_count * 22)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codesprite",
        description="Compile sprites into Z80 code for the SAM Coupe (mode 4).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_source_options(p: argparse.ArgumentParser) -> None:
        p.add_argument("source", help="sprite file (.txt, .png or .bin)")
        p.add_argument("--mask", dest="mask_path", help="mask image or file")
        p.add_argument("--transparent-index", type=_auto_int)
        p.add_argument("--palette", dest="palette_path")
        p.add_argument("--nearest", action="store_true", help="snap colours to palette")
        p.add_argument("--rect", type=_rect, help="crop x,y,w,h from a sheet")
        p.add_argument("--width", type=_auto_int, help="pixel width for .bin input")
        p.add_argument("--height", type=_auto_int, help="pixel height for .bin input")
        p.add_argument("--trim", action="store_true", help="drop transparent borders")

    compile_p = sub.add_parser("compile", help="generate sprite routines")
    add_source_options(compile_p)
    compile_p.add_argument("--name", required=True, help="label stem for the routines")
    compile_p.add_argument("--out-dir", required=True, help="directory for the files")
    compile_p.add_argument(
        "--routines",
        default="draw",
        help="comma separated: draw, erase, save, restore, restore_bb",
    )
    compile_p.add_argument("--erase-color", type=_auto_int, default=0)
    compile_p.add_argument("--erase-shape", default="rows", choices=list(SHAPES))
    compile_p.add_argument("--list-len", type=int, default=16,
                           help="expected list length, for costing the list form")
    compile_p.add_argument("--form", default="single", choices=["single", "list", "both"])
    compile_p.add_argument("--x-align", type=int, default=1, choices=[1, 2])
    compile_p.add_argument("--y-align", type=int, default=1, choices=[1, 2])
    compile_p.add_argument(
        "--reloc", default="none", choices=[r.value for r in Reloc]
    )
    compile_p.add_argument("--clip", default="none", choices=["none", "y-spill", "y-entry"])
    compile_p.add_argument("--screen-base", type=_auto_int, default=0x8000)
    compile_p.add_argument("--scratch-base", type=_auto_int, default=0xE000)
    compile_p.add_argument("--backbuffer-base", type=_auto_int)
    compile_p.add_argument("--at", default="0,0", help="fixed draw position x,y for --reloc none")
    compile_p.add_argument("--max-gap", type=int, default=1)
    compile_p.add_argument("--mode", default="best",
                           choices=["best", "auto", "hl", "stack", "ix"],
                           help="write mode; 'best' costs every candidate plan")
    compile_p.add_argument(
        "--stack",
        default="allow",
        choices=["allow", "none"],
        help="allow writing through SP (fastest), or forbid it entirely so "
        "the routine leaves SP alone and is safe with interrupts on",
    )
    compile_p.add_argument(
        "--interrupts",
        default="caller",
        choices=["caller", "di"],
        help="who guards stack writes: the caller (default - one DI/EI around "
        "a whole batch), or the routine itself",
    )
    compile_p.add_argument("--no-alternate", action="store_true",
                           help="do not use the alternate register bank")
    compile_p.add_argument("--moves-per-draw", type=float, default=1.0,
                           help="how many setpos calls to weigh against each draw")
    compile_p.add_argument("--no-verify", action="store_true")

    inspect_p = sub.add_parser("inspect", help="report sprite statistics")
    add_source_options(inspect_p)

    sizes_p = sub.add_parser("sizes", help="re-print the table from a previous run")
    sizes_p.add_argument("directory")
    sizes_p.add_argument("--name", help="sprite name if the directory holds several")
    return parser


def load_from_args(args: argparse.Namespace) -> tuple[Sprite, list | None]:
    sprite, palette = load_sprite(
        args.source,
        width=getattr(args, "width", None),
        height=getattr(args, "height", None),
        palette_path=getattr(args, "palette_path", None),
        transparent_index=getattr(args, "transparent_index", None),
        mask_path=getattr(args, "mask_path", None),
        nearest=getattr(args, "nearest", False),
        rect=getattr(args, "rect", None),
    )
    if getattr(args, "trim", False):
        sprite, _dx, _dy = sprite.trimmed()
    return sprite, palette


def command_inspect(args: argparse.Namespace) -> int:
    sprite, palette = load_from_args(args)
    print(f"{args.source}: {sprite.width}x{sprite.height} pixels")
    for phase in (0, 1):
        packed = sprite.pack(phase)
        rows = packed.rows()
        print(
            f"  phase {phase}: {packed.byte_width} bytes wide, "
            f"{len(packed.cells)} cells "
            f"({packed.opaque_count} opaque, {packed.half_count} half), "
            f"{len(rows)} non-empty rows, lower bound {lower_bound(packed)}T"
        )
    if palette:
        print(f"  palette: {len(palette)} entries")
    return 0


def command_compile(args: argparse.Namespace) -> int:
    sprite, palette = load_from_args(args)
    screen = Screen(args.screen_base)
    layout = MemoryLayout(screen, args.scratch_base, args.backbuffer_base)
    layout.check_backbuffer()

    reloc = Reloc(args.reloc)
    routines = [r.strip() for r in args.routines.split(",") if r.strip()]
    known = {"draw", "erase", "save", "restore", "restore_bb"}
    unsupported = set(routines) - known
    if unsupported:
        raise SystemExit(f"unknown routines {sorted(unsupported)}; known: {sorted(known)}")
    if "restore_bb" in routines and args.backbuffer_base is None:
        raise SystemExit("--routines restore_bb needs --backbuffer-base")
    forms = ("single", "list") if args.form == "both" else (args.form,)
    if "list" in forms and reloc is not Reloc.REGISTER:
        raise SystemExit("the list form needs --reloc register")
    if args.clip != "none":
        raise SystemExit("clipping arrives in M7; use --clip none")
    if args.stack == "none" and args.mode == "stack":
        raise SystemExit("--mode stack contradicts --stack none")

    x_at, y_at = (int(v, 0) for v in args.at.replace(",", " ").split())
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    command_line = " ".join(shlex.quote(a) for a in sys.argv[1:])
    source_hash = hashlib.sha256(Path(args.source).read_bytes()).hexdigest()[:12]

    report = Report(args.name, command_line=command_line, source=str(args.source))
    phases = (0,) if args.x_align == 2 else (0, 1)
    # A fixed-position build bakes in one y, so it has no parity variants;
    # relocatable builds need one per parity because the row-step encoding
    # (SET 7,L versus INC H : RES 7,L) alternates with it.
    if reloc is Reloc.NONE or args.y_align == 2:
        parities: tuple[int | None, ...] = (None,)
    else:
        parities = (0, 1)

    modes = {"best": None, "auto": "auto", "hl": Mode.HL, "stack": Mode.STACK,
             "ix": Mode.IX}
    mode = modes[args.mode]

    for phase in phases:
        packed = sprite.pack(phase)
        layout.check_scratch(scratch_size(packed))
        for parity in parities:
            if reloc is Reloc.NONE:
                # Addresses are baked in, so compile for the requested spot;
                # the "xo" variant sits one pixel right of an even --at.
                x = x_at if (x_at % 2) == phase else x_at + 1
                y = y_at
            else:
                # Relocatable builds are compiled at the canonical position
                # for their parities and moved from there.
                x, y = phase, (parity or 0)
            for routine in routines:
                for form in forms:
                    if form == "list" and routine != "draw":
                        continue  # only draw is worth batching in v1
                    row = build_variant(
                        args,
                        sprite,
                        packed,
                        palette,
                        screen,
                        layout,
                        reloc,
                        routine,
                        form,
                        phase,
                        parity,
                        x,
                        y,
                        out_dir,
                        command_line,
                        source_hash,
                    )
                    report.add(row)

    (out_dir / f"{args.name}_manifest.z80s").write_text(manifest(args.name, report.rows))
    report.write(out_dir)
    print(report.table())
    return 0


def routine_sprite(args, packed, routine):
    """The packed sprite a routine draws, if it is a draw-like routine."""
    if routine == "draw":
        return packed
    if routine == "erase":
        return erase_sprite(packed, args.erase_color, args.erase_shape)
    return None


def build_variant(
    args,
    sprite,
    packed,
    palette,
    screen,
    layout,
    reloc,
    routine,
    form,
    phase,
    parity,
    x,
    y,
    out_dir,
    command_line,
    source_hash,
) -> VariantRow:
    """Generate, verify and write one variant file; return its table row."""
    context = DrawContext(
        screen,
        x=x,
        y=y,
        reloc=reloc,
        interrupts=args.interrupts,
        allow_stack=args.stack == "allow",
        label=f"{args.name}_{routine}",
    )
    kwargs = {"use_alternate": not args.no_alternate}
    modes = {"best": None, "auto": "auto", "hl": Mode.HL, "stack": Mode.STACK,
             "ix": Mode.IX}
    mode = modes[args.mode]

    target = routine_sprite(args, packed, routine)
    setpos = None
    item_tstates = None
    notes: list[str] = []

    if target is not None:
        if form == "list":
            plan = baseline_plan(packed if target is packed else target,
                                 max_gap=args.max_gap,
                                 mode=mode if mode is not None else "auto",
                                 allow_stack=context.allow_stack)
            listing = generate_list(plan, context, label=context.label, **kwargs)
            program = listing.program
            item_tstates = listing.item_tstates
            notes.append(
                f"list form: {listing.prologue_tstates}T setup then "
                f"{listing.item_tstates}T per item"
            )
        elif mode is None:
            _plan, _cost, program = best_plan(
                target,
                context,
                max_gap=args.max_gap,
                patch_weight=13.0 * args.moves_per_draw,
                **kwargs,
            )
        else:
            plan = baseline_plan(
                target, max_gap=args.max_gap, mode=mode,
                allow_stack=context.allow_stack,
            )
            plan.validate(target)
            program = generate_draw(plan, context, **kwargs)
    else:
        to_screen = routine != "save"
        delta = layout.backbuffer_delta if routine == "restore_bb" else None
        program = generate_copy(
            packed, context, args.scratch_base, to_screen=to_screen, source_delta=delta
        )
        notes.append(
            f"scratch: {scratch_size(packed)} bytes at ${args.scratch_base:04X}"
            if routine != "restore_bb"
            else f"back buffer at ${args.backbuffer_base:04X}"
        )

    if reloc is Reloc.PATCH:
        program = label_patch_sites(program)
        setpos = generate_setpos(collect_sites(program), parity=y % 2)

    info = ModuleInfo(
        name=args.name,
        routine=routine,
        width=sprite.width,
        height=sprite.height,
        cells=len(packed.cells),
        phase=phase,
        parity=parity,
        form=form,
        reloc=reloc.value,
        clip=args.clip,
        command_line=command_line,
        source=str(args.source),
        source_hash=source_hash,
        palette=palette if routine == "draw" else None,
        lower_bound=lower_bound(packed) if routine == "draw" else None,
        compiled_at=(x, y),
        notes=notes,
    )
    if not args.no_verify:
        verify_variant(
            program, setpos, target, packed, screen, x, y, reloc, form, args
        )

    path = out_dir / f"{info.label}.z80s"
    path.write_text(render(program, info, setpos=setpos))
    return VariantRow(
        variant=info.label,
        form=form,
        path=str(path),
        size=program.size + (setpos.size if setpos else 0),
        tstates=program.tstates,
        item_tstates=item_tstates if item_tstates is not None
        else (setpos.tstates if setpos else None),
        patches=program.patch_count,
        uses_stack=uses_stack(program),
        lower_bound=info.lower_bound,
        cells=len(packed.cells),
        routine=routine,
    )


def verify_variant(
    program, setpos, target, packed, screen, x, y, reloc, form, args
) -> None:
    """Run the generated code and compare it with a reference composite.

    Relocatable variants are checked at several positions, since the whole
    point of them is that the same code draws anywhere.  Copy routines are
    exercised by the round-trip tests rather than here, since correctness
    for them means "the screen came back", not "these pixels appeared".
    """
    if target is None:
        return  # save/restore: covered by the round-trip tests
    if form == "list":
        positions = [(x, y)]
        for step in (32, 64):
            if x + step + packed.byte_width * 2 <= 256:
                positions.append((x + step, y))
        verify_list(program, target, screen, positions)
        return
    if reloc is Reloc.PATCH:
        for place in ((x, y), (40 + x % 2, 60 + y % 2), (200 + x % 2, 100 + y % 2)):
            if place[0] + packed.byte_width * 2 > 256 or place[1] + packed.height > 192:
                continue
            verify_patched(program, setpos, target, screen, (x, y), place)
        return
    registers = None
    if reloc is Reloc.REGISTER:
        address = screen.addr_byte(y, x // 2)
        registers = {"h": address >> 8, "l": address & 0xFF}
    verify_draw(
        program,
        target,
        screen,
        x,
        y,
        registers=registers,
        expected_tstates=program.tstates,
    )


def command_sizes(args: argparse.Namespace) -> int:
    import json

    directory = Path(args.directory)
    pattern = f"{args.name}_stats.json" if args.name else "*_stats.json"
    found = sorted(directory.glob(pattern))
    if not found:
        raise SystemExit(f"no stats file matching {pattern} in {directory}")
    for path in found:
        data = json.loads(path.read_text())
        report = Report(data["name"], source=data.get("source", ""))
        for row in data["variants"]:
            report.add(
                VariantRow(
                    variant=row["variant"],
                    form=row["form"],
                    path=row["path"],
                    size=row["size"],
                    tstates=row["tstates"],
                    item_tstates=row.get("item_tstates"),
                    patches=row.get("patches", 0),
                    lower_bound=row.get("lower_bound"),
                    cells=row.get("cells", 0),
                )
            )
        print(report.table())
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "compile":
        return command_compile(args)
    if args.command == "inspect":
        return command_inspect(args)
    if args.command == "sizes":
        return command_sizes(args)
    raise SystemExit(f"unknown command {args.command}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
