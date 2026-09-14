#!/usr/bin/env python3
"""
NAVCORE-SoOP — single source of truth for components and nets.

Everything downstream (schematic, PCB, BOM) is generated from this file.
MCU pin usage is cross-checked against firmware/reference/MatekH743-hwdef.dat
by tools/check_design.py, so the netlist cannot silently drift from the spec.

Convention: pins are given as "REF.PINNUMBER".
"""

R  = "Device:R";  C  = "Device:C";  L = "Device:L"; FB = "Device:FerriteBead"
LED = "Device:LED"; SW = "Switch:SW_Push"; XTAL = "Device:Crystal_GND24"

F_R0402  = "Resistor_SMD:R_0402_1005Metric"
F_C0402  = "Capacitor_SMD:C_0402_1005Metric"
F_C0805  = "Capacitor_SMD:C_0805_2012Metric"
F_C1206  = "Capacitor_SMD:C_1206_3216Metric"
F_L1210  = "Inductor_SMD:L_1210_3225Metric"
# Power-inductor lands, sized to the parts that actually go on them. A 1210 chip land is
# 3.2 x 2.5 mm and no 10 uH part that size carries more than about 0.5 A - the buck
# inductors were specified as 1210 and then filled with a 4.0 x 4.0 x 3.0 mm part by a
# table keyed on value alone, so neither fitted its own land.
F_ANR4030 = "Inductor_SMD:L_APV_ANR4030"   # 4.0 x 4.0 x 3.0 mm, courtyard 4.60 x 4.50
F_ANR5040 = "Inductor_SMD:L_APV_ANR5040"   # 5.0 x 5.0 x 4.0 mm, courtyard 5.60 x 5.50
F_L0805  = "Inductor_SMD:L_0805_2012Metric"
F_LED    = "LED_SMD:LED_0603_1608Metric"
F_SW     = "Button_Switch_SMD:SW_SPST_B3U-1000P"
F_UFL    = "Connector_Coaxial:U.FL_Hirose_U.FL-R-SMT-1_Vertical"

# ---------------------------------------------------------------- components
# ref : (symbol, footprint, value, lcsc, dnp)
COMPONENTS = {
 # ---- core ----
 # C5271084 is STM32H743VIT6TR - the SAME silicon and the same LQFP-100 package, in
    # tape-and-reel rather than tray. C114409 (tray) went out of stock on 2026-08-28 and
    # the reel part is both available and cheaper (~$7.66 vs ~$10-12). The symbol library
    # name still says _C114409 because that is the local symbol's name, not an order code.
    "U1" : ("jlc_parts:STM32H743VIT6_C114409", "jlc:LQFP-100_L14.0-W14.0-P0.50-LS16.0-BL", "STM32H743VIT6", "C5271084", False),
 "U2" : ("jlc_parts:ICM-42688-P",           "jlc:LGA-14_L3.0-W2.5-P0.50-TL",            "ICM-42688-P",   "C1850418", False),
 "U3" : ("jlc_parts:ICM-42605",             "jlc:LGA-14_L3.0-W2.5-P0.50-TL",            "ICM-42605",     "C2655099", False),
 "U4" : ("jlc_parts:MS561101BA03-50",       "jlc:SENSORS-SMD_MS5611-01BA03",            "MS5611",        "C15639",   False),
 "U5" : ("jlc_parts:W25Q128JVSIQTR",        "jlc:SOIC-8_L5.3-W5.3-P1.27-LS8.0-BL",      "W25Q128JVSIQ",  "C97521",   False),
 # ---- power ----
 "U8" : ("jlc_parts:TPS54202DDCR",          "jlc:SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL",    "TPS54202",      "C191884",  False),
 "U9" : ("jlc_parts:AP2112K-3_3TRG1",       "jlc:SOT-25-5_L2.9-W1.6-P0.95-LS2.8-BL",    "AP2112K-3.3",   "C51118",   False),
 "U10": ("jlc_parts:TLV75533PDBVR",         "jlc:SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR",    "TLV75533",      "C404027",  False),
 # ---- io ----
 "U11": ("jlc_parts:SN65HVD230DR",          "jlc:SOIC-8_L4.9-W3.9-P1.27-LS6.0-BL",      "SN65HVD230",    "C12084",   False),
 "U12": ("jlc_parts:USBLC6-2SC6_C2687116",  "jlc:SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL",    "USBLC6-2SC6",   "C2687116", False),
 "J1" : ("jlc_parts:TYPE-C_16PIN_2MD(073)", "jlc:USB-C-SMD_TYPE-C-16PIN-2MD-073",       "USB-C",         "C2765186", False),
 "J2" : ("jlc_parts:SM08B-SRSS-TB(LF)(SN)", "jlc:CONN-TH_SM08B-SRSS-TB-LF-SN",                "ESC 8P",        "C160407",  False),
 "J3" : ("jlc_parts:XY-SM06B-GHS-TB",       "jlc:CONN-SMD_XY-SM06B-GHS-TB",            "GPS+I2C",       "C51940119",False),
 "J5" : ("jlc_parts:SM04B-SRSS-TB_(LF)(SN)","jlc:CONN-SMD_4P-P1.00_SM04B-SRSS-TB-LF-SN","RC IN",         "C160404",  False),
 "J6" : ("jlc_parts:XY-SM04B-GHS-TB",       "jlc:CONN-SMD_4P-P1.25_12502-04WASMT",            "CAN",           "C51940118",False),
 "J7" : ("jlc_parts:XY-SM04B-GHS-TB",       "jlc:CONN-SMD_4P-P1.25_12502-04WASMT",            "RNGFND",        "C51940118",False),
 "J8" : ("jlc_parts:TF-01A",                "jlc:TF-SMD_TF-01A",                        "microSD",       "C91145",   False),
 # Y1 is a PASSIVE CRYSTAL and the part number matters more than it looks.
 #
 # docs/BUYING.md vetted SX3M8.000M20F30TNN (C2901556) on stock and price, and
 # this line was briefly changed to it. That part is an ACTIVE OSCILLATOR. It shares the
 # SMD3225-4P land pattern, so it drops straight into this footprint - and in an XO that
 # package is pin 1 OE, pin 2 GND, pin 3 OUT, pin 4 VDD. This board ties pins 2 and 4 to
 # ground and runs OSC_IN/OSC_OUT to pins 1 and 3, so the oscillator's supply would be
 # grounded and the board would never start.
 #
 # X32258MSB4SI is the passive crystal the design was drawn for: CL 20 pF, 120 ohm ESR,
 # SMD3225-4P, and cheaper and better stocked than the part that replaced it
 # ($0.093, 52080 in stock against $0.41, 40699).
 "Y1" : ("jlc_parts:X32258MSB4SI",          "jlc:CRYSTAL-SMD_4P-L3.2-W2.5-BL",          "8MHz",          "C2682774", False),
 # D1 WAS AN SMBJ33A (C19077586) and it protected nothing. Its clamping voltage is
 # 53.3 V against the TPS54202's 30 V absolute maximum (SLVSD26 5.1), so any surge big
 # enough to make it conduct - it does not start until ~37 V - reached U8 23 V over its
 # destruct limit. The old check judged it by CELL COUNT ("fine to 7.9S"), which is not
 # the question; tools/check_electrical.py section 5 now compares clamp against what is
 # downstream. SMBJ18A: 18 V standoff clears a full 4S pack (16.8 V), 20.0 V breakdown
 # minimum keeps it off through regen, and 29.2 V clamping is UNDER the 30 V limit.
 # CONSEQUENCE: this makes the BOARD 4S-only. 5S full is 21 V, past the 18 V standoff.
 # The ESC accepts 3-6S; this part is now the limit. design.CELLS is 4 and the specified
 # pack is a 4S Zeee 6500, so it matches the aircraft as designed - but a 6S build needs
 # a different regulator, not just a different TVS: no TVS that stands off 25.2 V clamps
 # under 30 V. [D] Littelfuse SMBJ series; verified C19077573 against the jlcparts mirror
 # (36488 in stock) and jlcpcb.com/partdetail/C19077573 (DO-214AA(SMB), same package).
 "D1" : ("Device:D_TVS",                    "jlc:DO-214AA_L4.4-W3.6-LS5.3-RD",                          "SMBJ18A",       "C19077573",False),
 # ---- SoOP receiver. The TUNER half is FITTED - the H743 does the Doppler on
 # board, which is the point of the project. Only the LNA/SAW half is DNP, and it is
 # DNP because the bought SAWbird+ IR does that job at the antenna instead. ----
 "U13": ("jlc_parts:MAX2112ETI+T",          "jlc:TQFN-28_L5.0-W5.0-P0.50-BL-EP3.3",      "MAX2112",       "C596391",  False),
 "U14": ("jlc_parts:OPA2374M{slash}TR",     "jlc:SOP-8_L4.9-W3.9-P1.27-LS6.0-BL",       "OPA2374",       "C444392",  False),
 "U15": ("jlc_parts:PSA4-5043+",            "jlc:SOT-343-4_L2.0-W1.3-P1.30-LS2.1-BR",           "PSA4-5043+",    "C5240848", True),
 "U16": ("jlc_parts:PSA4-5043+",            "jlc:SOT-343-4_L2.0-W1.3-P1.30-LS2.1-BR",           "PSA4-5043+",    "C5240848", True),
 # Y2 is an ACTIVE 4-pad TCXO (OW2EL89CEIUXFMYLC-25M, YXC YSOS510TP family). Its own
 # family datasheet (the PDF JLC attaches to C22381771) gives the pin table verbatim:
 # 1 = GND, 2 = GND, 3 = OUT, 4 = VDD. The YSOS510TP symbol below carries exactly that
 # pinout - pin 1 is GROUND, not OE/VC, so the R47 pull-up an earlier draft provisioned
 # would have been a dead resistor shorting +3V3A into a ground pin if anyone had ever
 # fitted it. The old SX3M27 symbol (pin 1 = EN) was a 27 MHz CMOS part's symbol reused
 # BY CLASS: the netlist that grounded pin 4 proved the class was right, and the
 # datasheet proved the pin NAMES were still wrong for this part. Transcribe, do not
 # infer - including when the thing you are inferring from is another symbol.
 "Y2" : ("jlc_parts:YSOS510TP",               "jlc:OSC-SMD_4P-L3.2-W2.5-BL",              "25MHz TCXO",    "C22381771",False),
 "FL1": ("jlc_parts:TA1575IG",                   "jlc:FILTER-SMD_6P-L3.0-W3.0-P1.19-TR",                       "SAW 1620MHz",   "",         True),
 # NOTE there is no "J9" here any more. J9 WAS the U.FL antenna connector, back when
 # the RF front end was going to live on this board and the strip block deleted the ref
 # wholesale. J9 is now the dedicated I2C port (added in the Phase C block below) and
 # the U.FL is J12. Leaving a dead U.FL entry under this ref would be a silent
 # collision waiting for the day someone re-enables the RF block: the later add() wins,
 # so the antenna would quietly become an I2C connector and ANT_IN would land on +5V.
}

def add(ref, sym, fp, val, lcsc="", dnp=False):
    COMPONENTS[ref] = (sym, fp, val, lcsc, dnp)

# passives ---------------------------------------------------------------
_p = []
def RES(ref, val, fp=F_R0402, dnp=False): add(ref, R, fp, val, "", dnp); _p.append(ref)
def CAP(ref, val, fp=F_C0402, dnp=False): add(ref, C, fp, val, "", dnp); _p.append(ref)
def IND(ref, val, fp=F_L1210, dnp=False): add(ref, L, fp, val, "", dnp); _p.append(ref)

# MCU decoupling: one 100n per VDD pin + bulk
for i, r in enumerate(["C1","C2","C3","C4","C5"]): CAP(r, "100n")
CAP("C6", "4u7", F_C0805); CAP("C7", "4u7", F_C0805)
CAP("C8", "2u2", F_C0402); CAP("C9", "2u2", F_C0402)     # VCAP1/2
CAP("C10","100n"); CAP("C11","1u")                        # VDDA
CAP("C12","100n"); CAP("C13","1u")                        # VREF+
CAP("C14","100n")                                         # NRST
# Crystal load capacitors, derived rather than asserted.
#
# The oscillator sees CL = (C15 * C16)/(C15 + C16) + C_stray, so matched caps of value C
# present C/2 + stray. Get this wrong and the board may simply not start - it is the one
# open item that can stop a unit booting, so the arithmetic lives here and
# tools/check_electrical.py checks the fitted values against it.
#
# CL comes from the X32258MSB4SI datasheet (LCSC C2682774): 20 pF, 120 ohm ESR. The
# 30 pF caps below follow from it - matched caps of value C present C/2 plus stray.
Y1_CL_PF        = 20.0
Y1_STRAY_PF     = 5.0
Y1_CL_CONFIRMED = True
# LCSC codes known to be PASSIVE crystals in this footprint. An active oscillator drops
# into the same SMD3225-4P land pattern and would be wired supply-to-ground here, so the
# substitution is silent, cheap to make and fatal. tools/check_electrical.py refuses any
# part for Y1 that is not on this list.
Y1_PASSIVE_LCSC = {"C2682774"}      # X32258MSB4SI, YXC, CL 20 pF, 120 ohm ESR

# ---- regulator ENABLE thresholds, and what the input rail is allowed to reach -------
#
# tools/check_electrical.py used to compute the UVLO from a HARDCODED 1.25 V with the
# comment "TPS54331 EN threshold is 1.25 V" - on a board carrying TPS54202. That is the
# same defect the VREF table two blocks down was created to end: a checker that assumes
# the part. Keyed on the fitted part, and an unlisted regulator is an ERROR rather than
# a silent default, the way check_topology.py refuses an unclassified regulator.
#
# CONFIRM_EN_THRESHOLD flags a value that has NOT been read off the datasheet page. The
# check reports it rather than trusting it, and preflight.py carries it in the
# "cannot be checked offline" list.
EN_THRESHOLD_V = {
    "TPS54331": (1.25, True, "[D] TI TPS54331 datasheet"),
    "TPS54202": (1.21, True, "[D] SLVSD26 5.5 Electrical Characteristics, V(EN_RISING) "
                             "typ 1.21 V (max 1.28); the same 1.21 V is used in the "
                             "datasheet's own UVLO equations, 6.3.5. "
                             "docs/datasheets/TPS54202-SLVSD26.pdf"),
}

# Input voltage limits of each part sitting directly on VBAT, so the TVS can be judged
# against WHAT IT PROTECTS instead of against cell count - see check_electrical.py sec 5.
#
# Two different numbers, and using the wrong one gives the wrong answer:
#   recommended - the band the part is SPECIFIED in. Governs steady-state design.
#   absolute    - the destruct limit. A TVS clamps a MICROSECOND surge, so this is the
#                 number a clamping voltage must be compared against.
# Comparing a clamp against the recommended maximum would reject every TVS that exists,
# because the Vc/Vrwm ratio of the whole SMBJ family is about 1.6.
#
# (recommended_max, absolute_max, absolute_confirmed, src)
VBAT_PART_VMAX = {
    "TPS54202": (28.0, 30.0, True,
                 "[D] SLVSD26 5.1 Absolute Maximum Ratings, VIN -0.3 to 30 V; "
                 "5.3 Recommended Operating Conditions, VIN 4.5-28 V. "
                 "docs/datasheets/TPS54202-SLVSD26.pdf"),
    # The protection FET sits between the TVS and everything else, so the TVS
    # verdict now has to protect IT too. VDS -40 V absolute (a 4S pack is 16.8 V), and
    # VGS +-20 V - the reason DZ1 clamps the gate at ~15 V.
    "WST4041": (30.0, 40.0, True,
                "[D] WST4041 WINSOK datasheet: VDS -40 V, VGS +-20 V absolute max "
                "(docs/datasheets/WST4041_WINSOK.pdf)"),
}

# Transient-suppressor clamping voltage at the datasheet's peak pulse current. The
# STANDOFF voltage says when a TVS starts to conduct; the CLAMPING voltage says what the
# protected part actually sees during the surge, and only the second one answers
# "does this protect anything".
# ---- the 3.3 V rails: loads, and the LDOs that have to drop 1.7 V to make them ------
#
# NOTHING IN THIS REPOSITORY HAD EVER CHECKED THESE. check_thermal.py's docstring said it
# covered "the switching regulators AND THE 3V3 RAIL"; the 3V3 rail appeared nowhere in
# its code. check_build.py gained a rail-vs-regulator-rating check for +5 V after the
# TPS54331 discovery and +3V3 never got one - so NET_CURRENT["+3V3"] sat at 0.6 A, which
# is EXACTLY the AP2112K's own maximum output, with nothing comparing the two.
#
# Both LDOs are LINEAR and both are fed from +5V (verified: U9.1/U9.3 and U10.1/U10.3 are
# on +5V, U9.5 on +3V3, U10.5 on +3V3A). Every milliamp they pass burns (5.0-3.3) = 1.7 V.
LDO_DROP_V = 5.0 - 3.3

# Itemised per rail, because the two LDOs are wildly asymmetric: U9 carries the MCU, the
# flash, the card and the CAN transceiver, while U10 carries three MEMS sensors. The old
# single "250 mA through the 3V3 LDOs" row in docs/HARDWARE.md hid that, and also left
# the microSD and CAN rows looking like 5 V loads when both sit on +3V3 behind U9.
LOADS_3V3 = [   # through U9, AP2112K-3.3
    ("STM32H743 core + IO at 480 MHz", 0.240, 0.240, "[A] docs/HARDWARE.md budget row, "
                                                     "less the sensors that are on +3V3A"),
    ("W25Q128 config flash",           0.004, 0.025, "[D] W25Q128JV: ~4 mA read, 25 mA "
                                                     "during program/erase"),
    # NOT zero continuous. ArduPilot logs to the card for the WHOLE flight at 400 Hz+,
    # so "idle between logs" describes the bench, not the aircraft. The card is writing
    # in bursts throughout, and it is the load that pushes U9 over its junction limit -
    # which makes it the opposite of a rare peak.
    ("microSD card (logging)",         0.040, 0.100, "[A] ~40 mA average while ArduPilot "
                                                     "logs; [D] 100 mA write peak"),
    ("SN65HVD230 CAN transceiver",     0.017, 0.070, "[D] 17 mA recessive, 70 mA dominant"),
    ("status LEDs D2/D3",              0.010, 0.010, "[A] 2 x ~5 mA through their resistors"),
]
LOADS_3V3A = [  # through U10, TLV75533
    ("ICM-42688-P",                    0.001, 0.002, "[D] ~0.88 mA 6-axis continuous"),
    ("ICM-42605",                      0.001, 0.002, "[D] ~0.75 mA 6-axis continuous"),
    ("MS5611 barometer",               0.001, 0.002, "[D] 1.4 mA peak during conversion"),
    # The SoOP receiver. This table is HAND-MAINTAINED and check_thermal reads it rather
    # than the netlist, so adding a part to NETS without adding it here changes nothing
    # the thermal check can see - which is exactly what happened when the tuner was
    # first wired in, and is why these three lines exist.
    ("MAX2112 tuner (U13)",            0.100, 0.100, "[D] MAX2112 Rev 3: 100 mA supply "
                                                     "current, VCC 3.3 V"),
    ("OPA2374 baseband amps (U14)",    0.002, 0.002, "[D] OPA2374: 585 uA per amplifier"),
    ("25 MHz TCXO (Y2)",               0.002, 0.002, "[L] JLCPCB C22381771: 3.3 V, "
                                                     "clipped sine, ~2 mA"),
]

# (package, theta_JA_minimal_copper, theta_JA_good_copper, theta_src, tj_max, i_max_A, src)
#
# TWO theta_JA values, for the same reason the buck carries two. A single figure was the
# defect this file's check_thermal.py block was written to expose (89.2 C/W cited to a
# datasheet that does not contain it) - and quoting ONLY the pessimistic end is the same
# error with the sign flipped. theta_JA for a leadframe package with no thermal pad is
# dominated by the board, not the die, so it is a range and the board decides where in it
# you land.
#
# The good-copper endpoint for SOT-23-5 is 100.8 C/W: TI's OWN measured EVM figure for
# this exact package in SBVS293 5.4, alongside its 231.1 C/W JEDEC figure. Applying it to
# the AP2112 is an ANALOGY across vendors - tagged [D~] for that reason - justified by
# theta_JA at this scale being a property of the copper rather than of the die, and by
# the two datasheets' JEDEC figures (184 and 231) bracketing each other.
#
# Which end THIS board sits at is measured, not asserted: tools/thermal_vias.py reports
# 7443 mm2 of GND plane on U9.2 across five layers and 739 mm2 of +3V3 plane on U9.5
# through five vias. For scale, a JEDEC 2s2p "high-K" test board is about 8700 mm2. So
# the good-copper end is the honest expectation here - and T3a still measures it.
LDO_SPEC = {
    "AP2112K-3.3": ("SOT-23-5", 184.0, 100.8,
                    "[D] AP2112 datasheet Absolute Maximum Ratings: theta_JA SOT-23-5 "
                    "184 C/W, explicitly '(No Heatsink)' - the MINIMAL-copper bound "
                    "(docs/datasheets/AP2112-DiodesInc.pdf). [D~] good-copper end from "
                    "SBVS293 5.4's measured SOT-23-5 EVM figure, 100.8 C/W",
                    150.0, 0.600,
                    "[D] TJ 150 C operating junction maximum; 600 mA minimum guaranteed "
                    "output"),
    "TLV75533":    ("SOT-23-5 (DBV)", 231.1, 100.8,
                    "[D] SBVS293 5.4 Thermal Information, DBV RthetaJA 231.1 C/W JEDEC "
                    "and 100.8 C/W on TI's EVM. docs/datasheets/TLV755P-SBVS293.pdf",
                    125.0, 0.500,
                    "[D] TJ 125 C recommended operating maximum; 500 mA output"),
}

# (clamping_V, standoff_V, breakdown_min_V, Ipp_A, src)
TVS_CLAMP_V = {
    "SMBJ33A": (53.3, 33.0, 36.7, 11.3, "[D] Littelfuse SMBJ series datasheet"),
    "SMBJ20A": (32.4, 20.0, 22.2, 18.6, "[D] Littelfuse SMBJ series datasheet"),
    "SMBJ18A": (29.2, 18.0, 20.0, 20.6, "[D] Littelfuse SMBJ series datasheet"),
}
_load = int(round(2 * (Y1_CL_PF - Y1_STRAY_PF)))
CAP("C15", f"{_load}p"); CAP("C16", f"{_load}p")
RES("R1", "10k")                                          # BOOT0 pulldown
IND("L1", "600R@100MHz", F_L0805)                          # VDDA ferrite

# buck 5V
CAP("C17","10u", F_C1206); CAP("C18","10u", F_C1206)      # VBAT bulk
CAP("C19","100n", F_C0402)                                 # VIN hf
RES("R3","preset")   # EN only - C20 (soft-start) deleted: TPS54202 is internal
RES("R4","392k"); RES("R5","78k7")                         # EN divider
CAP("C21","100n")                                          # BOOT cap
# RESOLVED - and this note was wrong about it twice. Verified against the artwork
# 2026-09-04: L2 sits on L_APV_ANR4030, the correct 4.0 x 4.0 land, on F.Cu BESIDE U8.
# Both halves of the old warning are now dead:
#
#   - the FOOTPRINT: it said "the board still has a 1210 land here". It does not. The
#     1210 land is L5's, not L2's - see the IND("L5", ...) line below, and note that
#     check_ratings measures the overhang there at 0.18 mm, not a part off its land.
#   - the CURRENT: it said 1.89 A and "118 % of rating, check_ratings.py FAILS on this
#     deliberately". True when the Pi Zero drew 700 mA from this rail; the Pi now runs
#     from its own BEC, so L2 carries 0.95 A of its 1.6 A Irms - 59 %, and check_ratings
#     PASSES.
#
# Nor does the switch node cross the board any more: U8 is F.Cu at (130.50, 112.94) and
# L2 is F.Cu at (130.79, 106.43). Keep them on the same side - the loop area on this
# node is the one placement decision that most directly threatens a 1.6 GHz receiver
# sitting on the same airframe (docs/BUILD.md T3b).
#
# The CURRENT half of this note was stale and is corrected here (2026-09-04). It said
# "1.89 A fully fitted ... 118 % of rating ... check_ratings.py FAILS on this
# deliberately". That was true when the Pi Zero drew 700 mA from this rail. The Pi now
# runs from its own BEC, so L2 carries 1.19 A of its 1.6 A Irms - 74 %, and
# check_ratings.py PASSES. (0.95 A / 59 % since the WS2812 budget was corrected to
# strobe duty, 2026-09-05.) Do not go looking for a failure that is no longer there.
#
# The rating is still the binding limit on the whole +5 V rail: see RAIL_5V. It must not
# be silenced by quietly changing the BOM to a part the land can take but the current
# cannot.
#
# The fix needs placement work, not a part swap: a 5x5 land collides with 7 bottom-side
# neighbours and a 4x4 with 4, and an iterative shove thrashed rather than converged -
# the bottom side is 82 of 115 parts. This applied to BOTH inductors when written; L2
# has since been moved to F.Cu beside U8 and given the right land. L5 has NOT: it is
# still B.Cu at (127.50, 119.00) on a 1210 land, opposite U18 on F.Cu, so the 9 V
# switch node still crosses the board. That block is DNP and BUCK9_PH is unroutable
# anyway, so the two defects share one fix - move L5 up beside U18 in a respin.
IND("L2", "10uH", F_ANR4030)   # 4x4 land - the FNR4030 never fitted a 1210
CAP("C22","22u", F_C1206); CAP("C23","22u", F_C1206)      # 5V out
# NOT THE SHIPPED VALUES. _VALUE_FIX (search for it) overrides these to 37k4 / 5k1 for
# the TPS54202's 0.596 V reference -> 4.967 V. The pair below is the original TPS54331
# 0.8 V design and is kept only so the diff against that part stays legible.
RES("R6","10k2"); RES("R7","3k24")                         # -> overridden, see _VALUE_FIX
# R8/C24/C25 COMP network DELETED - TPS54202 compensates internally

