#RF front end: the HC610's DC feed through the bias tee, and the 1.6 GHz carrier path
import math

import ngspice
from checks import Checks
from circuits import design, value

D = design()

CHOKE = D.RF_PARTS["bias_choke"]
ESD = D.RF_PARTS["ant_esd"]
L_CHOKE = CHOKE["inductance_nh"] * 1e-9          #27 nH
DCR = CHOKE["dcr_ohm"]                            #0.52 ohm
CJ = ESD["cj_pf"] * 1e-12                         #200 fF
C_BLK = value(D.COMPONENTS["C52"][2])             #series DC block, ANT_IN -> RFIN
#the bias feed's filter at the choke's DC end: C90 100 nF and C91 10 pF
C_TEE = value(D.COMPONENTS["C90"][2]) + value(D.COMPONENTS["C91"][2])
C_BULK = value(D.COMPONENTS["C93"][2])            #10 uF after the sense resistor
R_SENSE = value(D.COMPONENTS[D.ANT_FEED["sense_ref"]][2])
R_SWITCH = 0.135                                  #[D] AP22653 RDS(on) max over -40..85 C
I_LIMIT_MAX = 0.155                               #[D] DS41186: RLIM 210k, ILIMIT max at 25 C
P_SENSE_MAX = 0.0625                              #[D] 0402 thick film, 1/16 W at 70 C
R_SYS = 50.0                                      #[D] MAX2112 RF input is 50 ohm nominal
DC_RAIL = 5.016                                   #+5V, the main buck (design.BUCK_RAILS)
#[D] Tallysman HC610 datasheet: the LNA takes 15 mA at 2.2-12 V
LNA_I, LNA_V_MIN, LNA_V_MAX = 0.015, 2.2, 12.0
BAND_HZ = (1.6165e9, 1.6265e9)
BAND_MHZ = (1616.5, 1626.5)
INSL_MAX_DB = 0.5                                 #budget for the whole on-board path


#DC: the payload rail, the choke, the LNA's 15 mA
def bias():
    net = f"""* HC610 LNA bias: +5V, U24, R62, the filter, the choke
Vdc vdc 0 {DC_RAIL}
Rsw vdc sw {R_SWITCH}
Rsen sw b {R_SENSE}
Cbulk b 0 {C_BULK}
Rch b a {DCR}
Lch a ant {L_CHOKE}
Iload ant 0 {LNA_I}
Cesd ant 0 {CJ}
Cblk ant rfin {C_BLK}
Rleak rfin 0 1e9
.op
.end"""
    r, log = ngspice.run(net)
    if ngspice.errors(log):
        raise RuntimeError("\n".join(ngspice.errors(log)))
    return r["ant"][-1], r["rfin"][-1]


#AC: the LNA's 50 ohm output into the board
def carrier(cj):
    net = f"""* ANT_IN front end, 50 ohm source into a 50 ohm tuner
Vac src 0 AC 1
Rsrc src ant {R_SYS}
Cesd ant 0 {cj}
Vsen ant x 0
Lch x dcn {L_CHOKE}
Ctee dcn 0 {C_TEE}
Cblk ant rfin {C_BLK}
Rtun rfin 0 {R_SYS}
.ac lin 601 1e6 6e9
.end"""
    r, log = ngspice.run(net)
    if ngspice.errors(log):
        raise RuntimeError("\n".join(ngspice.errors(log)))
    return r


#the nearest sample to `f` (the sweep is linear, so this is exact enough)
def _at(freqs, vec, f):
    k = min(range(len(freqs)), key=lambda i: abs(freqs[i] - f))
    return freqs[k], vec[k]


#insertion loss against the matched 50/50 baseline of 0.5 V
def _loss_db(freqs, v_rfin, f):
    _f, v = _at(freqs, v_rfin, f)
    return -20.0 * math.log10(abs(v) / (R_SYS / (2 * R_SYS)))


