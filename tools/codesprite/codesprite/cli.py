"""Command line front end: ``codesprite compile | inspect | sizes``."""

from __future__ import annotations

import argparse
import hashlib
import shlex
import sys
from pathlib import Path

from .codegen.draw import DrawContext, generate_draw
from .emit.report import Report, VariantRow, manifest
from .emit.sjasm import ModuleInfo, render
from .ir import Mode, Reloc
from .optimize.baseline import baseline_plan
from .screen import MemoryLayout, Screen
from .sprite import PackedSprite, Sprite, load_sprite
from .verify import verify_draw


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
        "--routines", default="draw", help="comma separated: draw (more in M5)"
    )
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
    compile_p.add_argument("--no-serpentine", action="store_true")
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
    unsupported = set(routines) - {"draw"}
    if unsupported:
        raise SystemExit(
            f"routines {sorted(unsupported)} are not implemented yet (M5); "
            "only 'draw' is available"
        )
    if args.form != "single":
        raise SystemExit("the list form arrives in M5; use --form single")
    if reloc is not Reloc.NONE:
        raise SystemExit(
            "only --reloc none is implemented so far (M4 adds patch and register)"
        )

    x_at, y_at = (int(v, 0) for v in args.at.replace(",", " ").split())
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    command_line = " ".join(shlex.quote(a) for a in sys.argv[1:])
    source_hash = hashlib.sha256(Path(args.source).read_bytes()).hexdigest()[:12]

    report = Report(args.name, command_line=command_line, source=str(args.source))
    phases = (0,) if args.x_align == 2 else (0, 1)

    for phase in phases:
        packed = sprite.pack(phase)
        plan = baseline_plan(
            packed,
            max_gap=args.max_gap,
            serpentine=not args.no_serpentine,
            mode=Mode.HL,
        )
        plan.validate(packed)
        # A fixed-position build bakes in absolute addresses, so the x it is
        # compiled for must have the parity of the variant being generated:
        # the "xo" file draws one pixel to the right of an even --at.
        x = x_at if (x_at % 2) == phase else x_at + 1
        context = DrawContext(screen, x=x, y=y_at, reloc=reloc)
        program = generate_draw(plan, context)

        info = ModuleInfo(
            name=args.name,
            routine="draw",
            width=sprite.width,
            height=sprite.height,
            cells=len(packed.cells),
            phase=phase,
            form=args.form,
            reloc=reloc.value,
            clip=args.clip,
            command_line=command_line,
            source=str(args.source),
            source_hash=source_hash,
            palette=palette,
            lower_bound=lower_bound(packed),
        )
        if not args.no_verify:
            verify_draw(
                program, packed, screen, x, y_at, expected_tstates=program.tstates
            )
        path = out_dir / f"{info.label}.z80s"
        path.write_text(render(program, info))
        report.add(
            VariantRow(
                variant=info.label,
                form=args.form,
                path=str(path),
                size=program.size,
                tstates=program.tstates,
                patches=program.patch_count,
                lower_bound=info.lower_bound,
                cells=len(packed.cells),
            )
        )

    (out_dir / f"{args.name}_manifest.z80s").write_text(manifest(args.name, report.rows))
    report.write(out_dir)
    print(report.table())
    return 0


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