# LDOs
CAP("C26","1u"); CAP("C27","1u")                           # AP2112 in/out
CAP("C28","1u"); CAP("C29","1u")                           # TLV75533 in/out
CAP("C30","100n")                                          # 3V3A local

# sensors
CAP("C31","100n"); CAP("C32","100n")                       # IMU1 VDD/VDDIO
CAP("C33","100n"); CAP("C34","100n")                       # IMU2
CAP("C35","100n")                                          # baro
CAP("C36","100n")                                          # flash
RES("R9","4k7"); RES("R10","4k7")                          # I2C1 pullups
RES("R11","4k7"); RES("R12","4k7")                         # I2C2 pullups
# U6 (PMW3901), U7 (VL53L1X) and their passives C37-C40, R13 are deleted -
# neither sensor could see the ground through the ESC, and both freed pins for the
# dedicated I2C port (J9) that carries the same functions OFF the board instead.

# CAN
CAP("C41","100n"); RES("R14","10k")                        # HVD230 Rs slope
RES("R15","120R")                                          # termination (DNP by default)
COMPONENTS["R15"] = (R, F_R0402, "120R", "", True)

# USB
RES("R16","5k1"); RES("R17","5k1")                         # CC1/CC2
CAP("C42","1u", F_C0805)                                   # VBUS

# battery sense
RES("R18","10k"); RES("R19","1k")                          # 11:1 divider
CAP("C43","100n"); CAP("C44","100n")                       # V/I sense filters

# LEDs + buzzer
RES("R20","1k"); RES("R21","1k")
add("D2", LED, F_LED, "BLUE"); add("D3", LED, F_LED, "GREEN")
add("SW1", SW, F_SW, "BOOT"); add("SW2", SW, F_SW, "RESET")

# microSD
CAP("C45","10u", F_C0805); CAP("C46","100n")
for i,(r) in enumerate(["R22","R23","R24","R25","R26","R27"]): RES(r, "47k")  # SDMMC pullups

# RF section passives. The TUNER half is fitted; the LNA/SAW half is not on this board
# at all (the Nooelec SAWbird+ IR does that job at the antenna, which is where an LNA
# belongs and which is also why the un-sourceable 1620 MHz SAW stopped mattering).
for r,v in [("C49","100n"),("C50","100n"),("C51","1u"),
            ("C52","100p"),("C56","10n"),("C57","10n")]:
    CAP(r, v, F_C0402)
for r,v in [("R28","0R"),("R29","0R"),("R30","10k"),("R31","10k"),
            ("R34","1k"),("R35","1k"),("R36","4k7"),("R37","4k7")]:
    RES(r, v, F_R0402)
# C58 WAS an 18 pF crystal load cap. It is now the series coupling capacitor the
# datasheet asks for by value: "[D] MAX2112 Rev 3 pin 14 XTAL - Crystal-Oscillator
# Interface. Use with an external parallel-resonance-mode crystal through a series 1nF
# capacitor." Y2 is an ACTIVE oscillator driving that pin, which the same datasheet
# permits explicitly: "Input Overdrive level, AC-coupled sine-wave input, 0.5 / 1 /
# 2.0 VP-P". A clipped-sine TCXO sits inside that window; a CMOS-output part would
# swing 3.3 V and exceed it, which is why the output type is part of the part choice.
CAP("C58","1n", F_C0402)      # series AC coupling, Y2 output -> U13 XTAL
CAP("C59","100n", F_C0402)    # Y2 supply decoupling (was the second 18 pF load cap)
# ------------------------------------------------------------- connector orientation
#
# Which way a connector's opening faces, in FOOTPRINT-LOCAL coordinates, as a unit vector.
#
# This exists because both J1 and J2 shipped in the layout fitted BACKWARDS - mouths
# pointing into the board. J1 was fatal: no cable could be plugged in, so the board could
# not be flashed or talked to at all. J2 opened straight into U1, 3.28 mm away, with no
# room for the plug carrying VBAT and all four motor signals.
#
# Nothing caught it. check_design, check_hwdef, check_electrical, check_traces,
# check_placement, check_build and DRC all validate ELECTRICAL correctness; which way a
# connector faces is mechanical intent and no rule expressed it. check_build even measured
# J1's 0.83 mm to the board edge and passed it without ever asking which way it faced.
# gen_pcb.py picks a connector's rotation purely to make it FIT (0 or 90, whichever packs),
# so the placer knew where every connector went and never which way round.
#
# All four are +y, and that is not a coincidence - it falls out of how these parts are
# drawn. The signal pad row is at the REAR of a connector, because that is where the
# contacts leave the housing, and the courtyard and silkscreen extend further past the
# FRONT to reserve room for the plug. So:
#
#     mating face = the side opposite the largest pad row
#                 = the side the courtyard extends further toward
#
#   J1  USB-C  12 contacts at y -2.38; courtyard -3.24..+3.71; silk to +4.97 (plug keep-out)
#   J2  JST-SH  8 signals at y -1.94, anchor tabs at +1.94; body -1.60..+2.65; silk to +2.86
#   J3  JST-GH  6 signals at y -1.60, anchor tabs at +1.60; courtyard -2.75..+3.29
#   J8  microSD 9 contacts at y -5.28; courtyard reaches +9.92 - the card slot and the
#               space a card needs to be pushed into and pulled out of
#
# tools/check_connectors.py re-derives this from the footprint and fails if a declared
# value disagrees, so a footprint swap cannot silently invalidate the table.
MATING_FACE = {
    "J1": (0.0, +1.0),   # USB-C          - plug inserts along -y toward the board
    "J2": (0.0, +1.0),   # ESC JST-SH 8P
    "J3": (0.0, +1.0),   # GPS/I2C JST-GH 6P
    "J8": (0.0, +1.0),   # microSD card slot
    # Tier-1 connectors, both JST-SH 4P on the left edge (same class as J2, so
    # the same face convention: signal pad row at local -y, mouth at +y).
    # J4 (companion) and J10 (servo) are NOT here: they were cut on 2026-09-09
    # after an exhaustive geometry search proved neither has a legal edge home on
    # a 45 x 46 mm board with 30.5 mm mounts (see the edge-connector section).
    "J5": (0.0, +1.0),   # RC receiver JST-SH 4P
    "J9": (0.0, +1.0),   # I2C port (VCC/SCL/SDA/GND) - the dedicated bus
    "J11": (0.0, +1.0),  # SERIAL2 lidar port (5V/TX/RX/GND)
}

# How much straight, clear space the plug needs in front of the mating face, in mm.
# This is the check that would have caught J2: its mouth was 0.82 mm from the board edge
# and every clearance rule passed, but it faced inboard into the MCU with 3.28 mm of room
# - enough for neither the plug body nor the fingers to fit it and pull it out again.
MATING_CLEARANCE = {
    "J1": 9.0,    # USB-C plug overmould
    "J2": 6.0,    # JST-SH plug plus wire bend
    "J5": 6.0,    # JST-SH class, same as J2
    "J9": 6.0,    # JST-SH class, same as J2 (the dedicated I2C port)
    "J11": 6.0,   # JST-SH class, same as J2 (SERIAL2 lidar port)
    # J3 was 6.0, a JST-GH class nominal - it warned, because the measured clear run to
    # R21 is 5.30 mm. DERIVED 2026-09-05 and the class figure retired: the GPS pigtail
    # is a pre-wired GH shell whose wires exit the REAR at roughly the shell's
    # mid-height, ~2-3 mm above the board and already parallel to it, so nothing in the
    # corridor taller than the wire exit needs bend allowance. The only neighbour is
    # R21, a 0402 1k standing 0.55 mm. Shell half-width (2.6 mm) + 1.0 mm handling
    # margin = 3.6 mm against a measured 5.30 mm. Relocating R21 was mapped and
    # REJECTED: the corridor behind it is saturated by TP20's courtyard and a GND via
    # fence at y=140.6 - no position inside the J3-mouth-to-TP20 span yields 6.0 mm.
    # Residual risk is a bulky moulded boot or heatshrink on the pigtail - T2's
    # arrival checks include test-fitting it before headers are soldered.
    "J3": 3.6,    # JST-GH pigtail: shell half-width + handling margin (derived, not class)
    "J8": 14.0,   # a microSD card must come all the way out
}

# ----------------------------------------------------------------- vertical mating
#
# Connectors that mate along +z instead of across the board. The 2D mouth/corridor
# logic in check_connectors cannot express these, and adding a horizontal MATING_FACE
# vector would make the check answer a question about a connector that does not exist.
# J12 is the U.FL antenna port (Hirose U.FL-R-SMT-1, vertical): the plug stands up off
# the board and the coax bends 90 degrees, so the two things to assert are that the
# plug is on the TOP face and that plug + bend fit the vertical room between the board
# and the top plate (9.8 mm with the 35 mm standoff - see check_connectors).
VERTICAL_MATING = {
    "J12": dict(
        plug=2.2,    # mated plug height above the board, [D] Hirose U.FL-R-SMT-1
        bend=3.0,    # 90-degree coax bend radius above the plug, [D] RG178 bend radius
        radius=4.0,  # horizontal sweep the bend needs around the connector centre, mm
        src="[D] Hirose U.FL-R-SMT-1 vertical + RG178 coax bend"),
}


# ---- parts that must SEE something, not merely fit -------------------------------
# Every mechanical check on this board measured CLEARANCE - "does it fit" - and all of
# them passed U6 and U7 while both sensors were aimed at the top of the ESC 3 mm away.
# Fitting and seeing are different properties, and only one of them was ever tested.
# This is the same defect that put J1 and J2 on the board facing inwards: nothing
# expressed the requirement, so nothing could check it.
#
#   ref: (direction, half_angle_deg, range_mm, what it needs to see)
# direction is the surface normal the sensor looks along, in board coordinates, with
# +z out of the TOP face. A bottom-side downward sensor is therefore (0, 0, -1).
GROUND_FACING = {
    # U6 (PMW3901) and U7 (VL53L1X) are deleted: both faced the ESC 3.0 mm away and
    # could never see anything, which is why they shipped DNP. The downward functions
    # they were supposed to provide now arrive OFF the board (flow as MAVLink
    # OPTICAL_FLOW, range from the TFS20-L on the dedicated I2C port J9).
}

# The optical-flow CAMERA on the companion Pi is also ground-facing, but it is NOT on
# this board - it hangs under the FC on the Pi companion. Modelled separately in
# cad/drone.scad; its line-of-sight constraint (lens above the skid contact line) is
# checked there via the cam_drop / cam_mod_t figures.
CAMERA = dict(name="OV9281 global-shutter module", mod_w=30.0, mod_t=12.0,
              lens_dia=8.0, lens_len=3.5,
              src="[D] Arducam B0162 module; [A] mount position undecided")
# LANDING GEAR - and the published part is NOT what this design assumed.
#
# The TBS repo publishes SO1-V6-skate.stl, measured here at 75.96 x 102.17 x 6.00 mm.
# It is a FLAT WEAR PLATE printed lying down, not a tall leg: 6 mm of ground clearance
# where this design assumes 25 mm. So the open-source frame does NOT close the landing
# gear question, and an earlier note claiming it did was wrong.
#
# WHY THE DROP MATTERS: ground clearance is what protects anything looking downward. The
# flow camera is deferred, but the downward TFS20-L still has to survive landings, and
# check_mechanical's lens-vs-skid line is computed from SKID["drop"].
#
# TWO DIFFERENT PARTS, kept apart deliberately:
#   * SKID below - a tall TPU leg on the 19x19 motor pattern, still [A], still what the
#     clearance checks assume;
#   * SKATE - the published flat plate, real dimensions, 6 mm. Useful as arm-underside
#     protection; not a substitute for legs.
#
# AND THE THICKNESS FEEDS THE MOTOR SCREW. At 3.5 mm the screw is M3x14; a 6 mm skate
# sandwiched under the motor instead would need 16 mm. Do not mix them up when ordering.
# THE BELLY SENSOR POSITION - where anything that must see the GROUND actually goes.
#
# The recurring question is "the flight controller cannot see down, so how do we have a
# downward ToF and downward flow?" The premise is right and the conclusion does not
# follow: NOTHING ON THE FC NEEDS TO SEE. U6 (PMW3901) and U7 (VL53L1X) are DNP because
# they face the ESC 3.0 mm away, and U6 is 15.5 mm off the board centre so it could not
# even use the frame's 10 mm centre pass-through if the stack were inverted.
#
# Downward sensors mount UNDER THE BOTTOM PLATE and cable back. That is also what every
# commercial aircraft does - DJI's downward vision system is a belly module, not part of
# the flight controller.
#
# MEASURED SPACE: 43.5 mm from the bottom plate's underside to the skid contact line
# (SKID drop 40.0 + pad 3.5). A 12 mm module leaves 31.5 mm of clearance, which is what
# check_cad_fit.py's GROUND_PARTS check reports for belly_sensor.
#
# These three numbers were 28.5 / 16.5 / 13.0 until 2026-09-05 - the drop-25 figures,
# left behind when SKID['drop'] went to 40 mm. depth_available_mm below was fixed at the
# time and correctly derives from SKID; this PROSE beside it was not, so the file
# explained its own derived value using the superseded one.
#
# ONE MODULE CAN DO BOTH JOBS. A Matek 3901-L0X is PMW3901 flow + VL53L0X rangefinder in
# one 36 x 12 mm body on one UART - so if flow is ever added it REPLACES the downward
# rangefinder rather than competing with it for this position. Fitting the TFS20-L now
# and a flow module later means removing the TFS20-L, not finding a second belly slot.
BELLY_SENSOR = dict(
    # DERIVED, not a literal. This was hardcoded 28.5 while its own src line claimed it
    # was "computed from design.SKID" - so raising the skid drop on 2026-09-04 left it
    # stale and still reporting the old depth. Exactly the failure this repo keeps
    # finding: a value that claims to be derived and is not. Now it actually is.
    depth_available_mm=None,        # filled in below, once SKID exists - see the note
    typical_module_h=12.0,          # [L] TFS20-L / 3901-L0X class
    # Plan footprint of the bracketed module, for the CAD. Literals in
    # gen_scad_frame.py until now. Sized for the Matek 3901-L0X, which is the largest
    # thing this slot is meant to take (the TFS20-L itself is only 21 x 15 mm), so the
    # clearance results hold for either occupant.
    l_mm=36.0, w_mm=16.0,
    occupant="Benewake TFS20-L (downward rangefinder, I2C 0x10 on J3)",
    future="a Matek 3901-L0X would take this slot and REPLACE the TFS20-L, since it "
           "carries its own VL53L0X - one module, one cable, flow AND range",
    mount="printed bracket under the bottom plate; needs a clear cone to the ground and "
          "must stay above the skid contact line so a landing does not crush it",
    src="[M] depth computed from design.SKID; [M] the 12 mm module envelope at this "
        "position passes check_cad_fit's ground clearance with 31.50 mm of margin")

# POWERING THE RECORDING CAMERA - two wires, and that is the whole harness.
#
# This block first specified perfboard, a 14-way female socket and a coiled pigtail.
# That was over-engineered and the simpler answer is strictly better:
#
#   P41 (+5V) and P46 (GND) -> the XIAO's 5V and GND pins. Optionally a 2-pin JST in
#   the middle so the camera pod unplugs. 0.25 A against 0.41 A of rail headroom -
#   see RAIL_5V below; it is NOT the 1.8 A this comment used to claim.
#
# The socket bought nothing. The XIAO has USB-C on board, so it is reflashed in place;
# there is no reason to pull it out, and a 14-way header is 8.5 mm of height and a lot
# of solder joints to buy a capability nobody needs.
#
# ALTERNATIVE, if total isolation is ever wanted: the XIAO has BAT+/BAT- pads and a
# built-in 1S LiPo charger (370 mA), charged over its own USB-C. A 300 mAh cell runs
# it ~1.2 h at 0.25 A - several flights - with NO electrical connection to the flight
# controller at all. Rejected as the default because it trades a small isolation gain
# for a second charging routine that will eventually be forgotten before a flight.
#
# IT CANNOT MOUNT ON THE FC EITHER WAY. A socketed XIAO stands ~12 mm; the board has
# 3.0 mm beneath it (the compressed grommet gap to the ESC) and 5.4 mm above. The
# camera lives on the frame, so the routed board does not change to gain one.
#
# HOW A VTX WOULD BE POWERED - corrected 2026-09-04. An earlier version of this
# comment said "PF1 is the only VBAT pad". THAT WAS WRONG, and wrong in the way this
# repo keeps being wrong: PF1 is a schematic POWER FLAG (see PWR_FLAGS below), not a
# footprint. Verified against the artwork - VBAT reaches only J2, D1, R4/R18/R40, the
# four bulk caps and the two bucks. THERE IS NO VBAT PAD OR TEST POINT ON THIS BOARD.
#
# So an analogue FPV VTX has two real options, neither of them a VBAT pad:
#   - the +5V rail at P41/P46. Headroom there is 0.41 A, NOT the 1.8 A older comments
#     claimed - see RAIL_5V. A 25 mW EIRP AIO (~0.30 A) fits, but it and the recording
#     camera together do NOT. 25 mW EIRP is the licence-exempt Ofcom IR 2030 airborne
#     limit anyway, so this is the right size of transmitter regardless.
#   - the battery harness or the ESC's own VBAT pads, off-board, for anything bigger.
# Either way it is independent of how the ESP32 is powered, so run it only when FPV
# is actually chosen. The ESP32 itself can never be
# the FPV transmitter: no composite video out, and its only radio is 2.4 GHz WiFi -
# the band the ELRS control link uses.
PAYLOAD_BREAKOUT = dict(
    harness="2 wires: P41 (+5V) and P46 (GND) to the XIAO's 5V and GND pins",
    connector="optional 2-pin JST so the camera pod unplugs",
    # DERIVED. This was a hardcoded 0.413, a copy of the +5 V headroom as it stood
    # before the WS2812 row was corrected from a 300 mA guess to a 60 mA strobe-duty
    # budget. RAIL_5V has said 0.653 since; this said 0.413 for as long. It is assigned
    # below, once RAIL_5V exists, for the same reason depth_available_mm is.
    current_a=0.25, headroom_a=None,
    alt="1S LiPo on the XIAO's BAT+/BAT- pads (built-in 370 mA charger, own USB-C) "
        "for zero connection to the FC - costs a second charging routine",
    not_on_fc="a socketed XIAO needs ~12 mm; the FC has 3.0 mm below and 5.4 mm above",
    future="+5V + GND from P41/P46 for a later 5.8 GHz VTX (there is NO VBAT pad on "
          "this board - PF1 is a power flag, not a footprint) - separate decision, run it "
           "only if FPV is actually chosen",
    cost_gbp=1.0,
    src="[M] clearances from design.required_standoff(); [D] XIAO has BAT+/BAT- pads "
        "and a 1S charger; [M] 0.25 A against the +5V rail's 0.41 A headroom - see RAIL_5V")

# RECORDING CAMERA - a XIAO ESP32S3 Sense on the nose, writing to its own microSD.
#
# Chosen over a RunCam-class action cam because it does the same job for a fifth of the
# money: the board is ~GBP 10-14 on AliExpress and carries an OV2640/OV3660, a microSD
# slot and 8 MB PSRAM. With the existing open-source ESP32-CAM_MJPEG2SD firmware it
# writes ~20 fps AVI to the card. (Naive JPEG-per-frame gets ~1 fps at SVGA - use the
# firmware, not a for-loop.)
#
# WIFI AND ESP-NOW STAY OFF IN FLIGHT, and this is the important line. The RC link is
# 2.4 GHz ELRS. An ESP32 radiating 2.4 GHz a few centimetres from the ELRS receiver can
# desensitise it, and that is a CONTROL-LINK failure, not a video glitch. Recording to
# the local card needs no radio at all. This is also why FPV video lives on 5.8 GHz:
# band separation from the control link is the whole point.
#
# ESP-NOW CANNOT CARRY VIDEO in any case - it is a ~250-byte-payload telemetry
# protocol. If live video is wanted later it is a 5.8 GHz analogue AIO camera+VTX
# (~GBP 15-19) powered from the +5V pads P41/P46 or the battery harness - NOT from a
# VBAT pad, because this board has none - viewed on a 5.8 GHz UVC receiver that a
# laptop sees as a webcam. That is a separate purchase and a separate decision.
#
# Rolling shutter on a quad means jello - soft-mount it.
CAMERA_REC = dict(name="XIAO ESP32S3 Sense", L=21.0, W=17.5, H=13.0, g=6.0,
                  power="5V", current_a=0.25, storage="microSD <=32GB FAT32",
                  fw="ESP32-CAM_MJPEG2SD, ~20 fps AVI",
                  mount="nose; SO1-V6-AN-Cam-Mount.stl is 62.6 x 28.8 and made for a "
                        "19x19 analogue cam, so it needs a simple printed bracket",
                  radio_off=True,
                  # How far forward of centre it sits, in mm. Was a bare "78" inside
                  # gen_scad_frame.py's output string. It is a FREE CHOICE, not a
                  # measurement - the prop discs clear the nose everywhere along the
                  # plate - but it feeds check_cad_fit's props/rec_cam clearance, so it
                  # belongs where the airframe is defined rather than in a generator.
                  nose_y_mm=78.0,
                  src="[D] Seeed: XIAO form factor 21 x 17.5 mm, OV2640/OV3660, microSD, "
                      "8 MB PSRAM; [L] ~GBP 10-14 AliExpress; [A] 13 mm stacked height "
                      "and 6 g with the Sense expansion - MEASURE ON ARRIVAL")

# THERE IS NO LISTING TO CONFIRM HERE - the skid is a part you PRINT, so it has no
# marketplace page and never will. That distinction was blurred by tagging the whole
# dict [A] and telling the reader to "confirm on the listing", which cannot be done.
# The three numbers have quite different standing:
#   hole_pitch 19.0 is [D] - it is the motor's own bolt pattern, from BrotherHobby's
#     product data, and the skid must be DESIGNED to it. Nothing to verify; something
#     to build to.
#   t 3.5 and drop 25.0 are DESIGN CHOICES for a part you make, not guesses about a
#     product. Change them and reprint. The drop is what sets the camera's ground
#     clearance, so it is the number to settle before printing, not before ordering.
# NOTE the frame's own published skate is a 6.0 mm flat wear plate (PRINTABLE), NOT a
# 25 mm leg - printing that instead gives no ground clearance for a downward camera.
SKID = dict(t=3.5, drop=40.0, hole_pitch=19.0, printed=True,
            # DROP RAISED 25 -> 40 mm to give the LD06 a home. The lidar is [D] 33.30 mm
            # tall and the belly had only 28.5 mm at a 25 mm drop - short by 4.80 mm.
            #
            # 35 mm WAS TRIED FIRST AND WAS THE WRONG CALL. It clears by 5.20 mm, and
            # 35 was chosen over 40 to avoid raising the CG - but the trade was asserted,
            # not computed. Computing it: static tip-over goes 71.5 deg -> 69.9 deg, a
            # 1.6 deg change, and both are nowhere near the ~30 deg where a quad is
            # tippy. Meanwhile the ground clearance under the lidar DOUBLES, 5.20 ->
            # 10.20 mm. TPU landing gear deflects several mm under a firm arrival, so
            # 5.20 mm is inside the range one hard landing can consume - and the part
            # taking the hit would be the lidar, not the skid.
            #
            # 30 mm would leave 0.20 mm, which is not a clearance at all.
            #
            # This is a printed part, so the drop is a free parameter - which is exactly
            # why it must be set deliberately and BEFORE printing rather than inherited.
            # The trade: taller legs raise the aircraft's CG relative to the ground and
            # add tip-over moment on an uneven landing. Against that, the 42 g lidar
            # hangs BELOW the plates, and vertical CG is currently +14.9 mm ABOVE the
            # rotor plane with 61 % of mass high - so a belly load pulls CG the way it
            # needs to go.
            src="[D] 19x19 pitch is the motor's bolt pattern (BrotherHobby Avenger); "
                "[M] 3.5 mm thickness is a design choice for a printed part; "
                "[M] 40 mm drop DERIVED from the LD06's datasheet height plus margin - "
                "see BELLY_SENSOR and OFFBOARD['lidar']")

# Belly depth is SKID's drop plus its pad thickness, measured from the bottom plate's
# underside. It is filled in HERE rather than at BELLY_SENSOR's definition only because
# that dict is declared before SKID; the point is that it is computed, not typed. It was
# a hardcoded 28.5 whose own src line claimed it was "computed from design.SKID", so
# raising the drop would have left it silently stale.
BELLY_SENSOR["depth_available_mm"] = SKID["drop"] + SKID["t"]
# The ESC this board bolts to. Lived in check_mechanical.py AND cad/drone.scad and
# nowhere else - a fifth duplicated physical constant. One home.
# STANDOFF LENGTH IS DERIVED, NOT ASSUMED - and the assumed value was wrong.
#
# The frame kit ships 30 mm standoffs and this project carried 30 mm as "the frame
# inner height" for weeks. It does not fit. Measured from the bottom plate the stack
# needs 30.3 mm before any headroom at all, so a 30 mm standoff is 0.3 mm short and
# the top plate lands on the FC's tallest connector.
#
# Found by tools/check_cad_fit.py after cad/drone.scad was corrected to put the arms
# and the mid plate UNDER the stack instead of drawing everything from z = 0. The old
# model had the ESC sitting on the bottom plate, which hid 8.0 mm of frame.
#
# Two things make this cheap rather than fatal: standoffs are a few-pound purchase in
# 25/30/35/40 mm, and this is caught before ordering. BUY 35 mm.
#
# HONEST UNCERTAINTY: whether the frame's "30 mm inner height" is measured from the
# bottom plate or from the mid plate is not settled by a 2D DXF, and the readings
# differ by 8.0 mm. This takes the WORSE one. If the frame turns out to measure from
# the mid plate, 35 mm standoffs simply leave more room than computed - never less.
def required_standoff(board, headroom=3.0):
    """Standoff length needed from the BOTTOM plate, and the stock size to buy."""
    top, bot, topref, botref, _ = stack_heights(board, skip_dnp=True)
    below = FRAME["bottom_t"] + FRAME["arm_t"] + FRAME["medium_t"]
    stack = ESC["pcb"] + ESC["parts"] + MOUNTING["gap"] + bot + BOARD_T + top
    need  = below + stack + headroom
    stock = next((s for s in STANDOFF_STOCK if s >= need), None)
    return dict(below=below, stack=stack, headroom=headroom, need=need, buy=stock,
                top=top, bot=bot, topref=topref, botref=botref,
                slack=(stock - below - stack) if stock else None,
                src="[M] computed from the board + FRAME + ESC + MOUNTING")

