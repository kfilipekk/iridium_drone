# SITL harness — testing the navigation chain before the board exists

This flies ArduCopter in simulation using **the board's own `defaults.parm`**, takes GPS
away mid-flight, and measures what the EKF does against simulator truth it never sees.

It costs nothing to run and it found things that reading the source did not.

```bash
./run_scenarios.sh                 # every scenario
./run_scenarios.sh --only soop_gpsinput
./run_scenarios.sh --params        # do the shipped parameters actually exist?
python3 scenarios.py --list
```

Prerequisites: an ArduPilot checkout at `~/.cache/navcore/ardupilot` built for SITL
(`./waf configure --board sitl && ./waf copter`) and `pymavlink`. `tools/build_firmware.sh`
sets up the tree and venv.

**Do not run this and `tools/build_firmware.sh` at the same time.** They share one
ArduPilot checkout and `waf configure` is global to it, so the second one to configure
wins and the first produces something you did not ask for. Run them one after the other.

## A defect in this harness, found 2026-08-31

**`baseline_gps` was returning PASS with the aircraft on the ground.** `max_alt_m` 0.01,
`truth_excursion_m` 0.0, p95 position error 0.02 m — the error of a vehicle that never
moved, comfortably inside every threshold in the suite.

The harness sent `MAV_CMD_NAV_TAKEOFF`, slept 15 seconds, printed `airborne` and began
measuring. It never read the command ACK (the autopilot was returning
`MAV_RESULT_FAILED`), and the vehicle was auto-disarming before the takeoff arrived —
Copter disarms ~10 s after arming if the throttle stays down, and in GUIDED this harness
never touches throttle. Arming itself was confirmed from a `HEARTBEAT` that could be
seconds stale.

Now: `DISARM_DELAY 0`, arming re-confirmed from a fresh heartbeat, the takeoff ACK read
and printed, and the climb polled until 80% of target with a **hard failure** if it does
not get there.

| | max alt | vehicle moved | p95 | verdict |
|---|---|---|---|---|
| before | 0.01 m | 0.0 m | 0.02 m | **PASS** |
| after | 12.1 m | 35.8 m | 0.20 m | PASS |

The prearm results below are unaffected — they happen before takeoff. **Position-error
figures recorded before this fix are unverified.**

## What it found

These are the results that justify the harness. All of them are prearm behaviour that
only appears when you actually try to arm:

1. **`VISO_TYPE 1` on a board with no companion cannot arm** — `PreArm: VisOdom: not
   healthy`. Shipping it enabled would have meant a board that never flies until the Pi
   is running.
2. **`EK3_SRCn_POSXY 6` with `VISO_TYPE 0` cannot arm *either*** — `PreArm: AHRS: EK3
   sources require VisualOdom` — and this one **blocks plain GPS flight on SRC1**,
   because ArduPilot validates every configured source set, not just the active one. The
   two parameters are a matched pair.
3. **A configured-but-absent rangefinder blocks arming.** `U7` is not populated on the
   Economic assembly order, so `RNGFND2_TYPE 16` would have stopped a freshly built
   aircraft from arming.
4. **Anything judged healthy by data arrival must be arriving before you arm.** Enabling
   the backend and starting the companion afterwards is a race, and it loses.
5. **The architecture was wrong, and only a running simulator showed it.** See below.

The first four are handled in `tools/gen_hwdef.py`: everything optional ships disabled,
with the opt-in documented at the point it matters.

## The result that changed the design

With the parameters fixed, the ExternalNav scenario *still* would not arm — and the cause
is a constant, not a bug:

| | timeout | implied minimum rate |
|---|---|---|
| `AP_VISUALODOM_TIMEOUT_MS` (`AP_VisualOdom.h:31`) | **300 ms** | **> 3.3 Hz** |
| `GPS_TIMEOUT_MS` (`AP_GPS.cpp:74`) | **4000 ms** | **> 0.25 Hz** |

An Iridium Doppler fix arrives at about **1 Hz**. That comfortably satisfies a GPS and
leaves visual odometry flapping in and out of healthy - which is worse than failing
outright, because the aircraft arms sometimes and then quietly dead reckons on flow. So the SoOP solution now enters as a **second
GPS instance** (`GPS_TYPE2 14`, `GPS_INPUT`) rather than as `VISION_POSITION_ESTIMATE`.

