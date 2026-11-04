# Transient fueling development

Engine development now supports the previous TPS exponential decay, disabled transient correction, a TPS-rate table and a MAP-rate table. Existing tunes migrate to the previous algorithm with their original three settings intact. The selected web firmware still inhibits physical engine and idle outputs. The separate dummy-load build remains gated and has not been installed here.

## Configuration and accounting

Use **Engine development → Transient fueling**. The two four-point curves contain extra fuel percent against absolute positive source rate. Triggers and minimum movement use strict greater-than comparisons. Tables, hold duration, RPM taper, coolant multiplier and maximum extra percent are editable and validated even when their mode is inactive. A zero duration disables new events; equal taper endpoints disable that taper. Deceleration uses a total fuel percentage:100 is neutral and0 suppresses fuel while other spark logic continues.

The new modes measure change over a configured acquisition window,5–100ms. They use the fast calibrated sensor values and the MCP scan-start timestamp, with nominal5ms scans. Display smoothing is separate. Control timestamps determine expiry, not the measured derivative. An already expired event cannot be revived by delayed delivery. The old TPS algorithm retains its previous control-evaluation timebase and exact scalar/pulse behavior.

First observation, restart after crank/fault/DFCO, configuration change, invalid/future/stale input, acquisition gaps over20ms and reversed clocks clear history. A repeated acquisition timestamp cannot produce another derivative. The next eligible observation seeds a baseline. This conservative policy can omit a one-step throttle reopening immediately after DFCO; no special reopen enrichment is claimed.

A stronger same-sign rate can retrigger a hold. After the minimum-movement gate, any observed opposite-sign rate cancels the old phase; it starts a deceleration phase only if it also exceeds the rate threshold. The RPM/coolant correction is latched at trigger, rather than recomputed during the hold. Old-event expiry and a new measurement in the same control call still permit a new event. The expiry fix has a scheduling-equivalence regression and independent recheck.

For **Multiply fuel**, the tapered correction scales effective fuel before deadtime. For **Add reference fuel**, extra mass per physical cylinder per720° cycle is:

`reference_mg = (100000 × displacement_m3 / cylinder_count) / (287.05 × 298.15) × 1e6 / stoich_AFR`

`extra_mg = reference_mg × tapered_extra_percent / 100`

The reference assumes100kPa,25°C,100%VE and lambda1. It is independent of current MAP, VE, warmup and lambda corrections. Cylinder trims scale the complete base-plus-extra dose. Effective mass is divided by the strategy's opening count, converted by injector flow, then deadtime is added once per opening. Deceleration always multiplies. A zero result uses the existing fuel-cut path, with no deadtime-only injector pulse. Existing pulse/duty/capacity checks can inhibit the entire command.

The existing `accel` proposal remains the effective complete-dose ratio. New diagnostics separately report the nominal latched percentage and added reference mass. Active new phases freeze EGO correction, including neutral phases; legacy EGO gating remains unchanged.

## Wiring and debugging

The feature uses the existing protected J11 MAP and J12 TPS inputs. No pin, output driver or PCB route is added. Confirm each sensor's supply, connector pin1 ground, signal pinout, voltage range and calibrated kPa/percent first. Compare raw voltage, calibrated value, measured window, source rate, trigger/phase/reason and effective dose. Noise must be assessed at the input. Increasing enrichment limits cannot repair bad wiring.

Observations distinguish proposed correction from executed edges and physical measurements. `available` identifies the diagnostic object; the rate-valid flag identifies qualified derivatives. Priming, inhibited and disabled observations can contain unknown rates, represented by JSON null or MSL NaN. Remaining hold time is relative to the observation timestamp, so retained logs and completed simulator results do not count down live.

Detailed transient fields are in web/JSON, engine MSL004 and direct SIL MSL004. The fixed232-byte ESP-NOW schema2 remains unchanged and carries only the previous effective `accel` proposal. A paired screen does not receive the new curve/phase details through that packet.

## Tune and transport versions

Current engine JSON is schema6. Exact schema1–5 inputs migrate in memory without rewriting stored bytes or revision until Save. The new [own007 definition](../tuning/esp32-ecu-transient.ini) preserves the first4992 bytes of own006, appends mode/apply,13 scalars and four4-point arrays, and uses one5120-byte page. Reserved bytes remain checked. Older INIs, defaults and application files are historical records. Old MSQ identities cannot inherit a custom new transient mode from an editor.