BOARD_T = 1.6                       # [M] 6-layer stackup, tools/design.py
STANDOFF_STOCK = (25, 30, 35, 40, 45)   # [L] common M3 aluminium standoff lengths

# The soft mount between this board and the ESC. Duplicated in check_mechanical.py and
# cad/drone.scad; the gap sets ALL the stack clearance arithmetic, so it gets one home.
# It is [A]: silicone grommets compress under the stack bolt and nobody publishes the
# compressed height. 3.0 mm is the conservative (small) end - a larger real gap only adds
# clearance. This is the number to re-measure with calipers once the parts are in hand.
# plate_hole_d is the CLEARANCE hole in a frame plate, and it must be bigger than the
# screw. cad/drone.scad cut its plate holes at exactly screw_dia, so a 3.0 mm bolt sat
# in a 3.0 mm hole - coincident surfaces, and check_cad_fit.py measured 132.5 mm^3 of
# bolt inside the plates, which is very nearly the whole bolt (4 x pi/4 x 3^2 x 4.5 =
# 127 mm^3). 3.2 mm is the standard M3 close-clearance hole.
MOUNTING = dict(gap=3.0, grommet_d=6.0, screw="M3", screw_dia=3.0,
                hole_d=4.0, plate_hole_d=3.2,
                pitch=30.5,
                src="[A] M3 silicone grommet compressed to 3.0 mm; "
                    "[M] 30.5 mm pitch and 4.0 mm holes from design.BOARD")

# THE SIXTH duplicated physical constant, and it survived the round that fixed the other
# five. tools/check_build.py carried its own ESC dict - same part, same name, same L/W,
# but a DIFFERENT set of fields (H, g, cont_A, burst_A, proto, cur_scale_mv_per_A) that
# this one did not have. Two dicts describing one component, neither complete, is exactly
# how wheelbase came to be 295 in one file and 300 in another. Merged: the fields below
# are the union, and check_build.py now reads this.
#
# amps and cont_A are the same quantity under two names, kept both because check_build's
# output text uses cont_A and design's netlist notes use amps. They are asserted equal
# at the bottom of this file rather than left to drift.
ESC = dict(name="SpeedyBee BLS 60A", L=45.6, W=44.0, pcb=1.6, parts=6.2,
           mount=30.5, conn="JST-SH 8P", cells="3-6S", amps=60,
           H=7.8, g=10.5, cont_A=60.0, burst_A=80.0, proto="DSHOT300/600",
           cur_scale_mv_per_A=40.0,
           src="[D] SpeedyBee BLS 60A manual")
assert ESC["amps"] == ESC["cont_A"], "ESC amps and cont_A are the same rating"

SKATE = dict(name="SO1-V6-skate.stl", L=75.96, W=102.17, t=6.00, drop=6.00,
             printable=True,
             note="flat underside wear plate, NOT a landing leg - 6 mm clearance",
             src="[M] bounding box parsed from the STL published at "
                 "github.com/tbs-trappy/source_one, 2026-09-02")

# PRINTABLE ACCESSORIES published with the frame, all measured from their STLs and all
# inside an Ultimaker 2+ envelope (223 x 223 x 205 mm) with room to spare.
PRINTABLE = {
    "SO1-V6-skate.stl":          (75.96, 102.17,  6.00),
    "SO1-V6-AN-Cam-Mount.stl":   (62.60,  28.80,  4.00),
    "SO1-V6-O4-Cam-Mount.stl":   (62.30,  28.80,  4.00),
    "SO1-V6-GoPro-Mount.stl":    (36.20,  32.00, 19.40),
    "SO1-V6-O4-Antenna-Mount.stl": (33.30, 27.70, 28.80),
    "So1-V6-2025-SMA-mount.stl": (29.00,  15.60, 17.30),
    "SO1-V6-ImT-Mount.stl":      (48.90,  23.70,  8.50),
}
PRINTER = dict(name="Ultimaker 2+", x=223.0, y=223.0, z=205.0,
               src="[D] Ultimaker 2+ published build volume")
# THE COMPANION. Radxa Zero 3W. **DEFERRED — not fitted.**
#
# The optical-flow camera and the companion are both deferred (2026-09-02): the aircraft
# navigates on its real GPS outdoors, with ToF rangefinders indoors. This entry is KEPT,
# evidence included, because the SERIAL1 companion link (P41-P46) stays provisioned and
# every argument below is still what a revived companion must satisfy. The check_build.py
# mass and power budgets deliberately still COUNT it - they are conservative worst cases;
# the real aircraft is 12 g lighter with ~2 A more 5 V headroom.
#
# Chosen on cost and availability after the Raspberry Pi Zero 2 W turned out to be
# unbuyable: RRP is GBP 14.40, but it is sold out at The Pi Hut AND Pimoroni, and the
# open market wants GBP 70. Radxa Zero 3W 1GB is about GBP 18, is the same 65 x 30 mm
# Pi Zero form factor, and carries the same 22-pin 0.5 mm MIPI CSI socket - so it is a
# mechanical drop-in for what the CAD already models.
#
# WHAT IT COSTS INSTEAD: the OV9281 does not work out of the box. See CAMERA_IFACE.
#
# Rejected: Orange Pi Zero 2W - see PI_REJECTED. Deferred: Raspberry Pi Zero 2 W, which
# is the zero-work option if it ever restocks at RRP (libcamera + OV9281 on Raspberry
# Pi OS needs no kernel work at all). Production runs to 2030; an rpilocator alert costs
# nothing and this decision is reversible - the two boards share the envelope AND the
# CSI connector, so only the software changes.
#
# MOUNTING HOLES ARE NOT PUBLISHED. Radxa's own documentation gives 65 x 30 mm and
# nothing else; resellers claim "same mounting holes as the Raspberry Pi Zero 2 W", but
# the one number any of them quote - 61 mm diagonal - does NOT match the Pi Zero's
# hypot(58, 23) = 62.4 mm. So the claim is unconfirmed and the pattern stays None. This
# is the same discipline that was applied to the Orange Pi and it was right then.
PI = dict(name="Radxa Zero 3W (1GB) - DEFERRED, not fitted", L=65.0, W=30.0, t=1.2,
          hole_dia=2.75, hole_pitch=None,
          soc="RK3566 quad Cortex-A55 @ 1.6 GHz",
          power_a=2.0,
          # Mass lived only in check_build.py's own PI dict, so design.MASS_ITEMS could
          # not be assembled without reaching into a checker. Moved here with its source
          # intact: [A] ~12 g, not published by Radxa - same 65x30 mm PCB class as a Pi
          # Zero (11 g) with eMMC pads and a heavier SoC.
          g=12.0,
          csi="J7, FPC-22P-0.5mm, 4-lane MIPI CSI - the same connector as a Pi Zero, so "
              "a 22-to-15-pin Zero cable mates a 15-pin OV9281 module",
          src="[D] radxa.com/docs: 65 x 30 mm, 1x4-lane MIPI CSI, 5V/2A; "
              "[D] radxa_zero_3w_v1.12_schematic.pdf for the CSI connector; "
              "[U] mounting hole pattern NOT published by Radxa - measure the board")

# OPTICAL FLOW IS DEFERRED. The aircraft flies without it - see FLOW below.
#
# The reasoning that got here is worth keeping, because half of it is a correction.
#
# RIGHT: the flow camera is NOT the position source and never was. SoOP is. The IMU only
# has to bridge between SoOP updates, and at 5 Hz that is 0.2 s - at a realistic 0.1 deg
# tilt error the IMU accumulates 0.3 MILLIMETRES in that gap. The estimator does not need
# flow to hold position while an absolute fix is arriving.
#
# WRONG: "two good IMUs will not drift". Every IMU drifts, and it drifts QUADRATICALLY,
# because the dominant term is not accelerometer bias - it is ATTITUDE error leaking
# gravity into the horizontal axes, a = g*sin(theta). Unaided, from this board's
# ICM-42688-P + ICM-42605:
#
#     tilt error      10 s     30 s     60 s    120 s    300 s
#     0.05 deg         0.4 m    3.9 m   15.4 m   61.6 m   385 m
#     0.10 deg         0.9 m    7.7 m   30.8 m  123.3 m   771 m
#     0.30 deg         2.6 m   23.1 m   92.5 m  369.8 m  2311 m
#
# A SECOND IMU DOES NOT HELP THIS. Averaging two units improves white NOISE by root-2 and
# does nothing for bias or for tilt error, which is what the table is made of. Redundancy
# protects against an IMU failing, not against physics.
#
# So the honest statement is: with SoOP alive, no flow is needed. With SoOP gone, nothing
# on this aircraft holds position - and flow would not have held it either. Measured:
# the flow_only scenario reports p95 446 m, because flow is a VELOCITY aid. What it buys
# is turning quadratic drift into roughly linear drift during a SoOP outage; what it does
# NOT buy is a position source.
#
# WHY DEFERRING IS ACCEPTABLE:
#   * the dead-reckon applet's response to SoOP loss is to fly HOME immediately, not to
#     hold position, so the unaided window is tens of seconds, not minutes;
#   * first flights are on real GPS anyway - you do not commission a GNSS-denied
#     navigation system by first flying it GNSS-denied;
#   * the board is unaffected: flow arrives as MAVLink OPTICAL_FLOW (FLOW_TYPE 5), so
#     fitting it later is a companion-software change and nothing else.
#
# WHAT IS GIVEN UP, stated plainly: without flow the aircraft has no independent opinion
# about its own motion. If the SoOP solution is confidently wrong, nothing contradicts it.
# The sweep in sitl/ measured exactly that failure - soop_gpsinput diverged on 1 seed of
# 6 and soop_dropout on 3 of 6 - so this is a measured exposure, not a hypothetical one.
#
# NO PARAMETER CHANGE IS NEEDED OR WANTED. defaults.parm ships FLOW_TYPE 5 and that is
# correct with no camera fitted: the arming check tests the PARAMETER, not sensor health,
# so it arms fine, and it is ready the moment a flow source appears. Setting FLOW_TYPE 0
# while EK3_SRC2_VELXY / EK3_SRC3_VELXY are 5 is what GROUNDS the aircraft. See the
# matched-set rule in defaults.parm.
FLOW = dict(
    fitted=False,
    camera="OV9281 global shutter, 22-pin CSI - NOT ordered in this pass",
    arrives_as="MAVLink OPTICAL_FLOW from the companion, FLOW_TYPE 5",
    onboard_fallback="U6 PMW3901 is on the board but DNP - the ESC blocks its view, and "
                     "correlation sensors of that class fail over grass",
    operational_note="EK3_SRC2 and EK3_SRC3 both use VELXY 5 (flow). With no flow fitted "
                     "they have no data, and they are reachable ONLY by the pilot's RC9 "
                     "source-set switch. Do not select source set 2 or 3 in flight until "
                     "a flow source is fitted.",
    src="[M] drift table computed from a = g*sin(theta); [M] flow_only p95 446 m in sitl/")

# THE CAMERA INTERFACE, AND THE WORK IT STILL NEEDS.
#
# This is the one open item on the navigation-critical path, recorded here rather than in
# a document because this is where the decision is encoded.
#
# The OV9281 driver EXISTS in the Radxa kernel source but is not enabled in the shipped
# config, and there is NO official device-tree overlay for it. Checked directly against
# github.com/radxa/overlays (2026-09-02): the only Zero 3 camera overlays are
# radxa-zero3-rpi-camera-v1.3 (OV5647) and radxa-zero3-rpi-camera-v2 (IMX219), and BOTH
# ARE ROLLING SHUTTER - unusable for flow on a vibrating airframe, so neither is a
# fallback. Radxa forum thread 26386 documents a working build:
#
#   1. enable the OV9281 driver in the kernel config and rebuild with the BSP tool;
#   2. write a DT overlay based on the existing rpi-camera overlay;
#   3. set  pwdn-gpios = <&gpio3 RK_PC6 GPIO_ACTIVE_HIGH>;
#      without which the sensor fails I2C probe with -EIO (-5).
#
# THE SCHEMATIC CORROBORATES STEP 3 rather than leaving it as forum folklore: in
# radxa_zero_3w_v1.12_schematic.pdf, CSI connector J7 pin 18 is CAMERAB_PDN_L, and the
# VCCIO6 domain table maps CAMERAB_PDN_L to GPIO3_C6. RK_PC6 on gpio3 is that pin.
#
# ONE THING TO WATCH: the net is named CAMERAB_PDN_L - the _L suffix means active LOW -
# while the working overlay declares GPIO_ACTIVE_HIGH. That inversion is the most likely
# cause if the sensor probes with -EIO despite the overlay, so try the other polarity
# before assuming the wiring is wrong.
#
# J7 also carries: pin 19 CIF_CLKOUT (sensor master clock), pins 21/22 I2C2_SCL_M1 /
# I2C2_SDA_M1 (the control bus the -EIO happens on), and VCC_3V3.
CAMERA_IFACE = dict(
    connector="J7 FPC-22P-0.5mm, 4-lane MIPI CSI",
    pwdn_gpio="gpio3 RK_PC6 (CAMERAB_PDN_L, J7 pin 18)",
    i2c="I2C2_M1 on J7 pins 21/22",
    status="NOT WORKING OUT OF THE BOX - needs a kernel rebuild and a custom DT overlay",
    # NOT BLOCKING ANY MORE. Flow is deferred (see FLOW above), so the camera is not on
    # the critical path for first flight and this kernel work can happen at leisure - or
    # never, if a Pi Zero 2 W restocks and the companion changes back. It is kept
    # documented rather than dropped because the Radxa was chosen PRECISELY to keep this
    # door open: it is the cheapest board here that has the connector at all.
    blocking=False,
    src="[D] radxa_zero_3w_v1.12_schematic.pdf; [L] radxa forum thread 26386; "
        "[D] github.com/radxa/overlays has no ov9281 overlay, checked 2026-09-02")

# REJECTED companions, kept so the questions are not reopened from scratch.
PI_REJECTED = [
    dict(name="Orange Pi Zero 2W", price_gbp=25.0,
         why="NO MIPI CSI CONNECTOR AT ALL. The 24-pin 'function' connector sitting where "
             "the Pi Zero's CSI socket would be carries 100M Ethernet, 2x USB 2.0, "
             "TV-out, audio, IR and button lines - no CSI lanes. Confirmed from the "
             "vendor's OWN 176-page user manual, which documents USB (UVC) cameras only "
             "and contains no occurrence of 'CSI' or 'MIPI camera' anywhere. A USB UVC "
             "global-shutter module would work with no driver effort, but costs about "
             "GBP 45 against GBP 25 for the CSI part and adds USB 2.0 latency.",
         src="[D] OrangePi_Zero2w_H618_User-Manual_v1.1.pdf, searched in full"),
    dict(name="Raspberry Pi Zero 2 W", price_gbp=14.40,
         why="DEFERRED, NOT REJECTED - the zero-risk camera path, and the cheapest, but "
             "sold out at The Pi Hut and Pimoroni with the open market at GBP 70. Shares "
             "the 65 x 30 mm envelope AND the 22-pin CSI connector with the Radxa, so "
             "switching back later costs only software. Holes 58.0 x 23.0 mm per "
             "Raspberry Pi mechanical drawing RP-008358-DS-1.",
         src="[L] thepihut.com GBP 14.40 / pimoroni GBP 12.00, both out of stock "
             "2026-09-02; [D] RP-008358-DS-1"),
]


# What sits below the board in the assembled stack, as (name, top_mm, half_L, half_W)
# measured from the board's underside downward and from the board centre outward. The
# ESC is concentric with this board: both bolt to the same 30.5 mm pattern.
#
# The SpeedyBee BLS 60A is a solid 4-in-1 with no central aperture and the Source One's
# bottom plate is solid carbon, so there is nothing for a downward sensor to see through.
STACK_BELOW = [
    ("SpeedyBee BLS 60A ESC", 3.0, 45.6 / 2, 44.0 / 2,
     "[D] SpeedyBee manual + [A] 3.0 mm compressed grommet gap"),
]


# ---- off-board parts, and the interface each one lands on ---------------------------
#
# tools/check_purchase.py asserts these. They exist because the verification apparatus was
# lopsided: it gated the PCB with 63 checks and the ~GBP 425 of parts that bolt to it with
# almost nothing. Every entry here is an interface between two SEPARATELY BOUGHT things,
# which is the only class of error that cannot be fixed in software after the money moves.
#
# THE TFS20-L VARIANT. Benewake sell it in I2C and UART flavours and the listings do not
# always make the difference obvious. The I2C part works on J3 at 0x10.
#
# THIS BLOCK USED TO SAY the UART part was unusable "because SERIAL6 (UART4) exists in the
# hwdef but is ROUTED TO NO PAD on this board". THAT WAS FALSE, and docs/PINMAP.md said so
# all along - lines 36-37 document PB8/PB9 as "UART4 - TFmini-S rangefinder JST-GH port",
# unchanged between the default and SoOP configs. The board carries the pads: P71 (+5V), P72 UART4_TX
# (PB9), P73 UART4_RX (PB8), P74 (GND) - the old J7 "RF" group, all fitted.
#
# So EITHER variant is wired-in-able. The I2C part is still the one to buy, but for a
# better reason: it lands on J3 alongside the GPS with no extra port, and it leaves
# SERIAL6 free. Two files disagreeing about a pad is how a purchase gets decided wrongly.
OFFBOARD = dict(
    gps=dict(part="M10 + QMC5883L", conn="JST-GH 6P on J3",
             pinout=["5V", "USART2_TX", "USART2_RX", "I2C1_SCL", "I2C1_SDA", "GND"],
             note="this is the standard ArduPilot GPS order, so a stock M10 cable mates "
                  "pin-for-pin. Verify against the netlist, not against memory.",
             src="[M] design.py nets: J3.2/3 USART2, J3.4/5 I2C1, J3.6-8 GND"),
    rangefinder_down=dict(part="Benewake TFS20-L", variant="I2C", addr=0x10,
                          lands_on="J9 (dedicated I2C port)", vcc="3.3 V",
                          wrong_variant_note="the UART variant needs SERIAL6 (UART4). "
                                             "That IS routed - P71/P72/P73/P74, the old J7 "
                                             "'RF' group - so it would work. Buy I2C anyway: "
                                             "it plugs straight into J9 and leaves SERIAL6 free",
                          src="[D] AP_RangeFinder Benewake TFS20L driver, I2C 0x10"),
    rangefinder_up=dict(part="VL53L1X module (GY-53-L1X)", addr=0x29,
                        lands_on="J9 (dedicated I2C port)", vcc="3.3 V",
                        free_because="U7 is deleted - the on-board VL53L1X would "
                                     "otherwise own 0x29 and collide",
                        src="[D] VL53L1X fixed default address 0x29"),
    buzzer=dict(part="5V PASSIVE piezo", lands_on="PZ1 / PZ2", drive="PA15 TIM2_CH1 ALARM",
                must_be="passive",
                note="a TIMER channel means ArduPilot generates the tone patterns, so an "
                     "ACTIVE buzzer (own oscillator) loses every arming/failsafe pattern",
                src="[M] hwdef.dat: PA15 TIM2_CH1 TIM2 GPIO(32) ALARM"),
    led=dict(part="WS2812B strip", lands_on="PL1-PL3", volts=5,
             note="the on-board 74LVC1G17 outputs 5 V logic - a 12 V strip (WS2815) will "
                  "not light",
             src="[M] design.py: U17 drives WS2812_OUT at 5 V into PL1"),
    # THE GROUND STATION IS THE RADIO. ELRS >=3.5 carries MAVLink over the RC link, so one
    # radio and ONE UART give both RC control and full bidirectional telemetry - parameter
    # editing and mission planning in Mission Planner or QGroundControl, over LoRa, with
    # better range than a SiK pair. No separate telemetry radio, no second UART, no cost.
    #
    # THE TRAP: MAVLink mode requires an ESP-BASED receiver. STM32-based ELRS receivers
    # CANNOT do it, and plenty of cheap ones are STM32. This is a purchase-time fit
    # constraint with no software fix - the wrong receiver simply cannot carry telemetry.
    rx=dict(part="ELRS 2.4 GHz receiver - MUST BE ESP-BASED", lands_on="J5 (USART6)",
            mcu="ESP", min_fw="3.5.0",
            gcs_note="ELRS MAVLink needs SERIAL7_PROTOCOL 2, SERIAL7_BAUD 460, "
                     "RSSI_TYPE 5, and all SRx_ streams 1 except ADSB/PARAMS/RAW_CTRL. "
                     "RC then rides inside the MAVLink stream and gets ~1/4 of the "
                     "uplink slots, so RC rate is lower than plain CRSF - fine for a "
                     "cruiser, wrong for racing",
            src="[D] expresslrs.org/software/mavlink: ESP-based TX and RX only, "
                "firmware >=3.5.0, TX backpack >=1.5.0; STM32 devices cannot support "
                "MAVLink mode",
            note="solder pads, not a connector - no mating risk. In ELRS MAVLink mode "
                 "this ONE link carries both RC and full GCS telemetry, so no separate "
                 "telemetry radio and no second UART are needed"),
    # Replaces the 8-sensor ToF ring. PRX1_TYPE 16 is a PROTOCOL driver, so any LDROBOT
    # model in the family works - but the models differ enormously in ambient light
    # rating, and outdoors that is the spec that decides whether it is useful or actively
    # harmful. A lidar that hallucinates obstacles makes AC_Avoid brake for nothing.
    # LD06, chosen for INDOOR use - and the light rating is why the part changed.
    #
    # This was an STL-19P at $45 on a flat "buy >= 60 klux" rule. That rule is an OUTDOOR
    # one: full sun is ~100 klux, and the plain LD06 is rated 25 klux, so outdoors it
    # produces phantom obstacles and AC_Avoid brakes for nothing (an unresolved ArduPilot
    # Discourse thread). Applying it to a sensor whose job is INDOOR was wrong: room            # lighting is 300-500 lux, so 25 klux has ~50x of margin. The LD06 is
            # GBP 13.99 as the bare unit in the Okdo Lidar Hat kit (2026-09-05), which
            # makes the value case decisive for indoor work.
    #
    # The rule is therefore conditional on where it flies, not absolute. If this lidar is
    # ever taken outdoors, it must be swapped for a 60 klux part (LD19 / STL-19P /
    # STL-06P) or an 80 klux LD14P - same PRX1_TYPE 16 driver, so it is a purchase, not a
    # rework. check_purchase.py asserts the indoor-only condition.
    lidar=dict(part="LDROBOT LD06 - 12 m, 25 klux, INDOOR USE ONLY",
               lands_on="SERIAL2 (USART1) - the lidar's TX to TP6 (USART1_RX)",
               wires="TX only; PWM unconnected - the unit self-spins at a default rate",
               # MECHANICAL/ELECTRICAL from the LDROBOT LD06 datasheet, read 2026-09-04.
               # Previously absent or assumed: MODULES carried a guessed 250 mA, and the
               # real figures are 180 mA running with a 300 mA START-UP surge - the surge
               # matters more than the running current on a rail whose headroom is
               # 653 mA (see RAIL_5V - it was 413 before the WS2812 correction).
               L_mm=38.59, W_mm=38.59, H_mm=33.30, g=42.0,
               ma_run=180, ma_startup=300, volts=5.0, conn_on_lidar="ZH1.5T-4P",
               # Full [D] spec table, LDROBOT LD06 datasheet:
               range_m=(0.02, 12.0),          # 20 mm BLIND ZONE - nothing closer reads
               accuracy_mm=(30, 45),          # typical, max at 70 % target reflectivity
               resolution_mm=15,
               scan_hz=(5, 10, 13),           # min, typical, max - PWM-controlled
               sample_hz=4500,
               angular_res_deg=1.0, angular_err_deg=2.0,
               # STILL UNMEASURED: the height of the optical window above the mounting
               # base. The datasheet gives it only as a DRAWING (section 3, "Optical
               # Windows and Mechanical Dimensions"), which carries no extractable text.
               # It decides where the printed bracket may grip the body without blinding
               # the sensor, so it is on the arrival-measurement list, not assumed here.
               scan_plane_height_mm=None,
    # The RESOLVED price, as a field rather than a sentence buried in src. It was only
    # ever prose here, so MODULES["lidar_360"] carried its own gbp=100 - the retracted
    # figure - and docs/MODULES.md is generated from that. A number that decides a
    # purchase should be readable by the code that publishes it.
    gbp=13.99,
    # Position on the belly, mm aft of centre (negative = aft). Was a bare "-22" in
    # gen_scad_frame.py. It is load-bearing: it is the only thing keeping the LD06 clear
    # of the downward rangefinder at y = +18, and check_cad_fit reports that pair's
    # clearance, so the number that decides it belongs in the airframe definition.
    mount_y_mm=-22.0,     # [A] MEASURE ON ARRIVAL - see docs/BUILD.md
               # Power comes off the SERIAL6 pad group's 5V/GND pins. That does NOT claim
               # SERIAL6 - P72/P73, the UART pair, stay free.
               wiring={"TX": "TP6 (USART1_RX)", "5V": "P71", "GND": "P74"},
               params={"SERIAL2_PROTOCOL": 11, "SERIAL2_BAUD": 230, "PRX1_TYPE": 16,
                       "PRX1_ORIENT": 1, "BRD_SER2_RTSCTS": 0},
               orient_note="PRX1_ORIENT 1 = upside-down underneath, which is how this "
                           "airframe carries it - a top mount is blocked by the battery. "
                           "Arrow points FORWARD. ArduPilot warns the scan plane must be "
                           "unobstructed by legs, masts or the airframe, which is the "
                           "binding constraint here.",
               baud={"LD06/LD19/STL": 230400, "LD14P": 115200},
               indoor_only=True, klux=25, indoor_lux=(300, 500),
               outdoor_swap="LD19 / STL-19P / STL-06P (60 klux) or LD14P (80 klux, "
                            "115200 baud) - same driver, drop-in",
               buying_check="confirm the bundle contains the LIDAR UNIT, not a cable or "
                            "adapter board, and that it is LDROBOT protocol - a look-alike "
                            "clone is a Lua-driver project, not a purchase",
               src="[D] AP_Proximity_LD06.cpp: 47-byte frame, 0x54 start, CRC8 0x4D; "
                   "[D] ArduPilot LD06 wiring page: TX only, PWM unconnected, self-spins; "
                   "[L] klux ratings from LDROBOT and the kaiaai 2D-lidar survey; "
                   "[L] PRICE RESOLVED 2026-09-05: GBP 13.99 (eBay item 395159855374, "
                   "Okdo Lidar Hat Development Kit, >1000 sold) for the genuine LD06 as "
                   "a separate module + bracket + Pi HAT - use the UNIT ONLY, leave the "
                   "HAT off the aircraft. This overturns the earlier ~$99-131 "
                   "DO-NOT-BUY verdict; the value case now holds for indoor and "
                   "deliberate-slow work. PHYSICS UNCHANGED: 12 m at 10 Hz still only "
                   "protects to ~5 m/s, never a 15-20 m/s cruise, and 25 klux still "
                   "bans outdoor flight (LD19/STL-19P remains the outdoor swap); "
                   "[D] 38.59 x 38.59 x 33.30 mm, 42 g, 180 mA run / 300 mA start, "
                   "ZH1.5T-4P - LDROBOT LD06 datasheet 2026-09-04"),
    esc=dict(part="SpeedyBee BLS 60A", conn="JST-SH 8P on J2",
             note="J2 follows Betaflight's documented SpeedyBee F405 V4 order, but the "
                  "cable you receive must be buzzed before VBAT - this is the one "
                  "interface that genuinely cannot be desk-verified",
             src="[D] SpeedyBee manual + [M] design.py nets"),
    src="[M] every 'lands_on' traced to design.py nets")

