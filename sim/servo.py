#the payload buck (`U20`, L5, +5V_PAYLOAD) under a double TVC-servo stall
import ngspice
from checks import Checks
from circuits import design, value

D = design()
S = D.SERVO_RAIL

FSW = D.BUCK_THERMAL["LMR33630A"]["fsw"]          #400 kHz
VIN_5S = 5 * 4.2                                  #21.0 V, the worst-case input for ripple
VOUT = next(v for _r, n, v, *_ in D.BUCK_RAILS if n == "+5V_PAYLOAD")
L5 = value(D.COMPONENTS["L5"][2])                 #10 uH
ISAT, IRMS = D.RAIL_5V_PAYLOAD["isat_a"], D.RAIL_5V_PAYLOAD["irms_a"]
#output-cap ESR per package; the same assumption ldo.py states
PARASITIC = {"0402": (0.020, 0.6e-9), "0805": (0.010, 0.8e-9), "1206": (0.008, 1.0e-9)}
#the buck's loop cannot answer a step instantly
T_LOOP = 5e-6


#(lander mission, double stall) currents on the rail, from design.py
def loads():
    mission = D.PAYLOAD_MISSION_A["lander"]
    stall = mission + S["count"] * (S["stall_a"] - S["run_a"])
    return mission, stall


#(caps, total_C) for the fitted
def _bank(net):
    caps = []
    for pin in D.NETS.get(net, []):
        ref = pin.split(".")[0]
        comp = D.COMPONENTS.get(ref)
        if not comp or not ref.startswith("C"):
            continue
        _sym, fp, val, _lcsc, dnp = comp
        if dnp:
            continue
        esr, esl = next((v for k, v in PARASITIC.items() if k in fp), (0.020, 0.6e-9))
        caps.append((ref, value(val), esr, esl))
    return caps, sum(c for _, c, _, _ in caps)


#Open-loop switch node into the fitted inductor and cap bank (power.py's model)
def _filter(iout, vin=VIN_5S, tstop=8e-3):
    _caps, C = _bank("+5V_PAYLOAD")
    ton = (VOUT / vin) / FSW
    period = 1.0 / FSW
    net = f"""* payload buck output filter at one load
Vsw sw 0 PULSE(0 {vin} 0 5n 5n {ton:.6g} {period:.6g})
L1  sw out {L5}
C1  out n1 {C}
R1  n1 0 0.003
Rload out 0 {VOUT / iout:.6g}
.ic v(out)={VOUT} v(n1)={VOUT}
.tran 5n {tstop} uic
.end"""
    r, log = ngspice.run(net)
    if ngspice.errors(log):
        raise RuntimeError("\n".join(ngspice.errors(log)))
    t = r["time"]
    k0 = next(i for i in range(len(t)) if t[i] >= t[-1] - period)
    il = r["l1#branch"][k0:]
    vo = r["out"][k0:]
    rms = sum(x * x for x in il) / len(il)
    return max(il), min(il), rms ** 0.5, max(vo) - min(vo), _caps, C


#Cap-alone response to the stall step
def _step(i_from, i_to):
    caps, total = _bank("+5V_PAYLOAD")
    lines = ["* +5V_PAYLOAD load step: mission -> double stall",
             f"Vsrc ideal 0 {VOUT}", "Ro ideal rail 0.001"]
    for ref, c, esr, esl in caps:
        lines += [f"L{ref} rail a{ref} {esl}",
                  f"R{ref} a{ref} b{ref} {esr}",
                  f"C{ref} b{ref} 0 {c}"]
    lines += [f"Iload rail 0 PWL(0 0 1u {i_from:.6g} 2u {i_to:.6g} 40u {i_to:.6g})",
              ".tran 2n 40u", ".end"]
    r, log = ngspice.run("\n".join(lines))
    if ngspice.errors(log):
        raise RuntimeError("\n".join(ngspice.errors(log)))
    t, v = r["time"], r["rail"]
    after = [v[i] for i in range(len(t)) if t[i] >= 2.5e-6]
    return VOUT - min(after), total


