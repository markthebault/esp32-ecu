# Isolated idle interface development

The idle software already has [executed-PWM engine/Speeduino comparisons](engine-idle-control.md). This increment adds a separate routed **A5 carrier interface and IAC-DRAFT2 THT driver** to address the earlier draft's alternate-return fault and missing permanent bias. It updates the configuration UI's wiring/debug guide. It does not enable physical idle or qualify an engine, valve, vehicle, enclosure, EMI/surge or isolation rating.

Use the [A5 carrier](../hardware/a5-idle-interface/README.md), [isolated accessory](../hardware/idle-isolated/README.md) and [evidence](../reports/engine/idle-isolation/). A3/A4, the unrouted IAC-DRAFT1, their reports, manufacturing files and the old ZIP remain historical records. The A3 manual does not describe the new J21 header.

## What changed

A5 keeps the 120 mm outline and six layers. R154 supplies a permanent 2.2 kΩ GPIO3 pulldown, including with the accessory disconnected. J21 is a keyed PH4 logic connector; its pin order maps directly to the accessory's XH4 J1. The smaller PH family fits the available carrier placement space. All 2,973 old tracks/vias retain exact integer geometry and named nets; only 25 new objects are appended. The 661 old pad geometries are retained, with the intended U3.13 NC-to-IDLE_CMD net change. Native KiCad9 refills the original zone definitions, so original filled-copper equivalence is not claimed. New routes avoid the full provisional antenna rectangle; actual module/RF acceptance remains open.

IAC-DRAFT2 is a 90 × 60 mm, two-layer accessory. Input-side transistors buffer the GPIO/RUN signals into two 6N137 LEDs. The detector side uses a separate LM317AT rail, MCP100 supply supervisor, HCT02 NOR, UCC27524P.B driver and IRLZ44NPBF low-side switch. Carrier 5 V powers only the LED/buffer domain. The two returns have no intended conductive connection. An intentional copper star at Q1 source separates logic return from the coil-current return.

**Combined RUN loading remains unqualified.** U9 also drives R47/R50/R53, Q7 and ten HCT inputs. The earlier source budget omitted these loads; buffered LEDs alone do not establish adequate drive. The ST 500 µA input-current bound is at 10 V/25°C, and its fault-sink case differs. R2 was increased to 2.2 kΩ, but the revised budget is conditional. Measure loaded RUN/MAIN_IN, startup, temperature and fault behavior with both boards connected. Permanent R154 also adds nominal 1.5 mA GPIO load at 3.3 V.

The independent initial copper review found that the first routed board had a long shared driver return and poorly placed bypass capacitors, despite zero native violations. The revised layout adds local back-mounted 100 nF/1 µF driver bypass, direct opto/logic bypass paths and a source Kelvin return. The review snapshots preserve both the original findings and the corrected source bindings. Exact leaded parts, assembly/underside clearance, live-tab insulation and finished-hole fit remain open. All fitted electrical components are through-hole; the copper-only NT1 is not a fitted SMD component.

## Circuit experiments and their limits

The circuit harness runs **real ngspice 45.2** with a separately authored lumped network. It does not call firmware duty directly or pretend to be a manufacturer model. It models the actual bias/buffer resistors, a generic NPN/LED, conditional optical/logic transfer, declared supervisor timing, a bounded ideal regulator/pass path, gate capacitance, generic MOS channel and an 8 Ω / 12 mH NC-valve coil with flyback. It is independent of the earlier engine plant, not newly coupled to that engine or Speeduino. Full assumptions and source hashes accompany the generated decks and results.

The 25 runs include warm continuous drive, cold supply ramp, command/RUN loss, carrier power/return opens, actuator power/return opens, imposed local rail collapse, a drain-source short, a deliberately bridged return, supply corners, 1/2/4/10/40 µs commands with two assumed optical poles and a half-step refinement. Negative controls remain deliberately unsafe. They show why a fuse is insufficient for a normal-current stuck switch, and why an accidental case/scope ground bridge defeats return separation. Coil current decays after a cut rather than disappearing with the command.