That was the obvious-looking choice reversed by measurement, which is the whole reason to
build a harness rather than reason about it. `extnav_1hz` stays in the suite as a
regression test that **must fail to arm**.

## `--params`: metadata presence is not runtime settability

`tools/check_params.py` validates `defaults.parm` against the parameter metadata ArduPilot
generates from the pinned tree. That is the right idea, and it still passed a parameter
the firmware does not have.

ArduPilot renamed the GPS parameters in 4.6 — the name is **`GPS2_TYPE`**, and the
pre-4.6 `GPS_TYPE2` survives in the metadata as a conversion alias for ground stations.
The metadata check passed it; the firmware silently declined to set it; the second GPS
never appeared; and `soop_gpsinput` reported "NO DATA" during denial with no error
anywhere. That is precisely the failure `check_params.py` was written to prevent.

`check_params_live.py` closes it by asking a running build for every shipped parameter by
name. The only authority on what a build accepts is the build.

It reads them **individually with patient retries**, not via `PARAM_REQUEST_LIST`. The
bulk listing stalls partway and re-asking restarts it, so the received count can reach the
advertised total while individual parameters are still missing — which produced a
confident "missing" list containing `RNGFND1_ORIENT`, `RELAY1_PIN` and `EK3_SRC3_YAW`, all
of which a targeted read returns immediately holding exactly the shipped values.

## The error model is the whole design

`soop_link.py` does not inject clean truth with noise sprinkled on it. Doppler
positioning from signals of opportunity has three properties that all make life harder,
and a simulation that misses them flatters the design badly:

- **Slow** — a solution needs an observation arc across a satellite pass. ~1 Hz, not 10.
- **Late** — the arc must be observed before it can be solved. Seconds of latency.
- **Correlated error** — geometry and clock error drift slowly, so the solution has a
  *wandering bias*. This is the important one. White noise averages out inside the EKF;
  a random-walk bias does not, and it is what actually degrades a position hold.

Defaults are **σ 180 m, 2 s latency, 1 Hz, 5 % outage** — `SIGMA_IRIDIUM_NO_ELEV`, the
published Iridium NEXT figure without elevation aiding, tagged `[L]`. This line read
"deliberately pessimistic (σ 20 m …)" until 2026-09-05, which was wrong twice: 20 m was
an **assumption**, not a pessimistic one, and it flattered the receiver by roughly an
order of magnitude. **Tighten these against measured receiver performance, never to make
a test pass** — and note that at σ 180 m the binding constraint is no longer accuracy but
ArduPilot's hardcoded 50 m GPS-consistency gate, which is why the companion mirrors the
live fix until denial.

## The result is a rate, not a number

`soop_gpsinput` and `soop_dropout` do not produce a position error you can quote. They
produce **one of two outcomes**, and which one is a coin flip. Measured over six runs, one
per seed, nothing else changed (2026-09-02):

| | seed 1 | 2 | 3 | 4 | 5 | 6 | diverged |
|---|---|---|---|---|---|---|---|
| `soop_gpsinput` p95 | **270.3** | 47.6 | 70.2 | 24.2 | 30.2 | 38.7 | **1 / 6** |
| `soop_dropout` p95 | **392.6** | 68.4 | 79.6 | **457.1** | **216.7** | 43.4 | **3 / 6** |

Bounded runs top out at **79.6 m**. Diverged runs start at **216.7 m**. Nothing lands in
the 137 m between them, and in every diverged run `p95` tracks the vehicle's *true*
excursion almost exactly (392/473, 457/494, 217/230, 270/319) — the aircraft genuinely
flies away. These are not noisy measurements of a stable hold.

**Re-measured at the model's CURRENT sigma, 2026-09-05.** The table above was flown at
σ 20 m. The model now ships at **σ 180 m** (`SIGMA_IRIDIUM_NO_ELEV`, the published
Iridium figure), and `soop_dropout` was run 8 times at that sigma, nothing else changed
(25 % outage, 5 Hz, 110 s flights):

| | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| p95 (EKF error) | 453 | 326 | 331 | 279 | 386 | 418 | 476 | 435 |
| true excursion | 212.8 | 146.9 | 48.9 | 41.8 | 97.3 | 89.7 | 231.2 | 80.4 |

