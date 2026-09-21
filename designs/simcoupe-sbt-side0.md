# SimCoupe: a `.sbt` cannot be larger than side 0

A defect report, with a reproduction, from building `build/chequer10.sbt`
(see `loader.md`). Found in SimCoupe at
`1f96603` (2026-08-31), `Base/Disk.cpp`.

## What happens

A `.sbt` larger than **387,600 bytes** fails to load. SAMDOS stops partway
through with

    108  End of file, 0:1

and the machine is left with whatever had been read so far. The limit is
exact and was found by bisection: 387,000 bytes loads, 388,200 does not;
387,600 is 76 tracks × 10 sectors × 510 bytes, which is **everything on
side 0 from the first data track**.

`MAX_SAM_FILE_SIZE` in `Base/Disk.h` says 795,591 — both sides — so a file
between the two is accepted by `FileDisk::IsRecognised`, presented as a disk,
and then cannot be read to the end.

## Why

`FileDisk::ReadData` (`Base/Disk.cpp:681`) decides whether a sector holds
file data with

```cpp
else if (cyl >= MGT_DIRECTORY_TRACKS)
{
    auto offset = (head * MGT_DISK_CYLS + cyl - MGT_DIRECTORY_TRACKS) *
        (MGT_DISK_SECTORS * (NORMAL_SECTOR_SIZE - 2)) + ...
```

The **guard** treats "cylinder under 4" as a directory track on *both*
heads; the **offset**, one line below, treats only side 0's first four
tracks that way. So the file's data runs out at the end of side 0, and the
first sector of side 1 — which is where the sector chain written by the same
function points next — comes back as 512 zero bytes. A zero chain link is
end-of-file, so that is what DOS reports.

The chain itself is right. Written at `Base/Disk.cpp:695`, it goes from
cylinder 79 head 0 to cylinder 0 head 1, and the offset formula agrees with
it: `(1 * 80 + 0 - 4) = 76`, the 77th data track. Only the guard disagrees.

## Reproduction

Any file between 387,601 and 795,591 bytes will do, and the contents do
not matter, because the failure is in the load:

    head -c 400000 /dev/urandom > big.sbt
    head -c 387000 /dev/urandom > small.sbt
    simcoupe big.sbt            # 108  End of file, 0:1
    simcoupe small.sbt          # 29   Not understood, 0:1

Both were run here. The second message is the ROM refusing to *execute*
387,000 bytes of noise, which is the point: that file **loaded**. The
first never got that far.

## Suggested fix

Make the guard match the offset — the directory is on side 0 only:

```cpp
else if (head != 0 || cyl >= MGT_DIRECTORY_TRACKS)
```

which makes the usable size `MAX_SAM_FILE_SIZE`, as `Base/Disk.h` already
intends. Everything else — the sector chain, the directory entry's sector
map, the file header — already covers both sides.

## What it cost here

`chequer10`'s map is 341K in 26 pages. The natural image for it is the
memory map itself, with the screen buffers as holes, which is 27 pages and
442K — inside `MAX_SAM_FILE_SIZE` and outside what a `.sbt` can actually
read. The image therefore ships its eleven chunks back to back in 23 pages
(376,832 bytes, 10,768 under the limit) and a loader moves 22 pages into
place at run time. That is not wasted work — the loader is needed anyway for
page 0, which a linear load cannot reach — but the page moves and their
ordering are there because of this.

## Not a bug, but worth knowing beside it

A `.sbt` is auto-executed at **0x8000**, the first byte of the file, with
page 1 in section C: `FileDisk::FileDisk` fixes the CODE header to
`start 0x8000, first page 1, auto-execute`. So the first bytes of any `.sbt`
have to be executable, which decides what can be at page 1 of the map.
`Base/Disk.cpp:613` is where that is set, and the SAM's own `LOAD CODE
32768: CALL 32768` is the same convention, so this is a documentation point
rather than a limitation.
