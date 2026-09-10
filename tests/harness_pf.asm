; Test scaffold for polyfast.z80s against renderlit's own rasteriser.

                ORG 0x0000
                HALT
                DEFS 0x0100-$
                INCLUDE "mul8x8_qs.z80s"
                INCLUDE "democube.z80s"
                INCLUDE "renderlit.z80s"
                INCLUDE "polyfast.z80s"
                ASSERT $ <= 0x2000
                DEFS 0xE000-$
                INCLUDE "transform3d.z80s"