# ---- payload provisions: what a FUTURE module can actually have ---------------------
#
# "Reasonably modular" is worth nothing as an assertion, so this declares the spare
# resources explicitly and tools/check_payload.py asserts they are still spare. The point
# is to catch the day someone quietly consumes the last free PWM channel or UART for
# something else, which is exactly how a board stops being extensible without anyone
# deciding that it should.
#
# This is deliberately about what is UNCOMMITTED, not about any particular payload. A
# gimbal, a dropper/winch, a parachute or a deployable arm all want the same things: one
# or two actuator channels, a power tap that is not the flight controller's own rail, and
# ideally a serial link for feedback.
PAYLOAD = dict(
    pwm=[("PWM5", "PA2", "TP3", "SERVO5_FUNCTION"),
         ("PWM6", "PA3", "TP4", "SERVO6_FUNCTION")],
    # SERIAL_ORDER is OTG1 UART7 USART1 USART2 USART3 UART8 UART4 USART6 OTG2, so
    # index 2 is USART1 (TP5/TP6) and index 6 is UART4 (P71-P74).
    #
    # THERE ARE TWO FREE ROUTED UARTS, NOT ONE. This block claimed SERIAL6 was "NOT routed
    # to a pad - unreachable with a soldering iron". It is routed: P71 (+5V), P72 UART4_TX
    # (PB9), P73 UART4_RX (PB8), P74 (GND) - the old J7 "RF" pad group, all fitted.
    # docs/PINMAP.md lines 36-37 have documented it as a rangefinder port the whole time.
    # The two files disagreed and this one was wrong; it also gave the wrong reason for
    # the TFS20-L variant choice above.
    #
    # SERIAL4 (USART3) genuinely IS unrouted - PD8/PD9 stop at the MCU with no pad.
    #
    # So the 360 lidar takes SERIAL2 and SERIAL6 stays free - for a rangefinder, or for a
    # future optical-flow source, which is what makes adding flow later a no-conflict job.
    #
    # SETTLED 2026-09-04: SERIAL6 is the GENERAL-PURPOSE EXPANSION UART. Unclaimed.
    #
    # This was contradictory for a long time - docs/SENSORS.md called P71-P74 "earmarked
    # for the SoOP receiver" while docs/PINMAP.md called the same PB8/PB9 a RANGEFINDER
    # port. The contradiction dissolved once the module map was written out: NEITHER
    # claimant actually wants this port.
    #
    #   - the SoOP tuner is an ANALOGUE interface - I/Q into PC4/PA4, RSSI on PC5, PPS
    #     on PE10, landing on TP9/TP10/TP11/P44. It needs no UART at all. The RF_* net
    #     names are a fossil of an earlier architecture in which the receiver was a smart
    #     serial module, and that architecture is gone.
    #   - the chosen rangefinder is the TFS20-L *I2C* variant, which lands on J3.4/J3.5.
    #
    # So the port is free, and the honest label is "expansion", not either earmark. The
    # strongest future claimants are a UART optical-flow module or a serial rangefinder
    # variant - see docs/MODULES.md.
    #
    # The RF_* NET NAMES are deliberately NOT renamed: they appear nowhere on silkscreen
    # (verified 2026-09-04 - they are net names only), so the fossil is invisible on the
    # physical board, and renaming nets in the artwork days before a fabrication order
    # buys nothing and risks a diff nobody reviews.
    serial=[(2, "USART1", "J11 (TP5 / TP6 remain as probes)", "EARMARKED for the 360 lidar "
                                       "(PRX1_TYPE 16); free only until that is fitted"),
            (6, "UART4", "P71 / P72 / P73 / P74", "EXPANSION UART - unclaimed in "
                                                  "defaults.parm, but EARMARKED since "
                                                  "2026-09-14 for the companion computer "
                                                  "(MAVLink OPTICAL_FLOW), which moved here "
                                                  "when J4 was cut in the re-layout. A "
                                                  "payload and the companion cannot both "
                                                  "have it. The RF_* net names are "
                                                  "vestigial, not a second earmark")],
    # DERIVED AND CROSS-CHECKED. check_payload.py works this list out from SERIAL_ORDER
    # and the netlist and fails if this declaration disagrees, because as a hand-written
    # list it was wrong: it named only USART3 while UART7 had lost every pad when J4 was
    # cut, and UART8 has no nets in design.py at all. Two of the three were missing.
    serial_unrouted=[(1, "UART7"),    # PE8/PE7/PE9 stop at the MCU - J4 was cut, and
                                      # the companion moved to SERIAL6 on P71-P74
                     (4, "USART3"),   # PD8/PD9 stop at the MCU
                     (5, "UART8")],   # declared in hwdef, no nets in the design at all
    serial_earmarked=[(2, "360 lidar, PRX1_TYPE 16"),
                      (6, "companion computer, MAVLink OPTICAL_FLOW - moved from "
                          "SERIAL1 on 2026-09-14 when J4 was cut")],
    power_5v=["P71", "P61", "PL2", "P41", "J5.1", "J9.1", "J11.1"],
    gnd=["P74", "P64", "PL3", "P46", "J5.4", "J9.4", "J11.4"],
    # A servo drawing real current must NOT come off the flight controller's 5 V rail.
    # check_build reports 0.95 A of a 2.0 A regulator with everything fitted (L2's
    # 1.6 A Irms governs); a stalled hobby servo alone can pull more than the margin.
    power_note="signal is 3.3 V logic, which every hobby servo and ESC accepts as a valid "
               "PWM high. Take a high-current servo's 5 V from its own BEC, not from this "
               "board - the rail has only 0.65 A of headroom and a stalled servo eats it",
    mass_budget_g=885.0,   # payload at 40% hover throttle, from check_build
    src="[D] hwdef.dat PWM/SERIAL_ORDER + [M] defaults.parm claims + [M] check_build "
        "power and payload figures")

# ---- the airframe, one source of truth --------------------------------------------
# These lived in check_build.py while cad/drone.scad carried its OWN copies, and the two
# disagreed on four numbers: wheelbase 295 vs 300, arm thickness 6.0 vs 4.0, plate 3.0 vs
# 2.0 and inner height 35 vs 32. Same defect as BOT_PARTS - a quantity written down twice
# drifts, and the copy you happen to read decides the answer.
#
# cad/frame.scad is GENERATED from this by tools/gen_scad_frame.py, so the model and the
# checks cannot diverge again.

# TBS SOURCE ONE V5 7" DC - and the reason for it is the PROVENANCE, not the geometry.
#
# The Mark4 this replaced was specified from THREE RESELLER SPEC TABLES that disagreed
# with each other and with the AliExpress listing it started from. GEPRC's own product
# and download pages 404, so no manufacturer drawing was ever obtainable, and the honest
# consequence was a row of "MEASURE ON ARRIVAL" items - including the standoff spacing,
# which decides whether this board physically fits.
#
# TBS Source One is OPEN SOURCE HARDWARE. The frame's own DXF and DWG are published at
# github.com/tbs-trappy/source_one (So1-V6-7inDC-2025-JUL-07.dxf, 69 MB of real
# geometry). Every dimension is answerable BEFORE ordering, in CAD, instead of with
# calipers afterwards.
#
# VERIFIED HERE, not taken from the listing: the DXF was downloaded and its CIRCLE
# entities parsed on 2026-09-02. Square hole patterns of 30.50 mm and 20.00 mm are
# present, which is the stack mounting this board needs. That is an independent check of
# the retailer's claim against the manufacturer's own file.
#
# WHAT THE CHANGE BUYS, all of it measured rather than argued:
#
#   standoffs 30 mm (was 25)  -> the 22.3 mm stack has 7.7 mm spare, not 2.7 mm
#   arm 6.0 mm  (was 5.0)     -> motor screw needs 13.5 mm, which rounds to M3x14 at
#                                4.5 mm into the boss instead of 5.5 mm. The over-
#                                engagement warning nearly disappears.
#   wheelbase 320 (was 295)   -> prop gap +48.5 mm instead of +30.8 mm
#
# Costs GBP 35.90 against 17.97, and 143.5 g against 121 g. Both are worth it: the
# 22.5 g is 2% of AUW, and the 18 pounds buys the difference between a specification and
# a measurement.
#
# STANDOFF LENGTH IS NOT A FRAME CONSTRAINT, and treating it as one was an error in the
# document this replaces. M3 standoffs are a separate few-pound purchase in any length -
# 25, 30, 35, 40 mm. If the kit's are wrong, buy others. What IS frame-fixed is the plate
# geometry: the centre-plate opening and where the standoffs sit relative to this
# 45.1 x 46.1 mm board. That is the number the open CAD settles and the Mark4 could not.
#
# LANDING GEAR: the repo publishes SO1-V6-skate.stl (76.0 x 102.2 x 6.0 mm), so the skids
# are a real model rather than the [A] placeholder they were. Camera, GoPro, antenna and
# SMA mounts are published too. All fit an Ultimaker 2+ (223 x 223 x 205 mm).
FRAME = dict(name='TBS Source One V5 7in DC', wb=320.0, size=(200.0, 230.0),
             inner_h=30.0,
             bottom_t=2.5, medium_t=2.0, upper_t=2.0, arm_t=6.0, cam_plate_t=2.0,
             stack="30.5x30.5 M3 and 20x20 - VERIFIED from the manufacturer DXF",
             motor_holes="16x16 / 19x19",
             strap=(20.0, 300.0), price_gbp=35.90, g=143.5,
             src="[D] github.com/tbs-trappy/source_one So1-V6-7inDC-2025-JUL-07.dxf, "
                 "stack patterns parsed directly 2026-09-02; [L] hobbyrc.co.uk for "
                 "standoffs 30/22 mm, plates and 143.5 g; [A] plate outline 200x230 mm "
                 "- overall footprint only, not load-bearing on any check")

# THE FIT QUESTION, ANSWERED FROM THE DXF - not deferred to calipers.
#
# This was listed for a while as "open the board outline in the CAD and look", which was
# a cop-out: the file is right there and the geometry is extractable. Method, so it can be
# repeated or disputed: parse every CIRCLE and LWPOLYLINE out of
# So1-V6-7inDC-2025-JUL-07.dxf; find the 30.5 mm square of 3.00 mm holes; take the
# SMALLEST closed polygon containing its centre (a nested manufacturing DXF lays every
# plate out side by side, so the smallest containing outline is the part itself, not the
# sheet); then list only the circles inside that polygon.
#
# RESULT - the FC-mounting plate is 48.50 x 106.59 mm and the stack pattern is centred
# across its width, 24.3 mm from one long edge and 24.2 mm from the other:
#
#   board half-width  22.55 mm  vs plate half-width 24.25 mm  ->  1.70 mm clear per side
#   board half-length 23.05 mm  vs 24.09 mm to the nearer end ->  1.04 mm clear
#
# Features under the board are all THROUGH-HOLES, not posts: a 10.00 mm centre
# pass-through at the stack centre, and two 4.00 mm holes at (+/-7.95, -19.76). Nothing
# stands proud. The M3 holes that could carry standoffs are at |y| >= 27.90 mm, i.e.
# 4.85 mm beyond the board's own half-length, so they clear it.
#
# HONEST LIMITS OF THIS: a nested DXF gives each plate's shape, not the ASSEMBLY. It
# proves the board fits the plate it bolts to and that nothing on that plate fouls it. It
# does not prove that a standoff on a DIFFERENT plate clears the board's connectors - for
# that the 1.04 mm end margin is the number to watch, and it assumes the board is centred
# on the stack pattern.
# THE PLATES ARE PARSED. An earlier note here said they could not be - that was wrong,
# and the mistake is worth recording: I found the DXF full of 3DSOLID/ACIS entities,
# knew OpenCASCADE cannot read ACIS, and concluded the geometry was unreachable. It was
# reachable two ways I had not tried: ezdxf.acis parses ACIS directly, and more simply
# the PLATES ARE 2D POLYLINES all along - my first parser just could not see them
# because it compared block-local coordinates against top-level ones. Flattening INSERT
# transforms with ezdxf fixed it.
#
# METHOD CONFIRMED: the re-parse reproduces the previously known FC plate exactly - the
# 30.5 mm stack square at (+/-15.25, +13.91)/(+44.41), the 20x20 at (+/-10.00), the
# 10.00 mm centre pass-through, and the two 4.00 mm holes at (+/-8.00, -19.75) from the
# stack centre. Matching a known answer to two decimals is why the rest is trusted.
#
# PLATE INVENTORY (all [M], flattened from So1-V6-7inDC-2025-JUL-07.dxf, 2026-09-04):
#
#   48.50 x 106.59   FC / MID plate - carries BOTH stack patterns and the centre hole
#   42.50 x 160.26   TOP plate    - 8 x M3 only, at x = +/-14.60 and +/-11.00
#   48.50 x 107.62   BOTTOM plate - 29 holes incl. 4.3 / 6.0 / 2.0 / 2.2 mm accessory sizes
#   31.08 x 185.21   arm (x4);  29.15 x 160.72 arm variant (x4)
#
# TOP vs BOTTOM is INFERRED, not labelled in the DXF: the 160.26 mm plate is the only one
# long enough to carry the 138 mm battery, and the 107.62 mm one carries the varied
# accessory holes a bottom plate needs. Confirm with calipers on arrival.
#
# WHAT THIS SETTLES - three questions that were blocked:
#
#   1. UPWARD ToF beside the battery?  NO. The top plate is 42.50 mm wide and the
#      battery is 47 mm, so the pack already OVERHANGS the plate by 2.25 mm each side.
#      There is no "beside". It goes on the battery strap, on a mast, or not at all.
#   2. COMPANION on the top plate?  DIMENSIONALLY YES - a Radxa Zero 3W is 65 x 30 mm and
#      the plate is 42.50 x 160.26, so 6.25 mm clear each side. It cannot share with the
#      battery, which is a placement conflict, not a size one. The retraction in
#      docs/SENSORS.md was right to withdraw the old claim: the reasoning was wrong even
#      though "it does not fit alongside the battery" happens to hold.
#   3. FC MOUNTED UNDER THE BOTTOM PLATE, component-side down, to give U6/U7 a view?
#      NO. The bottom plate carries only 4 x M3 at x = +/-14.60 and +/-11.00 - there is
#      NO 30.5 mm pattern anywhere but the FC plate. The board could not bolt there.
PLATES = dict(
    fc=(48.50, 106.59), top=(42.50, 160.26), bottom=(48.50, 107.62),
    arm=(31.08, 185.21),
    top_m3_x=(14.60, 11.00), bottom_m3_x=(14.60, 11.00),
    battery_overhang_per_side=(47.0 - 42.50) / 2,
    src="[M] ezdxf flatten of So1-V6-7inDC-2025-JUL-07.dxf, 2026-09-04; method validated "
        "by reproducing the known FC plate to 2 dp. [A] which plate is top vs bottom - "
        "inferred from length against the 138 mm battery; confirm with calipers")

FRAME_CAD = dict(
    fc_plate=(48.50, 106.59),
    stack_from_edges=(24.3, 24.2),
    clear_per_side_w=1.70,
    clear_end_l=1.04,
    under_board_holes=[(0.0, 0.0, 10.00), (7.95, -19.76, 4.00), (-7.95, -19.76, 4.00)],
    nearest_standoff_candidate_y=27.90,
    src="[M] parsed from So1-V6-7inDC-2025-JUL-07.dxf, 2026-09-02")
# Weight and bolt pattern are from BrotherHobby's own Avenger 2806.5 product data.
# THRUST IS STILL UNVERIFIED: no clean thrust table was found for 1300KV on 4S with a
# 7040, and the figures search returns are visibly mangled (one claimed 16.8 kg from a
# single motor). 1250 g is a conservative estimate for the class, and every payload
# number below inherits its uncertainty. Get the manufacturer's table before trusting
# the payload figures.
# shaft_thread is what the PROP screws onto, and it was missing from both dicts - so
# nothing in this project could have caught a prop with the wrong bore. It is the classic
# unrecoverable purchase error: the props arrive, and they do not go on the motors.
MOTOR = dict(name="2806.5 1300KV", kv=1300, g=41.0, thrust_g=1250, holes="19x19",
             shaft_thread="M5", poles="12N14P",
             # Body envelope, for the CAD. These lived as literals inside
             # tools/gen_scad_frame.py's output f-string, which meant the airframe
             # definition did not contain the size of its own motors and nothing here
             # could be checked against a datasheet. "2806.5" IS the stator, 28 mm
             # diameter x 6.5 mm tall, so dia is [D] by definition; the 15 mm bell
             # height is [A] and is the one to measure on arrival.
             dia_mm=28.0, h_mm=15.0,
             src="[D] 41 g, M3 19x19, M5 prop adapter thread, 12N14P "
                 "(BrotherHobby Avenger product data); [A] 1250 g thrust; "
                 "[D] 28 mm body from the 2806.5 stator designation, [A] 15 mm bell height")
BATT = dict(name="Zeee 4S 6500mAh", L=138, W=47, H=48, g=615, conn="EC5", hard=True,
            cells=4, src="[L] retailer listing")
# The ESC, the smoke stopper and the pigtails are all XT60. The pack is EC5. That is an
# adapter, not an incompatibility - but it has to be BOUGHT, and forgetting it grounds
# the aircraft on the day everything else arrives.
POWER_CONN = dict(airframe="XT60", pack=BATT["conn"], adapter_needed=True,
                  src="[L] Zeee hardcase packs ship EC5; [D] SpeedyBee BLS 60A is XT60")
# CONFIRMED 2026-09-03 against the manufacturer, not a marketplace listing. Gemfan
# publishes the Flash 7040-3 as: centre hole 5 mm, disc 178.43 mm, 7.9 g, PC.
#
# Two things changed as a result:
#   BORE is now [D]. 5 mm matches MOTOR["shaft_thread"] = "M5", which is BrotherHobby's
#   own figure - so the one interface that could have made four props unusable is
#   datasheet-to-datasheet, with no listing in between.
#   MASS was WRONG. 6.0 g was assumed; the real part is 7.9 g, so four props are 7.6 g
#   heavier than budgeted. Immaterial against an 885 g payload budget, but it was a
#   made-up number sitting in a mass total, which is how mass totals stop being true.
#
# dia_mm is Gemfan's measured 178.43, not the nominal 7 x 25.4 = 177.8. The larger
# figure is the conservative one for prop-gap clearance.
PROP = dict(name="7040", dia_mm=178.43, g=7.9, bore_mm=5.0, mount="M5",
            src="[D] Gemfan Flash 7040-3 published spec: 5 mm centre hole, 178.43 mm "
                "disc, 7.9 g, PC. Bore matches the [D] M5 motor shaft. A different "
                "brand of 7040 may differ in mass; the 5 mm bore is universal for 7in")


# ---- MASS, one source of truth ----------------------------------------------------
# This list lived inside tools/check_build.py, and design.PAYLOAD carried a HAND-COPIED
# mass_budget_g = 885.0 sourced to it. The copy went stale the moment the prop mass was
# corrected 6.0 -> 7.9 g on 2026-09-03: check_build derived 877 g from then on, while
# design.py, tools/check_payload.py and a hardcoded string in preflight.py all kept
# printing 885. Same defect as depth_available_mm above - a value that claims to be
# derived and is not - so it gets the same fix.
#
# TWO CORRECTIONS TO THE ITEMS THEMSELVES, both found by reading the list rather than
# the total:
#   - "ToF ring + mux, 25 g [A]" was still budgeted. That architecture is SUPERSEDED
#     (docs/SENSORS.md): the 8-sensor ring behind a TCA9548A was replaced by the LD06.
#   - The LD06 that replaced it was budgeted at NOTHING, despite being 42 g [D] from
#     the datasheet - heavier than the thing it replaced, and the single heaviest
#     optional module on the aircraft.
# So the budget was carrying a part that does not exist and omitting the one that does.
# The LD06 is budgeted on the same convention as the flow camera two lines below it:
# deferred, but counted, because a thrust margin that only holds until you fit the part
# you are planning to fit is not a margin.
MASS_ITEMS = [
    ("frame",                            FRAME["g"],      FRAME["src"]),
    ("4x motors",                        4 * MOTOR["g"],  MOTOR["src"]),
    ("ESC",                              ESC["g"],        ESC["src"]),
    ("this board",                       20,              "[A]"),
    ("4x props",                         4 * PROP["g"],   PROP["src"]),
    ("battery",                          BATT["g"],       BATT["src"]),
    ("GPS",                              15,              "[A]"),
    ("RX",                               3,               "[A]"),
    # PI["src"] is the DATASHEET source for the 65x30 mm outline and the 5V/2A rating.
    # The MASS is not published by Radxa and is an estimate, so this row carries its own
    # [A] tag - using PI["src"] here would have laundered an assumption into a [D] and
    # dropped it out of check_build's end-of-run "values with no source" list.
    (PI["name"],                         PI["g"],
     "[A] ~12 g, not published by Radxa - same 65x30 mm PCB class as a Pi Zero (11 g) "
     "with eMMC pads and a heavier SoC"),
    ("camera+cable (deferred, budgeted)", 10,             "[A]"),
    ("TFS20-L",                          1.4,             "[D]"),
    ("LD06 360 lidar (deferred, budgeted)", OFFBOARD["lidar"]["g"],
     "[D] LDROBOT LD06 datasheet - REPLACES the superseded 25 g ToF ring + mux"),
    ("skids",                            12,              "[A]"),
    ("wiring/straps",                    60,              "[A]"),
]
AUW_G    = sum(g for _n, g, _s in MASS_ITEMS)
THRUST_G = 4 * MOTOR["thrust_g"]

# Payload at 40% hover throttle - the conservative figure, and the one quoted everywhere.
# DERIVED now, so it cannot disagree with check_build again.
PAYLOAD["mass_budget_g"] = max(0.0, THRUST_G * 0.4 - AUW_G)


# ---------------------------------------------------------------------- nets
# Pins may be given by NUMBER or by NAME ("U1.PA5"); the resolver handles both.
NETS = {}
def net(name, *pins): NETS.setdefault(name, []).extend(pins)

# ---- power rails -------------------------------------------------------
net("GND",
    "U1.10","U1.26","U1.49","U1.74","U1.99","U1.19",           # VSS + VSSA
    "U2.6","U3.6","U4.3","U5.4",
    "U8.1","U9.2","U10.2","U11.2","U12.2",
    "J1.A1B12","J1.B1A12","J1.13","J1.14",
    "J2.1","J2.9","J2.10", "J3.6","J3.7","J3.8",
    "J5.4","J5.5","J5.6", "J6.4","J6.5","J6.6", "J7.4","J7.5","J7.6",
    "J8.6","J8.10","J8.11","J8.12","J8.13",
    "Y1.2","Y1.4", "D1.1",
    "C1.2","C2.2","C3.2","C4.2","C5.2","C6.2","C7.2","C8.2","C9.2",
    "C10.2","C11.2","C12.2","C13.2","C14.2","C15.2","C16.2",
    "C17.2","C18.2","C19.2","C22.2","C23.2",
    "C26.2","C27.2","C28.2","C29.2","C30.2","C31.2","C32.2","C33.2","C34.2",
    "C35.2","C36.2","C41.2","C42.2",
    "C43.2","C44.2","C45.2","C46.2",
    "R1.2","R5.2","R7.2","R14.2","R19.2","SW1.2","SW2.2","D2.2","D3.2",
    "U4.4","U4.5",                                              # CSB + internal -> GND = addr 0x77
    )
