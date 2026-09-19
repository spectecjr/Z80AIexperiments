# tile - compiled sprite variants

Source: `examples/solid16.txt`

Command: `compile examples/solid16.txt --name tile --out-dir examples/generated --reloc register --form list --x-align 2 --y-align 2`

| variant | form | bytes | T(call) | T(item) | patches | stack | bound | gap |
|---|---|---|---|---|---|---|---|---|
| `tile_draw_list_xe` | list | 136 | 1027 | 1017 | 0 | yes | 704 | +46% |

**1 file(s), 136 bytes total**
