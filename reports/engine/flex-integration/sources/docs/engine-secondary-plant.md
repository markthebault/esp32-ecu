# Secondary tables on the external engine plant

The suite compares both project dispatchers with actual pinned Speeduino production loops. It defines128 primary runs,20 half-step refinements,4 exact disabled-path replays and20 deliberately corrupted results that must reject. [The evidence packet](../reports/engine/secondary-plant/README.md) contains complete compressed trajectories, actuator edges, source/executable hashes, independent reviews and reproducible audits. This is software characterization on an uncalibrated research plant. Full ECU parity, physical engine operation and online TunerStudio acceptance remain open.

## What runs

Each ECU controls its own MVEM air path, empirical fuel transport/combustion and free shaft. Executed injector openings and actual coil discharge angles drive that plant. Controllers do not share sensor trajectories, RPM, commanded fuel or a scheduler. Conservation checks independently replay the complete edge stream and mass/energy ledgers.

The four profiles are the portable project executor, the shared ESP32 target dispatcher through its native ABI, and production Speeduino with native32-bit or emulated16-bit timer counters. The reference pin is `9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20`, without `UNIT_TEST`. Its original checkout stays unchanged. Before-start profile writers read back every configuration field and map byte; secondary algorithms, sensor conversions, corrections, decoder and schedulers remain production code.

Project Input modes use the actual portable acquisition state machine and an independent digital MCP23008 register/contact model. The nominal5ms blocking monitor continues to let the plant and dispatcher advance. Registers are read at+400us, GPIO/OLAT at+1200us and the trailing IODIR guard completes at+1800us. Publication waits for completion and retains the conservative transaction-start source timestamp. Other bus durations are declared wire-clock-scale assumptions. This does not measure physical I2C timing, CPU load, electrical protection or SDK scheduling.

Reference Input modes independently poll virtual GPIO14/15 through the real configured pin mapping. They do not inherit project debounce, freshness, bus failures or acknowledgement policy. Diagnostic frames distinguish current raw pins from the pins and rotation state used by the last production loop. A same-time contact update does not retroactively change that completed loop.

## Coverage and acceptance

The32 cases per profile cover Off, edited unused Off metadata, neutral Multiply100/Add0, nonneutral composition, fuel-only/spark-only selection, RPM/MAP/TPS conditions, an exact TPS threshold plateau, a quantization counterexample, independent/shared/inverted/opposite contact choices, shared5/35ms debounce, bounce, batch/semi/sequential operation, bus NACK/timeout/underfill/reset, producer pause, skipped control observations, mixed TPS/ratio sources, zero ordinary fuel, overload and cylinder trims.

Assertions require actual primary/secondary selection witnesses, physical-source coordinates, independent arithmetic/clamps, complete actuator chronology, source freshness and bounded project high times. Project spark errors are checked against the event-latched advance with the existing0.2degree SIL bound. The reference newest-demand diagnostic is not an event-latched timing oracle. Neutral controls require identical complete edges, combustions and ledgers within each controller. Nonneutral controls must change executed edges and shaft work.

Recoverable input faults must reach an inhibited completed control observation, retain their exact pending identity across skipped observations, increment the consumption counter once, and obtain a new post-ACK guarded read before source-time debounce can finish. A normal already-qualified bouncing transition retains its old selection while pending. It does not automatically become a global fault.

The20 corruptions include inactive selection, omitted composition, unchanged actuators/plant, an unexercised fault, erased acknowledgement, a wrong coordinate and a consistently recomputed wrong-source lookup. The latter prevents mutually consistent diagnostics from substituting for the physical sensor source. Refinements halve plant steps from250us to125us for five representative cases in every profile; the declared bound is3% for final mean RPM, fuel input and combustion work. Native reference loop opportunities also change with the plant step, so this is combined coupling/cadence sensitivity.

## Bugs found and reference differences

The initial coupled Input run exposed a real project fault at crank-to-run transition: resetting the secondary spark filter throughout cranking forced a new debounce interval when running began. Stable contacts could therefore cut control briefly. Spark Input now qualifies continuously while the configured cranking angle remains active and secondary spark remains bypassed. Invalid/stale/future input still discards qualification. Independent review also found that a load-sensor error could conceal a simultaneous invalid switch; observing the switch before the coordinate guards fixes that recovery path while preserving load-fault reason precedence.

The frozen fix passes2507 independent checks, including sanitizers. Chrome validates791 valid selector observations, and seven runtime records retain native/browser parity across all188 MSL columns. Existing schema8/own009, runtime layout and selected inhibited-output policy stay unchanged.

These differences are retained explicitly:

* TPS condition thresholds and TPS table axes have separate native scaling. The near-threshold case intentionally activates the project while native ADC/threshold quantization leaves the reference on primary. Both controllers also execute an exactly representable physical20% plateau, remain on primary at equality and select secondary above it.
* Reference interpolation uses truncated QU1.8 positions, independently rounded corner weights and a truncated weighted sum. The weights need not sum to256; spark's+40 raw encoding participates in that calculation. Audits evaluate those integer operations instead of fitting a tolerance around ideal bilinear interpolation. The declared fixtures stay within raw lookup coordinates0..255. Higher ratio lookups can wrap the reference's8-bit bin-search coordinate and remain outside this matrix.
* Zero ordinary fuel creates no project injector opening. The reference retains deadtime-only pulses.
* The overload case switches to255VE after established running. The project reports Capacity and cuts within its15ms limit, then protects phase loss during coast-down. The reference can emit roughly28ms pulses and stall, with wrong-stroke or unsynchronized sequential discharges recorded as divergences in this negative case. These outcomes are not a usable tune or engine qualification.
* Project cylinder spark offsets precede secondary multiplication; reference individual offsets follow it. Fuel trim/deadtime order also differs. The trim case characterizes those policies with actual per-cylinder events. Mixed-source cases separately exercise secondary coordinates; combined nonflat trim-source changes are not claimed here.

Target ethanol acquisition, continuous blending, broader trigger/cylinder/control features, vendor online tuning acceptance and physical storage/USB/RF/timing/electrical/engine qualification remain open. The SW2 accessory remains a separate unqualified prototype. No board was flashed and no manufacturing or enclosure record is updated by these tests.

## Reproduce

Use fresh output directories. Earlier evidence is preserved.

```sh
python3 scripts/build_speeduino_sim.py --source ../speeduino --timer-bits 32
python3 scripts/build_speeduino_sim.py --source ../speeduino --timer-bits 16
uv run --with 'fmpy==0.3.26' python tools/run_secondary_scenarios.py .cache/engine/secondary-new-matrix
uv run --with 'fmpy==0.3.26' python tools/run_secondary_scenarios.py .cache/engine/secondary-new-fine --cases multiply input_bounce ratio_mixed trim_multiply producer_pause --step-us 125
uv run --with 'fmpy==0.3.26' python tools/check_secondary_experiments.py .cache/engine/secondary-new-matrix .cache/engine/secondary-new-checks --fine .cache/engine/secondary-new-fine
python3 tools/verify_secondary_plant_evidence.py --replay
```

The existing verified FMU build/cache and pinned PlatformIO cJSON dependency are required. See [the research benchmark](engine-research-benchmark.md) for plant construction and limits. The archive verifier checks saved trajectories and frozen native tests without rerunning the FMU; new experiments require the external model environment.