# The battery input is protected by Q4, a P-FET between the entry and the rail.
# VBAT_IN is the battery side (J2.2 and D1); VBAT is the protected rail downstream of
# Q4.source. ON Semi AND90146/D Fig. 4: drain to the battery, source to the load -
# the body diode conducts until the channel turns on, and a reversed pack reverse-
# biases the diode and leaves the rail dead.
net("VBAT_IN", "J2.2", "D1.2", "Q4.3")            # Q4 pin 3 = drain
net("VBAT", "Q4.2", "C17.1","C18.1","C19.1","U8.3","R4.1","R18.1")  # Q4 pin 2 = source
net("+5V",  "U8.2","C22.1","C23.1","U9.1","C26.1","U10.1","C28.1",
            "J3.1","J5.1","J6.1","J7.1","R6.1")
net("+3V3", "U9.5","C27.1","U1.11","U1.27","U1.50","U1.75","U1.100",
            "C1.1","C2.1","C3.1","C4.1","C5.1","C6.1","C7.1",
            "U5.8","C36.1",
            "U11.3","C41.1","J8.4","C45.1","C46.1","L1.1",
            "R9.1","R10.1","R11.1","R12.1","R20.1","R21.1",
            "R22.1","R23.1","R24.1","R25.1","R26.1","R27.1","SW1.1")
net("+3V3A","U10.5","C29.1","C30.1","U2.5","U2.8","C31.1","C32.1",
            "U3.5","U3.8","C33.1","C34.1","U4.1","U4.2","C35.1")   # U4.2=PS high -> I2C
net("VDDA", "L1.2","U1.21","U1.20","C10.1","C11.1","C12.1","C13.1")

# ---- MCU housekeeping --------------------------------------------------
net("VCAP1","U1.48","C8.1")
net("VCAP2","U1.73","C9.1")
net("NRST", "U1.14","C14.1","SW2.1")
net("BOOT0","U1.94","R1.1","SW1.1")
net("OSC_IN", "U1.PH0-OSC_IN","Y1.1","C15.1")
net("OSC_OUT","U1.PH1-OSC_OUT","Y1.3","C16.1")
net("VBAT_MCU","U1.6","+3V3_TIE")   # VBAT pin of MCU tied to +3V3 (no coin cell)
NETS["VBAT_MCU"] = ["U1.6"]; NETS["+3V3"].append("U1.6")
del NETS["VBAT_MCU"]

# ---- SWD ---------------------------------------------------------------
net("SWDIO","U1.PA13"); net("SWCLK","U1.PA14")

# ---- motors + battery sense (ESC connector) ----------------------------
net("M1","J2.3","U1.PB0"); net("M2","J2.4","U1.PB1")
net("M3","J2.5","U1.PA0"); net("M4","J2.6","U1.PA1")
net("BATT_V_DIV","R18.2","R19.1","C43.1","U1.PC0")
net("ESC_CUR","J2.7","C44.1","U1.PC1")
# ESC telemetry travels ESC -> FC, so it has to land on a RECEIVE pin. It was on
# U1.PE1 = UART8_TX, which cannot receive anything, while PE0 = UART8_RX sat 0.5 mm
# away wired to nothing. Moved on the routed board with tools/move_net_pin.py rather
# than by regenerating the PCB.
net("ESC_TEL","J2.8","U1.PE0")                                  # UART8_RX <- BLHeli_32/AM32 RPM

# ---- IMU1 (SPI1) -------------------------------------------------------
net("SPI1_SCK","U1.PA5","U2.13"); net("SPI1_MISO","U1.PA6","U2.1")
net("SPI1_MOSI","U1.PD7","U2.14"); net("IMU1_CS","U1.PC15","U2.12")
# ---- IMU2 (SPI4) -------------------------------------------------------
net("SPI4_SCK","U1.PE12","U3.13"); net("SPI4_MISO","U1.PE13","U3.1")
net("SPI4_MOSI","U1.PE14","U3.14"); net("IMU2_CS","U1.PE11","U3.12")
net("IMU3_CS","U1.PC13")                                        # hwdef-declared, unpopulated
# ---- SPI3: flow + flash ------------------------------------------------
net("SPI3_SCK","U1.PB3","U5.6"); net("SPI3_MISO","U1.PB4","U5.2")
net("SPI3_MOSI","U1.PB5","U5.5")
# EXT_CS1 (PD4) was deleted along with U6 - SPI3 now carries one device,
# the W25Q128 flash on EXT_CS2 (PE2). PD4 is freed for a future SPI3 peripheral.
net("EXT_CS2","U1.PE2","U5.1")
net("FLASH_WP","U5.7","+3V3_T2"); NETS["FLASH_WP"]=["U5.7"]; NETS["+3V3"].append("U5.7")
net("FLASH_HOLD","U5.3"); NETS["+3V3"].append("U5.3"); del NETS["FLASH_HOLD"]
del NETS["FLASH_WP"]
# ---- I2C ---------------------------------------------------------------
# I2C1 reaches the outside on J3 (the GPS port, I2C-by-standard per DS-009) AND on
# the dedicated 4-pin I2C port J9 - rangefinders no longer need a
# splitter into the GPS loom, which is what check_module_wiring reports as a splice.
# J9's pins are added in the Phase C block, NOT here: the RF-off block further down
# strips every 'J9.*' spec (the old U.FL antenna connector used that ref) and would
# silently delete the wiring otherwise.
net("I2C1_SCL","U1.PB6","R9.2","J3.4")
net("I2C1_SDA","U1.PB7","R10.2","J3.5")
net("I2C2_SCL","U1.PB10","R11.2","U4.8")
net("I2C2_SDA","U1.PB11","R12.2","U4.7")
# TOF_XSHUT (PD11) and TOF_INT (PD10) deleted with U7 - both pins freed.
# ---- UARTs -------------------------------------------------------------
net("USART2_TX","U1.PD5","J3.2"); net("USART2_RX","U1.PD6","J3.3")   # GPS1
net("UART7_TX","U1.PE8");  net("UART7_RX","U1.PE7")        # companion - NO LANDING:
net("PPS_SYNC","U1.PE10"); net("UART7_RTS","U1.PE9")        # J4 cut, and no free pad site
                                                                    # exists (board is full)
net("USART6_TX","U1.PC6","J5.2"); net("RC_IN","U1.PC7","J5.3")
net("UART4_TX","U1.PB9","J7.2");  net("UART4_RX","U1.PB8","J7.3")    # TFmini-S
# ---- CAN ---------------------------------------------------------------
net("CAN1_RX","U1.PD0","U11.4"); net("CAN1_TX","U1.PD1","U11.1")
net("CAN1_SILENT","U1.PD3","R14.1","U11.8")
net("CANH","U11.7","J6.2","R15.1"); net("CANL","U11.6","J6.3","R15.2")
# ---- USB ---------------------------------------------------------------
net("VBUS","J1.A4B9","J1.B4A9","U12.5","C42.1")
net("USB_DP_CON","J1.A6","J1.B6","U12.1"); net("USB_DM_CON","J1.A7","J1.B7","U12.3")
net("USB_DP","U12.6","U1.PA12"); net("USB_DM","U12.4","U1.PA11")
net("CC1","J1.A5","R16.1"); net("CC2","J1.B5","R17.1")
NETS["GND"] += ["R16.2","R17.2"]
# ---- microSD (SDMMC1) --------------------------------------------------
net("SD_D0","U1.PC8","J8.7","R22.2");  net("SD_D1","U1.PC9","J8.8","R23.2")
net("SD_D2","U1.PC10","J8.1","R24.2"); net("SD_D3","U1.PC11","J8.2","R25.2")
net("SD_CK","U1.PC12","J8.5");         net("SD_CMD","U1.PD2","J8.3","R26.2")
net("SD_CD","J8.9","R27.2")
# ---- LEDs / buzzer / WS2812 -------------------------------------------
net("LED0","U1.PE3","R20.2"); net("LED0_K","R20.2","D2.1")
NETS["LED0"]=["U1.PE3","R20.2"]; NETS["LED0_K"]=["R20.2","D2.1"]
net("LED1","U1.PE4","R21.2"); NETS["LED1_K"]=["R21.2","D3.1"]
net("BUZZER","U1.PA15"); net("WS2812","U1.PA8")
# ---- unpopulated MatekH743 features (kept defined so ERC is clean) -----
net("MAX7456_CS","U1.PB12")     # pull high, no OSD fitted
net("SPI2_SCK","U1.PB13"); net("SPI2_MISO","U1.PB14"); net("SPI2_MOSI","U1.PB15")
net("PWM5","U1.PA2"); net("PWM6","U1.PA3")
net("PWM7","U1.PD12"); net("PWM8","U1.PD13"); net("PWM9","U1.PD14"); net("PWM10","U1.PD15")
net("PWM11","U1.PE5"); net("PWM12","U1.PE6")
net("USART1_TX","U1.PA9"); net("USART1_RX","U1.PA10")
net("USART3_TX","U1.PD8"); net("USART3_RX","U1.PD9")
net("PE1_SPARE","U1.PE1")       # UART8_TX, unused: ESC telemetry is receive-only
net("PE15_SPARE","U1.PE15"); net("PB2_SPARE","U1.PB2")
net("PC2_SPARE","U1.PC2_C"); net("PC3_SPARE","U1.PC3_C")
# ---- SoOP analogue front end (SoOP config, DNP) ------------------------------
net("SOOP_I_ADC","U1.PC4","U14.1")
net("SOOP_Q_ADC","U1.PA4","U14.7")
net("SOOP_RSSI","U1.PC5","R30.2")
net("SPARE_ADC","U1.PA7")


# ---- RF front end (SoOP config, all DNP) -------------------------------------
# The antenna side arrives already amplified and filtered: J12 is a U.FL taking coax
# from the Nooelec SAWbird+ IR, which is the LNA and the 1620 MHz SAW in one shielded
# module sitting AT the antenna. So the board's own LNA/SAW chain (U15, U16, FL1, L3,
# L4 and their bias networks) is gone entirely - it was two amplifiers and a filter
# that could not be sourced, doing a job a bought part does better because noise figure
# is set before cable loss.
net("ANT_IN",   "J12.1","C52.1"); NETS["GND"] += ["J12.2"]
net("RFIN",     "C52.2","U13.4")
NETS["GND"] += ["U13.3","U13.10","U13.11","U13.29"]
net("VCC_RF",   "U13.1","U13.2","U13.6","U13.7","U13.13","U13.16","U13.25",
                "C49.1","C50.1","C51.1","R28.2")
# VCC_RF IS FED FROM +3V3A, NOT +3V3, and the reason is measured rather than stylistic.
# The MAX2112 draws 100 mA. On +3V3 that takes U9 (AP2112K) from 445 mA to 545 mA of
# its 600 mA guaranteed output - 91% - on the rail whose junction temperature is
# ALREADY the board's worst warning (179 C on the datasheet's no-heatsink figure).
# U10 (TLV75533, 500 mA) carries 3 mA today, so the same load lands at ~21% and about
# 175 mW of dissipation. It is also the RF-correct rail: a low-noise LDO feeding an
# analogue part, with R28 as the per-block isolation and C49/C50/C51 local to the pins.
#
# The cost is that 100 mA now shares a regulator with the IMUs and the barometer. The
# TLV75533's PSRR and the tuner's near-constant draw should make that a non-issue, but
# "should" is not a measurement: check IMU noise with the tuner powered at bench T3.
NETS["+3V3A"] += ["R28.1"]; NETS["GND"] += ["C49.2","C50.2","C51.2"]
# Y2 IS AN ACTIVE OSCILLATOR AND WAS WIRED AS A PASSIVE CRYSTAL. The old netlist put
# Y2.1 on the tuner's XTAL pin, grounded Y2.2 AND Y2.4, and ran Y2.3 into a load cap -
# which is the pin pattern of a 4-pad passive crystal (two terminals, two grounded
# shield tabs), exactly as Y1 legitimately uses. But the PART fitted here was an active
# CMOS oscillator, so that wiring GROUNDED ITS SUPPLY: pin 4 is VDD. It could never
# have started. Nothing caught it because the whole RF block was stripped and DNP, so
# no check ever ran over it.
#
# Correct wiring for this part, transcribed from the YSOS510TP family datasheet
# (the PDF JLC attaches to C22381771): 1 = GND, 2 = GND, 3 = OUT, 4 = VDD.
net("TUNER_REF",  "Y2.3", "C58.1")            # TCXO clipped-sine output
net("TUNER_XTAL", "C58.2", "U13.14")          # AC-coupled into the XTAL pin
NETS["+3V3A"] += ["Y2.4", "C59.1"]            # VDD + decoupling, on the quiet rail
NETS["GND"]  += ["Y2.2", "Y2.1", "C59.2"]    # both ground pins to ground
net("TUNER_ADDR","U13.28","R29.2"); NETS["GND"] += ["R29.1"]
NETS["I2C2_SDA"] += ["U13.26"]; NETS["I2C2_SCL"] += ["U13.27"]
net("VTUNE","U13.9","C56.1"); NETS["GND"] += ["C56.2"]
net("CPOUT","U13.12","R34.1"); net("LOOP","R34.2","C57.1"); NETS["GND"] += ["C57.2"]
net("VCOBYP","U13.8"); net("REFOUT","U13.15"); net("GC1","U13.5","R35.2")
NETS["GND"] += ["R35.1"]
# MAX2112 baseband -> OPA2374 difference amps -> ADC (resistor values TBD by sim)
net("IOUT_P","U13.19","R36.1"); net("IOUT_N","U13.20","R37.1")
net("QOUT_P","U13.17","R30.1"); net("QOUT_N","U13.18","R31.1")
net("OPA_IN1P","R36.2","U14.3"); net("OPA_IN1N","R37.2","U14.2")
net("OPA_IN2P","R30.1")  # placeholder, merged below
del NETS["OPA_IN2P"]
net("OPA_IN2P_","U14.5"); net("OPA_IN2N_","U14.6")
NETS["QOUT_P"] += ["U14.5"]; NETS["QOUT_N"] += ["U14.6"]
del NETS["OPA_IN2P_"], NETS["OPA_IN2N_"]
NETS["+3V3A"] += ["U14.8"]; NETS["GND"] += ["U14.4"]   # opamps follow the tuner
net("IDC_P","U13.21"); net("IDC_N","U13.22"); net("QDC_P","U13.23"); net("QDC_N","U13.24")

# ---------------------------------------------------------------- fixes ----
# LED chains: MCU -> resistor -> LED anode -> GND  (LEDs are active-low in hwdef,
# but Matek drives them low-to-light via the MCU pin, so anode sits on +3V3.)
for k in ("LED0","LED0_K","LED1","LED1_K"): NETS.pop(k, None)
net("LED0_A","+3V3_dummy"); NETS.pop("LED0_A")
NETS["+3V3"] += ["D2.2","D3.2"]
for r in ("R20.1","R21.1"):
    if r in NETS["+3V3"]: NETS["+3V3"].remove(r)
net("LED0_K","D2.1","R20.1"); net("LED0","R20.2","U1.PE3")
net("LED1_K","D3.1","R21.1"); net("LED1","R21.2","U1.PE4")
for g in ("D2.2","D3.2"):
    if g in NETS["GND"]: NETS["GND"].remove(g)

# TPS54331 5V buck - full wiring
net("BUCK_BOOT","U8.6","C21.1")
net("BUCK_PH",  "U8.2","C21.2","L2.1")
NETS["+5V"] += ["L2.2"]
net("BUCK_EN",  "U8.5","R4.2","R5.1")
net("BUCK_FB",  "U8.4","R6.2","R7.1")
# NO BUCK_SS AND NO BUCK_COMP. The TPS54202 has a 5 ms internal soft-start and internal
# loop compensation, so C20, R8, C24 and C25 are deleted outright - four fewer parts on
# this rail, and four fewer things to get wrong.
NETS.pop("R3", None)

# LDO enables tied to their inputs (always-on)
NETS["+5V"]  += ["U9.3","U10.3"]

COMPONENTS.pop("R2", None)
NETS["GND"] += ["R31.2"]

# BOOT0 button: +3V3 --SW1-- BOOT0 --R1-- GND   (was shorting +3V3 to BOOT0)
for n in ("BOOT0","+3V3","GND"):
    NETS[n] = [x for x in NETS[n] if x not in ("SW1.1","SW1.2")]
NETS["BOOT0"] += ["SW1.2"]; NETS["+3V3"] += ["SW1.1"]
# U8 pin 8 is the switch node only, not the 5V rail
NETS["+5V"] = [x for x in NETS["+5V"] if x != "U8.2"]
COMPONENTS.pop("R3", None)

# ---- MAX2112 bypass / DC-offset caps (datasheet-required, SoOP config DNP) ----
for r, v in [("C60","100n"),("C61","100n"),("C62","100n"),("C63","100n"),("C64","100n")]:
    CAP(r, v, F_C0402, dnp=True)
NETS["VCOBYP"] += ["C60.1"]
NETS["IDC_P"]  += ["C61.1"]; NETS["IDC_N"] += ["C62.1"]
NETS["QDC_P"]  += ["C63.1"]; NETS["QDC_N"] += ["C64.1"]
NETS["GND"]    += ["C60.2","C61.2","C62.2","C63.2","C64.2"]

# ---- power flags: tell ERC these rails are actually driven ---------------
PWR_FLAGS = {"VBAT":"PF1", "+5V":"PF2", "+3V3":"PF3", "+3V3A":"PF4",
             "GND":"PF5", "VDDA":"PF6", "VBUS":"PF7", "VCC_RF":"PF8",
             "VBAT_IN":"PF9"}
for netname, ref in PWR_FLAGS.items():
    add(ref, "power:PWR_FLAG", "", "PWR_FLAG", "", netname == "VCC_RF")
    NETS[netname].append(f"{ref}.1")

# ---- test points ---------------------------------------------------------
# Only signals worth the copper get a pad. An earlier pass auto-generated a test point
# for all 29 single-pin nets; at 41.6 x 39.4 mm they did not fit, and most were not
# worth having. Everything not listed here is left as an explicit no-connect - the pin
# exists in the hwdef but this board does not break it out.
TESTPOINT_NETS = ["SWDIO", "SWCLK", "PWM5", "PWM6",
                  "USART1_TX", "USART1_RX", "WS2812", "BUZZER"]
for i, netname in enumerate(TESTPOINT_NETS, 1):
    ref = f"TP{i}"
    add(ref, "Connector:TestPoint", "TestPoint:TestPoint_Pad_1.5x1.5mm", netname, "", False)
    NETS[netname].append(f"{ref}.1")

# ---- connector reduction: JST-GH -> solder pads ---------------------------
# TWO OF THE FOUR CAME BACK. This block was written when the board was 41.6 x 39.4 mm
# and four layers, and it degraded every connector except USB-C, the ESC and the GPS
# into bare 1.5 mm pads. The board is now 45.0 x 46.0 mm and six layers, and the pads
# turned out to cost more than the space they saved: an ELRS receiver is not optional
# equipment, and it was landing on four identical gold squares of which exactly one
# carried a silkscreen label. That is the highest-consequence hand-solder joint on the
# aircraft and the easiest one to get wrong.
#
# So J4 (companion, 6P) and J5 (RC, 4P) are connectors again. J6 (CAN) and J7 (the
# spare UART4) stay pads: nothing on this build plugs into either, and an unused
# connector is mass and edge length spent on nothing.
# Measured during layout: at 41.6 x 39.4 mm, seven JST-GH connectors plus an LQFP100
# and a microSD socket exceed the board. That is not a packing failure - the FC alone
# was already at 67.5% courtyard, above the ~60-65% routable ceiling for 4 layers.
#
# The fix is the one every real 30x30 FC uses (the SpeedyBee F405 V4 this replaces
# included): keep a connector only where you actually plug and unplug something, and
# make the rest solder pads. Keeps USB-C, the 8-pin ESC JST-SH, and the GPS JST-GH.
PAD_FP = "TestPoint:TestPoint_Pad_1.5x1.5mm"
_PAD_LABELS = {
 # J4 (companion) and J5 (RC) are NOT in this table any more - see the note below.
 "J6": {1:"CAN_5V", 2:"CANH",   3:"CANL",   4:"CAN_GND"},
 "J7": {1:"RF_5V",  2:"RF_TX",  3:"RF_RX",  4:"RF_GND"},
}
for jref, labels in _PAD_LABELS.items():
    COMPONENTS.pop(jref, None)
    for pinno, label in labels.items():
        pref = f"P{jref[1:]}{pinno}"
        add(pref, "Connector:TestPoint", PAD_FP, label, "", False)
        for netname, specs in NETS.items():
            for i, sp in enumerate(list(specs)):
                if sp == f"{jref}.{pinno}":
                    specs[i] = f"{pref}.1"
    # drop the connector's shell/mounting pins entirely
    for netname, specs in NETS.items():
        NETS[netname] = [sp for sp in specs if not sp.startswith(f"{jref}.")]

# P41/P46 were the +5V/GND pair every ad-hoc load taps - the VTX, the recording camera,
# a bench meter - and P44 was the SoOP tuner's PPS probe. Restoring J4 as a connector
# would have taken all three away, so they are re-created as standalone pads. A power
# tap wants a pad, not a plug: it is soldered once and never unplugged, and giving it a
# connector would mean a mating lead for two wires.
add("P41", "Connector:TestPoint", PAD_FP, "TEL_5V",  "", False)
add("P44", "Connector:TestPoint", PAD_FP, "TEL_PPS", "", False)
add("P46", "Connector:TestPoint", PAD_FP, "TEL_GND", "", False)
NETS["+5V"].append("P41.1")
NETS["PPS_SYNC"].append("P44.1")
NETS["GND"].append("P46.1")

# UART7 HAS NO LANDING, AND THE COMPANION DOES NOT NEED ONE.
#
# J4 (the GH-6P companion connector) was cut because the corner arcs and the M3
# keepout circles fence every remaining GH-6P edge candidate - that search is sound.
# The note that went with it, "the interior is full, so even a DNP pad had nowhere to
# go", is not: the board is 48.4% courtyard and a sweep finds 154 free 2 mm cells on
# F.Cu and 315 on B.Cu. But NEITHER claim was the one that mattered. Measured here:
#
#   nearest free cell to PE8/PE7/PE9, EITHER face:   28.2 mm
#
# Every free cell is out at the periphery; the middle of the board, where UART7 leaves
# the MCU, is genuinely packed. Pads were placed at that distance and DRC came back
# clean, so the space is real - but tools/route_nets.py could not thread a 28 mm run
# for any of the three (two rollbacks at +18 errors, one "no path"). Placeable is not
# routable, and that distinction is the whole finding.
#
# It does not cost the companion anything, because SERIAL6 IS ALREADY THERE. UART4
# comes out on P71/P72/P73/P74 - 5V, TX, RX, GND, routed, and recorded in
# design.PAYLOAD as "GENERAL-PURPOSE EXPANSION UART - free and unclaimed". With PPS on
# P44 that is a complete five-wire companion interface on pads that already exist. The
# companion moves from SERIAL1 to SERIAL6 and nothing else changes; "re-fitting needs a
# new board with a UART7 socket" was wrong.

# ---- SoOP RF front end moved OFF this board ------------------------------
# Measured, not guessed:
#   flight controller     2213 mm^2 = 67.5% courtyard across both sides
#   FC + RF front end     2516 mm^2 = 76.8%
# The routable ceiling for 4 layers is roughly 60-65%, so the FC is already at the
# limit and the RF section does not fit. Worse, at 1.6 GHz the LNA -> SAW -> tuner
# chain must be contiguous, and there is no free 220 mm^2 region left - the packer
# could only place it by scattering it, which would not work at that frequency.
#
# This is also the RF-correct answer: an LNA belongs AT THE ANTENNA, where it sets
# the system noise figure before cable loss. The original plan's two-board option
# had it there. So the SoOP front end becomes its own small board, fed from the
# RTL-SDR's bias-tee, and this board keeps the companion UART that carries the fix.
# The TUNER is on the board. The LNA and SAW are not, and never were sourceable:
# FL1 (TA1575IG, 1620 MHz SAW) has no LCSC part number at all. Both jobs are done by
# the bought Nooelec SAWbird+ IR at the antenna. Nothing below is defined any more -
# the block is kept only so a future two-board build knows what was removed and why.
INCLUDE_ONBOARD_LNA = False       # U15/U16/FL1/L3/L4 - see the ANT_IN comment
assert not INCLUDE_ONBOARD_LNA, ("the on-board LNA/SAW chain was deleted, not disabled - "
                                 "re-adding it needs the 1620 MHz SAW sourced first")
for _r in ("U15", "U16", "FL1", "L3", "L4"):
    COMPONENTS.pop(_r, None)

# Keep the SoOP receiver interface reachable from the board edge even though the RF
# front end now lives elsewhere: I/Q and AGC come back as pads.
for _i, _n in enumerate(["SOOP_I_ADC", "SOOP_Q_ADC", "SOOP_RSSI"], start=len(TESTPOINT_NETS)+1):
    if _n in NETS:
        _r = f"TP{_i}"
        add(_r, "Connector:TestPoint", "TestPoint:TestPoint_Pad_1.5x1.5mm", _n, "", False)
        NETS[_n].append(f"{_r}.1")

# ===========================================================================
# Phase A additions — the four gaps found in the component audit.
# Batched deliberately: each one alone would still force a full regeneration.
# ===========================================================================

F_SOT23   = "jlc:SOT-23-3_L2.9-W1.3-P1.90-LS2.4-BR"
F_SOD123  = "jlc:SOD-123F_L2.7-W1.6-LS3.8-RD"
F_SOT235  = "jlc:SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR"
PAD15     = "TestPoint:TestPoint_Pad_1.5x1.5mm"

