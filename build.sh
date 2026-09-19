#!/bin/sh
# Build the Bubble Bobble prototype for the SAM Coupe.
#
#   build/bb.bin  32K image for pages 0 and 1, entered at $0000 with
#                 LMPR selecting page 0 and the ROM paged out.
#   build/bb.sym  symbol table.
set -e
cd "$(dirname "$0")"

echo "== generating assets =="
python3 tools/bbgfx.py

echo "== assembling =="
mkdir -p build
# pasmo resolves INCLUDE relative to the working directory
(cd bubble && pasmo --bin bb.z80s ../build/bb.bin ../build/bb.sym)
ls -l build/bb.bin

echo "== verifying =="
python3 tools/bbverify.py
python3 tools/budget.py