def main(chk=None):
    chk = chk or Checks()
    print(f"ANT_IN front end: {CHOKE['part']} {CHOKE['inductance_nh']:.0f} nH "
          f"(DCR {DCR:.2f} ohm), {ESD['part']} Cd {ESD['cj_pf']} pF, "
          f"C52 {C_BLK*1e12:.0f} pF DC block")
    print(f"  carrier {BAND_MHZ[0]:.1f}-{BAND_MHZ[1]:.1f} MHz; tuner input {R_SYS:.0f} ohm; "
          f"HC610 LNA {LNA_I*1e3:.0f} mA at {LNA_V_MIN:.1f}-{LNA_V_MAX:.1f} V")

    #the DC half: does the LNA get its bias
    v_ant, v_rfin = bias()
    drop = DC_RAIL - v_ant
    print(f"  DC  LNA supply at ANT_IN: {v_ant:.4f} V "
          f"(rail {DC_RAIL:.3f} V less {drop*1e3:.1f} mV of switch, sense and choke)")
    print(f"  DC  at RFIN through C52:  {v_rfin*1e6:.3f} uV")
    chk.ok(LNA_V_MIN <= v_ant <= LNA_V_MAX,
           "HC610 LNA supply inside its 2.2-12 V window",
           f"{v_ant:.3f} V through {R_SWITCH + R_SENSE + DCR:.2f} ohm of feed")
    #a coax short with some resistance left in it can sit just under the switch's limit
    p_sense = I_LIMIT_MAX ** 2 * R_SENSE
    print(f"  DC  R62 at the switch's {I_LIMIT_MAX*1e3:.0f} mA worst-case limit: "
          f"{p_sense*1e3:.1f} mW of its {P_SENSE_MAX*1e3:.1f} mW")
    chk.ok(p_sense < P_SENSE_MAX,
           "the sense resistor survives a short held at the switch's maximum limit",
           f"{p_sense*1e3:.1f} mW vs {P_SENSE_MAX*1e3:.1f} mW; soop_ant switches the feed "
           f"off after {D.ANT_FEED['retry_after_s']:.0f} s of it")
    chk.ok(abs(v_rfin) < 1e-3,
           "C52 blocks the LNA's DC from the tuner's RF input",
           f"{v_rfin*1e6:.3f} uV at RFIN")

    #the AC half: carrier loss, the ESD's share of it
    r = carrier(CJ)
    freqs = r["frequency"]
    v_rfin_ac = r["rfin"]
    v_ant_ac = r["ant"]
    v_dcn = r["dcn"]
    i_choke = r["vsen#branch"]
    for f, mhz in zip(BAND_HZ, BAND_MHZ):
        loss = _loss_db(freqs, v_rfin_ac, f)
        print(f"  AC  insertion loss at {mhz:.1f} MHz: {loss:.3f} dB")
        chk.ok(loss < INSL_MAX_DB,
               f"carrier insertion loss at {mhz:.1f} MHz under {INSL_MAX_DB:.1f} dB",
               f"{loss:.3f} dB")

    #the ESD's own cost
    r0 = carrier(1e-15)
    for f, mhz in zip(BAND_HZ, BAND_MHZ):
        esd_db = _loss_db(freqs, v_rfin_ac, f) - _loss_db(r0["frequency"], r0["rfin"], f)
        print(f"  AC  ESD Cd {ESD['cj_pf']} pF changes the loss by {esd_db:+.3f} dB "
              f"at {mhz:.1f} MHz")
        #signed, because a small shunt beside C52 can as easily improve the match as spoil it
        chk.ok(abs(esd_db) < 0.05,
               f"ESD capacitance moves the loss by under 0.05 dB at {mhz:.1f} MHz",
               f"{esd_db:+.3f} dB")

    f, _ = _at(freqs, v_rfin_ac, CHOKE["f_carrier_ghz"] * 1e9)
    z_choke = abs(_at(freqs, v_ant_ac, f)[1] / _at(freqs, i_choke, f)[1])
    print(f"  AC  choke impedance at {CHOKE['f_carrier_ghz']:.4f} GHz: "
          f"{z_choke:.1f} ohm (2*pi*f*L = "
          f"{2*math.pi*f*L_CHOKE:.1f} ohm, floor {CHOKE['x_min_ohm']:.0f} ohm)")
    chk.ok(z_choke >= CHOKE["x_min_ohm"],
           "bias choke's measured impedance meets the front end's isolation floor",
           f"{z_choke:.0f} ohm vs {CHOKE['x_min_ohm']:.0f} ohm at the carrier")

    leak_db = 20.0 * math.log10(abs(_at(freqs, v_dcn, f)[1] / _at(freqs, v_ant_ac, f)[1]))
    print(f"  AC  carrier leaking onto the bias-tee DC rail: {leak_db:.1f} dB")
    chk.ok(leak_db < -20.0,
           "carrier leaking back onto the bias-tee supply is under -20 dB",
           f"{leak_db:.1f} dB")
    print()
    return chk


if __name__ == "__main__":
    main()
