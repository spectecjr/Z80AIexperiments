# spr_ship - compiled sprite variants

Source: `examples/ship14.txt`

Command: `compile examples/ship14.txt --name spr_ship --out-dir examples/generated --reloc patch --routines draw,erase,save,restore`

| variant | form | bytes | T(call) | T(item) | patches | stack | bound | gap |
|---|---|---|---|---|---|---|---|---|
| `spr_ship_draw_single_xe_ye` | single | 241 | 1078 | 34 | 2 | no | 500 | +116% |
| `spr_ship_erase_single_xe_ye` | single | 157 | 762 | 34 | 2 | no | - | - |
| `spr_ship_save_single_xe_ye` | single | 181 | 1133 | 41 | 2 | no | - | - |
| `spr_ship_restore_single_xe_ye` | single | 205 | 1229 | 41 | 2 | no | - | - |
| `spr_ship_draw_single_xe_yo` | single | 242 | 1082 | 34 | 2 | no | 500 | +116% |
| `spr_ship_erase_single_xe_yo` | single | 158 | 766 | 34 | 2 | no | - | - |
| `spr_ship_save_single_xe_yo` | single | 182 | 1137 | 41 | 2 | no | - | - |
| `spr_ship_restore_single_xe_yo` | single | 206 | 1233 | 41 | 2 | no | - | - |
| `spr_ship_draw_single_xo_ye` | single | 295 | 1325 | 34 | 2 | no | 693 | +91% |
| `spr_ship_erase_single_xo_ye` | single | 104 | 610 | 34 | 2 | yes | - | - |
| `spr_ship_save_single_xo_ye` | single | 185 | 1165 | 41 | 2 | no | - | - |
| `spr_ship_restore_single_xo_ye` | single | 209 | 1261 | 41 | 2 | no | - | - |
| `spr_ship_draw_single_xo_yo` | single | 296 | 1329 | 34 | 2 | no | 693 | +92% |
| `spr_ship_erase_single_xo_yo` | single | 105 | 614 | 34 | 2 | yes | - | - |
| `spr_ship_save_single_xo_yo` | single | 186 | 1169 | 41 | 2 | no | - | - |
| `spr_ship_restore_single_xo_yo` | single | 210 | 1265 | 41 | 2 | no | - | - |

**16 file(s), 3162 bytes total**