# ---- 1. Buzzer driver ------------------------------------------------------
# BUZZER was a bare MCU pin. A passive piezo sits between +5V and the FET drain;
# the flyback diode clamps the inductive kick when the FET turns off.
add("Q1", "jlc_parts:AO3400A",        F_SOT23,  "AO3400A", "C20917", False)
add("D4", "jlc_parts:1N4148W_C81598", F_SOD123, "1N4148W", "C81598", False)
RES("R38", "100R")       # gate series
RES("R39", "10k")        # gate pulldown - keeps the buzzer quiet while the MCU boots
add("PZ1", "Connector:TestPoint", PAD15, "BUZZ+", "", False)
add("PZ2", "Connector:TestPoint", PAD15, "BUZZ-", "", False)

net("BUZZ_GATE", "R38.2", "Q1.1", "R39.1")
NETS["BUZZER"] += ["R38.1"]                       # from U1.PA15
NETS["GND"]    += ["Q1.2", "R39.2"]
net("BUZZ_DRAIN", "Q1.3", "D4.2", "PZ2.1")        # D4 pin2 = anode
NETS["+5V"]    += ["D4.1", "PZ1.1"]               # D4 pin1 = cathode

# ---- 2. SWD probe reference pads -------------------------------------------
# SWDIO/SWCLK were isolated pads with nowhere to land a debug probe's ground.
add("TP20", "Connector:TestPoint", PAD15, "SWD_GND", "", False)
add("TP21", "Connector:TestPoint", PAD15, "SWD_3V3", "", False)
NETS["GND"]  += ["TP20.1"]
NETS["+3V3"] += ["TP21.1"]

# ---- 3. WS2812 level shifter ----------------------------------------------
# The MCU drives 3.3V; a 5V WS2812 strip wants >=0.7*VDD = 3.5V on DIN. The
# 74LVC1G17 is a Schmitt buffer powered from +5V, so the output swings to 5V.
add("U17", "jlc_parts:SN74LVC1G17DBVR", F_SOT235, "74LVC1G17", "C7836", False)
CAP("C65", "100n")
add("PL1", "Connector:TestPoint", PAD15, "LED_DIN", "", False)
add("PL2", "Connector:TestPoint", PAD15, "LED_5V",  "", False)
add("PL3", "Connector:TestPoint", PAD15, "LED_GND", "", False)
NETS["WS2812"] += ["U17.2"]                       # A input, from U1.PA8
net("WS2812_OUT", "U17.4", "PL1.1")               # Y output at 5V
NETS["+5V"] += ["U17.5", "C65.1", "PL2.1"]
NETS["GND"] += ["U17.3", "C65.2", "PL3.1"]

# ---- 4. 9V VTX BEC ---------------------------------------------------------
# Second TPS54202 (NOT a TPS54331 - this comment said so for a long time), same topology
# as the 5 V rail. The divider arithmetic below is the superseded 0.8 V-reference design:
# the TPS54202 references 0.596 V, and _VALUE_FIX ships 100k / 6k8 -> 9.361 V, chosen to
# reuse reels already on this BOM. +4 % is accepted on this rail alone because it feeds an
# analogue VTX and every analogue VTX takes 7-24 V.
#   superseded: R_top/R_bot = 9/0.8 - 1 = 10.25  ->  102k / 10k.
add("U18", "jlc_parts:TPS54202DDCR", "jlc:SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL",
    "TPS54202", "C191884", False)
# THE 1210 LAND MISMATCH LIVES HERE, not on L2 (which now has the correct ANR4030 land
# on F.Cu beside U8). Be precise about severity rather than repeating "4.0 mm part on a
# 3.2 x 2.5 mm land": check_ratings.py MEASURES terminal against pad and reports 0.18 mm
# of overhang in Y - solderable, check the fillet. A fillet concern, not a part hanging
# off its land. Current is not an issue either: 0.60 A of a 1.6 A Irms part.
#
# The real cost was the LOOP, and it is fixed: L5 moved from B.Cu (127.50, 119.00)
# to F.Cu at (130.50, 117.50) so the 9 V switch node no longer crosses the board - U18
# is F.Cu at (130.50, 121.22), so U18.2 to L5.1 is ~4.9 mm of the same-side copper
# instead of a board-crossing run to the other face. The land stays 1210: an ANR4030
# site was measured and there is none within 12 mm of U18, so "fix the land too" would
# have moved the inductor away from the switch node it exists to be near. That trade is
# why ADJACENCY["L5"] is now 5.5 (derived from this placement), not 2.5.
IND("L5", "10uH", F_L1210)
CAP("C66", "100n")                 # VIN hf
CAP("C68", "100n")                 # bootstrap
CAP("C69", "22u", F_C1206)         # output bulk
CAP("C70", "22u", F_C1206)
RES("R40", "392k"); RES("R41", "78k7")     # EN divider
RES("R42", "102k"); RES("R43", "10k")      # -> overridden to 100k / 6k8, see _VALUE_FIX
add("PV1", "Connector:TestPoint", PAD15, "VTX_9V",  "", False)
add("PV2", "Connector:TestPoint", PAD15, "VTX_GND", "", False)

NETS["VBAT"] += ["U18.3", "C66.1", "R40.1"]
net("BUCK9_BOOT",  "U18.6", "C68.1")
net("BUCK9_PH",    "U18.2", "C68.2", "L5.1")
net("BUCK9_EN",    "U18.5", "R40.2", "R41.1")
net("BUCK9_FB",    "U18.4", "R42.2", "R43.1")
# Same deletions as the 5 V rail: internal soft-start and compensation.
net("+9V", "L5.2", "C69.1", "C70.1", "R42.1", "PV1.1")
NETS["GND"] += ["U18.1", "C66.2", "C69.2", "C70.2",
                "R41.2", "R43.2", "PV2.1"]


# ---- 5. VTX power control --------------------------------------------------
# The 9 V rail's enable came from R40/R41 off VBAT alone, so the VTX powered up with the
# battery and stayed up: no failsafe video cut, no pit mode, nothing the firmware could
# do about it.
#
# Q3 pulls BUCK9_EN to ground when the MCU drives its gate high. R45 holds the gate down
# while the MCU is in reset, so the FET is OFF and the divider still enables the buck -
# the rail therefore fails SAFE TOWARDS VIDEO-ON, which is the right direction for a
# model you may need to find. Driving the pin high turns the VTX off.
#
# Driving U18.3 from a GPIO directly is not an option: that node sits at
# VBAT * 22/122, about 4.5 V on 6S, well over the MCU's absolute maximum.
#
# Same AO3400A already used for the buzzer, so this adds no new part number.
# The board is full around U18: the nearest place a SOT-23 fits is 11.6 mm away, which
# leaves ~15 mm of EN trace. EN is a high-impedance node (about 18k from the divider),
# and 15 mm of it running past a switching regulator is asking for glitches. C73 fixes
# that at the pin - a 0402 does fit 2.8 mm from U18.3 - giving roughly 180 us of
# filtering, far too fast to matter for an enable and far too slow for switching noise.
add("Q3", "jlc_parts:AO3400A", F_SOT23, "AO3400A", "C20917", False)
RES("R45", "10k")                       # gate pulldown: VTX on unless told otherwise
CAP("C73", "10n")                       # EN filter, sits next to U18.3

net("VTX_EN", "U1.PA7", "Q3.1", "R45.1")
NETS["GND"] += ["Q3.2", "R45.2", "C73.2"]
NETS["BUCK9_EN"] += ["Q3.3", "C73.1"]
# PA7, not PE15. Two reasons, both found by measuring rather than assuming:
#
#   * PE15 and PB2 look like ideal spares - genuinely unassigned - and BOTH are walled
#     into ~1 mm2 pockets inside the LQFP pad ring with no room for a via.
#     tools/scan_spare_pins.py measures this; PA7 escapes into 1.0 mm2 with 9 via-legal
#     cells, which is tight but real.
#   * PA7 is BATT2_CURRENT_SENS on MatekH743 - an ADC INPUT, never driven. A stock
#     MatekH743 binary therefore cannot assert this line, and R45 pulls the gate down,
#     so the VTX stays powered. Taking PB12 or PD8 instead would have handed a stock
#     binary an output that idles high and cuts video.
del NETS["SPARE_ADC"]                   # PA7 now has a job

# ===========================================================================
# Phase C — reverse-polarity protection and the edge connectors.
# ===========================================================================

# ---- 1. Reverse-polarity protection ------------------------------------------
# Q4 is a P-FET that blocks a reversed pack. ON Semi AND90146/D Figure 4 ("Reverse
# Polarity Protection using a P-Channel MOSFET") is explicit about the orientation:
# DRAIN TO THE BATTERY, SOURCE TO THE LOAD. The body diode conducts until the channel
# turns on, and a reversed pack reverse-biases the diode so the rail stays dead:
#
#   "When the battery is properly connected, the intrinsic body diode is conductive
#    till the MOSFET's channel is turned ON... When the battery is reversely
#    connected, the body diode is reversed biased, gate and source have the same
#    voltage thus turning OFF the P-Channel MOSFET. An additional Zener diode is
#    used to clamp the gate of the P-Channel MOSFET and protect it in the case of a
#    too high voltage."            -- AND90146/D
#
# The orientation is the whole circuit: drain = battery (VBAT_IN), source = load
# (VBAT). Written source-to-battery, the body diode would conduct a reversed pack
# straight into the rail. tools/check_topology.py keys the gate pull-down off the
# part number and will refuse to order a board whose Q4 gate floats.
#
# R46 pulls the gate to GND. A P-FET conducts with Vgs < -VT; with the source at VBAT
# and the gate at GND the channel is fully enhanced, and a floating gate (no R46)
# means the FET never turns on - the board is dead with a correct battery connected.
# DZ1 clamps Vgs at ~15 V, inside the WST4041's +-20 V gate rating (a full 4S pack
# alone would put -16.8 V on the gate). Zener CATHODE to source, ANODE to gate.
# J12 is the coax entry from the SAWbird+ IR. The KiCad footprint carries one signal
# pad and two ground pads, which is 3 electrical joints - and C5137195 is listed by
# JLCPCB at 3 joints, so check_footprints can verify it rather than take it on trust.
# The old U.FL was ref J9, which is now the I2C port; reusing that ref would have been
# the kind of collision the RF-strip block used to hide.
add("J12", "Connector:Conn_Coaxial", F_UFL, "U.FL ANT", "C5137195", False)

add("Q4", "jlc_parts:WST4041", F_SOT23, "WST4041", "C148357", False)
add("DZ1", "jlc_parts:BZT52C15", "jlc:SOD-123_L2.7-W1.6-LS3.7-RD",
    "BZT52C15", "C173427", False)
RES("R46", "100k")
net("VBAT_GATE", "Q4.1", "DZ1.2", "R46.1")   # Q4 pin 1 = gate; DZ1 pin 2 = anode
NETS["VBAT"] += ["DZ1.1"]                        # DZ1 pin 1 = cathode, on the source
NETS["GND"] += ["R46.2"]                         # gate pull-down to ground

# ---- 2. The edge connectors ---------------------------------------------------
# EDGE LENGTH IS NOW THE BINDING CONSTRAINT, so it is written down rather than
# discovered during layout. Measured from the footprints' own courtyards:
#
#   J1  USB-C        ~9.0 mm      J2  ESC   JST-SH 8P  ~12.0 mm
#   J3  GPS   GH 6P  13.32 mm     J8  microSD          ~15.0 mm
#   J5  RC    SH 4P   8.26 mm     J9  I2C   SH 4P        8.26 mm
#   J11 SER2  SH 4P   8.26 mm
#                                            TOTAL     ~78.0 mm
#
# J4 (companion GH 6P) and J10 (servo SH 4P) were CUT on 2026-09-09. The outline is
# 45.0 x 46.0 mm, so the perimeter is 182 mm; four M3 holes and the corner radii take
# roughly 30 mm, leaving ~150 mm usable - which sounds like slack, but an exhaustive
# geometry search (both faces, all four edges, pads >= 0.55 mm inside the outline,
# courtyard overlap and pad-to-M3 rules) proved the corner arcs and the M3 keepout
# circles fence every remaining candidate for a GH-6P or a second SH-4P: J5 owns the
# only legal SH-4P edge slot (B.Cu east), J11 the west one. The fallback ladder was
# applied in its own order: J10 first (no module in the buying list), J4 next ("cut
# first if space runs out"). Do NOT drop J5 - the RC receiver is what the whole change
# is for, and it now owns the B.Cu east edge at (41.71, 30.97) rot -90.
#
# JST-SH 4P (C160404) is used for four of them deliberately: one part number, one
# feeder, one cable type. It is friction-fit rather than latched, which is the same
# retention J2 already relies on for all four motor signals and is what every 30x30
# flight controller does. JST-GH (latched) would be better and costs 2.56 mm each; it
# was rejected because C51940118 is absent from the jlcparts mirror, so its pad count
# could not be machine-checked, while C160404 verifies at 6 joints against the
# footprint. Reliability that cannot be verified is not obviously reliability.
# An earlier draft brought I2C1 to the outside ONLY on J3, the GPS port. That is standard per
# DS-009, but every Pixhawk-class board also ships a dedicated 4-pin I2C port so
# sensors do not need a splitter into the GPS loom - check_module_wiring reported the
# missing one as NO_DEDICATED_BUS. J9 is that port: VCC/SCL/SDA/GND, on +5 V to match
# J3's own power pin and the Pixhawk I2C convention.
#
# THE RANGEFINDERS ARE NOT 5 V PARTS, and J9 does not change that. The TFS20-L is a
# 3.3 V module - check_purchase.py asserts exactly that - so it needs either an inline
# regulator in the lead or a breakout that regulates on board, the same as it did on
# J3. What J9 buys is the SPLITTER, not the LDO: the sensor stops sharing the GPS loom.
# The bus itself is 3.3 V logic either way, because R9/R10 pull I2C1 up to +3V3.
#
# J10 (servo port) and J4 (companion / TELEM1) were CUT on 2026-09-09. An
# exhaustive geometry search (both faces, all four edges, every rotation, pads
# >= 0.55 mm inside the outline, no courtyard overlap, pad-to-M3 rule) proved
# neither has a legal edge home on a 45 x 46 mm board with 30.5 mm mounts, and
# the interior is full, so even DNP pads had nowhere legal. This is the plan's
# own fallback ladder: "drop J10 (servo) first - the only one of the five whose
# module is not in the buying list", and J4 was tier 3, "cut first if space
# runs out". Their functions stay provisioned:
#   servo    PWM5/PWM6 on TP3/TP4, VSERVO on TP22 (fed from an external BEC -
#            VSERVO stays a separate net from +5 V on purpose, a power tap not
#            a splice, per check_module_wiring)
#   companion UART7_TX/RX/RTS has NO landing at all - P42/P43/P45 were
#            tried as new pads and removed again (2026-09-09) when the same
#            exhaustive search found no legal site for them either, on either
#            face, anywhere. P41/P44/P46 survive from the Rev A pad group but
#            carry no companion function.
add("J9", "jlc_parts:SM04B-SRSS-TB_(LF)(SN)",
    "jlc:CONN-SMD_4P-P1.00_SM04B-SRSS-TB-LF-SN", "I2C 4P", "C160404", False)
add("TP22", "Connector:TestPoint", "TestPoint:TestPoint_Pad_1.5x1.5mm",
    "VSERVO", "", False)
NETS["+5V"] += ["J9.1"]
NETS["I2C1_SCL"] += ["J9.2"]
NETS["I2C1_SDA"] += ["J9.3"]
NETS["GND"] += ["J9.4", "J9.5", "J9.6"]       # pin 4 = signal, 5/6 = anchor tabs
net("VSERVO", "TP22.1")

# J11 is SERIAL2 (USART1) with its own power and ground. The LD06 was landing on TP5
# and TP6 for its data pair and then reaching across the board to P71 and P74 for 5 V
# and ground - four wires from three places, which is the same fault J10 fixes for the
# servo. TP5/TP6 SURVIVE as probe points: a scope on a UART is worth a 1.5 mm pad, and
# a redundant pad costs nothing once the connector carries the module.
#
# The LD06 ships with a ZH1.5T-4P lead, which mates with nothing on any flight
# controller, so it needs an adapter whatever this port is - that is a property of the
# sensor, not of this choice.
add("J11", "jlc_parts:SM04B-SRSS-TB_(LF)(SN)",
    "jlc:CONN-SMD_4P-P1.00_SM04B-SRSS-TB-LF-SN", "SERIAL2 4P", "C160404", False)
NETS["+5V"] += ["J11.1"]
NETS["USART1_TX"] += ["J11.2"]
NETS["USART1_RX"] += ["J11.3"]
NETS["GND"] += ["J11.4", "J11.5", "J11.6"]

# ===========================================================================
# Phase B — placement intent.
#
# A decoupling cap sits between two PLANE nets (+3V3 and GND), so a centroid of
# "pads I connect to" gives it no useful target - which is exactly why the first
# layout scattered them and left VCAP2 30 mm from its pin. The pin each part
# serves is design intent and has to be stated.
#
#   ref -> (ref, pad, max_mm)   max_mm is a HARD limit checked at Gate 1.
# ===========================================================================
ADJACENCY = {
    # MCU VDD decoupling - one per supply pin, as close as the package allows
    "C1": ("U1", "11", 2.0), "C2": ("U1", "27", 2.0), "C3": ("U1", "50", 2.0),
    "C4": ("U1", "75", 2.0), "C5": ("U1", "100", 2.0),
    "C6": ("U1", "11", 4.0), "C7": ("U1", "75", 4.0),          # bulk, looser
    # VCAP - the H743's internal LDO. This is the one that was 30 mm away.
    "C8": ("U1", "48", 1.5), "C9": ("U1", "73", 1.5),
    # analogue supply and reference
    "C10": ("U1", "21", 2.0), "C11": ("U1", "21", 3.0),
    "C12": ("U1", "20", 2.0), "C13": ("U1", "20", 3.0),
    "L1":  ("U1", "21", 4.0),
    "C14": ("U1", "14", 3.0),                                   # NRST
    # crystal load caps
    "C15": ("Y1", "1", 2.5), "C16": ("Y1", "3", 2.5),
    # The load caps were pinned to Y1 but Y1 itself was pinned to nothing, so the
    # packer parked the whole crystal cluster in a corner 24-27 mm from the pins it
    # drives. At 8 MHz that is several pF of stray on a high-impedance node, which
    # pulls the frequency off, can stop the oscillator starting, and puts a sensitive
    # node next to the bucks and the DShot outputs. Same class of defect as VCAP2
    # being 30 mm from its pin - the rule was simply missing.
    "Y1": ("U1", "12", 5.0),
    # sensors
    "C31": ("U2", "5", 1.5), "C32": ("U2", "8", 1.5),
    "C33": ("U3", "5", 1.5), "C34": ("U3", "8", 1.5),
    "C35": ("U4", "1", 1.5),
    "C36": ("U5", "8", 1.5),
    "C41": ("U11", "3", 1.5),
    "C42": ("J1", "A4B9", 3.0),
    "C45": ("J8", "4", 3.0), "C46": ("J8", "4", 2.0),
    # regulators
    "C26": ("U9", "1", 2.0), "C27": ("U9", "5", 2.0),
    "C28": ("U10", "1", 2.0), "C29": ("U10", "5", 2.0), "C30": ("U10", "5", 3.0),
    "C65": ("U17", "5", 1.5),
    # 5V buck. TPS54202 DDC pinout: 1 GND, 2 SW, 3 VIN, 4 FB, 5 EN, 6 BOOT.
    # These anchors were written for the TPS54331's 8-pin numbering and pointed L2/C22/
    # C23 at "pin 8", which does not exist on a 6-pin part - the placer silently dropped
    # all six power parts. The switch-node loop must still be tight and the FB divider
    # must still be short and quiet.
    "C17": ("U8", "3", 3.0), "C18": ("U8", "3", 3.0), "C19": ("U8", "3", 1.5),
    "C21": ("U8", "6", 1.5),
    "R6": ("U8", "4", 2.5), "R7": ("U8", "4", 2.5),
    "R4": ("U8", "5", 3.0), "R5": ("U8", "5", 3.0),
    "L2": ("U8", "2", 3.0), "C22": ("U8", "2", 5.0), "C23": ("U8", "2", 5.0),
    # 9V buck, same part and the same remapping
    "C66": ("U18", "3", 1.5), "C68": ("U18", "6", 1.5),
    "R42": ("U18", "4", 2.5), "R43": ("U18", "4", 2.5),
    "R40": ("U18", "5", 3.0), "R41": ("U18", "5", 3.0),
    # L5 moved to F.Cu at (130.50, 117.50) so the 9 V switch node no longer
    # crosses the board - U18.2 sits at (130.50, 122.37), 4.87 mm below. The limit is
    # DERIVED from that placement, not a class figure: U18.2 to the nearest L5 pad
    # measures ~5.1 mm, so 5.5 is the real achievable bound. The old 2.5 assumed an
    # ANR4030 land right beside U18, and no such site exists within 12 mm of it - the
    # 1210 land stays (see the L5 comment in the 9 V block).
    "L5": ("U18", "2", 5.5), "C69": ("U18", "2", 5.0), "C70": ("U18", "2", 5.0),
    "C73": ("U18", "5", 3.0),      # EN filter, as close to the pin as the board allows
    # I2C pull-ups belong near the master, not scattered
    "R9": ("U1", "92", 4.0), "R10": ("U1", "93", 4.0),
    "R11": ("U1", "46", 4.0), "R12": ("U1", "47", 4.0),
    # buzzer / level shifter local parts
    "R38": ("Q1", "1", 2.0), "R39": ("Q1", "1", 2.0), "D4": ("Q1", "3", 3.0),
    # battery sense divider next to the MCU ADC pins
    "R18": ("U1", "15", 5.0), "R19": ("U1", "15", 4.0),
    "C43": ("U1", "15", 2.0), "C44": ("U1", "16", 2.0),
}

# Parts that were falling through to "place anywhere": give them intent too.
# A TVS clamps a surge where it ENTERS the board, so it belongs at the connector,
# not at a downstream regulator - by the time the transient reaches U8 it has already
# crossed everything else on VBAT. This rule used to point at U8.2, which put
# the TVS 33 mm from J2 and defeated the purpose. J2.2 is the ESC's VBAT pin.
ADJACENCY["D1"]  = ("J2",  "2", 5.0)     # TVS at the power entry, not the buck
ADJACENCY["SW2"] = ("U1", "14", 6.0)     # reset button near NRST
ADJACENCY["SW1"] = ("U1", "94", 6.0)     # boot button near BOOT0

ADJACENCY["U12"] = ("J1", "A6", 5.0)     # USB ESD belongs at the connector, not adrift

# Limits refined after the first placement pass. A 0402 cannot get within 1.5 mm of a
# QFN pad centre - the pad itself is ~1 mm inside the package - so 1.5 was unachievable
# rather than desirable. The switching-regulator OUTPUT caps went the other way: they
# were too loose, and on a buck the output loop is what radiates.
for _r in ("C31","C32","C33","C34","C35","C36","C65","C41"):
    if _r in ADJACENCY:
        t, pd, _m = ADJACENCY[_r]; ADJACENCY[_r] = (t, pd, 3.5)
for _r, _lim in (("C22", 3.0), ("C23", 3.0), ("C69", 3.0), ("C70", 3.0),
                 ("L2", 2.5)):
    if _r in ADJACENCY:
        t, pd, _m = ADJACENCY[_r]; ADJACENCY[_r] = (t, pd, _lim)

# ---------------------------------------------------------------- geometry ---
# One definition, imported by gen_pcb / route / fix_overlaps / check_placement.
# It was duplicated in four files, so growing the board left route.py drawing
# copper outside the new outline.
BOARD = dict(X0=100.0, Y0=100.0, W=45.0, H=46.0, R=4.0, MOUNT=30.5, HOLE_D=4.0)

# ===========================================================================
# Feedback dividers corrected, and LCSC codes for the passives.
#
# The 5 V buck's divider was 10k2 / 3k24, which is 0.8 * (1 + 10.2/3.24) = 3.32 V -
# a 3.3 V rail where a 5 V one was intended. Caught while sourcing the parts, because
# the odd E96 values were hard to buy and that prompted a recheck of the arithmetic.
# Both dividers are now E24 pairs that are actually stocked:
#     5 V : 27k / 5k1  -> 5.04 V
#     9 V : 47k / 4k7  -> 8.80 V   (any analogue VTX accepts 7-24 V)
#     EN  : 100k / 22k -> UVLO 6.9 V, well below a 3S pack's 11.1 V
# ===========================================================================
# FB dividers RECOMPUTED for the TPS54202's 0.596 V reference (TPS54331 was 0.800 V).
# Leaving these alone would have produced 3.75 V and 6.55 V - the classic silent
# failure when a regulator is swapped for one with a different reference.
#   +5V : 0.596 * (1 + 37.4/5.1)  = 4.967 V
#   +9V : 0.596 * (1 + 66.5/4.7)  = 9.029 V
# 9 V DIVIDER USES REELS ALREADY ON THIS BOM, deliberately.
# It was 66k5 / 4k7 -> 9.028 V, which needed a 66k5 part number this project could not
# confirm from a source (LCSC search is unreachable from the build environment, and the
# manufacturer PN alone does not give the C-code). 100k / 6k8 -> 9.361 V using two reels
# already here: one less line on the BOM, one less part to look up, no extra setup fee.
#
# +4.0 % is fine on THIS rail and only this one. It feeds an analogue VTX, and every
# analogue VTX takes 7-24 V - the note at the bottom of this block has said so since the
# rail was 8.80 V. The 5 V rail gets no such latitude (WS2812s want >= 4.5 V and the best
# sourced pair is -5.7 %), so R6 keeps its 37k4 and stays a genuine lookup.
_VALUE_FIX = {"R6": "37k4", "R7": "5k1", "R42": "100k", "R43": "6k8",
              "R4": "100k", "R5": "22k", "R40": "100k", "R41": "22k"}
