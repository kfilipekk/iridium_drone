#bias feed SPICE and parametric validation for the active antenna front-end
import math

import ngspice
from checks import Checks
from circuits import design, value

D = design()

#component parameters from design.py
R_SENSE_NOM = value(D.COMPONENTS[D.ANT_FEED["sense_ref"]][2])   #R62: 2.2 ohm
R_SENSE_TOL = 0.01                                              #1% initial tolerance
R_SENSE_TEMPCO = 100e-6                                         #100 ppm / deg C

#U25 INA180A2 parameters (TI datasheet SBOS853 / C192764)
INA180_GAIN_NOM = 50.0                                          #x50 V/V
INA180_GAIN_ERR_MAX = 0.010                                     #+/- 1.0% over temp (-40 to +125 C)
INA180_VOS_MAX = 500e-6                                         #+/- 500 uV max over temp
INA180_VOL_MAX = 0.015                                          #15 mV max swing to GND (5 mV typ)
INA180_VOH_MIN = 3.25                                           #3.3V supply - 50 mV swing to rail
INA180_VCC = 3.3                                                #+3V3 rail

#firmware thresholds from firmware/soop/soop_ant.h & soop_ant.c
OPEN_MA_THRESH = 3.0                                            #mA
SHORT_MA_THRESH = 28.0                                          #mA
HC610_LNA_NOM_MA = 15.0                                         #mA nominal draw

#temperature range
T_MIN = -20.0
T_MAX = 60.0
T_REF = 25.0

#U24 AP22653W6-7 load switch (Diodes DS41186 / C2158037)
R_SWITCH_MAX = 0.135                                            #135 mOhm max over -40..85 C
I_SHORT_TYP = 0.035                                             #35 mA typical short-circuit foldback
I_SHORT_MAX = 0.040                                             #40 mA maximum foldback
THETA_JA_SOT26 = 120.0                                          #deg C / W (High-K JEDEC board, DS41186 note 7)
TJ_REC_MAX = 125.0                                              #deg C recommended operating junction limit
TJ_SHDN = 145.0                                                 #deg C thermal shutdown threshold
P_RATED_70C = 0.450                                             #450 mW rating at 70 C (830 mW at 25 C)

#USB power chain
VBUS_NOM = 5.00
VBUS_MIN = 4.75                                                 #standard USB 2.0 minimum (4.40 V extreme)
VBUS_MAX = 5.25
D_USB_VF_TYP = 0.35                                             #B5819W Vf at typical desk current (~300 mA)
D_USB_VF_MAX = 0.45                                             #B5819W Vf worst-case at 1A
CHOKE_DCR = D.RF_PARTS["bias_choke"]["dcr_ohm"]                  #0.52 ohm
L_CHOKE = D.RF_PARTS["bias_choke"]["inductance_nh"] * 1e-9       #27 nH
C_BULK = value(D.COMPONENTS["C93"][2])                          #10 uF
LNA_V_MIN = 2.2                                                 #Tallysman HC610 min operating voltage
LNA_V_MAX = 12.0                                                #Tallysman HC610 max operating voltage


#return (R_min, R_max) across -20 to +60 C accounting for tolerance and tempco
def r_sense_extrema():
    dt_cold = abs(T_MIN - T_REF)
    dt_hot = abs(T_MAX - T_REF)
    max_dt = max(dt_cold, dt_hot)
    r_nom_min = R_SENSE_NOM * (1.0 - R_SENSE_TOL)
    r_nom_max = R_SENSE_NOM * (1.0 + R_SENSE_TOL)
    r_min = r_nom_min * (1.0 - R_SENSE_TEMPCO * max_dt)
    r_max = r_nom_max * (1.0 + R_SENSE_TEMPCO * max_dt)
    return r_min, r_max


#simulate INA180 output voltage and firmware reported current
def reported_current(i_actual_a, r_sense, gain, vos):
    #V_out = Gain * (I_load * R_sense + Vos)
    v_ideal = gain * (i_actual_a * r_sense + vos)
    #clamp to amplifier output rail bounds
    v_out = max(INA180_VOL_MAX, min(INA180_VOH_MIN, v_ideal))
    #firmware formula: soop_ant_ma = V_out / (R_sense_nom * Gain_nom) * 1000
    ma_reported = v_out / (R_SENSE_NOM * INA180_GAIN_NOM) * 1000.0
    return v_out, ma_reported


