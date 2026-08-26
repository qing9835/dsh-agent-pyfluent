# Boundary Conditions & Turbulence / Wall Treatment

Use for Fluent boundary setup review and for selecting turbulence models / wall treatment / mesh requirements.

## General boundary checks

- Confirm all zone names and types match the physical geometry; check units for every scalar (velocity, pressure, mass flow, temperature, turbulent intensity, hydraulic diameter, heat flux).
- Ensure inlet/outlet choices match what is actually known; do not impose both flow rate and pressure drop unless required.
- Confirm reference/operating pressure conventions before interpreting gauge pressures.
- Check outlet backflow conditions (temperature, turbulence, species, phase) are physically defined.

## Common boundary types

- Velocity inlet: direction + velocity profile known; provide turbulence and temperature/species/phase data if active.
- Mass-flow inlet: total inflow rate known, density handling appropriate.
- Pressure inlet: compressible/open-domain with known total/static pressure and direction assumption.
- Pressure outlet: common when downstream static pressure is known/acceptable; watch reversed-flow warnings.
- Outflow: use cautiously; avoid where backflow, strong gradients, or recirculation cross the outlet.
- Wall: no-slip/slip, roughness, heat flux/temperature/conjugate coupling, wall motion, wall-treatment compatibility.
- Symmetry: only where normal velocity and normal gradients are physically zero.
- Periodic: require matching topology and a valid periodic pressure/mass-flow assumption.
- Interface: confirm conformal/non-conformal pairing; mesh vs sliding interface intent.

## Rotating / moving zones

- MRF: define rotating cell zones and stationary/rotating interfaces consistently.
- Sliding mesh: verify time step, interface pairing, transient objective.
- Moving walls: distinguish wall motion from rotating frame motion.

## Decide laminar vs turbulent

Estimate Reynolds number and flow features. Laminar may be OK for low-Re internal/micro-flows, but transitional/separated cases need explicit justification.

## Turbulence model selection

- Spalart-Allmaras: external aero boundary layers, efficient attached-flow; weaker for strong separation/complex recirculation.
- k-epsilon: robust industrial default for many free-shear/full-turbulent internal flows; weaker near adverse pressure gradients and separation.
- Realizable/RNG k-epsilon: often better for strain, swirl, recirculation; still depends on wall treatment.
- k-omega SST: strong default for adverse pressure gradient, separation, near-wall sensitivity, turbomachinery, aero.
- Reynolds Stress Model: strong anisotropy, swirl, secondary flows, curvature when eddy-viscosity models fail.
- LES/DES/SAS: only with transient setup, suitable mesh/time step, enough compute budget.

## Wall resolution / y+

- State the expected y+ target before solving.
- Wall functions: y+ in a wall-function-compatible range + adequate BL mesh.
- Low-Re / enhanced wall treatment: near-wall cells fine enough to resolve the viscous sublayer.
- SST quality depends strongly on near-wall mesh and prism/inflation layers.
- For heat transfer, ensure thermal boundary layer resolution is adequate.

## Red flags

- Outlet placed inside a recirculation region; inlet turbulence left as meaningless defaults; wall thermal condition omitted in a heat-transfer case; symmetry used as a convenience; gauge pressure read without operating pressure.
- Switching turbulence models just to force convergence; comparing models without controlling mesh/numerics/monitors; trusting wall shear/heat-transfer/drag without wall-resolution evidence.