def main(chk=None):
    chk = chk or Checks()
    mission, stall = loads()
    print(f"TVC servo rail: {'/'.join(S['refs'])} on {S['net']}, {S['count']} servos "
          f"({S['run_a']*1e3:.0f} mA run / {S['stall_a']*1e3:.0f} mA stall each)")
    print(f"  lander mission load {mission:.3f} A; double stall {stall:.3f} A "
          f"({(stall - mission)*1e3:.0f} mA of extra load)")
    print(f"  buck U20 {FSW/1e3:.0f} kHz, L5 {L5*1e6:.0f} uH, "
          f"Isat {ISAT:.1f} A, Irms {IRMS:.1f} A, Vin {VIN_5S:.1f} V (5S)")

    #the converter's own current
    m_pk, _m_v, m_rms, m_rip, caps, total_c = _filter(mission)
    s_pk, s_v, s_rms, s_rip, _caps2, _c = _filter(stall)
    print(f"  fitted output bank: {len(caps)} caps, {total_c*1e6:.0f} uF")
    print(f"  inductor at mission: peak {m_pk:.3f} A, rms {m_rms:.3f} A")
    print(f"  inductor at stall:   peak {s_pk:.3f} A, rms {s_rms:.3f} A "
          f"({s_pk/ISAT*100:.0f} % of Isat, {s_rms/IRMS*100:.0f} % of Irms)")
    chk.ok(s_pk < ISAT,
           "output inductor stays below saturation at a double servo stall",
           f"peak {s_pk:.3f} A vs Isat {ISAT:.1f} A")
    chk.ok(m_rms < IRMS,
           "lander mission load is inside the inductor's thermal rating",
           f"rms {m_rms:.3f} A vs Irms {IRMS:.1f} A")
    if s_rms >= IRMS:
        print(f"  NOTE: a *sustained* double stall runs the inductor at "
              f"{s_rms/IRMS*100:.0f} % of Irms - it must be a transient. The bound "
              f"above is Isat, which is what a transient has to clear; the thermal "
              f"rating is what a locked rotor would need.")

    #the rail the servos actually see
    dip, _total = _step(mission, stall)
    loop = (stall - mission) * T_LOOP / total_c
    total_dip = dip + loop
    headroom = VOUT - S["v_min"]
    print(f"  SPICE stall step {mission:.2f} -> {stall:.2f} A: dips {dip*1e3:.1f} mV; "
          f"loop-delay bracket +{loop*1e3:.1f} mV")
    print(f"  rail window {S['v_min']:.3f}-{S['v_max']:.3f} V, "
          f"{headroom*1e3:.0f} mV of headroom below nominal {VOUT:.3f} V")
    chk.ok(total_dip < headroom,
           "rail stays inside the servos' window through the stall step",
           f"dip {total_dip*1e3:.1f} mV vs {headroom*1e3:.0f} mV of headroom")

    #topology: which rail the stall lands on
    pins = [f"{r}.2" for r in S["refs"]]
    on_payload = all(p in D.NETS.get("+5V_PAYLOAD", []) for p in pins)
    on_fc = any(p in D.NETS.get("+5V", []) for p in pins)
    print(f"  {', '.join(pins)} on +5V_PAYLOAD: {on_payload}; on the FC's +5V: {on_fc}")
    chk.ok(on_payload and not on_fc,
           "the stalled servo load cannot disturb the flight controller's own +5 V",
           f"{', '.join(pins)} on {S['net']}, not +5V")
    print()
    print("  The inductor model is power.py's open-loop switch node (right for the "
          "filter,\n  silent on the loop); the step model is an ideal regulator into the "
          "fitted cap\n  bank with a stated loop-delay bracket, as ldo.py uses.")
    return chk


if __name__ == "__main__":
    main()
