"""Conservative shaft step for the declared empirical research engine.

Starter/friction constants and low-speed combustion efficiency retain the
existing research hypotheses. Linear torque regions integrate analytically;
constant-power regions use an implicit midpoint energy balance. Boundaries at
zero speed, the20rad/s work ramp and starter cutoff are split explicitly.
This improves numerical integration; it does not calibrate a physical engine.
"""
import math

STARTER_NM = 55.
STARTER_LIMIT_RAD_S = 350*math.pi/30
FRICTION_NM = 12.
FRICTION_SLOPE = .006*30/math.pi
WORK_RAMP_RAD_S = 20.
INTEGRATOR = 'piecewise_exact_linear_and_energy_midpoint_v1'


def _linear(omega, a, b, inertia, duration):
    """Exact final speed and first two speed integrals, with stable small h."""
    if b == 0:
        acceleration = a/inertia
        return (omega+acceleration*duration,
                omega*duration+.5*acceleration*duration**2,
                omega**2*duration+omega*acceleration*duration**2+
                acceleration**2*duration**3/3)
    x = b*duration/inertia
    change = a/b-omega
    one_minus_exp = -math.expm1(-x)
    if abs(x) < .001:
        first = x*(.5+x*(-1/6+x*(1/24+x*(-1/120+x/720))))
        second = x*x*(1/3+x*(-1/4+x*(7/60+x*(-1/24+x*31/2520))))
    else:
        first = 1-one_minus_exp/x
        second = 1-2*one_minus_exp/x-math.expm1(-2*x)/(2*x)
    rotation = duration*(omega+change*first)
    squared = duration*(omega**2+2*omega*change*first+change**2*second)
    return omega+change*one_minus_exp, rotation, squared


def advance_shaft(omega, duration, inertia, available_work_j, starter=False, load_nm=5.):
    """Advance one constant-input interval and return independent work ledgers.

    Available combustion work is uniformly released over this interval. Below
    20rad/s its shaft fraction is omega/20; the rest becomes heat. Mechanical
    torque is starter55*max(0,1-rpm/350)-12-.006*rpm-load.
    """
    values = (omega, duration, inertia, available_work_j, load_nm)
    if (any(type(value) not in (int, float) or not math.isfinite(value) for value in values)
            or omega < 0 or duration <= 0 or inertia <= 0
            or available_work_j < 0 or type(starter) is not bool):
        raise ValueError('Invalid bounded research shaft interval')
    power = available_work_j/duration
    remaining = duration
    totals = dict(rotation_rad=0., starter_j=0., friction_j=0., load_j=0.,
                  combustion_work_j=0.)
    for _ in range(6):
        if remaining <= 0:
            break
        starter_torque = STARTER_NM*max(0., 1-omega/STARTER_LIMIT_RAD_S) if starter else 0.
        work_torque = power/WORK_RAMP_RAD_S if omega <= WORK_RAMP_RAD_S else power/omega
        derivative = starter_torque-FRICTION_NM-FRICTION_SLOPE*omega-load_nm+work_torque
        if omega == 0 and derivative <= 0:
            remaining = 0.
            break
        increasing = derivative >= 0
        ramp = omega < WORK_RAMP_RAD_S or omega == WORK_RAMP_RAD_S and not increasing
        active_starter = starter and (omega < STARTER_LIMIT_RAD_S or
                                      omega == STARTER_LIMIT_RAD_S and not increasing)
        starter_a = STARTER_NM if active_starter else 0.
        starter_b = STARTER_NM/STARTER_LIMIT_RAD_S if active_starter else 0.
        a = starter_a-FRICTION_NM-load_nm
        b = starter_b+FRICTION_SLOPE
        linear = ramp or power == 0
        if ramp:
            a += power/WORK_RAMP_RAD_S
        if linear:
            candidate, rotation, squared = _linear(omega, a, b, inertia, remaining)
        else:
            d = 2*inertia+b*remaining
            f = 2*inertia*omega+a*remaining
            discriminant = math.hypot(f, 2*math.sqrt(d*power*remaining))
            midpoint = ((f+discriminant)/(2*d) if f >= 0 else
                        2*power*remaining/(discriminant-f))
            candidate = 2*midpoint-omega
            rotation, squared = midpoint*remaining, midpoint**2*remaining
        boundaries = [0., WORK_RAMP_RAD_S]
        if starter:
            boundaries.append(STARTER_LIMIT_RAD_S)
        crossed = [value for value in boundaries if
                   (omega < value <= candidate or candidate <= value < omega)
                   # A rounded endpoint can equal a linear equilibrium. The
                   # exact trajectory approaches it without a finite crossing.
                   and not (linear and value == a/b)]
        used = remaining
        if crossed:
            boundary = min(crossed) if increasing else max(crossed)
            if linear:
                ratio_change = (boundary-omega)/(omega-a/b)
                used = -math.log1p(ratio_change)*inertia/b
                _, rotation, squared = _linear(omega, a, b, inertia, used)
            else:
                midpoint = (omega+boundary)/2
                used = inertia*(boundary-omega)/(a-b*midpoint+power/midpoint)
                rotation, squared = midpoint*used, midpoint**2*used
            if not 0 < used <= remaining*(1+1e-10):
                raise RuntimeError('Invalid research shaft boundary time')
            used = min(used, remaining)
            candidate = boundary
        work = power*rotation/WORK_RAMP_RAD_S if ramp else power*used
        totals['rotation_rad'] += rotation
        totals['starter_j'] += starter_a*rotation-starter_b*squared
        totals['friction_j'] += FRICTION_NM*rotation+FRICTION_SLOPE*squared
        totals['load_j'] += load_nm*rotation
        totals['combustion_work_j'] += work
        omega = candidate
        remaining = max(0., remaining-used)
    else:
        raise RuntimeError('Research shaft boundary iteration limit')
    totals['omega_rad_s'] = omega
    totals['heat_j'] = available_work_j-totals['combustion_work_j']
    if (not all(math.isfinite(value) for value in totals.values())
            or omega < 0 or totals['rotation_rad'] < 0
            or totals['heat_j'] < -1e-9):
        raise RuntimeError('Invalid integrated research shaft state')
    return totals
