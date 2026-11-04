# SW2-J4-DRAFT1 switch accessory

Separate80×60mm, two-layer, direct-solder THT prototype for two secondary-table dry contacts. The120×120mm carrier, service buttons, SAFE_N and archived manufacturing/case files retain their existing roles. **HOLD: no fabrication release, electrical rating, enclosure-fit or engine qualification.**

[Native schematic](switches.kicad_sch), [routed PCB](switches.kicad_pcb), [literal contract](net_contract.json) and [candidate BOM](bom.csv) describe42 footprints:38 fitted parts and four unplated M3 mounts. U1 is a directly soldered MCP23008-E/P PDIP18, without a socket. Ordinary resistors stand upright; confirm formed-lead and body heights before assembly. Exact capacitors, contact parts, wire/glands, mounting materials and some procurement choices remain open.

## Connections and ownership

| Carrier J4 | Accessory J1, XH4 | Signal |
| --- | --- | --- |
|1|1|GND|
|2|2|3V3|
|3|3|SDA, GPIO41|
|4|4|SCL, GPIO42|
|5|No wire or contact|SAFE_N, never connect to this accessory|

J4 is an internal3.3V logic header. Use a short internal harness with a five-position carrier housing and only positions1..4 populated, adapting to J1’s XH4 housing. The exact2.54mm carrier housing/contact and retention must be checked against the actual header. No loose fifth lead is permitted. J1 uses XHP-4 and four SXH-001T-P0.6 contacts as candidates; wire gauge/crimp tooling and fit need checking.

External J2 and J3 are VH2 connectors with3.96mm pitch, deliberately different from internal J1’s2.50mm XH4. Each VH2 uses pin1 SW and pin2 its ground return; J2 is input0 and J3 input1. VHR-2N housings and four SVH-21T-P1.1 contacts are candidates, with wire/crimp/retention checks pending. Keep these connectors inside the box and route each external pair through an appropriately selected sealed cable exit. No new sealed-box or printed-fit qualification is implied. Use dry-circuit rated switch contacts for the small sensing current.

A contact closes SW to its dedicated return. **Closed reads high, open reads low**, after transistor inversion. Selection polarity remains configurable per rule. An open wire looks open; a short to return looks closed. Static external voltage faults may also look like valid contact states. No continuity or wrong-wire diagnosis is implemented.

Saving a secondary rule in Input mode explicitly reserves J4’s bus and address0x20 for this fixed accessory contract. Connect no other I2C owner/device there. The marker/loop checks establish behavior, not unique identity. With neither rule in Input mode the firmware makes no device/register requests and releases its owned peripheral handles. PAIR, RESET, cam, pressure and SAFE_N retain their existing functions.

## Circuit and bounds

Each channel uses a1N4148 feed diode and2.2k0.6W1% bias, two4.99k1% base resistors,100k base-emitter bias, a reverse-BE1N4148 clamp, onsemi2N3904BU,4.7k collector pullup,10nF filtering and1k isolation to GP0/GP1. Do not substitute a transistor with another E/B/C bondout. GP2..5 have10k straps for0x28 under mask0x3C. GP7 is output-only on MCP23008; it drives GP6 through1k, with100k GP6 pulldown. These resistors limit contention if a register changes; they do not diagnose every contact failure.

MCP121-300E/TO is the prototype reset supervisor, with100k pullup matching its published test condition, local100nF bypass and a mandatory1k rail bleeder. The static trip range is2.857..3.003V; the stated80..180ms release interval has specified test conditions. Reset output leakage has no published maximum, hysteresis limits are at25°C, and assertion delay is typical only. The assembled RESET high/low margins, arbitrary ramps, power interruption and behavior below the specified operating supply remain unqualified. No guaranteed deep-brownout assertion is inferred from a different output load.

The feed diodes do not eliminate backfeed. Transistor B-C junctions and I2C/input clamp paths can energize an unpowered local rail. The1k bleeder and100Ω SDA/SCL series resistors are part of the prototype, not proof of safe arbitrary power sequences. The carrier already has4.7k I2C pullups; add no further bus pullups. Use100kHz and measure actual rise time/capacitance, VOL and fault behavior with the finished harness. Digital marker/loop/readback checks do not validate the analog conditioners: wrong transistor orientation, clamp faults or external wiring may still produce plausible contact bits. Independently measure both channels’ voltages/currents before accepting their raw levels.

The carrier LD1117’s200mA figure is a provisional **total thermal target**, not available accessory headroom. Measure the complete carrier, ESP32/Wi-Fi peaks and accessory rail loading/temperature. The module5V pad21 is NC. [Existing USB power restrictions](../../docs/web-configuration.md) still apply: remove the unpowered module before USB power; never combine powered carrier3V3 and module USB. A removed USB-powered module cannot read carrier sensors/J4.

