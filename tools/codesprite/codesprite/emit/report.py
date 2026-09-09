"""The size / cost table printed after every compile.

One row per generated variant file, so it is obvious what each option
costs in bytes and T-states before anything is included in a build.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

COLUMNS = [
    ("variant", 34, "<"),
    ("form", 7, "<"),
    ("bytes", 7, ">"),
    ("T(call)", 9, ">"),
    ("T(item)", 9, ">"),
    ("patches", 8, ">"),
    ("bound", 8, ">"),
    ("gap", 7, ">"),
]


@dataclass
class VariantRow:
    """One generated file's headline numbers."""

    variant: str
    form: str
    path: str
    size: int
    tstates: int
    item_tstates: int | None = None
    patches: int = 0
    lower_bound: int | None = None
    cells: int = 0
    routine: str = "draw"

    @property
    def gap(self) -> float | None:
        if not self.lower_bound:
            return None
        return 100.0 * (self.tstates - self.lower_bound) / self.lower_bound

    def cells_per_tstate(self) -> float | None:
        if not self.cells:
            return None
        return self.tstates / self.cells


@dataclass
class Report:
    name: str
    rows: list[VariantRow] = field(default_factory=list)
    command_line: str = ""
    source: str = ""

    def add(self, row: VariantRow) -> None:
        self.rows.append(row)

    @property
    def total_size(self) -> int:
        return sum(row.size for row in self.rows)

    def table(self) -> str:
        header = "".join(f"{title:{align}{width}}" for title, width, align in COLUMNS)
        lines = [header, "-" * len(header)]
        for row in self.rows:
            gap = row.gap
            values = [
                row.variant,
                row.form,
                str(row.size),
                str(row.tstates),
                "-" if row.item_tstates is None else str(row.item_tstates),
                str(row.patches),
                "-" if row.lower_bound is None else str(row.lower_bound),
                "-" if gap is None else f"{gap:+.0f}%",
            ]
            lines.append(
                "".join(
                    f"{value:{align}{width}}"
                    for value, (_t, width, align) in zip(values, COLUMNS)
                )
            )
        lines.append("-" * len(header))
        lines.append(f"{len(self.rows)} file(s), {self.total_size} bytes total")
        return "\n".join(lines)

    def markdown(self) -> str:
        titles = [title for title, _w, _a in COLUMNS]
        lines = [
            f"# {self.name} - compiled sprite variants",
            "",
        ]
        if self.source:
            lines += [f"Source: `{self.source}`", ""]
        if self.command_line:
            lines += [f"Command: `{self.command_line}`", ""]
        lines += ["| " + " | ".join(titles) + " |", "|" + "---|" * len(titles)]
        for row in self.rows:
            gap = row.gap
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{row.variant}`",
                        row.form,
                        str(row.size),
                        str(row.tstates),
                        "-" if row.item_tstates is None else str(row.item_tstates),
                        str(row.patches),
                        "-" if row.lower_bound is None else str(row.lower_bound),
                        "-" if gap is None else f"{gap:+.0f}%",
                    ]
                )
                + " |"
            )
        lines += ["", f"**{len(self.rows)} file(s), {self.total_size} bytes total**", ""]
        return "\n".join(lines)

    def to_json(self) -> str:
        return json.dumps(
            {
                "name": self.name,
                "source": self.source,
                "command_line": self.command_line,
                "total_size": self.total_size,
                "variants": [asdict(row) | {"gap_percent": row.gap} for row in self.rows],
            },
            indent=2,
        )

    def write(self, directory: str | Path) -> tuple[Path, Path]:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        md = directory / f"{self.name}_SIZES.md"
        js = directory / f"{self.name}_stats.json"
        md.write_text(self.markdown())
        js.write_text(self.to_json())
        return md, js


def manifest(name: str, rows: list[VariantRow]) -> str:
    """An sjasmplus file listing every variant as a commented INCLUDE."""
    lines = [
        f"; {name} - compiled sprite variant manifest",
        "; Uncomment the variants this project uses.",
        ";",
    ]
    for row in rows:
        lines.append(
            f";   {row.tstates:>6}T {row.size:>5}b  {row.form:<6}  "
            f"INCLUDE \"{Path(row.path).name}\""
        )
    lines.append("")
    for row in rows:
        lines.append(f'; INCLUDE "{Path(row.path).name}"')
    lines.append("")
    return "\n".join(lines)
