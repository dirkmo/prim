# Official board netlists

Unmodified copies downloaded from Olimex's official repositories on 2026-10-31.
Use these local files when checking connector signals, FPGA balls and pin
conflicts; no network access is needed for pin lookups.

| Local file | Board / revision | Official download |
|---|---|---|
| [iCE40HX8K-EVB_Rev_B.net](iCE40HX8K-EVB_Rev_B.net) | FPGA main board, Rev.B, CT256 | [Olimex source](https://raw.githubusercontent.com/OLIMEX/iCE40HX8K-EVB/master/HARDWARE/REV-B/iCE40HX8K-EVB_Rev_B.net) |
| [ICE40-IO_Rev_A.net](ICE40-IO_Rev_A.net) | VGA / PS2 / IrDA expansion, Rev.A | [Olimex source](https://raw.githubusercontent.com/OLIMEX/iCE40-IO/master/ICE40-IO_Rev_A.net) |

These snapshots were fetched from `master`; the checksums below identify the
exact saved contents, independently of later upstream changes. They retain
the original filenames, bytes and embedded design metadata.

```text
af507cc52effc0e7ddb7c0c9baef41a4e8d73d2ba9fddcd7c95d4cfb34690b19  iCE40HX8K-EVB_Rev_B.net
a048c4d3ec83bd46fd28c1ef439291e34f2dd1a331e92b962535408a2a8226a1  ICE40-IO_Rev_A.net
```

Verify them from this directory with `sha256sum *.net`.

For a connector-to-FPGA lookup, find the `GPIO1` node in the main board's
`nets` section and the `U4` node on the same net. For expansion signals, find
the named net (for example `/VGA_HSYNC`) and its `GPIO_In1` / `GPIO_Out1` pin,
then match that pin number to `GPIO1` on the main board. Current constraints
are in [board.pcf](../olimex_ice40hx8k_evb/board.pcf).