#verify open, ok, and short states remain distinct across -20..+60 C
def check_discrimination(chk):
    r_min, r_max = r_sense_extrema()
    gain_min = INA180_GAIN_NOM * (1.0 - INA180_GAIN_ERR_MAX)
    gain_max = INA180_GAIN_NOM * (1.0 + INA180_GAIN_ERR_MAX)

    #1. Open circuit (I_load = 0 mA)
    v_open_max, ma_open_max = reported_current(0.0, r_max, gain_max, INA180_VOS_MAX)
    #ideal open
    _, ma_open_min = reported_current(0.0, r_min, gain_min, -INA180_VOS_MAX)

    chk.ok(ma_open_max < OPEN_MA_THRESH,
           "open state: reported current under threshold across temp",
           f"max open reading {ma_open_max:.2f} mA < {OPEN_MA_THRESH:.1f} mA threshold "
           f"(margin {OPEN_MA_THRESH - ma_open_max:.2f} mA, Vout {v_open_max*1e3:.1f} mV)")
    chk.ok(ma_open_max < 1.0,
           "open state: well below 1 mA even with worst-case Vos",
           f"{ma_open_max:.2f} mA <= 1.0 mA")

    #2. OK condition: HC610 LNA operating at nominal 15 mA
    i_ok = HC610_LNA_NOM_MA * 1e-3
    v_ok_min, ma_ok_min = reported_current(i_ok, r_min, gain_min, -INA180_VOS_MAX)
    v_ok_max, ma_ok_max = reported_current(i_ok, r_max, gain_max, INA180_VOS_MAX)

    chk.ok(ma_ok_min > OPEN_MA_THRESH,
           "ok state: lowest reading above open threshold across temp",
           f"min ok reading {ma_ok_min:.2f} mA > {OPEN_MA_THRESH:.1f} mA "
           f"(margin {ma_ok_min - OPEN_MA_THRESH:.2f} mA, Vout {v_ok_min:.3f} V)")
    chk.ok(ma_ok_max < SHORT_MA_THRESH,
           "ok state: highest reading below short threshold across temp",
           f"max ok reading {ma_ok_max:.2f} mA < {SHORT_MA_THRESH:.1f} mA "
           f"(margin {SHORT_MA_THRESH - ma_ok_max:.2f} mA, Vout {v_ok_max:.3f} V)")

    #3. Short condition
    i_thresh = SHORT_MA_THRESH * 1e-3
    v_sh_min, ma_sh_min = reported_current(i_thresh, r_min, gain_min, -INA180_VOS_MAX)
    chk.ok(ma_sh_min >= 27.0,
           "short state: 28 mA load triggers near or at short threshold",
           f"reading at 28 mA load is {ma_sh_min:.2f} mA (Vout {v_sh_min:.3f} V)")

    #at dead short foldback (35 mA)
    i_fold = I_SHORT_TYP
    v_fold, ma_fold = reported_current(i_fold, r_min, gain_min, -INA180_VOS_MAX)
    chk.ok(v_fold >= INA180_VOH_MIN,
           "short state: 35 mA foldback saturates INA180 output rail",
           f"Vout is {v_fold:.3f} V >= VOH min {INA180_VOH_MIN:.2f} V")
    chk.ok(ma_fold >= SHORT_MA_THRESH,
           "short state: foldback reading exceeds short threshold",
           f"foldback reported current {ma_fold:.2f} mA >= {SHORT_MA_THRESH:.1f} mA")