MCP23008’s E order code does not establish3.3V operation to125°C. The data sheet’s3.3V operating domain ends at85°C. No assembled temperature rating is established. MRS25 candidate order codes are derived from the manufacturer’s coding scheme;0.6W is P70 subject to film/ambient limits, not an unrestricted enclosure dissipation rating. Exact capacitor part/body/lead spacing and all supplier footprints require physical verification.

## Acquisition and debugging

The monitor requests one logical operation per nominal5ms iteration. Startup reads the static marker before writes, sets sequential mode, configures GP7 as output, then alternates loopback challenges. Each GPIO sample reads registers0..10 and separately rereads IODIR. Owned configuration, marker, OLAT, INTF and loopback must agree; historical INTCAP is intentionally unused. A reset before the final guard rejects. A later reset remains unobserved until the next acquisition or freshness limit.

The entire operation has a measured3ms acceptance budget in the controller’s GP-timer epoch. Each synchronous SDK transfer receives the floored remaining integer-ms timeout; the trailing guard cannot start with less than1ms remaining. Source time is acquisition start. Writes never refresh it. SDK allocation/removal and preemption have no hard3ms deadline guarantee; an elapsed overrun invalidates the sample. Actual scheduling and watchdog behavior require HIL measurement.

Bus absence/NACK/timeout, register/loop/marker mismatch, malformed replies, elapsed overrun and producer gaps invalidate required inputs. Recoverable faults back off100ms and stay latched until a completed control observation consumes that exact fault ID. Successful reads alone cannot hide a fault when the engine lock was busy. A new guarded sample and each rule’s qualification period are required after acknowledgement. Clock/state faults require an ECU restart and survive Off/Input changes. Both rules may share one sampled channel with independent polarity/debounce.

The Engine page shows acquisition phase, requested mask, current/last fault, exact decimal-string source times/counters, fault awaiting consumption, operation durations and SDK ownership/result. Per-rule qualification, pending transition, age, raw level and selection remain in the existing web/USB/MSL diagnostics. Host stimuli stay synthetic; absent hardware diagnostics stay unknown. This adds no new tune/runtime wire fields or controller identity.

Start a future bench test with outputs disconnected/inhibited and both rules Off. Check rails and J4 wiring before enabling Input. Confirm each contact’s open/closed raw level, selected polarity, debounce and fault recovery, then deliberately test absence/reset/stuck lines and source freshness. Measure protection currents, reset levels, power-off backfeed, supply loading/temperature, scheduling and USB/RF interactions. A passing software/CAD/model check does not replace these measurements.

## Reproduction and limits

`/usr/bin/python3 scripts/build_switch_inputs.py` creates a fresh draft and refuses to replace an existing board without `--replace-generated`. Routing uses `scripts/route_switch_inputs.py` with pinned Freerouting1.9.0 and analytics disabled. Native KiCad9 all-severity ERC/DRC, connectivity and schematic parity are separate checks. No Gerber, drill or enclosure release is supplied.

`tools/run_switch_circuit.py` runs95 conditional ngspice cases: assumed BJT gain/temperature/rail/contact combinations, steady±18V experiments, unpowered I2C backfeed and two transient step sizes. Powered bus pullups follow the carrier rail; disconnected-supply cases use3.3V bus, plus a separate3.63V bus-only case. Bus-feed and carrier3V3-feed currents are reported separately. Its generic transistor/diode/clamp/supervisor parameters are **not manufacturer models or physical guarantees**. The±18V experiment is not an input rating or automotive surge test. The model intentionally retains backfeed and continuity limitations. Independent component-corner arithmetic likewise does not certify saturation/cutoff outside the manufacturer’s stated test conditions.

Primary references: [MCP23008 DS20001919I](https://ww1.microchip.com/downloads/aemDocuments/documents/APID/ProductDocuments/DataSheets/MCP23008-and-MCP23008-Data-Sheet-DS20001919.pdf), [MCP121 DS20001906D](https://ww1.microchip.com/downloads/en/DeviceDoc/20001906D.pdf), [onsemi2N3904](https://www.onsemi.com/download/data-sheet/pdf/2n3904-d.pdf), [1N4148](https://www.vishay.com/docs/81857/1n4148.pdf) and [MRS25](https://www.vishay.com/docs/28724/mrs16m25.pdf). Footprint origins and omitted metadata are recorded in [provenance](footprint-provenance.json).
