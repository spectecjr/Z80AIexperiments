import pytest

from codesprite.screen import BYTES_PER_ROW, MemoryLayout, Screen, ScreenError
from codesprite.sprite import (
    MASK_BOTH,
    MASK_HIGH,
    MASK_LOW,
    Sprite,
    SpriteError,
    load_bin,
    load_txt,
    save_txt,
)


def test_addressing_matches_formula():
    s = Screen(0x8000)
    assert s.addr(0, 0) == 0x8000
    assert s.addr(0, 1) == 0x8000  # two pixels share a byte
    assert s.addr(0, 2) == 0x8001
    assert s.addr(1, 0) == 0x8080
    assert s.addr(2, 0) == 0x8100
    assert s.addr(191, 254) == 0x8000 + 191 * 128 + 127
    assert s.end == 0x8000 + 24576 == 0xE000


def test_page_and_parity_decomposition():
    s = Screen(0x8000)
    for y in range(0, 192):
        for col in (0, 63, 127):
            assert (s.page_h(y) << 8) | s.low_l(y, col) == s.addr_byte(y, col)
            assert s.parity(y) == (s.low_l(y, col) >> 7)


def test_row_step_is_bit7_of_l():
    s = Screen(0x8000)
    for y in range(0, 191):
        here, below = s.addr_byte(y, 40), s.addr_byte(y + 1, 40)
        if y % 2 == 0:  # SET 7,L
            assert below == (here | 0x80)
        else:  # INC H : RES 7,L
            assert below == ((here + 0x100) & ~0x80 & 0xFFFF)


def test_addr_wraps_for_spill():
    s = Screen(0x8000)
    assert s.addr(-1, 0) == 0x7F80
    assert Screen(0x0000).addr(-1, 0) == 0xFF80


def test_bad_base_rejected():
    with pytest.raises(ScreenError):
        Screen(0x8001)


def test_scratch_overlap_detected():
    layout = MemoryLayout(Screen(0x8000), scratch_base=0xE000)
    layout.check_scratch(0x2000)
    with pytest.raises(ScreenError):
        MemoryLayout(Screen(0x8000), scratch_base=0xD000).check_scratch(0x100)
    with pytest.raises(ScreenError):
        layout.check_scratch(0x2001)


def test_backbuffer_delta():
    layout = MemoryLayout(Screen(0x8000), backbuffer_base=0x2000)
    layout.check_backbuffer()
    assert layout.backbuffer_delta == (0x2000 - 0x8000) & 0xFFFF


def test_pack_even_phase_high_nibble_is_left_pixel():
    sprite = Sprite([[1, 2, 3, 4]])
    packed = sprite.pack(0)
    assert packed.byte_width == 2
    assert [(c.col, c.value, c.mask) for c in packed.cells] == [
        (0, 0x12, MASK_BOTH),
        (1, 0x34, MASK_BOTH),
    ]


def test_pack_odd_phase_creates_half_bytes_at_both_ends():
    sprite = Sprite([[1, 2, 3, 4]])
    packed = sprite.pack(1)
    assert packed.byte_width == 3
    assert [(c.col, c.value, c.mask) for c in packed.cells] == [
        (0, 0x01, MASK_LOW),
        (1, 0x23, MASK_BOTH),
        (2, 0x40, MASK_HIGH),
    ]


def test_transparent_pixels_drop_or_halve_cells():
    sprite = Sprite([[None, 5, None, None]])
    packed = sprite.pack(0)
    assert [(c.col, c.value, c.mask) for c in packed.cells] == [(0, 0x05, MASK_LOW)]


def test_pack_odd_width():
    packed = Sprite([[7, 8, 9]]).pack(0)
    assert packed.byte_width == 2
    assert [(c.col, c.value, c.mask) for c in packed.cells] == [
        (0, 0x78, MASK_BOTH),
        (1, 0x90, MASK_HIGH),
    ]


def test_rows_spans_and_counts():
    sprite = Sprite([[1, 2, 3, 4], [None, None, None, None], [None, 9, 9, None]])
    packed = sprite.pack(0)
    assert set(packed.rows()) == {0, 2}
    assert packed.span(0) == (0, 1)
    assert packed.span(1) is None
    # Row 2's two pixels straddle a byte boundary: one low-nibble cell and
    # one high-nibble cell, so two opaque cells (row 0) and two half cells.
    assert packed.opaque_count == 2
    assert packed.half_count == 2
    assert packed.span(2) == (0, 1)


def test_crop_and_trim():
    sprite = Sprite(
        [
            [None, None, None],
            [None, 3, None],
            [None, None, None],
        ]
    )
    trimmed, dx, dy = sprite.trimmed()
    assert (trimmed.width, trimmed.height, dx, dy) == (1, 1, 1, 1)
    assert trimmed.pixels == [[3]]
    with pytest.raises(SpriteError):
        sprite.crop(2, 2, 3, 3)


def test_txt_roundtrip(tmp_path):
    path = tmp_path / "s.txt"
    path.write_text("# a comment\n0f.\n.a1\n")
    sprite = load_txt(path)
    assert sprite.pixels == [[0, 15, None], [None, 10, 1]]
    out = tmp_path / "out.txt"
    save_txt(sprite, out)
    assert load_txt(out).pixels == sprite.pixels


def test_txt_rejects_ragged(tmp_path):
    path = tmp_path / "s.txt"
    path.write_text("012\n01\n")
    with pytest.raises(SpriteError):
        load_txt(path)


def test_bin_with_transparent_index(tmp_path):
    path = tmp_path / "s.bin"
    path.write_bytes(bytes([0x12, 0x34, 0x00, 0x56]))
    sprite = load_bin(path, width=4, height=2, transparent_index=0)
    assert sprite.pixels == [[1, 2, 3, 4], [None, None, 5, 6]]


def test_bin_with_mask(tmp_path):
    data = tmp_path / "s.bin"
    data.write_bytes(bytes([0x12, 0x34]))
    mask = tmp_path / "s.msk"
    mask.write_bytes(bytes([1, 0, 0, 1]))
    sprite = load_bin(data, width=4, height=1, mask_path=mask)
    assert sprite.pixels == [[1, None, None, 4]]


def test_png_indexed_roundtrip(tmp_path):
    PIL = pytest.importorskip("PIL.Image")
    from codesprite.sprite import load_png

    image = PIL.new("P", (2, 2))
    image.putpalette([0, 0, 0, 255, 0, 0, 0, 255, 0] + [0] * (256 * 3 - 9))
    image.putpixel((0, 0), 1)
    image.putpixel((1, 0), 2)
    image.putpixel((0, 1), 0)
    image.putpixel((1, 1), 1)
    path = tmp_path / "s.png"
    image.save(path)
    sprite, palette = load_png(path, transparent_index=0)
    assert sprite.pixels == [[1, 2], [None, 1]]
    assert palette[:3] == [(0, 0, 0), (255, 0, 0), (0, 255, 0)]


def test_pixel_range_validated():
    with pytest.raises(SpriteError):
        Sprite([[16]])
    with pytest.raises(SpriteError):
        Sprite([])