Reading it honestly: **the σ 20 m bimodality is gone.** Every p95 lands 279–476 m —
above the old diverged floor — but that is no longer "the aircraft flew away": in four
runs the vehicle's true excursion stayed under 100 m while the EKF's position estimate
wandered hundreds of metres *with the injected fix*, which is what feeding a 180 m-noise
position into position-hold does. The two worst runs (212.8 m, 231.2 m) tracked their
estimates. **All 8 runs ended recoverable — the dead-reckon applet engaged RTL in every
one.** The takeaway matches docs/BENCHMARK.md: single-receiver SoOP at the published
sigma is a coarse, bounded aid, not a position hold; the differential-SoOP path
(~0.6–0.8 m literature) is what changes this.

**So run repeats and read the rate:**

```bash
./sitl/run_scenarios.sh --only soop_dropout --repeat 10
```

The summary then prints a divergence-rate block. It stays silent on a single pass, because
"1/1 diverged" is not a rate and printing it invites exactly the over-reading this section
exists to prevent.

**Do not try to gate this by sweeping `--seed`.** `--seed` defaults to 1 and seeds only
the `DopplerErrorModel` RNG; SITL itself is given no seed and runs against wall-clock. Two
runs at seed 1 gave **52.53 m and 270.29 m**. An earlier version of this document
recommended a fixed-seed distribution; that recommendation was wrong.

**The caveat that outranks the measurement:** the SoOP model is now **180 m sigma** and
2 s latency — sourced from the literature rather than assumed (it was `[A] 20 m`, which
turned out to be the best published *five-satellite, two-constellation, static* result),
an assumption rather than a measurement of any real receiver. This number characterises
the *model*, and only becomes a claim about the aircraft once a real receiver's noise is
fed back into `soop_link.py`.

## The canary

`flow_only` configures no position source at all and **must drift badly**. If it ever
reports a small error, the harness has stopped measuring anything and every other result
in the report is worthless. A test suite that cannot fail is not a test suite.

## Scenarios

<!-- BEGIN GENERATED SCENARIOS -->
| Name | What it does | How it is judged |
|---|---|---|
| `baseline_gps` | GPS throughout | pass/fail, p95 <= 3 m |
| `soop_gpsinput` | THE SHIPPED CONFIGURATION | informational - no pass/fail |
| `soop_raw_1hz` | NEGATIVE RESULT | must FAIL to arm |
| `soop_no_velocity` | What sending velocity is worth | informational - no pass/fail |
| `soop_dropout` | SoOP itself drops out repeatedly during denial | informational - no pass/fail |
| `soop_dropout_flow` | THE CAMERA'S VALUE, MEASURED - AND IT IS ZERO HERE | informational - no pass/fail |
| `proximity_absent` | NEGATIVE RESULT, MEASURED | must FAIL to arm |
| `soop_dropout_honest` | THE COMPANION TELLS THE TRUTH | informational - no pass/fail |
| `soop_dropout_lowlat` | LATENCY SENSITIVITY | informational - no pass/fail |
| `soop_dropout_lowsigma` | ACCURACY SENSITIVITY | informational - no pass/fail |
| `soop_arming_180m` | ARMING REGRESSION at sigma 180 m | informational - no pass/fail |
| `extnav_1hz` | Why the SoOP fix is a GPS and not ExternalNav | informational - no pass/fail |
| `measurement_canary` | CANARY | canary - must report the injected offset |
| `proximity_ring` | Proximity ring end-to-end: MAVLink OBSTACLE_DISTANCE must produce a healthy PRX1 backend, clear prearm, and airborne flight with live proximity data | informational - no pass/fail |
| `rangefinder_ceiling` | INVESTIGATION | informational - no pass/fail |
| `flow_only` | No position source at all: flow and baro only | informational - no pass/fail |
| `rc_loss` | LATE CUT | pass/fail: aircraft in RTL |
| `rc_loss_early` | EARLY CUT | pass/fail: aircraft in RTL |
| `rc_loss_dr` | THE REJECTED ALTERNATIVE, kept as a counter-example | pass/fail: aircraft in RTL |
| `ekf_failsafe` | Does a 1 Hz-derived fix trip FS_EKF_ACTION on its own? Stock FS_EKF_THRESH is tuned against a 5 Hz GPS, and a LAND triggered by nothing worse than a slow position source would be a serious defect | pass/fail: failsafe must annunciate without acting |
| `deadreckon` | The dead-reckon applet end-to-end | pass/fail on applet mode transitions |

