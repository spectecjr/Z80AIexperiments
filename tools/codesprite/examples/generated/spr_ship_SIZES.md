# spr_ship - compiled sprite variants

Source: `examples/ship14.txt`

Command: `compile examples/ship14.txt --name spr_ship --out-dir examples/generated --reloc patch --routines draw,erase,save,restore --x-align 2 --y-align 2`

| variant | form | bytes | T(call) | T(item) | patches | stack | bound | gap |
|---|---|---|---|---|---|---|---|---|
| `spr_ship_draw_single_xe` | single | 241 | 1078 | 34 | 2 | no | 500 | +116% |
| `spr_ship_erase_single_xe` | single | 157 | 762 | 34 | 2 | no | - | - |
| `spr_ship_save_single_xe` | single | 178 | 1123 | 41 | 2 | no | - | - |
| `spr_ship_restore_single_xe` | single | 203 | 1223 | 41 | 2 | no | - | - |

**4 file(s), 779 bytes total**