The optical and supervisor delays are sensitivity inputs. Under one assumed optical pole the 1 µs command produces a gate pulse; under the other it does not. The MCP100's typical 10 µs assertion has no guaranteed maximum, and a longer assumed delay extends the model's invalid-rail gate interval. These runs establish no physical minimum pulse, brownout guarantee, regulator stability, transistor storage range or real current/temperature limit. There is no PCB/lead/harness parasitic extraction, valve mechanics or physical isolation capacitance in this circuit model. The actual procured PDIP driver's guarantee remains a release hold.

## Configuration and debugging

**Engine development → Idle air control → Driver connection and debugging** and the connector guide now describe J21, R154, the isolated domains and the independent branch disconnect. All existing idle tune fields and diagnostics retain their semantics. No configuration value enables hardware writes. Controller/PWM fields are digital observations; the simulated valve state is explicitly synthetic and there is no physical valve feedback.

The accessory README gives a probe/reference table and assembly order. Begin eventual electrical work with an independent cutoff and a current-limited resistor fixture. Measure the local rail/supervisor/ENA, gate relative to source, drain and both return currents through startup, reset, signal loss and opened-return cases. Proper differential/isolated probing must preserve protective earth and the intended barrier. Do not lift scope earth or connect ordinary ground clips across the domains.

Before any powered valve integration, specify the protected switched/fused branch, actual ≤2 A valve and independent disconnect; resolve actual GPIO3/JTAG eFuse routing without burns, exact driver guarantees, LED/loaded GPIO timing, minimum pulse, brownout, thermal, lead/finished-hole fit, underside clearance and enclosure/RF/sealing. A5 and IAC-DRAFT2 have no fabrication release or new printable-case fit claim. No board was flashed.

## Reproduction

Use an unused output directory and inspect generated files before replacing local edits. KiCad Python/CLI 9.0.8, Java21, pinned Freerouting1.9.0 with analytics disabled, and ngspice45.2 were used. The router source/tag, command lines and source bytes are bound in the evidence. Twelve inherited stock footprint sources have local archive hashes, without a claimed frozen upstream commit; new external footprints have official pinned source records.

```sh
/usr/bin/python3 scripts/build_idle_isolated.py --replace-generated
/usr/bin/python3 scripts/route_idle_isolated.py --prepare NEW_ACCESSORY_ROUTER_DIR
# Run the pinned Freerouting JAR on isolated.dsn with -da -dct 0.
/usr/bin/python3 scripts/route_idle_isolated.py --import-session NEW_ACCESSORY_ROUTER_DIR/isolated.ses
/usr/bin/python3 scripts/build_a5_idle_interface.py --replace-generated
/usr/bin/python3 scripts/route_a5_idle_interface.py --prepare NEW_CARRIER_ROUTER_DIR
# Run the pinned Freerouting JAR on carrier.dsn with -da -dct 0.
/usr/bin/python3 scripts/route_a5_idle_interface.py --import-session NEW_CARRIER_ROUTER_DIR/carrier.ses
uv run --with numpy --with matplotlib python tools/run_idle_circuit.py \
  --ngspice PATH_TO_NGSPICE --report-dir NEW_CIRCUIT_DIR
python3 scripts/generate_idle_ui.py
python3 scripts/embed_web.py
```

Use absolute native project input paths, all-severity ERC, DRC with `--all-track-errors --schematic-parity`, and writable project/library configuration. The independent reviewer preserves immutable source snapshots and uses a byte-identical writable cache copy for native checks. KiCad9 does not reliably resolve the local library table from a read-only project snapshot. A zero native result is necessary for this draft, not physical acceptance. Keep the [remaining feature ledger](engine-feature-coverage.md) open.