21 scenarios; 12 are informational by design and 9 can fail. `flow_only`, `extnav_1hz` and `soop_raw_1hz` are expected to look bad - a suite where everything passes by construction measures nothing.

`./sitl/run_scenarios.sh --list` prints the full rationale for each. This table is generated by `tools/gen_scenario_table.py`; do not edit it here.
<!-- END GENERATED SCENARIOS -->

## Harness bugs that produced confidently wrong answers

Worth recording, because each of them looked like a finding about the *board* and was
actually a fault in the test rig. A harness that lies is worse than no harness.

1. **SITL persists parameters to `eeprom.bin` in its working directory, and stored values
   override `--defaults`.** A scenario that set `SIM_GPS1_ENABLE 0` to deny GPS left every
   later run starting GPS-denied — so they never got a fix and "failed to arm" for a
   reason unrelated to what they were testing. Results contaminated each other in run
   order. Fixed by running in a scratch directory and wiping the eeprom before each
   scenario.
2. **Draining one message per sleep against a ~100 msg/s stream.** `recv_match` once per
   100 ms falls permanently behind, and `conn.messages` reflects a state minutes old. It
   presented as "no GPS fix" long after the GPS had locked.
3. **Probing the port by connecting to it.** SITL accepts exactly one client, so a
   `/dev/tcp` liveness check took the slot and the real client then talked to a simulator
   about to drop it — the endless `EOF on TCP socket` spin. Checked passively with `ss`
   now.
4. **`BAD_DATA` counted as traffic**, which kept the link watchdog satisfied while nothing
   real arrived.
5. **Injecting the EKF's own estimate back into it.** The velocity sent in `GPS_INPUT`
   was taken from `GLOBAL_POSITION_INT`, whose `vx/vy/vz` are the estimator's *own*
   velocity output. That closes a positive feedback loop: estimator error is fed back as
   independent evidence for itself and grows without bound.

   This one deserves study because of how convincingly it lied. Over 70 s it looked like
   a clean 20 m position hold. Over 340 s the aircraft sat perfectly still while its
   estimated position ran away to several kilometres. And because divergence depended on
   the noise realisation, some seeds stayed bounded — so it presented as *marginal
   stability in the vehicle's control loop*, a plausible and interesting-sounding finding
   that was entirely an artefact of the rig. Truth velocity is now differentiated from
   `SIMSTATE`.

   The tell was in the trajectory log: truth frozen at one point while the estimate
   wandered kilometres. **When a result is surprising, plot the underlying quantities
   before believing it.**
6. **`pkill -f` matching the harness's own command line.** Three separate times, a kill
   pattern that appeared in the invoking shell's `/proc/*/cmdline` killed the caller.
   Everything now matches the process *name* (`pkill -x arducopter`).

The general lesson: **check that the rig can still produce a known-good result** after
every change to it. `baseline_gps` exists for that as much as for the measurement.

## The proximity path, and a lesson about negative results

`PRX1_TYPE 2` reports `PRX1: No Data` in this setup and refuses to arm. Both
`OBSTACLE_DISTANCE` and `DISTANCE_SENSOR`, at 5–10 Hz, from three different source system
ids, every field populated by keyword, parameter confirmed reading back as 2.0,
`AP_Proximity_MAV.cpp.o` present, routing confirmed at `GCS_Common.cpp:4608`.

It would have been easy — and wrong — to conclude the ToF ring's software path is broken.
**The decisive test was `PRX1_TYPE 10`**, the SITL backend that generates its own data and
needs no incoming messages at all. It fails identically. So proximity cannot be exercised
in this SITL setup by *any* route, and every failure above is a property of the rig.

This is the same principle as the `measurement_canary`, arriving from the other direction:
a test that **cannot pass** proves nothing when it fails. Before reporting a negative
result, find the control that should trivially succeed and check that it does.

## Honest limits

This proves the **interface and the parameter set**, not the physics. It says nothing
about whether Iridium NEXT Doppler can actually produce a 20 m fix from this antenna —
that is what the receiver work has to establish. What it does prove is that *if* the
receiver produces a fix of a given quality, ArduPilot can or cannot fly on it, and by how
much the position wanders.

Simulated flow is also perfect flow. Real camera flow over grass is the other half of the
problem and needs recorded footage, not a simulator.