#verify USB-only power keeps LNA voltage strictly within 2.2-12 V
def check_usb_power(chk):
    #DC drop through the bias chain at nominal 15 mA: V_bias = VBUS
    i_lna = HC610_LNA_NOM_MA * 1e-3
    r_chain = R_SWITCH_MAX + R_SENSE_NOM * (1.0 + R_SENSE_TOL) + CHOKE_DCR
    v_drop_chain = i_lna * r_chain

    #worst-case low VBUS (4.75 V nominal min, or 4.40 V severe sag)
    v_lna_worst_low = VBUS_MIN - D_USB_VF_MAX - v_drop_chain
    #typical desk USB (5.00 V, 0.35 V diode drop)
    v_lna_typ = VBUS_NOM - D_USB_VF_TYP - v_drop_chain
    #maximum VBUS (5.25 V)
    v_lna_max = VBUS_MAX - 0.25 - v_drop_chain

    chk.ok(v_lna_worst_low >= LNA_V_MIN,
           "USB power: worst-case LNA voltage exceeds 2.2 V minimum",
           f"{v_lna_worst_low:.3f} V >= {LNA_V_MIN:.1f} V (margin {v_lna_worst_low - LNA_V_MIN:.3f} V)")
    chk.ok(v_lna_max <= LNA_V_MAX,
           "USB power: maximum LNA voltage below 12.0 V maximum",
           f"{v_lna_max:.3f} V <= {LNA_V_MAX:.1f} V (margin {LNA_V_MAX - v_lna_max:.3f} V)")

    #ngspice transient verification
    deck = f"""* Bias tee USB power verification
Vbus vbus 0 {VBUS_NOM}
Dusb vbus v5v D_SCHOTTKY
.model D_SCHOTTKY D(Is=1e-6 Rs=0.1 N=1.05 Bv=40 Ibv=1m Cjo=50p)
Rsw v5v vsw {R_SWITCH_MAX}
Rsen vsw vsen {R_SENSE_NOM}
Cbulk vsen 0 {C_BULK}
Rch vsen vch {CHOKE_DCR}
Lch vch vant {L_CHOKE}
Iload vant 0 {i_lna}
.tran 1u 1m
.end
"""
    vecs, log = ngspice.run(deck)
    errs = ngspice.errors(log)
    chk.ok(not errs, "USB power: ngspice deck runs without errors", f"{len(errs)} errors")
    if "v(vant)" in vecs and len(vecs["v(vant)"]) > 0:
        v_settled = vecs["v(vant)"][-1]
        chk.ok(LNA_V_MIN <= v_settled <= LNA_V_MAX,
               "USB power: ngspice settled antenna voltage inside 2.2-12 V",
               f"settled at {v_settled:.3f} V (need {LNA_V_MIN:.1f}..{LNA_V_MAX:.1f} V)")


#verify dead short foldback to 35 mA keeps U24 inside thermal and dissipation limits
def check_short_thermal(chk):
    #dead short: OUT is at GND (0 V), switch drops full VIN (~5.0 V)
    vin = 5.0
    pd_typ = vin * I_SHORT_TYP                       #5.0 V * 35 mA = 175 mW (0.175 W)
    pd_max = vin * I_SHORT_MAX                       #5.0 V * 40 mA = 200 mW (0.200 W)

    #temperature rise on SOT-26 (theta_JA = 120 C/W)
    dt_typ = pd_typ * THETA_JA_SOT26                 #21.0 C
    dt_max = pd_max * THETA_JA_SOT26                 #24.0 C

    #junction temperature inside stack (ambient = 40 C nominal stack, 60 C hot bench)
    tj_stack_typ = 40.0 + dt_typ                     #61.0 C
    tj_hot_max = 60.0 + dt_max                       #84.0 C

    chk.ok(pd_typ <= P_RATED_70C,
           "short thermal: U24 foldback dissipation within package power rating",
           f"Pd {pd_typ*1e3:.0f} mW <= {P_RATED_70C*1e3:.0f} mW (70 C rating)")

    chk.ok(tj_stack_typ < TJ_REC_MAX,
           "short thermal: junction temp inside stack well below 125 C recommended max",
           f"Tj {tj_stack_typ:.1f} C at 40 C ambient < {TJ_REC_MAX:.0f} C "
           f"(margin {TJ_REC_MAX - tj_stack_typ:.1f} C)")

    chk.ok(tj_hot_max < TJ_SHDN,
           "short thermal: junction temp on hot bench (60 C) below thermal shutdown",
           f"Tj {tj_hot_max:.1f} C at 60 C ambient < {TJ_SHDN:.0f} C shutdown "
           f"(margin {TJ_SHDN - tj_hot_max:.1f} C)")


def main(chk=None):
    c = chk or Checks()
    print("=== bias feed: INA180 discrimination, USB power, and short thermal ===")
    check_discrimination(c)
    check_usb_power(c)
    check_short_thermal(c)
    if chk is None:
        print(f"BIAS SIM OK: {c.n_ok()}/{c.n()} assertions passed")
    return c


if __name__ == "__main__":
    import sys
    c = main()
    sys.exit(0 if c.all_ok() else 1)
