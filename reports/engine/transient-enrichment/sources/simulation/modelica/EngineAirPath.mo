// SPDX-License-Identifier: GPL-3.0-or-later
// External composition using unchanged, separately cached Modelica-MVEM parts.
// Air path only. Fuel, ignition and free shaft are explicit external states.
model EngineAirPath
  package Air = MVEMLib.Basic.Media.FuelAirMixture.airMedium;
  parameter Real displacement_m3 = 0.002;
  parameter Real manifold_m3 = 0.003;
  parameter Real ambient_pa = 100000;
  parameter Real ambient_k = 298.15;
  input Real shaft_rad_s(start=0);
  input Real throttle_pct(start=0);
  input Real idle_pct(start=0);
  output Real map_kpa;
  output Real temperature_k;
  output Real cylinder_air_kg_s;
  output Real inlet_air_kg_s;
  output Real inventory_kg;
  output Real inventory_j;
  output Real accumulated_inlet_kg(start=0, fixed=true);
  output Real accumulated_outlet_kg(start=0, fixed=true);
  output Real accumulated_inlet_j(start=0, fixed=true);
  output Real accumulated_outlet_j(start=0, fixed=true);
  MVEMLib.Basic.Sources.ConstantGasReference ambient(
    redeclare package Medium=Air, p=ambient_pa, T=ambient_k);
  MVEMLib.Basic.Restrictions.Compressible throttle(redeclare package Medium=Air);
  MVEMLib.Basic.Volumes.FixedVolume intake(
    redeclare package Medium=Air, VStart=manifold_m3,
    pStart=ambient_pa, TStart=ambient_k);
  MVEMLib.Engines.Combustion.Parts.SpeedDensityEngineFlow pumping(
    redeclare package Medium=Air, Vd=displacement_m3/4, nCyl=4, rc=9.2, C=0.84);
  MVEMLib.Basic.Sources.ConstantGasReference exhaustPressure(
    redeclare package Medium=Air, p=ambient_pa, T=ambient_k);
equation
  assert(shaft_rad_s >= 0 and shaft_rad_s < 1100, "shaft speed outside research plant domain");
  assert(throttle_pct >= 0 and throttle_pct <= 100, "throttle outside0..100%");
  assert(idle_pct >= 0 and idle_pct <= 100, "idle outside0..100%");
  assert(intake.gas.p > 10000 and intake.gas.p < ambient_pa*1.001,
    "NA manifold pressure outside research plant domain");
  assert(pumping.InPut.dm >= -1e-12, "reverse cylinder pumping unsupported");
  throttle.Aeff = 0.72*(17e-6 + 6e-4*throttle_pct/100 + 2e-5*idle_pct/100);
  pumping.wEng = shaft_rad_s;
  connect(ambient.OutPut, throttle.InPut);
  connect(throttle.OutPut, intake.InPut);
  connect(intake.OutPut, pumping.InPut);
  connect(pumping.OutPut, exhaustPressure.OutPut);
  map_kpa = intake.gas.p/1000;
  temperature_k = intake.gas.T;
  cylinder_air_kg_s = pumping.InPut.dm;
  inlet_air_kg_s = intake.InPut.dm;
  inventory_kg = intake.gas.p*manifold_m3/intake.gas.R/intake.gas.T;
  inventory_j = inventory_kg*intake.gas.u;
  der(accumulated_inlet_kg) = intake.InPut.dm;
  der(accumulated_outlet_kg) = -intake.OutPut.dm;
  der(accumulated_inlet_j) = intake.InPut.dH;
  der(accumulated_outlet_j) = -intake.OutPut.dH;
  annotation(uses(Modelica(version="3.2.3")), experiment(Tolerance=1e-8));
end EngineAirPath;
