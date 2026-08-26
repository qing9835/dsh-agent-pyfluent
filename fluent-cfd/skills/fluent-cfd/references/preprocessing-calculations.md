# Pre-processing Calculations

Use this reference to compute the physical inputs you need BEFORE touching the
solver: porous-medium resistance (transpiration cooling / porous zones) and
isentropic-flow inlet conditions (total→static, Mach, sound speed, mass flux).

These are the standard engineering formulas for porous-medium and isentropic
flow, and the porous-resistance convention is recorded here so it is not
re-derived wrongly.

## Porous-Media Resistance (Ergun / Forchheimer)

Inputs required:
- `dp` — mean particle (or pore) diameter, in **m** (e.g. 25 µm = 25e-6 m).
- `epsilon` — porosity (dimensionless, e.g. 0.3).

Porous zone momentum source (Fluent):
```
S_i = - (mu / K) * v_i  -  C2 * 0.5 * rho * |v| * v_i
```
This is what Fluent expects. So the two scalar inputs are:

1. **Permeability** `K` (m^2):
   ```
   K = dp^2 * epsilon^3 / (150 * (1 - epsilon)^2)
   ```
   Fluent **viscous resistance** `1/K` (1/m^2).

2. **Inertial resistance** `C2` (1/m). The common Ergun-based forms are
   equivalent up to the factor convention; use this form:
   ```
   C2 = 3.5 * (1 - epsilon) / (epsilon^3 * dp)
   ```
   This equals `2 * F/sqrt(K)` with `F = 1.75/(sqrt(150)*epsilon^1.5)`.

### Pitfall — do NOT re-derive with the wrong F_eps reading
The form `F_eps = 1.75 / sqrt(150)*epsilon^1.5` gives `F = 0.8696`, and
`C2 = F/sqrt(K) = 1.8148e6`. A *different* grouping
`F = 1.75/sqrt(150*epsilon^1.5)` gives `F = 0.3525` and `C2 = 7.36e5`.
Use the `3.5` form above for a consistent Ergun convention; the `1.81e6` and
`7.36e5` results correspond to different groupings and should not be used here.

### Red flags
- Mixing `dp` and `epsilon` from different setups (confirm the intended values
  for the case being built).
- Treating viscous resistance as `K` (it is `1/K`), or using m^2 vs 1/m^2.
- Forgetting that Fluent's porous model needs BOTH `1/K` and `C2`.

## Isentropic Flow (total ↔ static, Mach, speed of sound)

For dry air use `k = 1.4`; for real-gas / variable-k the exact integrator in
`scripts/preprocessing.py` interpolates `gamma(T)` from a data table.

Isentropic relations:
```
T_static / T0 = 1 / (1 + (k-1)/2 * Ma^2)
P_static / P0 = (1 + (k-1)/2 * Ma^2)^(-k/(k-1))
c  = sqrt(k * Rg * T_static)
v0 = Ma * c
rho = P_static / (Rg * T_static)
mass_flux_main = rho * v0
mass_flux_coolant = F * mass_flux_main        (F = blowing ratio)
```
with `Rg = R_univ / M * 1000`, `R_univ = 8.314472`, `M_air = 28.9634`.

### Blowing ratio convention
`F = mass_flux_coolant / mass_flux_main`. Typical values are a few percent
(`F ≈ 0.008–0.02`) for transpiration cooling. The coolant mass *flow rate* at the
coolant inlet then must be converted to the actual inlet area to set a
mass-flow-inlet BC.

### Red flags
- Using static pressure as total pressure (or vice versa) in a pressure-inlet BC.
- Forgetting the coolant inlet is a mass-flow-inlet (specify mass flow, not velocity).
- Using `T0`/`P0` that belong to a different operating point — confirm the
  `T0`/`P0`/`Ma` you enter match the case being built before using the results.

## Scripts

Run the bundled calculator:
- `scripts/preprocessing.py` — CLI: porous params and/or isentropic flow.
  ```
  python scripts/preprocessing.py --porous --dp <dp_m> --eps <epsilon>
  python scripts/preprocessing.py --isentropic --ma <Ma> --t0 <T0_K> --p0 <P0_Pa>
  ```
  Use the outputs directly when setting porous-zone resistances and
  pressure/mass-flow inlet boundary conditions.

## y+ / Boundary-Layer First-Cell Height

Compute the first-cell height from a target y+ BEFORE building the boundary-layer
mesh. For high-speed flows a first-cell height around 2e-6 m with a growth ratio
near 1.1 and y+ < 5 is a common target; confirm the value that matches your case.

Inputs: freestream density, velocity, characteristic length, viscosity (or static
temperature), target y+, growth ratio.

Steps (matching the reference calc script):
```
Re  = rho * v * L / mu
Cf  = (2*log10(Re) - 0.65)^-2.3                 # Schlichting, Re < 1e9
tau_w = 0.5 * Cf * rho * v^2
u_tau = sqrt(tau_w / rho)
yp  = yplus * mu / (rho * u_tau)                # first-cell center offset
y_one = 2 * yp                                 # first-cell HEIGHT
delta = (Re < 5e5) ? 4.91*L/Re^0.5 : 0.38*L/Re^0.2
n    = log(1 - delta*(1-r)/y_one) / log(r)      # number of BL cells, r = growth
```
Viscosity: Sutherland's law —
```
mu = mu0 * (T/288.15)^1.5 * (288.15 + 110.4) / (T + 110.4);  mu0 = 1.7894e-5 kg/(m s)
```

### Checklist
- `Re` must be in the Schlichting-correlation range (turbulent side if the flow
  is turbulent). For transpiration cooling the near-wall flow may be laminar-ish;
  if `Re < 5e5` the laminar formula will be used automatically.
- For a low-Re / omega-SST near-wall resolution, target `y+ ~ 1` and place the
  first cell center in the viscous sublayer. For wall-function models, `y+` is
  typically 30–300.
- The first-cell HEIGHT is `2*yp` (Fluent reports cell center, so the cell spans
  `-yp` to `+yp` about the wall). Do not use `yp` directly as the wall mesh height.

### Red flags
- Using the freestream `L` for the whole chamber when the boundary layer actually
  grows from the porous plate / leading edge — the local `L` must match the flow
  that sets the wall shear.
- Treating a single `y_one` as the whole BL mesh; the growth ratio must be applied
  and the cell count checked against `delta`.
- Always verify the computed `y_one` against the target and confirm the actual mesh
  resolves it; an incorrectly scaled domain (e.g. coordinates 1000x too large)
  breaks the y+ assumption entirely.
