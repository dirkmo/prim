# Project reporting preferences

- Read `forth/TODO.md` when working on Forth. Keep task status current and
  briefly remind the user of remaining tasks at the end of relevant Forth work.
  These reminders do not authorize starting additional tasks automatically.

- Keep IRQs disabled while an ISR executes; do not allow nested interrupt
  handlers. Re-enable IRQs only as part of the ISR return. The current Forth
  handler uses INTDI as its first instruction and INTEI.RET at its end.

- After changes to Forth, report the remaining free RAM in bytes. Use the
  freshly built image/map and identify the profile and usable dictionary range;
  do not count reserved SRAM or MMIO as freely available memory.
- After changes to the FPGA bitstream, report FPGA utilization from the matching
  synthesis/place-and-route reports: logic cells, LUT4, flip-flops, block RAM
  and PLLs, with device capacities where available. Identify estimates explicitly.