The runtime block is320 bytes, preserving the first256. One full `r` request receives one coherent native snapshot:321 payload bytes including status,327 bytes framed. Page chunks stay256 bytes; `f` retains256-byte blocking factors. Multi-request runtime reads do not have a cross-request snapshot guarantee. Real TunerStudio online acceptance remains unresolved because the tested application rejected our own identity; this work does not establish how that application would split a320-byte runtime read. USB rings remain1024 bytes. Physical enumeration, runtime heap/stack margins and USB/flash-load behavior need measurement.

The bounded recorder retains256 rows. Target HTTP export copies a fixed page, then serializes and sends one row at a time. Native tooling's full-page DOM is substantially larger and is not the target export path. Source budgets and native allocation-failure tests do not establish minimum free heap or stack high-water on the board.

## Comparison scope

The pinned Speeduino production sensors, corrections, fuel calculation, decoder and schedulers execute unchanged in a native virtual HAL. The adapter declares and reads back raw configuration. TPS sampling retains its33ms production clock and0.5% quantization; MAP retains its accepted integer-kPa delta timing and1kHz correction dispatch. Rate-axis raw units are divided by10, duration is10ms units, RPM taper isRPM/100, and coolant endpoints areC+40. Mapped values round to nearest integer, ties to even; unrepresentable values are rejected.

The reference has no field corresponding to our acquisition window or maximum-extra clamp. Its weaker opposite rate can leave an earlier phase active until timeout. These are reported differences, not evidence of an identical algorithm. Timer16 models4µs modulo/equality counters, without AVR CPU/vector/register emulation. Both native profiles have zero CPU/IRQ execution cost.

Each controller drives its own independent external Modelica MVEM air path and local empirical fuel-film/combustion/free shaft using executed electrical edges. Physical cylinder order stays1-3-4-2. Warm film is5% with50ms evaporation; cold film is45% with1.5s evaporation. These parameters are fixed independently of the tune and are uncalibrated. The mild comparison curves are not an engine base tune. Reference neutral controls use zero extra-fuel curves,100% decel and zero duration; upstream can still set internal phase flags. These controls test fuel sensitivity; lambda error is an observation, not a promised improvement. Halving coupling step also changes reference main-loop cadence, so it is not isolated solver convergence.

No simulation proves perfect engine operation. Wall-film calibration, extra OEM decoders, broader engine/channel strategies, protection features, actual online vendor integration and physical timing/electrical/EMI/thermal/splash/fit qualification remain open in the [coverage ledger](engine-feature-coverage.md).

```sh
python3 scripts/generate_transient_ui.py
python3 scripts/generate_tuning_wire.py
python3 scripts/generate_tunerstudio_ini.py
CXX=c++ sh scripts/test_firmware.sh
uv run --with playwright --with fmpy==0.3.26 python -m unittest discover -s tools -p 'test_*.py'
uv run --with playwright python tools/test_transient_ui.py --report-dir NEW_BROWSER_DIR
uv run --with fmpy==0.3.26 python tools/run_transient_scenarios.py --output-dir NEW_MATRIX_DIR
```

The64-run comparison completed with all declared edge/ledger/profile checks passing:48 primary runs,8 refinements and8 neutral controls. In this uncalibrated plant, mild additive enrichment reduced the cold tip-in lambda error and increased the warm error relative to neutral controls. The feature changes delivered fuel; these curves are not an optimal tune.

[Published evidence](../reports/engine/transient-enrichment/) includes155 Python tests, native sanitizer/allocation-failure checks,8 exact legacy engine replays, actual Chrome workflows and three firmware build/static audits. Independent core, storage and execution reviews found and rechecked fixes for coincident expiry and incomplete browser log export/validation. The initial matrix coverage failures remain alongside corrected profiles. Maximum declared step-refinement difference was0.229%; reference main-loop cadence changes with the step.

Actual TunerStudio MS Lite3.3.01 loaded own007, displayed both new curve axes and saved a hold edit120→125.5ms. The [application file](../tuning/examples/tunerstudio-transient-roundtrip.msq) imports through native and Chrome paths. MegaLogViewer HD Lite4.6.14 opened105-field engine and62-field SIL logs, plotting `AeCorrectionPct` and `AeMode`. These are offline file checks.

Target compiler sizes are352 bytes per runtime sample,94,296 bytes for the256-row recorder and5,976 bytes for a copied16-row page. The reviewed one-row native cJSON export peaked at19,671 requested bytes in a worst-numeric probe, excluding allocator overhead. Static frame reports remain below the configured task stacks; they are not measured stack high-water or free heap. Selected N16R8 firmware uses167,100 static RAM bytes and1,507,845 app flash bytes. The separate dummy-load image retains gated physical writes; neither image was installed.

```sh
python3 tools/verify_transient_evidence.py
```