for _r, _v in _VALUE_FIX.items():
    if _r in COMPONENTS:
        s, f, _old, l, d = COMPONENTS[_r]; COMPONENTS[_r] = (s, f, _v, l, d)

# LCSC codes for generic passives, so the BOM is orderable rather than a shopping list.
#
# KEYED ON (value, footprint), NOT value alone. Keying on value shipped one part number
# against two different package sizes: "10u" -> C1713 covered both C17/C18 on 1206 and
# C45 on 0805, and "1u" -> C52923 covered both the 0402 positions and C42 on 0805.
# C1713 is a 0805 part and C52923 is a 0402 part, so in each pair one position had a
# physically wrong component assigned to it and JLCPCB would have placed it.
PASSIVE_LCSC = {
    ("100n", F_C0402): "C1525",   ("1u",   F_C0402): "C52923",
    ("2u2",  F_C0402): "C12530",  ("4u7",  F_C0805): "C354262",
    ("10n",  F_C0402): "C15195",  ("30p",  F_C0402): "C107004",
    ("47p",  F_C0402): "C60137",  ("3n3",  F_C0402): "C26404",
    # C17/C18, the VBAT bulk caps, moved C70462 -> C16195875 on 2026-09-03 for two
    # reasons found in the same check against JLCPCB's own parts library:
    #   STOCK. C70462 was down to 7 pieces against 2 needed. That is enough for exactly
    #   one board and nothing if someone else orders first.
    #   DERATING. check_ratings.py had warned about C70462 since it went in: 25 V on a
    #   16.8 V rail is 1.5x, and an X7R MLCC loses much of its value near rating. The
    #   replacement is 35 V, so the same 10 uF sits at 2.1x and holds more of it.
    # Same 10 uF, same X7R, same 1206 land - Samsung CL31B106KLHNNNE, 126626 in stock.
    # Confirmed against the jlcparts mirror AND lcsc.com/product-detail/C16195875.html.
    ("10u",  F_C0805): "C1713",   ("10u",  F_C1206): "C16195875",
    ("1u",   F_C0805): "C91185",  ("22u",  F_C1206): "C5177178",
    # RF-block passives that shipped without a code, so the BOM printed three blank
    # LCSC columns and preflight's "every line has an LCSC code" caught them. All three
    # were read off their own LCSC product page, not inferred:
    #   0R    C17168   UNI-ROYAL 0402WGF0000TCE, 0 ohm 1% 50V 0402
    #   100p  C1546    FH 0402CG101J500NT, 100 pF 50V C0G 0402  (RF coupling - C0G)
    #   1n    C1523    FH 0402B102K500NT, 1 nF 50V X7R 0402     (XTAL series cap)
    ("0R",   F_R0402): "C17168",  ("100p", F_C0402): "C1546",
    ("1n",   F_C0402): "C1523",
    ("100R", F_R0402): "C25076",  ("120R", F_R0402): "C25862",
    ("1k",   F_R0402): "C11702",  ("4k7",  F_R0402): "C25900",
    ("5k1",  F_R0402): "C25905",  ("6k8",  F_R0402): "C25917",
    ("10k",  F_R0402): "C25744",  ("22k",  F_R0402): "C25767",
    ("27k",  F_R0402): "C25771",  ("47k",  F_R0402): "C25792",
    ("100k", F_R0402): "C25741",
    # THE TPS54202 FEEDBACK DIVIDERS. Value is settled (0.596 V reference -> 4.967 V and
    # 9.029 V); the LCSC C-code is NOT, and inventing one is exactly the class of
    # unverified assertion that let the missing catch diode through.
    #
    # The MANUFACTURER part numbers ARE verified, from Uniroyal's documented scheme
    # (0402 = size, WG = 1/16 W, F = 1%, then 3 significant figures + decade multiplier,
    # TCE = tape and reel) and cross-checked against the entries above - 1k is
    # 0402WGF1001TCE / C11702 and 5k1 is 0402WGF5101TCE / C25905:
    #
    #     37k4  ->  0402WGF3742TCE
    #     66k5  ->  0402WGF6652TCE
    #
    # Paste either MPN into lcsc.com to get its C-code, then replace the sentinel below.
    # tools/preflight.py gates this - "every line has an LCSC code" fails while it stands.
    # 37.4k 1% 0402, UNI-ROYAL 0402WGF3742TCE. Resolved 2026-09-03 and CONFIRMED TWICE,
    # because one source for a part number is how a board gets the wrong resistor:
    #   1. the jlcparts dataset (yaqwsx.github.io/jlcparts), which mirrors JLCPCB's own
    #      library - "37.4kOhm 50V 62.5mW Thick Film ±1% ±100ppm/C 0402", 6810 in stock
    #   2. lcsc.com/product-detail/C25888.html itself, which agrees on all five fields
    # LCSC's search is unreachable from this environment; the dataset is the way in.
    ("37k4", F_R0402): "C25888",
    ("10uH", F_L1210): "C167879",     # DOES NOT FIT - see the note at L2
    ("10uH", F_ANR4030): "C167879",   # FNR4030S100MT, Isat 2.4 A, Irms 1.6 A
    ("10uH", F_ANR5040): "C354610",   # CKCS5040-10uH/M, Isat 2.5 A, Irms 2.1 A
    ("600R@100MHz", F_L0805): "C18305",
    ("BLUE", F_LED):   "C965807", ("GREEN", F_LED): "C965804",
    ("BOOT", F_SW):    "C231329", ("RESET", F_SW): "C231329",
}

# Per-reference overrides, applied FIRST and never touched by the generic fill above
# (which only fills a component whose LCSC code is still empty).
#
# These exist because a value alone does not determine the right part. C19 and C66 are
# 100 nF like 25 other positions on this board, but they sit on VBAT - 16.8 V on a fully
# charged 4S - and the generic 100 nF here is a 16 V part. An MLCC operated over its
# rating on a LiPo's main rail fails short, across the battery.
PART_LCSC = {
    # VBAT high-frequency bypass. The generic 100 nF (C1525) is a 16 V part and VBAT
    # reaches 16.8 V on a fully charged 4S, so it was operating OVER its rating on the
    # battery's own rail. C131394 is the same 0402 100 nF X7R at 50 V.
    "C19": "C131394",
    "C66": "C131394",
}

for _r, _lcsc in PART_LCSC.items():
    if _r in COMPONENTS:
        s, f, v, _l, d = COMPONENTS[_r]; COMPONENTS[_r] = (s, f, v, _lcsc, d)

_unpriced = []
for _r, (s, f, v, l, d) in list(COMPONENTS.items()):
    if l: continue
    key = (v, f)
    if key in PASSIVE_LCSC:
        COMPONENTS[_r] = (s, f, v, PASSIVE_LCSC[key], d)
    elif v in {k[0] for k in PASSIVE_LCSC}:
        # the value is known but not in this package - that is the bug the tuple key
        # exists to catch, so report it rather than silently fitting the wrong part
        _unpriced.append((_r, v, f))
if _unpriced:
    import sys as _sys
    for _r, _v, _f in _unpriced:
        print(f"design.py: {_r} is {_v} in {_f} - no LCSC part for that "
              f"(value, footprint) pair", file=_sys.stderr)

# ---------------------------------------------------------------- part ratings
#
# What each LCSC part actually IS, read off its own product page. Nothing in this
# repository recorded a voltage, power or temperature rating before this table existed,
# and no tool checked one - a part could be correct in every topological sense and still
# be destroyed on first power-up. Two were:
#
#   C17/C18  10 uF on VBAT   were C1713,  a 16 V 0805 part, on a 1206 footprint, on a
#                            rail that reaches 16.8 V. Wrong package AND over its rating.
#   C19/C66  100 nF on VBAT  were C1525,  a 16 V part, likewise over its rating. An MLCC
#                            run over rating fails SHORT - across a LiPo's main rail.
#
# Both came from PASSIVE_LCSC being keyed on value alone, so "10u" meant one part number
# whatever the footprint or the net.
#
#   uF / V / dielectric / tolerance / package / temp range / source
# Dielectric matters as much as voltage in two places: crystal load caps must be C0G/NP0
# or the oscillator pulls with temperature, and a Class II part loses most of its marked
# capacitance at its rated voltage (DC bias), which is why tools/check_ratings.py warns
# below 2x even when the part is not strictly over its rating.
RATINGS = {
 # LCSC        value   V    dielectric  tol     package  Tmin Tmax  source
 "C1525":    ("100n",  16,  "X7R",     "10%",  "0402",  -55, 125, "[D] LCSC product page, 2026-08-29"),
 "C131394":  ("100n",  50,  "X7R",     "10%",  "0402",  None, None, "[D] LCSC product page, 2026-08-29"),
 "C52923":   ("1u",    25,  "X5R",     "10%",  "0402",  -55,  85, "[D] LCSC product page, 2026-08-29"),
 "C91185":   ("1u",    50,  "X7R",     "10%",  "0805",  None, None, "[D] LCSC product page, 2026-08-29"),
 "C1713":    ("10u",   16,  "X5R",     "10%",  "0805",  -55,  85, "[D] LCSC product page, 2026-08-29"),
 "C16195875":("10u",   35,  "X7R",     "10%",  "1206",  None, None, "[D] LCSC + jlcparts, 2026-09-03"),
 "C5177178": ("22u",   16,  "X5R",     None,   "1206",  None, None, "[D] LCSC product page, 2026-08-29"),
 "C107004":  ("30p",   50,  "NP0",     "5%",   "0402",  None, None, "[D] LCSC product page, 2026-08-29"),
 # 0603, NOT 0805 - a third position where the value-keyed table fitted the wrong package
 "C19666":   ("4u7",   16,  "X5R",     "10%",  "0603",  -55,  85, "[D] LCSC product page, 2026-08-29"),
 "C354262":  ("4u7",   25,  "X7R",     "10%",  "0805",  None, None, "[D] LCSC product page, 2026-08-29"),
 "C12530":   ("2u2",  6.3,  "X5R",     "20%",  "0402",  None, None, "[D] LCSC product page, 2026-08-29"),
 "C15195":   ("10n",   50,  "X7R",     "10%",  "0402",  None, None, "[D] LCSC product page, 2026-08-29"),
 "C26404":   ("3n3",   50,  "X7R",     "10%",  "0402",  None, None, "[D] LCSC product page, 2026-08-29"),
 "C60137":   ("47p",   50,  "NP0",     "5%",   "0402",  None, None, "[D] LCSC product page, 2026-08-29"),
 "C1546":    ("100p",  50,  "NP0",     "5%",   "0402",  None, None, "[D] LCSC product page (0402CG101J500NT), 2026-09-11"),
 "C1523":    ("1n",    50,  "X7R",     "10%",  "0402",  None, None, "[D] LCSC product page (0402B102K500NT), 2026-09-11"),
}
# Parts whose ratings have NOT been read off a datasheet yet. check_ratings.py reports
# these loudly rather than assuming a value - a silent default is exactly how the
# component-height table came to count J2 and both power inductors as 1.0 mm.
# Every capacitor on the board now has its ratings read off its own LCSC page.
# The resistors are not individually listed: their package power rating is checked in
# check_ratings.py from the footprint, and a 0402 thick-film part's 50 V maximum working
# voltage is a property of the package, not of the specific part number. The worst case
# on this board is R18 at 45 % of its rating.
RATINGS_UNVERIFIED = set()

# Inductors: current ratings and REAL body size, which is not what the footprint says.
#   LCSC          L      Isat  Irms  DCR    body LxWxH mm   source
INDUCTORS = {
 "C167879":  ("10uH", 2.4, 1.6, 0.130, (4.0, 4.0, 3.0), "[D] LCSC page 2026-08-29, FNR4030S100MT"),
 "C354610":  ("10uH", 2.5, 2.1, 0.064, (5.0, 5.0, 4.0), "[D] LCSC page 2026-08-29, CKCS5040-10uH/M"),
 "C18305":   ("600R@100MHz", None, None, None, (2.0, 1.25, 0.85), "[A] 0805 ferrite bead, package typical"),
}
# Continuous current each inductor actually carries, from the rail it feeds.
# The +5V figure is the fully-fitted configuration in check_build.py: the board's own
# 620 mA plus Pi Zero 2 W, lidar, the 8-sensor ToF ring, the mux and the LED strip.
# Worst-case DC through each buck's inductor.
#
# L2 was 1.89 A, which included 700 mA for the Pi and put the FNR4030 at 118% of its
# 1.6 A RMS rating. The Pi now runs from its own BEC - see the note on LOADS_5V in
# tools/check_build.py - which is better practice anyway, since a Linux SBC's load
# transients have no business on the flight controller's own buck. 0.95 A is 59% of
# the part, with the 2.4 A saturation figure well clear. (1.19 A / 74% until the
# WS2812 load was corrected from a 300 mA guess to a 60 mA strobe-duty budget,
# 2026-09-05 - see LOADS_5V in tools/check_build.py.)
#   board 620 mA + TFS20-L 106 + ToF ring 160 + mux 1 + WS2812 60 = 947 mA
# (WS2812 was 300 mA [A] "at low brightness" until 2026-09-05; the honest budget is
# strobe duty <=10% of its 10x60 mA full-white peak - see LOADS_5V in check_build.py)
INDUCTOR_LOAD_A = {"L2": 0.95, "L5": 0.60}

# ---- package heights, the single source of truth ---------------------------------
# Height of each package above the board surface it sits on, mm. [D] package-typical
# maxima unless noted.
#
# This table lived in check_build.py, and the same quantity was ALSO hardcoded as 2.5 mm
# in check_mechanical.BOT_PARTS and as the string "2.3 mm" in preflight.py. Three numbers
# for one measurement, none of them derived from the board, and all three wrong at once:
#
#   * BOT_PARTS cited "the tallest bottom-side part: L2/L5". L2 had been moved to the TOP
#     during the buck re-layout and the source line was never revisited.
#   * L_1210 was declared 2.5 mm on the strength of a generic 1210 inductor. The part
#     actually bought for that land is an FNR4030 (C167879), 4.0 x 4.0 x 3.0 mm - the
#     whole point of the earlier land work. 0.5 mm understated.
#   * L_APV_ANR4030 was absent, so L2 fell through to the silent 1.0 mm default and was
#     counted as a third of its real height. The comment above the table warns about
#     exactly this failure mode; the table still had it.
#
# Longest key wins, so "SOT-23-6" beats "SOT-23". Unknown footprints are REPORTED by
# part_height(), never silently defaulted - a silent default is how the old table hid J2.
PART_HEIGHT = {
    "CONN-SMD_XY-SM06B": 4.4,   # JST GH 6P
    "CONN-TH_SM08B": 2.9,       # JST SH 8P - the ESC connector
    "USB-C": 3.2, "TF-SMD": 1.9, "COB": 2.3, "DO-214": 2.3,
    "OPTO": 1.6, "SOIC": 1.8, "SOP": 1.8,
    "LQFP": 1.6, "LGA-14": 0.95, "SENSORS-SMD_MS5611": 1.1,
    "CRYSTAL-SMD_4P": 0.9, "SOD-123F": 1.1,
    "SOT-23-3": 1.45, "SOT-23-5": 1.45, "SOT-23-6": 1.45, "SOT-25": 1.45,
    "SW_SPST_B3U": 0.8, "TestPoint_Pad": 0.0,
    # Both 10 uH power inductors are the same part, C167879, 4.0 x 4.0 x 3.0 mm. L2 sits
    # on the ANR4030 land on the top side; L5 on a 1210 land on the bottom, and is DNP
    # unless the analogue-FPV variant is populated.
    "L_APV_ANR4030": 3.0, "L_1210": 3.0,
    "L_0805": 1.2,        # ferrite bead
    "C_1206": 1.6, "C_0805": 1.45, "C_0402": 0.55,
    "R_0402": 0.45, "LED_0603": 0.55,
    # Rev B parts. These five arrived with the tuner / connector work and spent a session
    # absent from this table, so check_mechanical reported "!! footprints with no
    # declared height" and preflight refused the board - the same silent-default class
    # the comment above warns about, one layer up.
    "CONN-SMD_4P-P1.00_SM04B": 2.9,   # JST SH 4P vertical (J5/J9/J11), same 2.9 as the SH 8P
    "OSC-SMD_4P": 0.9,                 # 3.2 x 2.5 clipped-sine TCXO (Y2) [D] Ostar
    "SOD-123": 1.1,                    # DZ1 zener, same body as the SOD-123F already here
    "TQFN-28_L5.0": 0.8,               # U13 MAX2112, 5 x 5 QFN [D] Maxim
    "U.FL_Hirose": 1.2,                # J12 vertical U.FL [D] Hirose U.FL-R-SMT-1
}


def part_height(fp_name):
    """Height in mm for a footprint name, or None if nothing in the table matches.

    None means "not known" and every caller must say so out loud. Returning a default
    here would recreate the bug this table exists to document.
    """
    keys = [k for k in PART_HEIGHT if k in fp_name]
    return PART_HEIGHT[max(keys, key=len)] if keys else None


