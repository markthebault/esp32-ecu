// SPDX-License-Identifier: GPL-3.0-or-later
// Preserve the historical four-cylinder adapter and its cached FMU.
// Total displacement is divided among the declared physical cylinders.
model EngineProfileAirPath
  parameter Integer cylinders(min=1, max=8) = 4;
  extends EngineAirPath(pumping(Vd=displacement_m3/cylinders, nCyl=cylinders));
equation
  assert(cylinders >= 1 and cylinders <= 8, "physical profile outside1..8 cylinders");
  assert(displacement_m3 >= 25e-6 and displacement_m3 <= 0.012,
    "displacement outside research profile domain");
end EngineProfileAirPath;
