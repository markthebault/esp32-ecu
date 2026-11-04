# Shared-I2C status LED software checkpoint

The separate `compact_n16r8_flex_dev` build removes GPIO38 RMT ownership, configures it as input and drives an advisory ordinary RGB interface through MCP23008 address0x21. A single monitor owner shares one3ms transaction origin with required switches at0x20. Switch guards run first; LED guarded reads wait for two remaining integer-ms timeout slots. No physical device was flashed.

The driver initializes OLAT off before direction, makes every GP an output (unused GP3..7 NC/low), and verifies a nonuniform IOCON4 frame plus trailing IODIR. Independent review found and closed an initial all-zero/byte-mode alias. Full U64 observation/completion/query ordering, SDK failures, partial ownership cleanup, stale data and cross-task policy coalescing have native checks. SDK allocation/deletion and CPU/lock overhead are not proven hard WCET.

The paired-screens UI separates requested policy from verified/historical latch and clears verification after failed polls. Six actual-service mocked-I2C fixtures,25 malformed payloads and installed Chrome desktop/mobile checks pass. Screenshots explicitly label their native SDK-model replay. Latch readback is not light output or live CPU health; a failed bus/CPU can retain green. A missing LED alone adds no engine dependency, while a shared-bus fault invalidates required switches and produces a control cut in the native controller check.

Parent checks:518 portable LED,243 legacy switch service,2336 actual shared-service assertions (2366 with six fixture exports),74 status allocation cuts, full native regression,28 radio/configuration Python tests and62,297 unchanged ingress assertions. Independent review adds its own8-case SDK model,103 UI checks, build/config/generation negatives and read-only linked-ELF audits. Its exact scope/source hashes are in reviews/independent/review.json.

Final004 has four successful real Linux builds, identical before/after compilation inputs, retained unchanged current default cache and lossless gzip ELF archives. All three web ELFs contain the exact current complete HTML in flash rodata; the bench profile omits web UI. Existing linked-engine policy and exclusive-USB audits pass; the new profile's complete current ISR closure passes static placement. These checks do not establish runtime heap/stack, actual USB, interrupt interference or physical behavior. Only the existing A3 dummy-load image has its separately gated dummy policy; selected N16R8 physical engine scheduling stays inhibited.

Two build-tool issues are disclosed. The first direct PlatformIO invocation after editing platformio.ini automatically removed older generated default environment caches; the original selected10c99... ELF was not recovered after a bounded search. Source history and old immutable report packets remain. Later builds use a fresh owned PLATFORMIO_BUILD_DIR, retain the current default cache/SDK configs and archive resulting ELF bytes losslessly. Initial build001/002 embedded stale UI;003 correctly rejected its unchanged-source assertion because declared header generation occurred before sampling. Final004 regenerates first, permits only the declared header output, then attests stable compilation inputs. Earlier receipts are preserved as history, not relabeled successes for current UI.

The GPIO38 capture worker, source-local masking/publication/control-ACK fences, protected frontend, exact physical LED driver/circuit, PCB/case integration, physical HIL/EMI/surge/thermal/splash/fit, negotiated flex radio, ethanol chemistry and supported online vendor identity remain open. Required target flex still inhibits control. This checkpoint does not complete Speeduino parity or qualify an engine/vehicle.

Current sources are copied under sources/. Native cJSON dependencies are bundled with their license notices. Reviewer executables/objects remain in the original local cache; the omission list retains hashes, while final firmware ELFs are bundled losslessly. Four compressed ELFs and firmware.bin files are records for inspection, not installation instructions or a manufacturing release.

```sh
python3 -B tools/verify_shared_led_evidence.py --replay
python3 -B scripts/build_firmware_preserved.py --output .cache/engine/NEW_BUILD --environment compact_n16r8_flex_dev
```

Default verification uses frozen evidence. Add --check-live-sources only to compare this checkpoint with the current worktree. Replays execute portable/native models only, never an Xtensa or production Speeduino image.