def stack_heights(board, skip_dnp=True):
    """Tallest fitted part on each side, measured from the board.

    Returns (top_mm, bot_mm, tallest_top_ref, tallest_bot_ref, unknown{name: [refs]}).

    skip_dnp excludes parts that are not populated, because the two build variants have
    genuinely different bottom-side heights: L5 is a 3.0 mm inductor on the bottom, and
    it is fitted only on the analogue-FPV build.
    """
    top = bot = 0.0
    top_ref = bot_ref = None
    unknown = {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        comp = COMPONENTS.get(ref)
        if skip_dnp and comp and comp[4]:
            continue
        name = str(fp.GetFPID().GetLibItemName())
        h = part_height(name)
        if h is None:
            unknown.setdefault(name, []).append(ref)
            continue
        if fp.IsFlipped():
            if h > bot:
                bot, bot_ref = h, ref
        elif h > top:
            top, top_ref = h, ref
    return top, bot, top_ref, bot_ref, unknown

# Maximum working voltage of each net, for the ratings check. VBAT is a 4S pack at its
# fully-charged 4.2 V/cell, not its 14.8 V nominal - the charged case is the one that
# breaks parts, and it is the state the aircraft is in every time it is switched on.
CELLS = 4
NET_VMAX = {
    "VBAT": CELLS * 4.2,
    "+9V": 9.0, "+5V": 5.0, "VBUS": 5.25, "+3V3": 3.3, "+3V3A": 3.3, "VDDA": 3.3,
    "GND": 0.0,
}
# The bootstrap capacitors sit BETWEEN boot and phase, so they see the TPS54331's
# internal bootstrap supply (~8 V), not VBAT + 8 V. The node swings with the switch; the
# capacitor does not see that swing across its own terminals.
NET_VMAX.update({"BUCK_BOOT": 8.4, "BUCK_PH": 8.4, "BUCK9_BOOT": 8.4, "BUCK9_PH": 8.4})

# Internal nodes. These were undeclared, so check_ratings.py listed them and then checked
# nothing - twelve capacitors passing by omission rather than by test. Every one turns
# out to be fine, which is exactly why it needed writing down: "benign on inspection" and
# "verified" are different states, and the gap between them is where this project's
# defects have lived.
#
# All are bounded by a 3.3 V rail or by a regulator that cannot drive above it:
#   NRST                 pulled up to +3V3
#   OSC_IN / OSC_OUT     crystal pins, +3V3 domain
#   BUCK_SS / BUCK9_SS   TPS54331 soft-start, charged by an internal current source
#                        that stops well below the 3 V pin abs-max
#   (BUCK_COMP2 / BUCK9_COMP2 are GONE - the TPS54202 compensates internally, so there
#    is no error-amplifier output brought outside the package any more)
#   BATT_V_DIV           divider output into an ADC pin - it MUST stay under 3.3 V or the
#     ESC_CUR            MCU is damaged, and check_electrical.py is what proves the
#                        divider ratio actually holds it there. Declared here at the
#                        limit it is required to respect, not at a measured value.
NET_VMAX.update({
    "NRST": 3.3, "OSC_IN": 3.3, "OSC_OUT": 3.3,
    "BUCK_SS": 3.3, "BUCK9_SS": 3.3,
    "BUCK_COMP": 3.3, "BUCK9_COMP": 3.3, "BUCK_FB": 3.3, "BUCK9_FB": 3.3,
    "BATT_V_DIV": 3.3, "ESC_CUR": 3.3,
    # VCAP1/2 are the H743's internal core LDO output, 1.2 V nominal. 1.5 V is the
    # datasheet ceiling for the pin, and the right number to rate a capacitor against.
    "VCAP1": 1.5, "VCAP2": 1.5,
    # BUCK9_EN is VBAT through R40/R41, a 100k/22k divider:
    #   16.8 V * 22 / (100 + 22) = 3.03 V, well under the TPS54331's EN abs-max.
    # Q3 only ever pulls this node DOWN, so it cannot raise the ceiling.
    "BUCK9_EN": 3.1,
})


# ------------------------------------------------------------ 9 V VTX buck: DNP
#
# docs/BUYING.md has always said "9 V VTX buck - DNP by default; populate only for an
# analogue-FPV build", and not one of its parts was marked DNP. The BOM shipped all
# sixteen: bought, placed and paid for, for a feature this build does not use.
#
# It also matters electrically. The +9V rail's last two unrouted connections sit in the
# band at U1's left edge that has defeated every attempt to route through it; with the
# block unpopulated, that copper carries no fitted component.
#
# C66 is deliberately NOT here. It is a VBAT bulk cap that happens to sit by U18's VIN
# pin - useful whether or not the 9 V buck is fitted.
#
# To build an analogue-FPV variant, delete this loop. The pads are all still there, so a
# populated board can also be made by hand-fitting them later.
VTX_BUCK_DNP = ("U18", "L5", "C67", "C68", "C69", "C70", "C71", "C72", "C73",
                "R40", "R41", "R42", "R43", "R44", "R45", "Q3", "PV1")
# DNP AGAIN, 2026-09-03 - the premise of the decision below turned out to be false.
#
# It read "the 9 V buck used to be DNP because the rail was unrouted; IT IS ROUTED NOW".
# It is not. BUCK9_PH cannot be closed on this placement: U18 is a SOT-23-6 on F.Cu with
# its inductor L5 and boot cap C68 on B.Cu, the switch node is the MIDDLE pad of three
# with 0.42 mm either side, and the only reachable via site is 2.6 mm away across the
# ground pour - taking it strands U18's GND pad, whose ONLY connection is that pour.
# Via-in-pad is blocked too, by a VBAT track under the pad. docs/ROUTING-TODO.md has the
# measurements.
#
# So populating would put 12 parts down on a regulator whose switch node reaches nothing.
# It would not merely be wasteful, it would be a lie on the BOM: a rail that looks built
# and cannot work. DNP is the honest BOM for a board with that net open.
#
# NOTHING IN THIS BUILD WANTS THE RAIL. The FPV camera and VTX are docs/PARTS.csv status
# LATER at $0 ("You said no goggles yet"), and +9V's only other consumer is the PV1 test
# pad. The cost of this decision today is zero.
#
# To revive it: fix the routing (KiCad's interactive router can shove copper, which none
# of the tools here can) or move U18/L5/C68 onto one side in a respin, then set this True.
#
# The original reasoning, kept because it is still correct ABOUT ASSEMBLY COST:
# L5's FNR4030 fits its 1210 land, and the parts are mostly JLC Basic on a board that is
# already a two-sided assembly - so both stencils and both placement passes are paid for
# either way.
#
# The alternative was hand-fitting later, and the geometry argues against it: 11 of the
# 16 parts are 0402 and 14 of 16 are on the BOTTOM side, the closest 4.4 mm from U6's
# lens. DNP positions also get no paste from JLC's stencil, so each one would be
# hand-pasted or wire-soldered on a face that already carries both IMUs and the baro.
#
# Populating changes three things, all of them wanted: check_power_cut stops suppressing
# +9V as "all loads DNP" so the rail becomes a real gate; the underside goes 2.30 -> 3.00
# mm (L5), which still clears; and the CPL grows to match what is ordered.
POPULATE_VTX = False
if not POPULATE_VTX:
    for _r in VTX_BUCK_DNP:
        if _r in COMPONENTS:
            _s, _f, _v, _l, _d = COMPONENTS[_r]
            COMPONENTS[_r] = (_s, _f, _v, _l, True)


# ---- sensors that cannot see out of this stack ------------------------------------
# U6 (PMW3901) and U7 (VL53L1X) are DELETED rather than shipped DNP. Both sat
# on the board's underside aimed at the top of the solid 4-in-1 ESC 3.0 mm away - they
# could never see anything, which is why an earlier draft shipped them DNP - and deleting them
# frees PD4 (EXT_CS1), PD10 and PD11 plus five passives and ~$50 of BOM.
#
# The functions are still provisioned, off the board:
#   * flow comes from the Pi's global-shutter camera over MAVLink. defaults.parm ships
#     FLOW_TYPE 5, which is MAVLink, NOT 2/Pixart - U6 was never enabled anyway.
#   * height comes from the TFS20-L on the DEDICATED I2C port J9 at 0x10 - no more
#     splitter into the GPS loom, which is what check_module_wiring called a splice.
#   * deleting U7 frees I2C 0x29, which docs/PARTS.csv already depends on for the
#     upward-facing VL53L1X module ("only works because U7 is left unpopulated").
#
# POPULATE_BLIND_SENSORS is kept as an (empty) flag so gen_bom.py's variant logic does
# not change shape; there is nothing left to populate.
POPULATE_BLIND_SENSORS = False
BLIND_SENSORS = ()


# Bare copper pads are not components - they must not appear in a BOM or a CPL.
NOT_A_PART = {r for r in COMPONENTS
              if r.startswith("TP")
              or (r[0] == "P" and (r[1:].isdigit() or (len(r) > 1 and r[1] in "ZLV")))}

# ===========================================================================
# How much current each power net actually has to carry.
#
# Nothing in the toolchain checked this, and it is not a detail: the router lays every
# net at TRACK_W (0.1016 mm / 4 mil) because that is the design rule, and a 4 mil
# external trace carries about 0.45 A at a 10 degC rise by IPC-2221 - roughly 0.23 A on
# an inner layer. VBAT feeds two switching regulators. tools/check_electrical.py
# compares these figures against the NARROWEST trace actually on each net.
#
# Currents are worst case at the LOWEST supported pack voltage, because a buck draws
# more input current as its input falls.
#
#   VBAT  4S, so 13 V under load at 3.25 V/cell. The 5 V buck at its full 3 A is 15 W,
#         about 16.7 W in at 90%, so 1.28 A; the 9 V VTX rail adds roughly 0.38 A.
#   +5V   sized for what the REGULATOR CAN DELIVER, not for the expected load. If a
#         hungry companion computer is plugged into P41 the copper must not be the fuse.
#   +9V   a typical analogue VTX
# ===========================================================================
# Where current ENTERS each rail. Needed because "this pad sits on a plane pour" turned
# out not to mean what it looked like: VBAT's plane is in two disconnected groups and
# +5V's in four, so a pad can sit on copper that never reaches the source. The real
# question is the narrowest point along the path from source to load.
NET_SOURCE = {
    "VBAT_IN": "J2.2",   # battery connector, before the protection FET
    "VBAT":    "Q4.2",   # after the protection FET - Q4 pin 2 = source
    "+5V":   "L2.2",     # 5 V buck output inductor
    "+9V":   "L5.2",     # 9 V buck output inductor
    "+3V3":  "U9.5",     # AP2112 output
    "+3V3A": "U10.5",    # TLV75533 output
    "VBUS":  "J1.A4B9",  # USB-C
}

# Worst-case CONTINUOUS load each rail must carry. NOT the regulator's rating: copper
# carries what the loads actually draw, and a fault is the regulator's job - the
# TPS54331 current-limits and folds back.
#
# +5V was 3.0 A, the regulator's full output, and that failed the board at 2.9 A of
# measured copper - a 3% shortfall against an estimate check_power_cut.py itself calls
# "optimistic by construction". With the Pi moved to its own BEC the real figure is:
#   board 620 mA + TFS20-L 106 + ToF ring 160 + mux 1 + WS2812 60 = 947 mA
# (WS2812 corrected 300 -> 60 mA on 2026-09-05: a strobe-duty budget, not a brightness
# guess - see LOADS_5V in tools/check_build.py.)
# The copper measures 2.9 A, so it covers the fitted TPS54202's 2.0 A output even into
# a short - and L2's 1.6 A Irms, the binding limit, with 65% margin.
NET_CURRENT = {
    "VBAT": 1.7,
    "+5V":  0.95,
    # 0.30 A is what this rail CAN deliver, established by trying to raise it and
    # failing. It is not the figure anyone wanted - a 500 mW carrier needs ~0.5 A - so
    # here is the evidence, because the number looks like a capitulation and is not:
    #
    #   * The path from L5 to PV1 runs through a 12.85 mm artery on In3.Cu at 0.15 mm.
    #     IPC-2221 halves internal conductors, so 0.15 mm = 0.30 A at a 10 C rise.
    #   * widen_net.py is exhausted. Measured clearance around that artery: a VBAT via
    #     at 0.20 mm and GND vias at 0.32-0.48 mm. Keeping the 0.1016 mm rule, the
    #     widest it could ever become is 0.189 mm - about 0.35 A. Not enough.
    #   * A parallel run on an outer layer was scanned for at every x from 124 to 134 mm
    #     over the full y span. EVERY position is blocked on both F.Cu and B.Cu, by
    #     L2.1 (BUCK_PH) and C40.2 (GND) among others. There is no corridor.
    #   * A rip-and-reroute was attempted with route_final.py. It rejoined one break and
    #     reverted the other at 43-48 violations, twice. The board was restored.
    #
    # 0.30 A is therefore a measured ceiling, not an assumption, and it buys a 200-250 mW
    # VTX. A 500 mW carrier needs the region around x=129.7, y=104-117 relaid - moving
    # GND and VBAT vias - which needs a respin, not a widening.
    #
    # UK note: Ofcom caps 5.8 GHz FPV at 25 mW EIRP licence-exempt, and its amateur
    # guidance says airborne use needs amateur to be PRIMARY in the band (5 GHz is
    # Secondary) and names drone FPV as incompatible with the licence. So 0.30 A is well
    # clear of anything legally flyable here without a UAS Radio Operator licence.
    "+9V":  0.30,
    # NOTE this is a COPPER budget (what the trace must carry), not a load estimate.
    # The load is itemised in LOADS_3V3 and comes to 271 mA continuous / 445 mA peak.
    # 0.6 A here is deliberately conservative for copper - and it happens to be exactly
    # the AP2112K's own maximum output, which for a long time was the only number
    # anywhere near this rail and was never compared against the part. check_thermal.py
    # now does that comparison.
    "+3V3": 0.6,
    "+3V3A": 0.35,   # was 0.2 - the MAX2112's 100 mA now lands on this rail
    # VBUS carries NO load current. It reaches only the USBLC6's reference pin and a
    # bypass cap - nothing bridges it to +5V, so USB cannot power the board and the net
    # is not a supply path. Rating it at 500 mA was rating a wire that feeds nothing.
    "VBUS": 0.05,
}

# ===========================================================================
# What each MCU pin is FOR, in the electrical sense.
#
# check_design.py proves a pin is wired. check_hwdef.py proves the firmware does not
# name a pin the board lacks. Neither notices when a pin is wired to the wrong END of
# something - and that is the failure mode that actually grounds an aircraft:
#
#   * PD11 drives TOF_XSHUT, which R13 pulls up to enable the VL53L1X. The hwdef
#     declared it OUTPUT ... LOW, so the MCU held the rangefinder in shutdown from boot.
#   * PD10 sits on TOF_INT, which is the sensor's own interrupt OUTPUT. The hwdef
#     declared it OUTPUT too, so both ends drive the same node.
#   * ESC_TEL carries telemetry FROM the ESC, and landed on PE1 = UART8_TX. A transmit
#     pin cannot receive; PE0 (UART8_RX) is wired to nothing.
#
# None of those is visible from connectivity alone. So direction is stated here, next to
# the netlist it describes, and tools/check_pin_semantics.py enforces it.
#
#   mcu   what the MCU must do:  in | out | bidir | analog
#   boot  the level the pin MUST be at after reset for the device to work, if it matters
#   why   why, in one line - this is the bit a reviewer actually reads
# ===========================================================================
PIN_INTENT = {
    # --- motors and battery ------------------------------------------------
    "M1": dict(mcu="out", why="DShot to ESC motor 1"),
    "M2": dict(mcu="out", why="DShot to ESC motor 2"),
    "M3": dict(mcu="out", why="DShot to ESC motor 3"),
    "M4": dict(mcu="out", why="DShot to ESC motor 4"),
    "BATT_V_DIV": dict(mcu="analog", why="11:1 pack divider into ADC1"),
    "ESC_CUR":    dict(mcu="analog", why="ESC current-sense output into ADC1"),
    "ESC_TEL":    dict(mcu="in",     why="ESC transmits telemetry to the FC - RX pin"),

    # --- IMU1 / IMU2 SPI ---------------------------------------------------
    "SPI1_SCK": dict(mcu="out", why="clock to ICM-42688-P"),
    "SPI1_MOSI": dict(mcu="out", why="MCU drives"),
    "SPI1_MISO": dict(mcu="in",  why="sensor drives"),
    "IMU1_CS":  dict(mcu="out", boot="high", why="chip select, idle high"),
    "SPI4_SCK": dict(mcu="out", why="clock to ICM-42605"),
    "SPI4_MOSI": dict(mcu="out", why="MCU drives"),
    "SPI4_MISO": dict(mcu="in",  why="sensor drives"),
    "IMU2_CS":  dict(mcu="out", boot="high", why="chip select, idle high"),

    # --- SPI3: optical flow + TLE flash ------------------------------------
    "SPI3_SCK": dict(mcu="out", why="shared clock, PMW3901 + W25Q128"),
    "SPI3_MOSI": dict(mcu="out", why="MCU drives"),
    "SPI3_MISO": dict(mcu="in",  why="devices drive"),
    "EXT_CS2":  dict(mcu="out", boot="high", why="W25Q128 select, idle high"),

    # --- I2C ---------------------------------------------------------------
    "I2C1_SCL": dict(mcu="bidir", why="open-drain, 4k7 pull-up"),
    "I2C1_SDA": dict(mcu="bidir", why="open-drain, 4k7 pull-up"),
    "I2C2_SCL": dict(mcu="bidir", why="open-drain, 4k7 pull-up"),
    "I2C2_SDA": dict(mcu="bidir", why="open-drain, 4k7 pull-up"),

    # --- serial ------------------------------------------------------------
    "USART2_TX": dict(mcu="out", why="to GPS RX"),
    "USART2_RX": dict(mcu="in",  why="from GPS TX"),
    "UART7_TX":  dict(mcu="out", why="to companion RX"),
    "UART7_RX":  dict(mcu="in",  why="from companion TX"),
    "UART7_RTS": dict(mcu="out", why="flow control out"),
    "PPS_SYNC":  dict(mcu="in",
                      why="companion PPS edge in (the default config wires it as UART7_CTS, also an input)"),
    "USART6_TX": dict(mcu="out", why="to receiver, or half-duplex CRSF"),
    "RC_IN":     dict(mcu="in",  why="receiver drives the FC"),
    "UART4_TX":  dict(mcu="out", why="to rangefinder/peripheral RX"),
    "UART4_RX":  dict(mcu="in",  why="from rangefinder/peripheral TX"),

    # --- CAN ---------------------------------------------------------------
    "CAN1_RX":     dict(mcu="in",  why="transceiver RXD drives the MCU"),
    "CAN1_TX":     dict(mcu="out", why="MCU drives transceiver TXD"),
    "CAN1_SILENT": dict(mcu="out", boot="low",
                        why="SN65HVD230 Rs: LOW = high-speed mode, HIGH = standby"),

    # --- USB / SD ----------------------------------------------------------
    "USB_DP": dict(mcu="bidir", why="USB differential pair"),
    "USB_DM": dict(mcu="bidir", why="USB differential pair"),
    "SD_D0": dict(mcu="bidir", why="SDMMC data"),
    "SD_D1": dict(mcu="bidir", why="SDMMC data"),
    "SD_D2": dict(mcu="bidir", why="SDMMC data"),
    "SD_D3": dict(mcu="bidir", why="SDMMC data"),
    "SD_CMD": dict(mcu="bidir", why="SDMMC command"),
    "SD_CK":  dict(mcu="out",   why="SDMMC clock"),
    "SD_CD":  dict(mcu="in",    why="card-detect switch to GND, 10k pull-up"),

    # --- notify ------------------------------------------------------------
    "LED0":   dict(mcu="out", why="status LED via 1k"),
    "LED1":   dict(mcu="out", why="status LED via 1k"),
    "BUZZER": dict(mcu="out", boot="low",
                   why="AO3400A gate; R39 pulls down so it is silent through reset"),
    "WS2812": dict(mcu="out", why="into the 74LVC1G17 level shifter"),

    # --- VTX power ---------------------------------------------------------
    "VTX_EN": dict(mcu="out", boot="low",
                   why="Q3 gate: LOW leaves the 9 V VTX rail enabled, HIGH cuts it"),

    # --- brought out to test pads only, no device fitted --------------------
    "USART1_TX": dict(mcu="out", why="telem2 TX on test pad TP5"),
    "USART1_RX": dict(mcu="in",  why="telem2 RX on test pad TP6"),
    "PWM5": dict(mcu="out", why="spare motor output on test pad TP3"),
    "PWM6": dict(mcu="out", why="spare motor output on test pad TP4"),

    # --- debug -------------------------------------------------------------
    "SWDIO": dict(mcu="bidir", why="SWD data"),
    "SWCLK": dict(mcu="in",    why="probe drives the clock"),
}


# ---------------------------------------------------------------------------
# MODULES - the one board, and everything that can bolt onto it later.
#
# THERE IS ONE PCB AND ONLY ONE. Older notes used "Rev A" and "Rev B" for two
# different things - first two firmware configurations, later a board revision -
# and both readings are retired: the board is fabricated once. Where a change
# really would need a second fabrication run, `needs_board_change` says so in
# those words. Everything below
# attaches to pads or connectors that ALREADY EXIST unless `needs_board_change`
# says otherwise, which is what makes the design modular rather than staged.
#
# `lands_on` is asserted against the real footprints by tools/check_modules.py,
# so this table cannot drift away from the board the way prose does.
# ---------------------------------------------------------------------------
MODULES = {
    "esc": dict(
        what="SpeedyBee BLS 60A 4-in-1", lands_on=["J2"], conn="JST-SH 8P (friction fit)",
        needs_board_change=None, gbp=0, status="fitted",
        ma_5v=0, counted=True,
        note="J2 follows Betaflight's documented SpeedyBee pinout; buzz it before VBAT"),
    "gps_compass": dict(
        what="M10 + QMC5883L", lands_on=["J3"], conn="JST-GH 6P (LATCHED)",
        needs_board_change=None, gbp=15, status="fitted",
        ma_5v=50, counted=True,
        note="carries USART2 *and* I2C1 - the I2C pair is what every ToF sensor shares"),
    "rangefinder_down": dict(
        what="Benewake TFS20-L, 20 m", lands_on=["J9"], conn="I2C1 off J9.2/J9.3, addr 0x10",
        needs_board_change=None, gbp=32, status="later",
        ma_5v=106, counted=True,
        note="RNGFND1 - POSZ only. Proximity is never an EKF POSXY source. The "
             "dedicated I2C port J9 means no splitter into the GPS loom"),
    "rangefinder_up": dict(
        what="VL53L1X (GY-53-L1X), 4 m", lands_on=["J9"], conn="I2C1 off J9.2/J9.3, addr 0x29",
        needs_board_change=None, gbp=6, status="later",
        ma_5v=20, counted=True,
        note="MOUNT SETTLED 2026-09-04: fore or aft of the battery on the top plate. The "
             "battery overhangs the plate in WIDTH (47 vs 42.50 mm, 2.25 mm per side) but "
             "not in LENGTH - 138 mm on a 160.26 mm plate leaves 22.26 mm. Needs >=11.5 mm "
             "clearance from the 48 mm battery wall to keep the 27 deg cone clear, so the "
             "battery must sit at ONE end rather than centred (centred gives 11.13 mm per "
             "end, 0.4 mm short). Moving 615 g of 1123 g AUW by 11.13 mm shifts CG 6.1 mm; "
             "displace it AWAY from the existing +3.1 mm offset and CG improves to -3.0 mm"),
    "lidar_360": dict(
        what="LDROBOT LD06, 12 m, INDOOR ONLY", lands_on=["J11"], conn="SERIAL2 (USART1) on J11",
        # PRICE, THIRD AND FINAL CORRECTION. The history matters because this figure
        # decides the purchase and it has been wrong in both directions:
        #   GBP 19  - from a superseded "~GBP 15 AliExpress" line
        #   GBP 100 - docs/BUYING.md's ~$99-131, which moved it to DO NOT BUY YET
        #   GBP 13.99 - RESOLVED 2026-09-05 against a real listing (eBay 395159855374,
        #               Okdo Lidar Hat kit, >1000 sold), recorded in OFFBOARD['lidar']
        # This dict kept the 100 while OFFBOARD carried the resolved 13.99, so the two
        # halves of the same part disagreed by 7x and docs/MODULES.md - which is
        # GENERATED from here - faithfully published the retracted number.
        # Read it from the one place that resolved it.
        needs_board_change=None, gbp=OFFBOARD["lidar"]["gbp"], status="later",
        ma_5v=180, counted=False,
        note="[D] 180 mA running, but 300 mA at START-UP - the surge is what matters on a "
             "653 mA of rail headroom. 33.30 mm tall against 28.5 mm of belly at the old 25 mm "
             "skid drop - SKID['drop'] is now 40 mm, giving 10.20 mm of ground clearance. "
             "NOT in check_build.LOADS_5V, which "
             "budgets an 8x VL53L1X ring instead of this"),
    "rc_link": dict(
        what="ELRS 2.4 GHz, ESP-based", lands_on=["J5"], conn="JST-SH 4P on J5 (USART6)",
        needs_board_change=None, gbp=12, status="fitted",
        ma_5v=100, counted=True,
        note="MAVLink downlink caps at 1470 B/s - carries telemetry, never video"),
    "soop_tuner": dict(
        what="SoOP RF front end - the point of the project",
        lands_on=["TP9", "TP10", "TP11", "P44"], conn="solder pads (I/Q ADC pair, RSSI, PPS)",
        needs_board_change=None, gbp=70, status="later",
        ma_5v=0, counted=True,
        note="a reflash plus a bought tuner, NOT a fabrication run. "
             "The tuner is laptop-side and takes no current from this rail"),
    "fpv": dict(
        what="5.8 GHz camera + VTX, 25 mW EIRP", lands_on=["P41", "P46"],
        conn="+5V / GND pads",
        needs_board_change=None, gbp=25, status="later",
        ma_5v=300, counted=False,
        note="a 25 mW AIO runs off the +5V rail, so it does NOT need the unroutable 9 V "
             "block. NOTE there is no VBAT pad on this board - anything wanting 7-26 V "
             "takes it from the battery harness, off-board"),
    "rec_camera": dict(
        what="XIAO ESP32-S3 Sense, records to its own SD", lands_on=["P41", "P46"], conn="two wires, +5V/GND",
        needs_board_change=None, gbp=14, status="later",
        ma_5v=250, counted=False,
        note="0.25 A against 0.41 A headroom; can also run standalone on a 1S cell, "
             "which is the right answer if anything else is on the rail"),
    "flow_globalshutter": dict(
        what="global-shutter flow via a companion",
        lands_on=["P71", "P72", "P73", "P74"],
        conn="SERIAL6 (UART4) pads, MAVLink OPTICAL_FLOW",
        needs_board_change=None,
        gbp=60, status="later",
        ma_5v=0, counted=True,
        note="FLOW_TYPE 5 (MAVLink) - the companion does the vision, the H7 just consumes "
             "it. Runs from its OWN BEC: a Linux SBC's transients do not belong on the "
             "flight controller's buck. MOVED FROM SERIAL1 TO SERIAL6 on 2026-09-14: J4 "
             "was cut in the re-layout and this was recorded as 'needs a new board with a "
             "UART7 socket', which was wrong. UART4 already comes out on P71-P74 as 5 V, "
             "TX, RX and GND, routed, and design.PAYLOAD lists it as the unclaimed "
             "expansion UART. With PPS on P44 that is a complete five-wire companion "
             "interface on pads that already exist. Set SERIAL6_PROTOCOL 2 (MAVLink2) "
             "and SERIAL6_BAUD to match the companion"),
    "flow_pmw3901": dict(
        what="PixArt PMW3901 flow", lands_on=[], conn="SPI3 - no socket on this board",
        needs_board_change="U6 is deleted and SPI3 carries only the W25Q128 flash, so "
                           "re-fitting on-board flow WOULD NEED A NEW BOARD: a SPI3 "
                           "socket plus a PD4 re-assignment",
        gbp=12, status="blocked",
        ma_5v=0, counted=True,
        note="U6 is deleted - it faced the ESC and could never see the ground, "
             "and correlation flow of that class fails over grass anyway. MAVLink flow "
             "from the companion (flow_globalshutter) is the supported path"),
    "vtx_9v_rail": dict(
        what="on-board 9 V buck for a VTX", lands_on=[], conn="BUCK9_PH",
        needs_board_change="none - L5 sits on F.Cu beside U18, closing the switch-node "
                           "loop, so the rail is routable; populate U18/L5/C68/C69/C70 to use it",
        gbp=0, status="dnp",
        ma_5v=0, counted=True,
        note="was DNP in an earlier draft because BUCK9_PH was unroutable with L5 on the "
             "other face. The loop is fixed; the rail stays DNP because the 25 mW VTX runs from +5V "
             "and nothing on this build wants 9 V"),
    "src": "[M] every lands_on asserted against real footprints by tools/check_modules.py",
}


# ---------------------------------------------------------------------------
# RF_BENCH - the T3b self-interference measurements, and the gate on them.
#
# This is the least-verified risk in the project and the one most likely to end
# it: a 1616-1626.5 MHz receiver working at -110 to -120 dBm, bolted to an
# airframe carrying two switchers, a 60 A ESC and a 2.4 GHz transmitter. ESC
# switching noise is documented in the 1-2 GHz band, which is exactly where
# Iridium lives.
#
# NOTHING here can be computed. Each entry is a slot for a MEASURED number, and
# tools/check_rf.py refuses to report ready-to-FLY (as distinct from the
# ready-to-ORDER that preflight reports) until they are filled in.
#
# The steps are ordered so that each degradation names its own culprit - that
# ordering IS the experiment, so they must be recorded in order.
# ---------------------------------------------------------------------------
RF_BENCH = dict(
    results="fab/rf-bench-results.json",
    band_mhz=(1616.0, 1626.5),
    steps=[
        ("baseline", "SAWbird+ IR + RTL-SDR + patch, outdoors, clear sky, AIRCRAFT OFF",
         "the reference. Needs no aircraft - do it the week the SDR parts arrive"),
        ("board_powered", "board powered, motors off, same position and same sky",
         "any drop is the flight controller: its two switchers and the H7"),
        ("motors_spinning", "motors spinning, props off, tethered",
         "any further drop is the ESC and the four motor leads acting as antennas"),
        ("elrs_tx", "ELRS transmitting",
         "isolates front-end desense from the control link"),
    ],
    # Fields each step must carry. bursts_per_min is the headline; without a noise
    # floor a burst count cannot be interpreted, and without the sky condition two
    # sessions are not comparable - so all four are mandatory.
    fields=("bursts_per_min", "noise_floor_dbm", "utc", "sky"),
    # A step keeping this fraction of baseline bursts is a pass. NOT a datasheet
    # figure and not measured - it is the point below which the link budget stops
    # closing often enough to bound drift, and it is the number to revisit first
    # once real data exists.
    min_fraction_of_baseline=0.5,
    mitigations=["antenna placement and separation", "ferrites on the motor leads",
                 "shielding the SAWbird",
                 "keep the SDR off the airframe entirely - the receive chain is "
                 "laptop-side, so this board allows it"],
    src="[A] min_fraction_of_baseline is a judgement call; every other field is a slot "
        "for an [M]easured value recorded by docs/BUILD.md T3b",
)


# ---------------------------------------------------------------------------
# RAIL_5V - what is actually left on the +5 V rail, and why it is not 1.8 A.
#
# CORRECTED 2026-09-04. Five places in this file and one in docs/HARDWARE.md
# claimed "1.8 A of headroom". That number came from
#
#     Isat 2.4 A  -  the board's own 620 mA  =  1.78 A
#
# which is wrong twice over, and wrong in this repo's signature way - measuring
# something ADJACENT to the property that matters:
#
#   1. Isat (2.4 A) is a SATURATION figure - the point at which the core stops
#      being an inductor. The limit that governs a continuous load is Irms
#      (1.6 A), a THERMAL rating. Budgeting a steady load against Isat is
#      budgeting against the wrong failure mode entirely.
#   2. It subtracted only the board's own 620 mA, ignoring every other load
#      check_build.py's LOADS_5V already counts - the rangefinder, the ToF ring,
#      the mux and the LED strip. INDUCTOR_LOAD_A["L2"] has said 1.19 A all along.
#
# The honest figure is Irms minus the fully-fitted load. It is tight, and it is
# the reason the modularity map cannot promise every 5 V module at once.
# ---------------------------------------------------------------------------
RAIL_5V = dict(
    irms_a=1.6,          # [D] FNR4030S100MT, C167879 - the THERMAL limit, and the budget
    isat_a=2.4,          # [D] saturation - a transient limit, NOT a load budget
    fitted_load_a=0.947,  # [M] sum of check_build.LOADS_5V; = INDUCTOR_LOAD_A["L2"]
    headroom_a=1.6 - 0.947,
    # THIS NOTE NAMED THE WRONG PART AND THE WRONG OUTCOME. It read "L2 is ALSO an
    # unresolved defect: a 4.0x4.0x3.0 mm part on a 3.2x2.5 mm 1210 land.
    # check_ratings.py fails on it deliberately." Both halves are false against the
    # current design: L2 is on L_APV_ANR4030, the correct 4x4 land, and it is L5 that
    # sits on L_1210_3225Metric. check_ratings.py does not fail on either - it emits a
    # note, "C167879's terminal overhangs the pad by 0.18 mm in Y - solderable, check
    # the fillet". A warning about a checker failing, when that checker passes, is worse
    # than no warning: it trains the reader to discount the tool.
    note="L5 (the 9 V VTX buck's inductor, DNP on this build) sits on a 1210 land while "
         "C167879 is a 4.0x4.0x3.0 mm part, so its terminal overhangs by 0.18 mm in Y. "
         "check_ratings.py reports this as a note, not a failure - it is solderable, and "
         "the fillet is what to inspect. L2, the fitted +5 V inductor, is on the correct "
         "L_APV_ANR4030 land. Do not 'fix' L5 by swapping in a part the 1210 land takes "
         "but the current does not.",
    src="[D] Irms/Isat from the FNR4030S100MT datasheet; [M] fitted_load_a is the sum "
        "of tools/check_build.py LOADS_5V, independently equal to INDUCTOR_LOAD_A['L2']",
)

# The payload breakout quotes the +5 V headroom. It used to carry its own copy (0.413),
# frozen at the value RAIL_5V had before the WS2812 row was corrected. One derivation.
PAYLOAD_BREAKOUT["headroom_a"] = RAIL_5V["headroom_a"]
