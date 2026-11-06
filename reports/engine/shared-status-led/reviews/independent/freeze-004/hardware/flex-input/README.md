# Flex input architecture draft

`FLEX-G38-DRAFT1` reserves GPIO38 for a future protected flex input on a new carrier revision. The [machine-readable contract](architecture.json) records allocation, capture ownership, shared I2C limits and unfinished gates. This directory contains no circuit or released CAD. Do not connect a sensor using this draft.

The preferred allocation moves the external GPIO38 WS2812 status function to an ordinary RGB LED driven through a direct-solder PDIP18 MCP23008 at address0x21. Existing switch acquisition remains at0x20 with its GP7-to-GP6 challenge and full-byte IODIR guard. IO7 must be configured as output even when it is NC on the new expander. [Microchip DS20001919I, Register1-1](https://ww1.microchip.com/downloads/aemDocuments/documents/APID/ProductDocuments/DataSheets/MCP23008-and-MCP23008-Data-Sheet-DS20001919.pdf)

GPIO45/46 stay unconnected. GPIO46 must be low with BOOT low for joint download; GPIO45 can select VDD_SPI without a verified eFuse override. Chip Reset strap sampling differs from resets that retain GPIO state. This allocation avoids depending on an unmeasured strap gate, reset retention or the supplier module's fuses. No eFuse change is requested. [Espressif boot documentation](https://docs.espressif.com/projects/esptool/en/latest/esp32s3/advanced-topics/boot-mode-selection.html)

Historical compact GPIO38 LED firmware and generic GPIO38 ARM firmware cannot own the new input. The separate `compact_n16r8_flex_dev` build excludes every old RMT initialization/write and explicitly disables GPIO output before configuring GPIO38 as an input. Historical/default builds keep their WS2812 wiring. The new build has no flex capture worker yet, so required flex input still inhibits control. No device has been flashed.

The existing group0 capture timer stays running and calibrated. Its third channel would acquire both flex edges at priority3; crank/cam keep their channels, status and timing. The hardware has one event latch per channel. Software queues cannot establish lossless capture. The [portable ingress](../../firmware/include/ecu/flex_ingress.hpp) implements bounded handoff and suppression decisions only. The target must supply source-specific interrupt masking/clearing, locking, a single worker, actual calibration/revision binding and completed-control ACK routing. Every stop/rearm or binding change must also invalidate the separate floating-point Capture series. Ingress queue clearing cannot do that itself. Only the owning worker may forward both fault tickets after a completed matching invalid control evaluation; the ingress cannot verify control execution.

Sample callback/owner time after taking the same lock used for the ingress call. A timestamp sampled before waiting can be older than an intervening event and correctly fail the monotonic-clock check, even when an ACK's metadata is stale. Snapshot holdoff status is evaluated at its recorded `last_observed_us`, not at the time a diagnostic reader receives it.

The32-callback/10ms fixed window applies to matching active callbacks within an armed episode. It is not a global IRQ budget across inactive/foreign callbacks or arbitrary stop/arm cycles. The trusted owner must honor local interrupt suppression and the ACK/holdoff retry path, and must not implement noise retries as repeated normal stop/arm.

Pop followed by floating-point work outside the lock is not a publication fence. Retain context, fault generation and arm boundary with the pop. Before publishing, atomically revalidate current context/generation/armed state and the event timestamp against the current arm boundary, then commit under that same lock or an equivalent versioned commit. A mismatch discards the result and invalidates/reacquires the separate Capture series. The edge has no generation field, so the companion snapshot/version must be retained. This owning-worker fence remains unimplemented.

The new software implements one bus owner and one shared3ms transaction deadline per5ms tick. Required switch guards run first. LED work uses remaining slack, coalesces requests and advances one bounded operation at a time. Two-transaction LED verification waits for at least two remaining integer-ms timeout slots; it never starts a second3ms budget. Bus release preserves either device's ownership. SDK allocation/deletion lack timeout APIs; CPU/lock overhead and target timing remain unmeasured, so this is not a hard WCET claim.

GP0/1/2 are active-high red/green/blue driver inputs. All GP pins are outputs (`IODIR=0`); unused GP3..7 are NC and held low. The driver writes OLAT off before direction, uses IOCON.ODR=1 (`IOCON=4`) and verifies the full sequential register image plus an independent trailing IODIR. The nonzero IOCON marker rejects byte-mode reads that would otherwise repeat zero across an all-zero frame. This software contract does not select a transistor/LED circuit or authorize direct sensor/LED connection.

Normal requests steady green; pairing and detected problems request blue/red with250ms on/off intervals, with fault priority. MCP outputs can retain green after CPU/bus failure. The paired-screens UI shows requested policy separately from verified latch, age and fault state, and clears readback on a failed HTTP poll. Known historical green is never presented as a current optical or CPU-health measurement. A missing LED alone does not add an engine-control dependency; a failed shared bus still invalidates required switch inputs.

The protected frontend, exact LED/driver/resistors, bias, polarity, off-state back-power and pulse skew remain open. The parent U7 has two spare3.3V SN74HC14N gates that may be reusable, but copying a divider/RC does not qualify them. Preserve the physical sensor LOW width. The core's2µs endpoint allowance covers timestamp quantization, not an unmeasured circuit delay. No sensor model, supply or harness pinout has been selected.

The120×120mm limit, ordinary leaded parts, direct-solder DIP, pluggable N16R8, inward10mm antenna allowance and sealed PAIR/RESET remain constraints. Physical dimensions and RF/fit behavior remain unverified. A3/A4/A5 sources and manufacturing records remain historical copies. Physical engine outputs remain inhibited.

Build only into a new owned directory, for example:

```sh
python3 -B scripts/build_firmware_preserved.py --output .cache/engine/NEW_BUILD --environment compact_n16r8_flex_dev
```

PlatformIO automatically removes its build cache after project configuration changes. The first direct build for this increment cleared previous generated environment caches before retention was applied; their original ELF bytes were not recovered. Source/history and frozen reports remain. The wrapper now retains the current default cache, sets a fresh `PLATFORMIO_BUILD_DIR`, verifies source/cache hashes and archives each resulting ELF losslessly. It never flashes.
