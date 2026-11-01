# VGA 8x16 glyph source

`cp437-8x16.hex` contains 256 glyphs in CP437 byte order, one glyph per
line and 16 scanline bytes per glyph. Bit 7 is the leftmost pixel.

The bytes are the unmodified glyph payload of `default8x16.psfu` from
[kbd v2.8.0](https://github.com/legionus/kbd/blob/v2.8.0/data/consolefonts/default8x16.psfu).
The PSF header and Unicode table are omitted; the FPGA uses byte character codes.
The upstream package is distributed under GPL-2.0-or-later; its license text is
included in `COPYING.kbd`.

Upstream PSF SHA256:
`27c671292282a42ebb442100a37cc77712d5abebe087ac29b016e523e913fcfd`

4096-byte glyph payload SHA256:
`602906c22a6d9e1dcf04cffe4fcfa4c9f5239762d670390b9d069bca5588d593`

The original repository atlas `VGA-8x16.png` already clips descenders inside
its cells (for example g/j/y) and contains no underscore pixels. Changing
the crop or scanout cannot recover those missing pixels. The complete glyph
source replaces that atlas for normal ROM generation; the atlas remains a
historical input supported by the optional PNG importer.
