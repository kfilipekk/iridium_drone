#!/usr/bin/env python3
"""NAVCORE-SoOP — single source of truth for components and nets."""

R  = "Device:R";  C  = "Device:C";  L = "Device:L"; FB = "Device:FerriteBead"
LED = "Device:LED"; SW = "Switch:SW_Push"; XTAL = "Device:Crystal_GND24"

F_R0402  = "Resistor_SMD:R_0402_1005Metric"
F_R0603  = "Resistor_SMD:R_0603_1608Metric"
F_C0402  = "Capacitor_SMD:C_0402_1005Metric"
F_C0805  = "Capacitor_SMD:C_0805_2012Metric"
F_C1206  = "Capacitor_SMD:C_1206_3216Metric"
F_L1210  = "Inductor_SMD:L_1210_3225Metric"
# Power-inductor lands, sized to the parts that actually go on them.
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
 # C5271084 is STM32H743VIT6TR - the same silicon and the same LQFP-100 package, in
    "U1" : ("jlc_parts:STM32H743VIT6_C114409", "jlc:LQFP-100_L14.0-W14.0-P0.50-LS16.0-BL", "STM32H743VIT6", "C5271084", False),
 "U2" : ("jlc_parts:ICM-42688-P",           "jlc:LGA-14_L3.0-W2.5-P0.50-TL",            "ICM-42688-P",   "C1850418", False),
 "U3" : ("jlc_parts:ICM-42605",             "jlc:LGA-14_L3.0-W2.5-P0.50-TL",            "ICM-42605",     "C2655099", False),
 "U4" : ("jlc_parts:MS561101BA03-50",       "jlc:SENSORS-SMD_MS5611-01BA03",            "MS5611",        "C15639",   False),
 "U5" : ("jlc_parts:W25Q128JVSIQTR",        "jlc:SOIC-8_L5.3-W5.3-P1.27-LS8.0-BL",      "W25Q128JVSIQ",  "C97521",   False),
 # ---- power ----
 # U8 is A TI LMR33630ARNXR (VQFN-12 HotRod, RNX), swapped in PLACE.
 "U8" : ("jlc_parts:LMR33630ARNXR",         "jlc:VQFN-12_L3.0-W2.0-P0.65-BL_TI_RNX",    "LMR33630A",     "C2861505",  False),
 "U9" : ("jlc_parts:AP2112K-3_3TRG1",       "jlc:SOT-25-5_L2.9-W1.6-P0.95-LS2.8-BL",    "AP2112K-3.3",   "C51118",   False),
 "U10": ("jlc_parts:TLV75533PDBVR",         "jlc:SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR",    "TLV75533",      "C404027",  False),
 # ---- io ----
 "U11": ("jlc_parts:SN65HVD230DR",          "jlc:SOIC-8_L4.9-W3.9-P1.27-LS6.0-BL",      "SN65HVD230",    "C12084",   False),
 "U12": ("jlc_parts:USBLC6-2SC6_C2687116",  "jlc:SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL",    "USBLC6-2SC6",   "C2687116", False),
 "J1" : ("jlc_parts:TYPE-C_16PIN_2MD(073)", "jlc:USB-C-SMD_TYPE-C-16PIN-2MD-073",       "USB-C",         "C2765186", False),
 "J2" : ("jlc_parts:SM08B-SRSS-TB(LF)(SN)", "jlc:CONN-TH_SM08B-SRSS-TB-LF-SN",                "ESC 8P",        "C160407",  False),
 "J3" : ("jlc_parts:XY-SM06B-GHS-TB",       "jlc:CONN-SMD_XY-SM06B-GHS-TB",            "GPS+I2C",       "C51940119",False),
 "J5" : ("jlc_parts:SM04B-SRSS-TB_(LF)(SN)","jlc:CONN-SMD_4P-P1.00_SM04B-SRSS-TB-LF-SN","RC IN",         "C160404",  False),
 "J6" : ("jlc_parts:SM04B-SRSS-TB_(LF)(SN)","jlc:CONN-SMD_4P-P1.00_SM04B-SRSS-TB-LF-SN","CAN 4P",        "C160404",  False),
 "J7" : ("jlc_parts:XY-SM04B-GHS-TB",       "jlc:CONN-SMD_4P-P1.25_12502-04WASMT",            "RNGFND",        "C51940118",False),
 "J8" : ("jlc_parts:TF-01A",                "jlc:TF-SMD_TF-01A",                        "microSD",       "C91145",   False),
 # Y1 is a passive crystal and the part number matters more than it looks.
 "Y1" : ("jlc_parts:X32258MSB4SI",          "jlc:CRYSTAL-SMD_4P-L3.2-W2.5-BL",          "8MHz",          "C2682774", False),
 "D1" : ("jlc_parts:SMBJ22A_C113993",          "jlc:SMB_L4.6-W3.6-LS5.3-RD",                          "SMBJ22A",       "C113993",False),
 # ---- SoOP receiver. The tuner half is fitted - the H743 does the Doppler on
 "U13": ("jlc_parts:MAX2112ETI+T",          "jlc:TQFN-28_L5.0-W5.0-P0.50-BL-EP3.3",      "MAX2112",       "C596391",  False),
 "U14": ("jlc_parts:OPA2374M{slash}TR",     "jlc:SOP-8_L4.9-W3.9-P1.27-LS6.0-BL",       "OPA2374",       "C444392",  False),
 "U15": ("jlc_parts:PSA4-5043+",            "jlc:SOT-343-4_L2.0-W1.3-P1.30-LS2.1-BR",           "PSA4-5043+",    "C5240848", True),
 "U16": ("jlc_parts:PSA4-5043+",            "jlc:SOT-343-4_L2.0-W1.3-P1.30-LS2.1-BR",           "PSA4-5043+",    "C5240848", True),
 # Y2 is an active 4-pad clipped-sine TCXO feeding U13's reference through C58.
 "Y2" : ("jlc_parts:T132S4-25000ML33DTL",     "jlc:OSC-SMD_4P-L3.2-W2.5-BL",              "25MHz TCXO",    "C5563878", False),
 "FL1": ("jlc_parts:TA1575IG",                   "jlc:FILTER-SMD_6P-L3.0-W3.0-P1.19-TR",                       "SAW 1620MHz",   "",         True),
}

def add(ref, sym, fp, val, lcsc="", dnp=False):
    COMPONENTS[ref] = (sym, fp, val, lcsc, dnp)

# passives ---------------------------------------------------------------
_p = []
def RES(ref, val, fp=F_R0402, dnp=False): add(ref, R, fp, val, "", dnp); _p.append(ref)
def CAP(ref, val, fp=F_C0402, dnp=False): add(ref, C, fp, val, "", dnp); _p.append(ref)
# The default land is the 4x4 one, not F_L1210.
def IND(ref, val, fp=F_ANR4030, dnp=False): add(ref, L, fp, val, "", dnp); _p.append(ref)

# MCU decoupling: one 100n per VDD pin + bulk
for i, r in enumerate(["C1","C2","C3","C4","C5"]): CAP(r, "100n")
CAP("C6", "4u7", F_C0805); CAP("C7", "4u7", F_C0805)
CAP("C8", "2u2", F_C0402); CAP("C9", "2u2", F_C0402)     # VCAP1/2
CAP("C10","100n"); CAP("C11","1u")                        # VDDA
CAP("C12","100n"); CAP("C13","1u")                        # VREF+
CAP("C14","100n")                                         # NRST
Y1_CL_PF        = 20.0
Y1_STRAY_PF     = 5.0
Y1_CL_CONFIRMED = True
# LCSC codes known to be passive crystals in this footprint.
Y1_PASSIVE_LCSC = {"C2682774"}      # X32258MSB4SI, YXC, CL 20 pF, 120 ohm ESR

# ---- regulator enable thresholds, and what the input rail is allowed to reach -------
EN_THRESHOLD_V = {
    "TPS54331": (1.25, True, "[D] TI TPS54331 datasheet"),
    "TPS54202": (1.21, True, "[D] SLVSD26 5.5 Electrical Characteristics, V(EN_RISING) "
                             "typ 1.21 V (max 1.28); the same 1.21 V is used in the "
                             "datasheet's own UVLO equations, 6.3.5. "
                             "docs/datasheets/TPS54202-SLVSD26.pdf"),
    "LMR33630A": (1.231, True, "[D] SNVSAN3F 7.5 Electrical Characteristics, VEN-H rising "
                               "1.2 / 1.231 / 1.26 V, hysteresis 100 mV. Note VEN-VCC "
                               "(the internal-LDO turn-on) rising is only 1.0 V, so the "
                               "lower threshold governs start-up. "
                               "docs/datasheets/LMR33630-SNVSAN3F.pdf"),
}

VBAT_PART_VMAX = {
    "LMR33630A": (36.0, 38.0, True,
                  "[D] SNVSAN3F 7.1 Absolute Maximum Ratings, VIN to PGND -0.3 to 38 V; 7.3 "
                  "Recommended Operating Conditions, VIN 3.8-36 V. "
                  "docs/datasheets/LMR33630-SNVSAN3F.pdf"),
    "WST4041": (30.0, 40.0, True,
                "[D] WST4041 WINSOK datasheet: VDS -40 V, VGS +-20 V absolute max "
                "(docs/datasheets/WST4041_WINSOK.pdf)"),
}

# Transient-suppressor clamping voltage at the datasheet's peak pulse current.
# ---- the 3.3 V rails: loads, and the LDOs that have to drop 1.7 V to make them ------
LDO_DROP_V = 5.0 - 3.3

LOADS_3V3 = [   # through U9, AP2112K-3.3
    ("STM32H743 core + IO at 480 MHz", 0.240, 0.240, "[A] docs/HARDWARE.md budget row, "
                                                     "less the sensors that are on +3V3A"),
    ("W25Q128 config flash",           0.004, 0.025, "[D] W25Q128JV: ~4 mA read, 25 mA "
                                                     "during program/erase"),
    # Not zero continuous.
    ("microSD card (logging)",         0.040, 0.100, "[A] ~40 mA average while ArduPilot "
                                                     "logs; [D] 100 mA write peak"),
    # U11 (CAN) runs from +3V3_CAN through U21, not from this rail.
    ("status LEDs D2/D3",              0.010, 0.010, "[A] 2 x ~5 mA through their resistors"),
    ("TMP119 temp sensor (U19)",       0.000, 0.000, "[D] TMP119: 3.5 uA active, "
                                                     "1.25 uA at the 1 Hz default rate"),
]
LOADS_3V3A = [  # through U10, TLV75533
    ("ICM-42688-P",                    0.001, 0.002, "[D] ~0.88 mA 6-axis continuous"),
    ("ICM-42605",                      0.001, 0.002, "[D] ~0.75 mA 6-axis continuous"),
    ("MS5611 barometer",               0.001, 0.002, "[D] 1.4 mA peak during conversion"),
    # The SoOP receiver.
    ("MAX2112 tuner (U13)",            0.100, 0.100, "[D] MAX2112 Rev 3: 100 mA supply "
                                                     "current, VCC 3.3 V"),
    ("OPA2374 baseband amps (U14)",    0.002, 0.002, "[D] OPA2374: 585 uA per amplifier"),
    ("25 MHz TCXO (Y2)",               0.002, 0.002, "[L] JLCPCB C22381771: 3.3 V, "
                                                     "clipped sine, ~2 mA"),
]

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
    "SMBJ26A": (42.1, 26.0, 28.9, 14.3, "[D] Littelfuse SMBJ series datasheet"),
    "SMBJ24A": (38.9, 24.0, 26.7, 15.4, "[D] Littelfuse SMBJ series datasheet"),
    "SMBJ22A": (35.5, 22.0, 24.4, 16.9, "[D] Littelfuse SMBJ series datasheet; JLCPCB C113993 "
                                         "lists Vrwm 22 V, Vc 35.5 V"),
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
CAP("C21","100n")                                          # boot cap
IND("L2", "10uH", F_ANR4030)   # 4x4 land - the FNR4030 never fitted a 1210
CAP("C22","22u", F_C1206); CAP("C23","22u", F_C1206)      # 5V out
CAP("C78","1u")                                           # U8 VCC bypass, pin 5
RES("R6","10k2"); RES("R7","3k24")                         # -> overridden, see _VALUE_FIX
# R8/C24/C25 COMP network deleted - TPS54202 compensates internally

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

# CAN
CAP("C41","100n")                                          # HVD230 VCC, on +3V3_CAN below
RES("R14","10k")                                           # HVD230 Rs slope
RES("R15","120R")                                          # termination (DNP by default)
COMPONENTS["R15"] = (R, F_R0402, "120R", "", True)

# USB
RES("R16","5k1"); RES("R17","5k1")                         # CC1/CC2
CAP("C42","1u", F_C0805)                                   # VBUS

# battery sense
RES("R18","10k", F_R0603); RES("R19","1k")                  # 11:1 divider (R18 is 0603 for 6S 100mW headroom)
CAP("C43","100n"); CAP("C44","100n")                       # V/I sense filters

# LEDs + buzzer
RES("R20","1k"); RES("R21","1k")
add("D2", LED, F_LED, "BLUE"); add("D3", LED, F_LED, "GREEN")
add("SW1", SW, F_SW, "BOOT"); add("SW2", SW, F_SW, "RESET")

# microSD
CAP("C45","10u", F_C0805); CAP("C46","100n")
for i,(r) in enumerate(["R22","R23","R24","R25","R26","R27"]): RES(r, "47k")  # SDMMC pullups

# RF section passives.
for r,v in [("C49","100n"),("C50","100n"),("C51","1u"),
            ("C52","100p"),("C56","100p"),("C57","100n")]:
    CAP(r, v, F_C0402)
for r,v in [("R28","0R"),("R29","0R"),("R31","4k7"),
            ("R34","330R"),("R35","1k"),("R36","4k7"),("R37","4k7")]:
    RES(r, v, F_R0402)
CAP("C58","10n", F_C0402)     # series DC-cut, Y2 output -> U13 XTAL [D] TCXO: 0.01 uF min
CAP("C59","100n", F_C0402)
# ------------------------------------------------------------- connector orientation
MATING_FACE = {
    "J1": (0.0, +1.0),   # USB-C          - plug inserts along -y toward the board
    "J2": (0.0, +1.0),   # ESC JST-SH 8P
    "J3": (0.0, +1.0),   # GPS/I2C JST-GH 6P
    "J8": (0.0, +1.0),   # microSD card slot
    "J5": (0.0, +1.0),   # RC receiver JST-SH 4P
    "J6": (0.0, +1.0),   # DroneCAN JST-SH 4P
    "J9": (0.0, +1.0),   # I2C port (VCC/SCL/SDA/GND) - the dedicated bus
    "J11": (0.0, +1.0),  # SERIAL2 lidar port (5V/TX/RX/GND)
    "J14": (0.0, +1.0),  # SPI3 Optical Flow JST-SH 6P
    "J15": (0.0, +1.0),  # WS2812 RGB LED JST-SH 3P
    "J16": (0.0, +1.0),  # Buzzer JST-SH 2P
    "J17": (0.0, +1.0),  # TVC Servos / Actuator Header JST-SH 6P
    "J18": (0.0, +1.0),  # Pyrotechnic deployment JST-SH 2P
    "J19": (0.0, +1.0),  # SWD Debug JST-SH 4P
    "J20": (0.0, +1.0),  # Lander Touchdown microswitch JST-SH 2P
}

# How much straight, clear space the plug needs in front of the mating face, in mm.
MATING_CLEARANCE = {
    "J1": 9.0,    # USB-C plug overmould
    "J2": 6.0,    # JST-SH plug plus wire bend
    "J5": 6.0,    # JST-SH class, same as J2
    "J6": 6.0,    # JST-SH class, DroneCAN
    "J9": 6.0,    # JST-SH class, same as J2 (the dedicated I2C port)
    "J11": 6.0,   # JST-SH class, same as J2 (SERIAL2 lidar port)
    "J14": 6.0,   # JST-SH class, Optical Flow
    "J15": 6.0,   # JST-SH class, WS2812 LED
    "J16": 6.0,   # JST-SH class, Buzzer
    "J17": 6.0,   # JST-SH class, TVC Servos
    "J18": 6.0,   # JST-SH class, Pyro
    "J19": 6.0,   # JST-SH class, SWD
    "J20": 6.0,   # JST-SH class, Touchdown
    "J3": 3.6,
    "J8": 14.0,   # a microSD card must come all the way out
}

# ----------------------------------------------------------------- vertical mating
# Connectors that mate along +z instead of across the board.
VERTICAL_MATING = {
    "J12": dict(
        plug=2.2,    # mated plug height above the board, [D] Hirose U.FL-R-SMT-1
        bend=3.0,    # 90-degree coax bend radius above the plug, [D] RG178 bend radius
        radius=4.0,  # horizontal sweep the bend needs around the connector centre, mm
        src="[D] Hirose U.FL-R-SMT-1 vertical + RG178 coax bend"),
}


# ---- parts that must see something, not merely fit -------------------------------
GROUND_FACING = {
}

CAMERA = dict(name="OV9281 global-shutter module", mod_w=30.0, mod_t=12.0,
              lens_dia=8.0, lens_len=3.5,
              src="[D] Arducam B0162 module; [A] mount position undecided")
BELLY_SENSOR = dict(
    # Derived, not a literal.
    depth_available_mm=None,        # filled in below, once SKID exists - see the note
    typical_module_h=12.0,          # [L] TFS20-L / 3901-L0X class
    # Plan footprint of the bracketed module, for the CAD.
    l_mm=36.0, w_mm=16.0,
    occupant="Benewake TFS20-L (downward rangefinder, I2C 0x10 on J3)",
    future="a Matek 3901-L0X would take this slot and REPLACE the TFS20-L, since it "
           "carries its own VL53L0X - one module, one cable, flow AND range",
    mount="printed bracket under the bottom plate; needs a clear cone to the ground and "
          "must stay above the skid contact line so a landing does not crush it",
    src="[M] depth computed from design.SKID; [M] the 12 mm module envelope at this "
        "position passes check_cad_fit's ground clearance with 31.50 mm of margin")

PAYLOAD_BREAKOUT = dict(
    harness="2 wires: P41 (+5V) and P46 (GND) to the XIAO's 5V and GND pins",
    connector="optional 2-pin JST so the camera pod unplugs",
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

# A XIAO ESP32S3 Sense on the nose, writing to its own microSD.
CAMERA_REC = dict(name="XIAO ESP32S3 Sense", L=21.0, W=17.5, H=13.0, g=6.0,
                  power="5V", current_a=0.25, storage="microSD <=32GB FAT32",
                  fw="ESP32-CAM_MJPEG2SD, ~20 fps AVI",
                  mount="nose; SO1-V6-AN-Cam-Mount.stl is 62.6 x 28.8 and made for a "
                        "19x19 analogue cam, so it needs a simple printed bracket",
                  radio_off=True,
                  # How far forward of centre it sits, in mm.
                  nose_y_mm=78.0,
                  src="[D] Seeed: XIAO form factor 21 x 17.5 mm, OV2640/OV3660, microSD, "
                      "8 MB PSRAM; [L] ~GBP 10-14 AliExpress; [A] 13 mm stacked height "
                      "and 6 g with the Sense expansion - MEASURE ON ARRIVAL")

# ---- the MOTOR / ARM / SKID bolt pattern - one number, one home -------------------
MOTOR_JOINT = dict(
    pitch_mm=19.0,          # [D] BrotherHobby Avenger 2806.5: M3 at 19 x 19
    screw="M3",             # [D] same source
    screw_dia=3.0,
    # What the screw passes through, head first, and the hole it passes through in each.
    layers=(
        ("frame arm", ("FRAME", "arm_t"), 3.2,
         "[D] So1-V6 arm 6.0 mm; [A] 3.2 mm hole - the frame's motor holes are published "
         "as the 19x19 PATTERN, not as diameters"),
        ("printed skid", ("SKID", "t"), 3.2,
         "[M] design.SKID - printed, so the hole is ours to specify; 3.2 mm is standard "
         "M3 close clearance for a 3.0 mm screw"),
    ),
    engages="motor tapped boss",
    tap_dia=3.0,
    engage_mm=4.0,          # [A] 1 x diameter for M3 in aluminium - see fasteners.py
    boss_depth_mm=None,     # not published anywhere - see the overshoot warning below
    src="[D] BrotherHobby Avenger 2806.5 product data (M3, 19x19); "
        "[M] arm and skid thicknesses referenced from this file",
)


def fmt_pattern(pitches_mm):
    """(16.0, 19.0) -> '16x16 / 19x19', for doc tables and check messages."""
    return " / ".join(f"{p:.0f}x{p:.0f}" for p in sorted(pitches_mm))

# The skid is a part you print, so it has no marketplace page and never will.
SKID = dict(t=3.5, drop=40.0, hole_pitch=MOTOR_JOINT["pitch_mm"], printed=True,
            # Drop raised 25 -> 40 mm to give the LD06 a home.
            src="[D] 19x19 pitch is the motor's bolt pattern (BrotherHobby Avenger); "
                "[M] 3.5 mm thickness is a design choice for a printed part; "
                "[M] 40 mm drop DERIVED from the LD06's datasheet height plus margin - "
                "see BELLY_SENSOR and OFFBOARD['lidar']")

# Belly depth is SKID's drop plus its pad thickness, measured from the bottom plate's underside.
BELLY_SENSOR["depth_available_mm"] = SKID["drop"] + SKID["t"]
# The ESC this board bolts to.
TOP_PLATE_MOUNT = dict(
    front_standoff=22.0, rear_standoff=30.0, post_od=5.0,        # [D] tbs: "30 and 22mm"
    front_posts=((-14.6, -27.88), (14.6, -27.88), (-14.6, -52.88), (14.6, -52.88)),
    rear_posts=((-14.6, 27.88), (14.6, 27.88), (-11.0, 80.75), (11.0, 80.75)),
    plate_centre_y=dict(fc=-29.16, bottom=31.09, top=4.78),
    src="[D] cad/frame-dxf.json (So1-V6-7inDC-2025-JUL-07.dxf sha 398556cd), hole "
        "patterns per plate; [D] team-blacksheep.com prod:source1v6 'Standoff height: "
        "30 and 22mm'; [M] 22-on-mid / 30-on-bottom forced by top-plate flatness")


def required_standoff(board, headroom=None):
    """The stack against the top plate the kit actually gives it."""
    top, bot, topref, botref, _ = stack_heights(board, skip_dnp=True)
    below = FRAME["bottom_t"] + FRAME["arm_t"] + FRAME["medium_t"]
    stack = ESC["pcb"] + ESC["parts"] + MOUNTING["gap"] + bot + BOARD_T + top
    front = TOP_PLATE_MOUNT["front_standoff"]
    top_plate_z = below + front
    assert abs(top_plate_z - (FRAME["bottom_t"] + TOP_PLATE_MOUNT["rear_standoff"])) < 1e-6, \
        "22-on-mid and 30-on-bottom no longer meet at one flat top plate"
    return dict(below=below, stack=stack, headroom=front - stack, need=below + stack,
                buy=front, kit=True, top_plate_z=top_plate_z,
                top=top, bot=bot, topref=topref, botref=botref,
                slack=front - stack,
                src="[M] computed from the board + FRAME + ESC + MOUNTING against "
                    "TOP_PLATE_MOUNT (the kit's 22 mm front standoffs on the mid plate)")

BOARD_T = 1.6                       # [M] 6-layer stackup, tools/design.py
STANDOFF_STOCK = (25, 30, 35, 40, 45)   # [L] common M3 aluminium standoff lengths

# The soft mount between this board and the ESC.
MOUNTING = dict(gap=3.0, grommet_d=6.0, screw="M3", screw_dia=3.0,
                hole_d=4.0, plate_hole_d=3.2,
                pitch=30.5,
                src="[A] M3 silicone grommet compressed to 3.0 mm; "
                    "[M] 30.5 mm pitch and 4.0 mm holes from design.BOARD")

ESC = dict(name="SpeedyBee BLS 60A", L=45.6, W=44.0, pcb=1.6, parts=6.2,
           mount=30.5, conn="JST-SH 8P", cells="3-6S", amps=60,
           H=7.8, g=10.5, cont_A=60.0, burst_A=80.0, proto="DSHOT300/600",
           cur_scale_mv_per_A=40.0,
           # The 8-pin JST-SH order as the ESC'S manual documents IT.
           pin_order=("GND", "VBAT", "M1", "M2", "M3", "M4", "CUR", "TEL"),
           src="[D] SpeedyBee BLS 60A manual")
assert ESC["amps"] == ESC["cont_A"], "ESC amps and cont_A are the same rating"

SKATE = dict(name="SO1-V6-skate.stl", L=75.96, W=102.17, t=6.00, drop=6.00,
             printable=True,
             note="flat underside wear plate, NOT a landing leg - 6 mm clearance",
             src="[M] bounding box parsed from the STL published at "
                 "github.com/tbs-trappy/source_one, 2026-09-02")

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
# Radxa Zero 3W.
PI = dict(name="Radxa Zero 3W (1GB) - DEFERRED, not fitted", L=65.0, W=30.0, t=1.2,
          hole_dia=2.75, hole_pitch=None,
          soc="RK3566 quad Cortex-A55 @ 1.6 GHz",
          power_a=2.0,
          g=12.0,
          csi="J7, FPC-22P-0.5mm, 4-lane MIPI CSI - the same connector as a Pi Zero, so "
              "a 22-to-15-pin Zero cable mates a 15-pin OV9281 module",
          src="[D] radxa.com/docs: 65 x 30 mm, 1x4-lane MIPI CSI, 5V/2A; "
              "[D] radxa_zero_3w_v1.12_schematic.pdf for the CSI connector; "
              "[U] mounting hole pattern NOT published by Radxa - measure the board")

# The aircraft flies without it - see FLOW below.
FLOW = dict(
    fitted=False,
    camera="OV9281 global shutter, 22-pin CSI - NOT ordered in this pass",
    arrives_as="MAVLink OPTICAL_FLOW from the companion, FLOW_TYPE 5",
    onboard_fallback="there is no on-board flow part. U6 (PMW3901) was DELETED from the "
                     "design in the Rev B re-layout - the ESC sat 3.0 mm below it and "
                     "would have blocked its view, and correlation sensors of that class "
                     "fail over grass anyway. Do not shop for one: there is no pad.",
    operational_note="EK3_SRC2 and EK3_SRC3 both use VELXY 5 (flow). With no flow fitted "
                     "they have no data, and they are reachable ONLY by the pilot's RC9 "
                     "source-set switch. Do not select source set 2 or 3 in flight until "
                     "a flow source is fitted.",
    src="[M] drift table computed from a = g*sin(theta); [M] flow_only p95 446 m in sitl/")

# The CAMERA interface, and the work it still NEEDS.
CAMERA_IFACE = dict(
    connector="J7 FPC-22P-0.5mm, 4-lane MIPI CSI",
    pwdn_gpio="gpio3 RK_PC6 (CAMERAB_PDN_L, J7 pin 18)",
    i2c="I2C2_M1 on J7 pins 21/22",
    status="NOT WORKING OUT OF THE BOX - needs a kernel rebuild and a custom DT overlay",
    blocking=False,
    src="[D] radxa_zero_3w_v1.12_schematic.pdf; [L] radxa forum thread 26386; "
        "[D] github.com/radxa/overlays has no ov9281 overlay, checked 2026-09-02")

# rejected companions, kept so the questions are not reopened from scratch.
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


STACK_BELOW = [
    ("SpeedyBee BLS 60A ESC", 3.0, 45.6 / 2, 44.0 / 2,
     "[D] SpeedyBee manual + [A] 3.0 mm compressed grommet gap"),
]


# ---- off-board parts, and the interface each one lands on ---------------------------
# Tools/check_purchase.py asserts these.
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
    # Replaces the 8-sensor ToF ring.
    # The rule is therefore conditional on where it flies, not absolute.
    lidar=dict(part="LDROBOT LD06 - 12 m, 25 klux, INDOOR USE ONLY",
               lands_on="SERIAL2 (USART1) - the lidar's TX to TP6 (USART1_RX)",
               wires="TX only; PWM unconnected - the unit self-spins at a default rate",
               # MECHANICAL/ELECTRICAL from the LDROBOT LD06 datasheet, read.
               L_mm=38.59, W_mm=38.59, H_mm=33.30, g=42.0,
               ma_run=180, ma_startup=300, volts=5.0, conn_on_lidar="ZH1.5T-4P",
               # Full [D] spec table, LDROBOT LD06 datasheet:
               range_m=(0.02, 12.0),          # 20 mm blind zone - nothing closer reads
               accuracy_mm=(30, 45),          # typical, max at 70 % target reflectivity
               resolution_mm=15,
               scan_hz=(5, 10, 13),           # min, typical, max - PWM-controlled
               sample_hz=4500,
               angular_res_deg=1.0, angular_err_deg=2.0,
               # The height of the optical window above the mounting base.
               scan_plane_height_mm=None,
    gbp=13.99,
    # Position on the belly, mm aft of centre (negative = aft).
    mount_y_mm=-22.0,     # [A] measure on arrival - see the runbook, Part 4
               # Power comes off the SERIAL6 pad group's 5V/GND pins. That does not claim
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

# ---- payload provisions: what a future module can actually have ---------------------
PAYLOAD = dict(
    pwm=[("PWM5", "PA2", "TP3", "SERVO5_FUNCTION"),
         ("PWM6", "PA3", "TP4", "SERVO6_FUNCTION")],
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
    serial_unrouted=[(1, "UART7"),
                                      # the companion moved to SERIAL6 on P71-P74
                     (4, "USART3"),   # PD8/PD9 stop at the MCU
                     (5, "UART8")],   # declared in hwdef, no nets in the design at all
    serial_earmarked=[(2, "360 lidar, PRX1_TYPE 16"),
                      (6, "companion computer, MAVLink OPTICAL_FLOW - moved from "
                          "SERIAL1 on 2026-09-14 when J4 was cut")],
    power_5v=["P71", "P61", "PL2", "P41", "J5.1", "J9.1", "J11.1"],
    gnd=["P74", "P64", "PL3", "P46", "J5.4", "J9.4", "J11.4"],
    # A servo drawing real current must not come off the flight controller's 5 V rail.
    power_note="signal is 3.3 V logic, which every hobby servo and ESC accepts as a valid "
               "PWM high. Take a high-current servo's 5 V from its own BEC, not from this "
               "board - the rail has only 0.65 A of headroom and a stalled servo eats it",
    mass_budget_g=885.0,   # payload at 40% hover throttle, from check_build
    src="[D] hwdef.dat PWM/SERIAL_ORDER + [M] defaults.parm claims + [M] check_build "
        "power and payload figures")

# ---- the airframe, one source of truth --------------------------------------------

# Tbs source one V5 7" DC - and the reason for it is the provenance, not the geometry.
FRAME = dict(name='TBS Source One V5 7in DC', wb=320.0, size=(200.0, 230.0),
             # 22, not 30.
             inner_h=22.0,
             bottom_t=2.5, medium_t=2.0, upper_t=2.0, arm_t=6.0, cam_plate_t=2.0,
             stack="30.5x30.5 M3 and 20x20 - VERIFIED from the manufacturer DXF",
             # Numeric, not the string "16x16 / 19x19".
             motor_patterns_mm=(16.0, 19.0),
             strap=(20.0, 300.0), price_gbp=35.90, g=143.5,
             src="[D] github.com/tbs-trappy/source_one So1-V6-7inDC-2025-JUL-07.dxf, "
                 "stack patterns parsed directly 2026-09-02; [L] hobbyrc.co.uk for "
                 "standoffs 30/22 mm, plates and 143.5 g; [A] plate outline 200x230 mm "
                 "- overall footprint only, not load-bearing on any check")
assert FRAME["inner_h"] == TOP_PLATE_MOUNT["front_standoff"], \
    "FRAME.inner_h must be the kit's front standoff (TOP_PLATE_MOUNT) - one number"
assert abs(FRAME["arm_t"] + FRAME["medium_t"]
           - (TOP_PLATE_MOUNT["rear_standoff"] - TOP_PLATE_MOUNT["front_standoff"])) < 1e-6, \
    "the two standoff sets stand on plates 8 mm apart and hold one flat top plate"

# The fit question, answered from the DXF - not deferred to calipers.
PLATES = dict(
    fc=(48.50, 106.59), top=(42.50, 160.26), bottom=(48.50, 107.62),
    arm=(31.08, 185.21),
    top_m3_x=(14.60, 11.00), bottom_m3_x=(14.60, 11.00),
    battery_overhang_per_side=(47.0 - 42.50) / 2,
    src="[D] tools/parse_frame_dxf.py -> cad/frame-dxf.json from "
        "So1-V6-7inDC-2025-JUL-07.dxf (sha 398556cd); re-derivable, not a one-off flatten")

FRAME_CAD = dict(
    fc_plate=(48.50, 106.59),
    stack_from_edges=(24.3, 24.2),
    clear_per_side_w=1.70,
    clear_end_l=1.04,
    under_board_holes=[(0.0, 0.0, 10.00), (7.95, -19.76, 4.00), (-7.95, -19.76, 4.00)],
    nearest_standoff_candidate_y=27.90,
    src="[M] parsed from So1-V6-7inDC-2025-JUL-07.dxf, 2026-09-02")
# Weight and bolt pattern are from BrotherHobby's own Avenger 2806.5 product data.
MOTOR = dict(name="2806.5 1300KV", kv=1300, g=41.0, thrust_g=1250,
             hole_pitch_mm=MOTOR_JOINT["pitch_mm"],
             shaft_thread="M5", poles="12N14P",
             # Body envelope, for the CAD.
             dia_mm=28.0, h_mm=15.0,
             src="[D] 41 g, M3 19x19, M5 prop adapter thread, 12N14P "
                 "(BrotherHobby Avenger product data); [A] 1250 g thrust; "
                 "[D] 28 mm body from the 2806.5 stator designation, [A] 15 mm bell height")
BATT = dict(name="Zeee 4S 6500mAh", L=138, W=47, H=48, g=615, conn="EC5", hard=True,
            cells=4, src="[L] retailer listing")
# The ESC, the smoke stopper and the pigtails are all XT60.
POWER_CONN = dict(airframe="XT60", pack=BATT["conn"], adapter_needed=True,
                  src="[L] Zeee hardcase packs ship EC5; [D] SpeedyBee BLS 60A is XT60")
# Confirmed against the manufacturer, not a marketplace listing.
PROP = dict(name="7040", dia_mm=178.43, g=7.9, bore_mm=5.0, mount="M5",
            src="[D] Gemfan Flash 7040-3 published spec: 5 mm centre hole, 178.43 mm "
                "disc, 7.9 g, PC. Bore matches the [D] M5 motor shaft. A different "
                "brand of 7040 may differ in mass; the 5 mm bore is universal for 7in")


# ---- mass, one source of truth ----------------------------------------------------
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
# derived now, so it cannot disagree with check_build again.
PAYLOAD["mass_budget_g"] = max(0.0, THRUST_G * 0.4 - AUW_G)


# ---------------------------------------------------------------------- nets
# Pins may be given by number or by name ("U1.PA5"); the resolver handles both.
NETS = {}
def net(name, *pins): NETS.setdefault(name, []).extend(pins)

# ---- power rails -------------------------------------------------------
net("GND",
    "U1.10","U1.26","U1.49","U1.74","U1.99","U1.19",           # VSS + VSSA
    "U2.6","U3.6","U4.3","U5.4",
    # Pin 7 of both IMUs.
    "U2.7","U3.7",
    "U8.1","U8.6","U8.11","U9.2","U10.2","U11.2","U12.2",   # U8: PGND 1/11 + AGND 6
    "J1.A1B12","J1.B1A12","J1.13","J1.14",
    "J2.1","J2.9","J2.10", "J3.6","J3.7","J3.8",
    "J5.4","J5.5","J5.6", "J6.4","J6.5","J6.6", "J7.4","J7.5","J7.6",
    "J8.6","J8.10","J8.11","J8.12","J8.13",
    "Y1.2","Y1.4", "D1.2",
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
net("VBAT_IN", "J2.2", "D1.1", "Q4.3")            # D1 pin 1 = cathode; Q4 pin 3 = drain
net("VBAT", "Q4.2", "C17.1","C18.1","C19.1","U8.2","U8.10","R4.1","R18.1")  # Q4 p2 = source
net("+5V",  "C22.1","C23.1","U9.1","C26.1","U10.1","C28.1",
            "J3.1","J5.1","J7.1","R6.1")
net("+3V3", "U9.5","C27.1","U1.11","U1.27","U1.50","U1.75","U1.100",
            "C1.1","C2.1","C3.1","C4.1","C5.1","C6.1","C7.1",
            "U5.8","C36.1",
            "J8.4","C45.1","C46.1","L1.1",
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
# ESC telemetry travels ESC -> FC, so it has to land on a receive pin.
net("ESC_TEL","J2.8","U1.PE0")                                  # UART8_RX <- BLHeli_32/AM32 rpm

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
net("EXT_CS2","U1.PE2","U5.1")
net("FLASH_WP","U5.7","+3V3_T2"); NETS["FLASH_WP"]=["U5.7"]; NETS["+3V3"].append("U5.7")
net("FLASH_HOLD","U5.3"); NETS["+3V3"].append("U5.3"); del NETS["FLASH_HOLD"]
del NETS["FLASH_WP"]
# ---- I2C ---------------------------------------------------------------
net("I2C1_SCL","U1.PB6","R9.2","J3.4")
net("I2C1_SDA","U1.PB7","R10.2","J3.5")
net("I2C2_SCL","U1.PB10","R11.2","U4.8")
net("I2C2_SDA","U1.PB11","R12.2","U4.7")
# TOF_XSHUT (PD11) and TOF_INT (PD10) deleted with U7 - both pins freed.
# ---- UARTs -------------------------------------------------------------
net("USART2_TX","U1.PD5","J3.2"); net("USART2_RX","U1.PD6","J3.3")   # GPS1
net("UART7_TX","U1.PE8");  net("UART7_RX","U1.PE7")        # companion - no landing:
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
# PC5 is FREE.
net("SPARE_ADC","U1.PA7")


# ---- RF front end (SoOP config, all DNP) -------------------------------------
net("ANT_IN",   "J12.1","C52.1"); NETS["GND"] += ["J12.2"]
net("RFIN",     "C52.2","U13.4")
NETS["GND"] += ["U13.3","U13.10","U13.11","U13.29"]
net("VCC_RF",   "U13.1","U13.2","U13.6","U13.7","U13.13","U13.16","U13.25",
                "C49.1","C50.1","C51.1","R28.2")
NETS["+3V3A"] += ["R28.1"]; NETS["GND"] += ["C49.2","C50.2","C51.2"]
net("TUNER_REF",  "Y2.3", "C58.1")            # TCXO clipped-sine output
net("TUNER_XTAL", "C58.2", "U13.14")          # AC-coupled into the XTAL pin
NETS["+3V3A"] += ["Y2.4", "C59.1"]            # VDD + decoupling, on the quiet rail
NETS["GND"]  += ["Y2.2", "Y2.1", "C59.2"]    # both ground pins to ground
net("TUNER_ADDR","U13.28","R29.2"); NETS["GND"] += ["R29.1"]
NETS["I2C2_SDA"] += ["U13.26"]; NETS["I2C2_SCL"] += ["U13.27"]
# PLL loop filter, third order as in the MAX2112 typical application circuit: C81 and
# R34+C57 at CPOUT, R57 from CPOUT to VTUNE, C56 at VTUNE. Sized for a ~50 kHz loop at
# ICP 600 uA over the VCO's 50-175 MHz/V (LO-referred): 75-77 deg phase margin.
CAP("C81", "1n", F_C0402); RES("R57", "470R", F_R0402)
net("VTUNE","U13.9","C56.1","R57.2"); NETS["GND"] += ["C56.2"]
net("CPOUT","U13.12","R34.1","C81.1","R57.1"); net("LOOP","R34.2","C57.1")
NETS["GND"] += ["C57.2", "C81.2"]
net("VCOBYP","U13.8"); net("REFOUT","U13.15")
# GC1 needs 0.5-2.7 V (0.5 V = maximum gain): R58/R35 from VCC_RF gives 0.58 V.
RES("R58", "4k7", F_R0402)
net("GC1","U13.5","R35.2","R58.2"); NETS["GND"] += ["R35.1"]; NETS["VCC_RF"] += ["R58.1"]
# 1 nF beside the LO/VCO (pins 6-7) and synthesizer (pin 13) supplies, which set the
# VCO's phase noise and the PLL's spurs. The datasheet asks for one at every VCC pin;
# the RF, digital and baseband pins have no room within 3 mm and share C49/C50/C51.
for _c, _pin in (("C84", 6), ("C86", 13)):
    CAP(_c, "1n", F_C0402)
    NETS["GND"] += [f"{_c}.2"]; NETS["VCC_RF"] += [f"{_c}.1"]
# ---- MAX2112 baseband -> OPA2374 difference amplifiers -> ADC ------------------------
# The comment here read "resistor values TBD by sim" and nothing ever came back to it.
for r, v in [("R47","4k7"), ("R48","10k"), ("R49","10k"), ("R50","10k"),
             ("R51","10k"), ("R52","10k"), ("R53","10k")]:
    RES(r, v, F_R0402)
CAP("C75", "1u", F_C0402)
CAP("C76", "100p", F_C0402); CAP("C77", "100p", F_C0402)

# I channel: IOUT+ -> R36 -> +in A (R51 to VREF); IOUT- -> R37 -> -IN A (R50 to out A)
net("IOUT_P","U13.19","R36.1"); net("IOUT_N","U13.20","R37.1")
net("OPA_IN1P","R36.2","U14.3","R51.1"); net("OPA_IN1N","R37.2","U14.2","R50.1")
NETS["SOOP_I_ADC"] += ["R50.2", "C76.2"]             # feedback, out A -> -IN A
NETS["OPA_IN1N"] += ["C76.1"]                        # C76 across R50: anti-alias
# Q channel: QOUT+ -> R47 -> +in B (R49 to VREF); QOUT- -> R31 -> -IN B (R48 to out B)
net("QOUT_P","U13.17","R47.1"); net("QOUT_N","U13.18","R31.1")
net("OPA_IN2P","R47.2","U14.5","R49.1"); net("OPA_IN2N","R31.2","U14.6","R48.1")
NETS["SOOP_Q_ADC"] += ["R48.2", "C77.2"]             # feedback, out B -> -IN B
NETS["OPA_IN2N"] += ["C77.1"]                        # C77 across R48: anti-alias
# the mid-rail reference both channels share
net("BB_VREF","R52.2","R53.1","C75.1","R51.2","R49.2")
NETS["+3V3A"] += ["R52.1", "U14.8"]; NETS["GND"] += ["R53.2", "C75.2", "U14.4"]
# DC-offset servo capacitors, one across each pair as the datasheet draws them
net("IDC_P","U13.21","C61.1"); net("IDC_N","U13.22","C61.2")
net("QDC_P","U13.23","C63.1"); net("QDC_N","U13.24","C63.2")

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

# LMR33630 RNX 5V buck - full wiring, remapped PIN-FOR-PIN from the TPS54202.
net("BUCK_BOOT","U8.4","C21.1")                   # boot  (TPS54202 pin 6)
net("BUCK_PH",  "U8.12","U8.3","C21.2","L2.1")    # SW 12 + NC 3, tied per SNVSAN3F 10.1
net("BUCK_VCC", "U8.5","C78.1")                   # VCC, new pin - the internal 5 V LDO
NETS["GND"] += ["C78.2"]
NETS["+5V"] += ["L2.2"]
net("BUCK_EN",  "U8.9","R4.2","R5.1")             # EN    (TPS54202 pin 5)
net("BUCK_FB",  "U8.7","R6.2","R7.1")             # FB    (TPS54202 pin 4)
NETS.pop("R3", None)

# LDO enables tied to their inputs (always-on)
NETS["+5V"]  += ["U9.3","U10.3"]

COMPONENTS.pop("R2", None)

for n in ("BOOT0","+3V3","GND"):
    NETS[n] = [x for x in NETS[n] if x not in ("SW1.1","SW1.2")]
NETS["BOOT0"] += ["SW1.2"]; NETS["+3V3"] += ["SW1.1"]
# No U8 pin sits on +5V: the switch node reaches it through L2 only.
COMPONENTS.pop("R3", None)

# ---- MAX2112 bypass / DC-offset caps ---------------------------------------------
# C60 is a supply bypass. C61/C63 set the IDC/QDC DC-offset correction loop, which the
# datasheet caps at 47 nF: "Keep the value of the external capacitor less than 47 nF to
# form a typical highpass corner of 250 Hz." 100 nF halves that corner to ~120 Hz, so
# these two are 47 nF even though 100 nF is used everywhere else.
for r, v in [("C60","100n"),("C61","47n"),("C63","47n")]:
    CAP(r, v, F_C0402)
NETS["VCOBYP"] += ["C60.1"]; NETS["GND"] += ["C60.2"]
# C61 spans IDC_P/IDC_N and C63 spans QDC_P/QDC_N - wired where the nets are declared

# ---- power flags: tell ERC these rails are actually driven ---------------
PWR_FLAGS = {"VBAT":"PF1", "+5V":"PF2", "+3V3":"PF3", "+3V3A":"PF4",
             "GND":"PF5", "VDDA":"PF6", "VBUS":"PF7", "VCC_RF":"PF8",
             "VBAT_IN":"PF9"}
for netname, ref in PWR_FLAGS.items():
    add(ref, "power:PWR_FLAG", "", "PWR_FLAG", "", netname == "VCC_RF")
    NETS[netname].append(f"{ref}.1")
NOT_A_PART = set()

# ---- test points ---------------------------------------------------------
# Only signals worth the copper get a pad.
TESTPOINT_NETS = ["SWDIO", "SWCLK", "PWM5", "PWM6",
                  "USART1_TX", "USART1_RX", "WS2812", "BUZZER"]
for i, netname in enumerate(TESTPOINT_NETS, 1):
    ref = f"TP{i}"
    add(ref, "Connector:TestPoint", "TestPoint:TestPoint_Pad_1.5x1.5mm", netname, "", False)
    NETS[netname].append(f"{ref}.1")

# ---- connector reduction: JST-GH -> solder pads ---------------------------
PAD_FP = "TestPoint:TestPoint_Pad_1.5x1.5mm"
_PAD_LABELS = {
    # J6 is now a fitted JST-GH 4P connector (DroneCAN) powered from +5V_PAYLOAD!
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

add("P41", "Connector:TestPoint", PAD_FP, "TEL_5V",  "", False)
add("P44", "Connector:TestPoint", PAD_FP, "TEL_PPS", "", False)
add("P46", "Connector:TestPoint", PAD_FP, "TEL_GND", "", False)
NETS["+5V"].append("P41.1")
NETS["PPS_SYNC"].append("P44.1")
NETS["GND"].append("P46.1")

# UART7 has no landing, and the companion does not need ONE.

# ---- SoOP RF front end moved off this board ------------------------------
INCLUDE_ONBOARD_LNA = False       # U15/U16/FL1/L3/L4 - see the ANT_IN comment
assert not INCLUDE_ONBOARD_LNA, ("the on-board LNA/SAW chain was deleted, not disabled - "
                                 "re-adding it needs the 1620 MHz SAW sourced first")
for _r in ("U15", "U16", "FL1", "L3", "L4"):
    COMPONENTS.pop(_r, None)

# Keep the SoOP receiver interface reachable from the board edge even though the RF
# front end now lives elsewhere: I/Q and AGC come back as pads.
for _i, _n in enumerate(["SOOP_I_ADC", "SOOP_Q_ADC"], start=len(TESTPOINT_NETS)+1):
    if _n in NETS:
        _r = f"TP{_i}"
        add(_r, "Connector:TestPoint", "TestPoint:TestPoint_Pad_1.5x1.5mm", _n, "", False)
        NETS[_n].append(f"{_r}.1")

# ===========================================================================
# Phase A additions — the four gaps found in the component audit.
# ===========================================================================

F_SOT23   = "jlc:SOT-23-3_L2.9-W1.3-P1.90-LS2.4-BR"
F_SOD123  = "jlc:SOD-123F_L2.7-W1.6-LS3.8-RD"
F_SOT235  = "jlc:SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR"
PAD15     = "TestPoint:TestPoint_Pad_1.5x1.5mm"

# ---- 1. Buzzer driver ------------------------------------------------------
add("Q1", "jlc_parts:AO3400A",        F_SOT23,  "AO3400A", "C20917", False)
add("D4", "jlc_parts:1N4148W_C81598", F_SOD123, "1N4148W", "C81598", False)
RES("R38", "100R")       # gate series
RES("R39", "10k")        # gate pulldown - keeps the buzzer quiet while the MCU boots
add("PZ1", "Connector:TestPoint", PAD15, "BUZZ+", "", False)
add("PZ2", "Connector:TestPoint", PAD15, "BUZZ-", "", False)
add("J16", "jlc_parts:SM02B-SRSS-TB_(LF)(SN)",
    "jlc:CONN-SMD_2P-P1.00_SM02B-SRSS-TB-LF-SN", "BUZZ 2P", "C160402", False)

net("BUZZ_GATE", "R38.2", "Q1.1", "R39.1")
NETS["BUZZER"] += ["R38.1"]                       # from U1.PA15
NETS["GND"]    += ["Q1.2", "R39.2", "J16.3", "J16.4"]
net("BUZZ_DRAIN", "Q1.3", "D4.2", "PZ2.1", "J16.2")        # D4 pin2 = anode
NETS["+5V"]    += ["D4.1", "PZ1.1", "J16.1"]               # D4 pin1 = cathode

# ---- 2. SWD debug port ------------------------------------------------------
# J19: Dedicated 4-pin SWD debug header alongside reference pads.
add("TP20", "Connector:TestPoint", PAD15, "SWD_GND", "", False)
add("TP21", "Connector:TestPoint", PAD15, "SWD_3V3", "", False)
add("J19", "jlc_parts:SM04B-SRSS-TB_(LF)(SN)",
    "jlc:CONN-SMD_4P-P1.00_SM04B-SRSS-TB-LF-SN", "SWD 4P", "C160404", False)
NETS["GND"]  += ["TP20.1", "J19.4", "J19.5", "J19.6"]
NETS["+3V3"] += ["TP21.1", "J19.1"]
NETS["SWDIO"] += ["J19.2"]
NETS["SWCLK"] += ["J19.3"]

# ---- 3. Secondary 5V / 3A Payload Buck (U20) -------------------------------
# Second LMR33630A (TI VQFN-12 HotRod, 3A, 400 kHz), identical to U8.
# Powers high-draw external peripherals: servos, LiDAR, SAWbird+, WS2812 LEDs, CAN.
add("U20", "jlc_parts:LMR33630ARNXR", "jlc:VQFN-12_L3.0-W2.0-P0.65-BL_TI_RNX",
    "LMR33630A", "C2861505", False)
IND("L5", "10uH", F_ANR4030)
CAP("C66", "100n")                 # VIN hf (50V rated in PART_LCSC)
CAP("C68", "100n")                 # bootstrap
CAP("C79", "1u")                   # internal VCC bypass
CAP("C69", "22u", F_C1206)         # output bulk
CAP("C70", "22u", F_C1206)
RES("R40", "100k"); RES("R41", "22k")       # EN divider
RES("R42", "100k"); RES("R43", "24k9")      # 1.000 V reference -> 5.016 V output
add("PV1", "Connector:TestPoint", PAD15, "PAYLOAD_5V",  "", False)
add("PV2", "Connector:TestPoint", PAD15, "PAYLOAD_GND", "", False)

NETS["VBAT"] += ["U20.2", "U20.10", "C66.1", "R40.1"]
net("BUCK_PAYLOAD_BOOT", "U20.4", "C68.1")
net("BUCK_PAYLOAD_PH",   "U20.12", "U20.3", "C68.2", "L5.1")
net("BUCK_PAYLOAD_VCC",  "U20.5", "C79.1")
net("BUCK_PAYLOAD_EN",   "U20.9", "R40.2", "R41.1")
net("BUCK_PAYLOAD_FB",   "U20.7", "R42.2", "R43.1")
net("+5V_PAYLOAD", "L5.2", "C69.1", "C70.1", "R42.1", "PV1.1")
PWR_FLAGS["+5V_PAYLOAD"] = "PF10"
add("PF10", "power:PWR_FLAG", "", "PWR_FLAG", "", False)
NETS["+5V_PAYLOAD"].append("PF10.1")
NETS["GND"] += ["U20.1", "U20.6", "U20.11", "C66.2", "C79.2", "C69.2", "C70.2",
                "R41.2", "R43.2", "PV2.1"]

# ---- 4. WS2812 level shifter & J15 -----------------------------------------
# The MCU drives 3.3V; a 5V WS2812 strip wants >=0.7*VDD = 3.5V on DIN. The
# 74LVC1G17 is a Schmitt buffer powered from +5V, so the output swings to 5V.
add("U17", "jlc_parts:SN74LVC1G17DBVR", F_SOT235, "74LVC1G17", "C7836", False)
CAP("C65", "100n")
add("PL1", "Connector:TestPoint", PAD15, "LED_DIN", "", False)
add("PL2", "Connector:TestPoint", PAD15, "LED_5V",  "", False)
add("PL3", "Connector:TestPoint", PAD15, "LED_GND", "", False)
add("J15", "jlc_parts:SH1_0MM-3P-WT",
    "jlc:CONN-SMD_3P-P1.00_SH1.0MM-3P-WT", "LED 3P", "C53055319", False)
NETS["WS2812"] += ["U17.2"]                       # A input, from U1.PA8
net("WS2812_OUT", "U17.4", "PL1.1", "J15.2")       # Y output at 5V
NETS["+5V"] += ["U17.5", "C65.1"]
NETS["+5V_PAYLOAD"] += ["PL2.1", "J15.1"]
NETS["GND"] += ["U17.3", "C65.2", "PL3.1", "J15.3", "J15.4", "J15.5"]

# ---- 5. Payload power control (PA7) ----------------------------------------
add("Q3", "jlc_parts:AO3400A", F_SOT23, "AO3400A", "C20917", False)
RES("R45", "10k")                       # gate pulldown: payload on unless asserted
CAP("C73", "10n")                       # EN filter

net("PAYLOAD_EN", "U1.PA7", "Q3.1", "R45.1")
NETS["GND"] += ["Q3.2", "R45.2", "C73.2"]
NETS["BUCK_PAYLOAD_EN"] += ["Q3.3", "C73.1"]

# ---- 6. DroneCAN Micro-LDO (U21) -------------------------------------------
# Powers U11 (SN65HVD230) from +5V_PAYLOAD with rock-solid 3.3V, isolating
# U9 (+3V3 LDO) from the 70 mA dominant CAN transceiver load.
add("U21", "jlc_parts:XC6206P332MR", "jlc:SOT-23-3_L2.9-W1.6-P1.90-LS2.8-BR",
    "XC6206P332MR", "C5446", False)
CAP("C67", "1u")
CAP("C80", "1u")
NETS["+5V_PAYLOAD"] += ["U21.3", "C80.1"]
NETS["GND"] += ["U21.1", "C67.2", "C80.2"]
net("+3V3_CAN", "U21.2", "U11.3", "C67.1", "C41.1")
NETS["+5V_PAYLOAD"] += ["J6.1"]

# ---- 7. Dedicated SPI3 Optical Flow Socket (J14) ---------------------------
# Breaks out SPI3 + PD4 (EXT_CS1) + PD11 (FLOW_MOTION) onto a 6-pin JST-SH connector.
add("J14", "jlc_parts:SH1_0MM-6P-WT",
    "jlc:CONN-SMD_SH1.0MM-6P-WT", "FLOW 6P", "C53055322", False)
NETS["+3V3"] += ["J14.1"]
NETS["SPI3_SCK"] += ["J14.2"]
NETS["SPI3_MISO"] += ["J14.3"]
NETS["SPI3_MOSI"] += ["J14.4"]
net("EXT_CS1", "U1.PD4", "J14.5")
NETS["GND"] += ["J14.6", "J14.7", "J14.8"]
net("FLOW_MOTION", "U1.PD11")

# ---- 8. TVC Gimbal & Actuator Header (J17) --------------------------------
# Dedicated 6-pin JST-SH header on independent timer TIM4 (PWM7-10).
# Eliminates external PCA9685 board on lander; allows 4 DShot motors + 4 servos on drone!
add("J17", "jlc_parts:SH1_0MM-6P-WT",
    "jlc:CONN-SMD_SH1.0MM-6P-WT", "SERVO 6P", "C53055322", False)
net("PWM7",  "U1.PD12", "J17.1")
net("PWM8",  "U1.PD13", "J17.2")
net("PWM9",  "U1.PD14", "J17.3")
net("PWM10", "U1.PD15", "J17.4")
NETS["+5V_PAYLOAD"] += ["J17.5"]
NETS["GND"] += ["J17.6", "J17.7", "J17.8"]

# ---- 9. Pyrotechnic / Recovery Deployment Channel (J18) -------------------
# Switched low-side N-FET (Q5 AO3400A) driven by PC5 with 3A PPTC fuse on VBAT.
add("J18", "jlc_parts:SM02B-SRSS-TB_(LF)(SN)",
    "jlc:CONN-SMD_2P-P1.00_SM02B-SRSS-TB-LF-SN", "PYRO 2P", "C160402", False)
add("Q5", "jlc_parts:AO3400A", F_SOT23, "AO3400A", "C20917", False)
add("D5", "jlc_parts:1N4148W_C81598", F_SOD123, "1N4148W", "C81598", False)
add("F1", "Device:Polyfuse_Small", "Fuse:Fuse_1206_3216Metric", "3A", "C14165", False)
RES("R54", "1k")
RES("R55", "47k")
net("PYRO_FIRE", "U1.PC5", "R54.1")
net("PYRO_GATE", "R54.2", "Q5.1", "R55.1")
NETS["GND"] += ["Q5.2", "R55.2", "J18.3", "J18.4"]
NETS["VBAT"] += ["F1.1"]
net("VBAT_FUSED", "F1.2", "J18.1", "D5.1")
net("PYRO_DRAIN", "Q5.3", "J18.2", "D5.2")

# ---- 10. Landing Leg Touchdown Detection Port (J20) ------------------------
add("J20", "jlc_parts:SM02B-SRSS-TB_(LF)(SN)",
    "jlc:CONN-SMD_2P-P1.00_SM02B-SRSS-TB-LF-SN", "TOUCH 2P", "C160402", False)
RES("R56", "10k")
net("TOUCHDOWN", "U1.PD10", "J20.1", "R56.1")
NETS["+3V3"] += ["R56.2"]
NETS["GND"] += ["J20.2", "J20.3", "J20.4"]

# ---- 11. USB-C Desk Powering Diode (D_USB) --------------------------------
add("D_USB", "jlc_parts:B5819W_C8598",
    "jlc:SOD-123_L2.7-W1.6-LS3.7-RD-1", "B5819W", "C8598", False)
NETS["VBUS"] += ["D_USB.2"]
NETS["+5V"] += ["D_USB.1"]
# PA7, not PE15.
del NETS["SPARE_ADC"]                   # PA7 now has a job

# ===========================================================================
# Phase C — reverse-polarity protection and the edge connectors.
# ===========================================================================

# ---- 1. Reverse-polarity protection ------------------------------------------
# Q4 is a P-FET that blocks a reversed pack.
add("J12", "Connector:Conn_Coaxial", F_UFL, "U.FL ANT", "C5137195", False)

# ---- U19: the board measures its own temperature ----------------------------
# U9's junction is the one number on this board that nothing at a desk can compute.
add("U19", "jlc_parts:TMP119AIYBGR", "jlc:DSBGA-6_L1.5-W1.0-R2-C3-P0.40-BL",
    "TMP119", "C22428347", False)
CAP("C74", "100n")                       # U19 supply decoupling
NETS["I2C1_SDA"] += ["U19.A1"]
NETS["I2C1_SCL"] += ["U19.A2"]
NETS["+3V3"] += ["U19.B1", "C74.1"]
NETS["GND"] += ["U19.B2", "C74.2", "U19.C1"]   # C1 = ADD0 low -> address 0x48

add("Q4", "jlc_parts:WST4041", F_SOT23, "WST4041", "C148357", False)
add("DZ1", "jlc_parts:BZT52C15", "jlc:SOD-123_L2.7-W1.6-LS3.7-RD",
    "BZT52C15", "C173427", False)
RES("R46", "100k")
net("VBAT_GATE", "Q4.1", "DZ1.2", "R46.1")   # Q4 pin 1 = gate; DZ1 pin 2 = anode
NETS["VBAT"] += ["DZ1.1"]                        # DZ1 pin 1 = cathode, on the source
NETS["GND"] += ["R46.2"]                         # gate pull-down to ground

# ---- 2. The edge connectors ---------------------------------------------------
add("J9", "jlc_parts:SM04B-SRSS-TB_(LF)(SN)",
    "jlc:CONN-SMD_4P-P1.00_SM04B-SRSS-TB-LF-SN", "I2C 4P", "C160404", False)
add("TP22", "Connector:TestPoint", "TestPoint:TestPoint_Pad_1.5x1.5mm",
    "VSERVO", "", False)
NETS["+5V"] += ["J9.1"]
NETS["I2C1_SCL"] += ["J9.2"]
NETS["I2C1_SDA"] += ["J9.3"]
NETS["GND"] += ["J9.4", "J9.5", "J9.6"]       # pin 4 = signal, 5/6 = anchor tabs
net("VSERVO", "TP22.1")

# J11 is SERIAL2 (USART1) with its own power and ground.
add("J11", "jlc_parts:SM04B-SRSS-TB_(LF)(SN)",
    "jlc:CONN-SMD_4P-P1.00_SM04B-SRSS-TB-LF-SN", "SERIAL2 4P", "C160404", False)
NETS["+5V_PAYLOAD"] += ["J11.1"]
NETS["USART1_TX"] += ["J11.2"]
NETS["USART1_RX"] += ["J11.3"]
NETS["GND"] += ["J11.4", "J11.5", "J11.6"]

# ===========================================================================
# Phase B — placement intent.
# ===========================================================================
ADJACENCY = {
    # MCU VDD decoupling - one per supply pin, as close as the package allows.
    "C1": ("U1", "11", 2.0), "C2": ("U1", "27", 2.0), "C3": ("U1", "50", 2.0),
    "C4": ("U1", "75", 2.0), "C5": ("U1", "100", 2.0),
    "C6": ("U1", "11", 4.0), "C7": ("U1", "75", 4.0),          # bulk, looser
    # The H743's internal LDO.
    "C8": ("U1", "48", 1.5), "C9": ("U1", "73", 1.5),
    # analogue supply and reference
    "C10": ("U1", "21", 2.0), "C11": ("U1", "21", 3.0),
    "C12": ("U1", "20", 2.0), "C13": ("U1", "20", 3.0),
    "L1":  ("U1", "21", 4.0),
    "C14": ("U1", "14", 3.0),                                   # NRST
    # crystal load caps
    "C15": ("Y1", "1", 2.5), "C16": ("Y1", "3", 2.5),
    "Y1": ("U1", "12", 5.0),
    # sensors
    "C31": ("U2", "5", 1.5), "C32": ("U2", "8", 1.5),
    "C33": ("U3", "5", 1.5), "C34": ("U3", "8", 1.5),
    "C35": ("U4", "1", 1.5),
    "C36": ("U5", "8", 1.5),
    # U19 is a temperature sensor and its whole value is where it sits.
    "U19": ("U9", "1", 4.0),
    "C74": ("U19", "B1", 3.5),
    # The OPA2374 difference-amplifier network.
    "R36": ("R37", "1", 8.0),  "R47": ("R31", "1", 6.0),
    "R48": ("U14", "6", 8.0),
    "R49": ("U14", "5", 8.0),  "R50": ("U14", "2", 8.0),
    "R51": ("U14", "3", 8.0),
    "C76": ("R50", "1", 12.0), "C77": ("R48", "1", 8.0),   # in parallel with them; a few
                                                            # mm of trace is ~1 pF against 100 pF
    "R52": ("U14", "8", 12.0),                # VREF divider: a DC reference, 1 uF at
    "R53": ("R52", "2", 3.0),                 # the far end makes distance irrelevant
    "C75": ("R53", "1", 3.0),
    "C61": ("U13", "21", 3.5), "C63": ("U13", "23", 3.5),
    "C60": ("U13", "8", 2.0),
    "C41": ("U11", "3", 1.5),
    "C42": ("J1", "A4B9", 3.0),
    "C45": ("J8", "4", 3.0), "C46": ("J8", "4", 2.0),
    # regulators
    "C26": ("U9", "1", 2.0), "C27": ("U9", "5", 2.0),
    "C28": ("U10", "1", 2.0), "C29": ("U10", "5", 2.0), "C30": ("U10", "5", 3.0),
    "C65": ("U17", "5", 1.5),
    "C17": ("U8", "2", 3.0), "C18": ("U8", "2", 3.0), "C19": ("U8", "2", 1.5),
    "C78": ("U8", "5", 2.0),
    "C21": ("U8", "4", 1.5),
    "R6": ("U8", "7", 2.5), "R7": ("U8", "7", 2.5),
    "R4": ("U8", "9", 3.0), "R5": ("U8", "9", 3.0),
    "L2": ("U8", "12", 3.0), "C22": ("U8", "12", 5.0), "C23": ("U8", "12", 5.0),
    # Payload 5V buck (U20 TI LMR33630A VQFN-12)
    "C66": ("U20", "2", 3.5), "C68": ("U20", "4", 3.0),
    "C79": ("U20", "5", 2.5),
    "R42": ("U20", "7", 2.5), "R43": ("U20", "7", 2.5),
    "R40": ("U20", "9", 3.0), "R41": ("U20", "9", 3.0),
    "L5": ("U20", "12", 5.5), "C69": ("U20", "12", 5.0), "C70": ("U20", "12", 5.0),
    "C73": ("U20", "9", 3.0),      # EN filter
    "C67": ("U21", "2", 2.0),      # CAN 3.3V LDO output cap
    "C80": ("U21", "3", 3.0),      # CAN 3.3V LDO input cap; 2.61 mm is the nearest
                                    # DRC-clean cell - see tools/place_c80.py
    "D_USB": ("J1", "A4B9", 6.0),  # USB desk power diode near USB-C
    # I2C pull-ups belong near the master, not scattered
    "R9": ("U1", "92", 4.0), "R10": ("U1", "93", 4.0),
    "R11": ("U1", "46", 4.0), "R12": ("U1", "47", 4.0),
    # buzzer / level shifter local parts
    "R38": ("Q1", "1", 2.0), "R39": ("Q1", "1", 2.0), "D4": ("Q1", "3", 3.0),
    # Battery sense divider next to the MCU ADC pins.
    "R18": ("U1", "15", 5.0), "R19": ("U1", "15", 4.0),
    "C43": ("U1", "15", 2.0), "C44": ("U1", "16", 2.0),
}

ADJACENCY["D1"]  = ("J2",  "2", 5.0)     # TVS at the power entry, not the buck
ADJACENCY["SW2"] = ("U1", "14", 6.0)     # reset button near NRST
ADJACENCY["SW1"] = ("U1", "94", 6.0)     # boot button near BOOT0

ADJACENCY["U12"] = ("J1", "A6", 5.0)     # USB ESD belongs at the connector, not adrift

# Limits refined after the first placement pass.
for _r in ("C31","C32","C33","C34","C35","C36","C65","C41"):
    if _r in ADJACENCY:
        t, pd, _m = ADJACENCY[_r]; ADJACENCY[_r] = (t, pd, 3.5)
for _r, _lim in (("C22", 3.0), ("C23", 3.0), ("C69", 3.0), ("C70", 3.0),
                 ("L2", 2.5)):
    if _r in ADJACENCY:
        t, pd, _m = ADJACENCY[_r]; ADJACENCY[_r] = (t, pd, _lim)

# ---------------------------------------------------------------- geometry ---
# One definition, imported by gen_pcb / route / fix_overlaps / check_placement.
BOARD = dict(X0=100.0, Y0=99.4, W=45.0, H=47.2, R=0.5, MOUNT=30.5, HOLE_D=4.0)

# ===========================================================================
# ===========================================================================
_VALUE_FIX = {"R6": "100k", "R7": "24k9", "R42": "100k", "R43": "24k9",
              "R4": "100k", "R5": "22k", "R40": "100k", "R41": "22k"}
for _r, _v in _VALUE_FIX.items():
    if _r in COMPONENTS:
        _s, _f, _, _l, _d = COMPONENTS[_r]
        COMPONENTS[_r] = (_s, _f, _v, _l, _d)

PASSIVE_LCSC = {
    ("100n", F_C0402): "C1525",   ("1u",   F_C0402): "C52923",
    ("47n",  F_C0402): "C82219",  # MAX2112 IDC/QDC offset caps, datasheet < 47 nF
    ("2u2",  F_C0402): "C12530",  ("4u7",  F_C0805): "C354262",
    ("10n",  F_C0402): "C15195",  ("30p",  F_C0402): "C107004",
    ("47p",  F_C0402): "C60137",  ("3n3",  F_C0402): "C26404",
    # C17/C18, the VBAT bulk caps, upgraded to 50 V rated 1206 MLCCs (Samsung
    # CL31A106KBHNNNE, C13585, 2.8M in stock) for universal 3S-6S LiPo operation.
    ("10u",  F_C0805): "C1713",   ("10u",  F_C1206): "C13585",
    ("1u",   F_C0805): "C91185",  ("22u",  F_C1206): "C5177178",
    ("0R",   F_R0402): "C17168",  ("100p", F_C0402): "C1546",
    ("1n",   F_C0402): "C1523",
    ("100R", F_R0402): "C25076",  ("120R", F_R0402): "C25862",
    ("1k",   F_R0402): "C11702",  ("4k7",  F_R0402): "C25900",
    ("330R", F_R0402): "C25104",  ("470R", F_R0402): "C25117",
    ("5k1",  F_R0402): "C25905",  ("6k8",  F_R0402): "C25917",
    ("10k",  F_R0402): "C25744",  ("22k",  F_R0402): "C25767",
    ("10k",  F_R0603): "C25804",
    ("27k",  F_R0402): "C25771",  ("47k",  F_R0402): "C25792",
    ("100k", F_R0402): "C25741",
    ("37k4", F_R0402): "C25888",
    ("24k9", F_R0402): "C25874",
    ("10uH", F_L1210): "C167879",     # FNR4030 on a 1210 land - does not fit
    ("10uH", F_ANR4030): "C167879",   # FNR4030S100MT, Isat 2.4 A, Irms 1.6 A
    ("10uH", F_ANR5040): "C354610",   # CKCS5040-10uH/M, Isat 2.5 A, Irms 2.1 A
    ("600R@100MHz", F_L0805): "C18305",
    ("BLUE", F_LED):   "C965807", ("GREEN", F_LED): "C965804",
    ("BOOT", F_SW):    "C231329", ("RESET", F_SW): "C231329",
}

PART_LCSC = {
    # VBAT high-frequency bypass.
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
        _unpriced.append((_r, v, f))
if _unpriced:
    import sys as _sys
    for _r, _v, _f in _unpriced:
        print(f"design.py: {_r} is {_v} in {_f} - no LCSC part for that "
              f"(value, footprint) pair", file=_sys.stderr)

# ---------------------------------------------------------------- part ratings
# What each LCSC part actually is, read off its own product page.
RATINGS = {
 # LCSC        value   V    dielectric  tol     package  Tmin Tmax  source
 "C1525":    ("100n",  16,  "X7R",     "10%",  "0402",  -55, 125, "[D] LCSC product page, 2026-08-29"),
 "C82219":   ("47n",   50,  "X7R",     "10%",  "0402",  -55, 125, "[L] JLCPCB part API: FH 0402B473K500NT 47nF 50V X7R 0402, 2026-09-26"),
 "C131394":  ("100n",  50,  "X7R",     "10%",  "0402",  None, None, "[D] LCSC product page, 2026-08-29"),
 "C52923":   ("1u",    25,  "X5R",     "10%",  "0402",  -55,  85, "[D] LCSC product page, 2026-08-29"),
 "C91185":   ("1u",    50,  "X7R",     "10%",   "0805",  None, None, "[D] LCSC product page, 2026-08-29"),
 "C1713":    ("10u",   16,  "X5R",     "10%",  "0805",  -55,  85, "[D] LCSC product page, 2026-08-29"),
 "C16195875":("10u",   35,  "X7R",     "10%",  "1206",  None, None, "[D] LCSC + jlcparts, 2026-09-03"),
 "C13585":   ("10u",   50,  "X5R",     "10%",  "1206",  -55,  85, "[D] Samsung CL31A106KBHNNNE (A = X5R) 10uF 50V 1206, LCSC C13585"),
 "C5177178": ("22u",   16,  "X5R",     None,   "1206",  None, None, "[D] LCSC product page, 2026-08-29"),
 "C107004":  ("30p",   50,  "NP0",     "5%",   "0402",  None, None, "[D] LCSC product page, 2026-08-29"),
 "C19666":   ("4u7",   16,  "X5R",     "10%",  "0603",  -55,  85, "[D] LCSC product page, 2026-08-29"),
 "C354262":  ("4u7",   25,  "X7R",     "10%",  "0805",  None, None, "[D] LCSC product page, 2026-08-29"),
 "C12530":   ("2u2",  6.3,  "X5R",     "20%",  "0402",  None, None, "[D] LCSC product page, 2026-08-29"),
 "C15195":   ("10n",   50,  "X7R",     "10%",  "0402",  None, None, "[D] LCSC product page, 2026-08-29"),
 "C26404":   ("3n3",   50,  "X7R",     "10%",  "0402",  None, None, "[D] LCSC product page, 2026-08-29"),
 "C60137":   ("47p",   50,  "NP0",     "5%",   "0402",  None, None, "[D] LCSC product page, 2026-08-29"),
 "C1546":    ("100p",  50,  "NP0",     "5%",   "0402",  None, None, "[D] LCSC product page (0402CG101J500NT), 2026-09-11"),
 "C1523":    ("1n",    50,  "X7R",     "10%",  "0402",  None, None, "[D] LCSC product page (0402B102K500NT), 2026-09-11"),
}
# Parts whose ratings have not been read off a datasheet yet.
RATINGS_UNVERIFIED = set()

# Inductors: current ratings and real body size, which is not what the footprint says.
#   LCSC          L      Isat  Irms  DCR    body LxWxH mm   source
INDUCTORS = {
 "C167879":  ("10uH", 2.4, 1.6, 0.130, (4.0, 4.0, 3.0), "[D] LCSC page 2026-08-29, FNR4030S100MT"),
 "C354610":  ("10uH", 2.5, 2.1, 0.064, (5.0, 5.0, 4.0), "[D] LCSC page 2026-08-29, CKCS5040-10uH/M"),
 "C18305":   ("600R@100MHz", None, None, None, (2.0, 1.25, 0.85), "[A] 0805 ferrite bead, package typical"),
}
# Continuous current each inductor actually carries, from the rail it feeds.
# ---- what the +5 V buck (U8) actually carries ----------------------------------------
# One list, two derived NUMBERS.
LOADS_5V = [
    ("U9 (+3V3) input, = LOADS_3V3",   sum(r[1] for r in LOADS_3V3),  sum(r[2] for r in LOADS_3V3),
     "[M] derived: LDO input current equals its output; MCU, flash, microSD, LEDs, TMP119"),
    ("U10 (+3V3A) input, = LOADS_3V3A", sum(r[1] for r in LOADS_3V3A), sum(r[2] for r in LOADS_3V3A),
     "[M] derived: both IMUs, the baro, the MAX2112 tuner (100 mA), OPA2374, TCXO"),
    ("M10 GPS + QMC5883L on J3",        0.050, 0.050, "[A] docs/HARDWARE.md budget row; typical M10 module ~40-50 mA"),
    ("ELRS receiver on J5",             0.100, 0.100, "[A] docs/HARDWARE.md budget row; ESP-based RX with telemetry"),
    ("TFS20-L rangefinder on J9",       0.106, 0.106, "[D] 0.35 W at 3.3 V via its inline LDO - optional (stage B2), budgeted as fitted"),
    ("GY-53-L1X upward ToF on J9",      0.020, 0.020, "[D] VL53L1X module ~20 mA - optional (stage B2), budgeted as fitted"),
]
LOADS_5V_CONT_A = round(sum(r[1] for r in LOADS_5V), 3)
LOADS_5V_PEAK_A = round(sum(r[2] for r in LOADS_5V), 3)

INDUCTOR_LOAD_A = {"L2": LOADS_5V_CONT_A}

# ---- package heights, the single source of truth ---------------------------------
# Height of each package above the board surface it sits on, mm.
PART_HEIGHT = {
    "CONN-SMD_XY-SM06B": 4.4,   # JST GH 6P
    "CONN-TH_SM08B": 2.9,       # JST SH 8P - the ESC connector
    "USB-C": 3.2, "TF-SMD": 1.9, "COB": 2.3, "DO-214": 2.3,
    "OPTO": 1.6, "SOIC": 1.8, "SOP": 1.8,
    "LQFP": 1.6, "LGA-14": 0.95, "SENSORS-SMD_MS5611": 1.1,
    "CRYSTAL-SMD_4P": 0.9, "SOD-123F": 1.1,
    "SOT-23-3": 1.45, "SOT-23-5": 1.45, "SOT-23-6": 1.45, "SOT-25": 1.45,
    "SW_SPST_B3U": 0.8, "TestPoint_Pad": 0.0,
    "L_APV_ANR4030": 3.0, "L_1210": 3.0,
    "L_0805": 1.2,        # ferrite bead
    "C_1206": 1.6, "C_0805": 1.45, "C_0402": 0.55,
    "R_0603_1608Metric": 0.55,  # standard 0603 resistor; [D] package max typical
    "R_0402": 0.45, "LED_0603": 0.55,
    # Rev B parts.
    "CONN-SMD_4P-P1.00_SM04B": 2.9,   # JST SH 4P vertical (J5/J9/J11), same 2.9 as the SH 8P
    "OSC-SMD_4P": 0.9,                 # 3.2 x 2.5 clipped-sine TCXO (Y2) [D] Ostar
    "SOD-123": 1.1,                    # DZ1 zener, same body as the SOD-123F already here
    "TQFN-28_L5.0": 0.8,               # U13 MAX2112, 5 x 5 QFN [D] Maxim
    "VQFN-12_L3.0": 0.9,              # U8 LMR33630ARNXR; [D] SNVSAN3F RNX0012B "0.9 mm max height"
    "U.FL_Hirose": 1.2,                # J12 vertical U.FL [D] Hirose U.FL-R-SMT-1
    # Rev C additions:
    "CONN-SMD_2P-P1.00": 2.9,          # J13/J16/J18/J20 JST-SH 2P
    "CONN-SMD_3P-P1.00": 2.9,          # J15 JST-SH 3P
    "CONN-SMD_SH1.0MM": 2.9,           # J14/J17 JST-SH 6P
    "SMB_L4.6": 2.4,                   # D1 SMBJ22A DO-214AA / SMB
    "Fuse_1206": 1.0,                  # F1 1206 PPTC fuse
    "DSBGA-6": 0.525,
}


def part_height(fp_name):
    """Height in mm for a footprint name, or None if nothing in the table matches."""
    keys = [k for k in PART_HEIGHT if k in fp_name]
    return PART_HEIGHT[max(keys, key=len)] if keys else None


def stack_heights(board, skip_dnp=True):
    """Tallest fitted part on each side, measured from the board."""
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

# Maximum working voltage of each net, for the ratings check.
CELLS = 5
NET_VMAX = {
    "VBAT": CELLS * 4.2,
    "VBAT_IN": CELLS * 4.2,
    "VBAT_FUSED": CELLS * 4.2,
    "+5V_PAYLOAD": 5.0,
    "+5V": 5.0,
    "VBUS": 5.25,
    "+3V3": 3.3,
    "+3V3A": 3.3,
    "+3V3_CAN": 3.3,
    "VDDA": 3.3,
    "GND": 0.0,
}
NET_VMAX.update({
    "BUCK_BOOT": 8.4, "BUCK_PH": 8.4,
    "BUCK_PAYLOAD_BOOT": 8.4, "BUCK_PAYLOAD_PH": 8.4,
})
NET_VMAX.update({
    "NRST": 3.3, "OSC_IN": 3.3, "OSC_OUT": 3.3,
    "BUCK_FB": 3.3, "BUCK_PAYLOAD_FB": 3.3,
    "BATT_V_DIV": 3.3, "ESC_CUR": 3.3,
    "VCAP1": 1.5, "VCAP2": 1.5,
    "BUCK_PAYLOAD_EN": 3.3,
    "PAYLOAD_EN": 3.3,
    "PYRO_FIRE": 3.3,
    "PYRO_GATE": 3.3,
    "TOUCHDOWN": 3.3,
    "FLOW_MOTION": 3.3,
})

# In Rev C, both buck switchers (U8 Core 5V and U20 Payload 5V) are fully fitted.
POPULATE_VTX = True
POPULATE_BLIND_SENSORS = False

# ---- the two bucks, keyed on the fitted part ---------------------------------------
VREF_V = {
    "TPS54331": (0.800, "[D] TI TPS54331 datasheet"),
    "TPS54202": (0.596, "[D] TI TPS54202 SLVSD26C, 'typical voltage reference is designed at 0.596 V'"),
    "LMR33630A": (1.000, "[D] SNVSAN3F 7.5 Voltage Reference (FB pin), VFB ADJ option 0.985 / 1.000 / 1.015 V"),
}

# (ref, rail, vout_as_fitted_V, Rtop, Rbot, inductor)
BUCK_RAILS = (("U8",  "+5V",         5.016, "R6",  "R7",  "L2"),
              ("U20", "+5V_PAYLOAD", 5.016, "R42", "R43", "L5"))

BUCK_THERMAL = {
    "TPS54202": dict(
        fsw=500e3, rds_hs=0.148, rds_ls=0.078, theta_jedec=118.6, theta_evm=57.2,
        tj_max=125.0, tj_absmax=150.0, t_shutdown=160.0,
        src="[D] SLVSD26 5.4 Thermal Information, DDC (SOT-23-6)"),
    "LMR33630A": dict(
        fsw=400e3, rds_hs=0.075, rds_ls=0.050, theta_jedec=72.5, theta_evm=None,
        tj_max=125.0, tj_absmax=150.0, t_shutdown=165.0,
        src="[D] SNVSAN3F 7.4 Thermal Information, RNX (12-pin VQFN)"),
}


def buck_dnp(ref):
    """True when this rail's regulator is not fitted on the build being ordered."""
    return False


NET_SOURCE = {
    "VBAT_IN": "J2.2",     # battery connector, before the protection FET
    "VBAT":    "Q4.2",     # after the protection FET - Q4 pin 2 = source
    "VBAT_FUSED": "F1.2",  # pyrotechnic fused rail
    "+5V":   "L2.2",       # Core 5 V buck output inductor
    "+5V_PAYLOAD": "L5.2", # Payload 5 V buck output inductor
    "+3V3":  "U9.5",       # AP2112 output
    "+3V3A": "U10.5",      # TLV75533 output
    "+3V3_CAN": "U21.2",   # XC6206 output
    "VBUS":  "J1.A4B9",    # USB-C
}

NET_CURRENT = {
    "VBAT": 2.5,
    "+5V":  0.95,
    "+5V_PAYLOAD": 1.5,
    "+3V3": 0.6,
    "+3V3A": 0.35,
    "+3V3_CAN": 0.1,
    "VBUS": 0.5,
}

# Per-load continuous currents for check_power_cut.py.
LOAD_CURRENT = {
    "+5V_PAYLOAD": {
        # [M] the BEC loom wired to PV1/PV2: VTX 0.30 + XIAO 0.25 + SAWbird 0.18
        # (docs/HARDWARE.md generated power table, BEC load 910 mA minus the LD06 row)
        "PV1.1": 0.73,
        # [M] WS2812 strip average, 10% duty rule (HARDWARE.md: 60 mA cont / 600 mA peak)
        "PL2.1": 0.06,
        "J15.1": 0.06,
        # [D] LD06 steady 0.18 (300 mA is its start-up surge).
        "J11.1": 0.18,
        "J17.5": 0.50,
        # [D] U21 is the +3V3_CAN LDO feed for the SN65HVD230; its input current equals
        # that rail's own budget figure (NET_CURRENT["+3V3_CAN"])
        "U21.3": 0.10,
        # [A] one small DroneCAN node (J6 powers the bus per design.py:2098)
        "J6.1": 0.10,
    },
    "+3V3A": {
        # [D] OPA2374: 585 uA per amplifier, two amplifiers (LOADS_3V3A row)
        "U14.8": 0.002,
    },
    # The +5V rows of LOADS_5V, per pad. Without them check_power_cut charged every
    # +5V pad the whole rail's 0.95 A.
    "+5V": {
        "U9.1": 0.294, "U9.3": 0.0,     # U9 (+3V3 LDO) input; pin 3 is EN
        "U10.1": 0.107, "U10.3": 0.0,   # U10 (+3V3A LDO) input; pin 3 is EN
        "J3.1": 0.05,                   # M10 GPS + compass
        "J5.1": 0.1,                    # ELRS receiver
        "J9.1": 0.126,                  # TFS20-L 0.106 + upward ToF 0.02
    },
}

# ---- the payload buck (U20, +5V_PAYLOAD): which loads run together ------------------
# LOAD_CURRENT above says what each payload connector draws.
PAYLOAD_PROFILES = {
    "drone": dict(keys=("PV1.1", "PL2.1", "J11.1", "U21.3", "J6.1"),
                  what="quad on GPS/SoOP: VTX + XIAO camera + SAWbird+ on PV1/PV2, "
                       "LED strip, LD06 lidar, CAN transceiver and one node"),
    "lander": dict(keys=("J17.5", "PL2.1", "U21.3", "J6.1"),
                   what="TVC lander: two TVC servos running on J17 (aux servos are "
                        "one-shot deployers), LED strip, CAN transceiver and one node"),
}
PAYLOAD_ALL_WIRED = tuple(k for k in LOAD_CURRENT["+5V_PAYLOAD"] if k != "J15.1")


def payload_amps(keys):
    return round(sum(LOAD_CURRENT["+5V_PAYLOAD"][k] for k in keys), 3)


PAYLOAD_MISSION_A = {name: payload_amps(p["keys"]) for name, p in PAYLOAD_PROFILES.items()}
PAYLOAD_ALL_WIRED_A = payload_amps(PAYLOAD_ALL_WIRED)
RAIL_5V_PAYLOAD = dict(
    irms_a=1.6, isat_a=2.4,   # [D] L5 is the same FNR4030S100MT (C167879) as L2
    worst_mission=max(PAYLOAD_MISSION_A, key=PAYLOAD_MISSION_A.get),
    worst_mission_a=max(PAYLOAD_MISSION_A.values()),
    src="[D] FNR4030S100MT Irms/Isat; [M] currents are design.LOAD_CURRENT['+5V_PAYLOAD'] "
        "keys grouped by design.PAYLOAD_PROFILES")
INDUCTOR_LOAD_A["L5"] = RAIL_5V_PAYLOAD["worst_mission_a"]


# ===========================================================================
# What each MCU pin is for, in the electrical sense.
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
    "EXT_CS1":  dict(mcu="out", boot="high", why="optical flow PMW3901 chip select, idle high"),
    "EXT_CS2":  dict(mcu="out", boot="high", why="W25Q128 select, idle high"),
    "FLOW_MOTION": dict(mcu="in", why="PMW3901 motion interrupt input pin"),

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

    # --- Payload 5V buck power ---------------------------------------------
    "PAYLOAD_EN": dict(mcu="out", boot="low",
                       why="Q3 gate: LOW leaves the 5V Payload rail enabled, HIGH cuts it"),

    # --- TVC servos / secondary actuators (TIM4 on J17) -------------------
    "PWM7":  dict(mcu="out", why="TIM4_CH1 servo / actuator PWM on J17"),
    "PWM8":  dict(mcu="out", why="TIM4_CH2 servo / actuator PWM on J17"),
    "PWM9":  dict(mcu="out", why="TIM4_CH3 servo / actuator PWM on J17"),
    "PWM10": dict(mcu="out", why="TIM4_CH4 servo / actuator PWM on J17"),

    # --- Lander / recovery peripherals -------------------------------------
    "PYRO_FIRE": dict(mcu="out", boot="low",
                      why="AO3400A gate driving recovery / e-match pyro channel on J18"),
    "TOUCHDOWN": dict(mcu="in",
                      why="landing leg touchdown switch to GND with 10k pull-up on J20"),

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
# The one board, and everything that can bolt onto it later.
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
        what="LDROBOT LD06, 12 m, INDOOR ONLY", lands_on=["J11"],
        conn="SERIAL2 (USART1) on J11; J11.1 is +5V_PAYLOAD (U20) in Rev C", bec=True,
        # Price, third and final CORRECTION.
        needs_board_change=None, gbp=OFFBOARD["lidar"]["gbp"], status="later",
        ma_5v=180, counted=False,
        note="[D] 180 mA running, but 300 mA at START-UP - which is why it is on the payload "
             "BEC and not this board's buck. 33.30 mm tall against 28.5 mm of belly at the "
             "old 25 mm skid drop - SKID['drop'] is now 40 mm, giving 10.20 mm of ground "
             "clearance"),
    "rc_link": dict(
        what="ELRS 2.4 GHz, ESP-based", lands_on=["J5"], conn="JST-SH 4P on J5 (USART6)",
        needs_board_change=None, gbp=12, status="fitted",
        ma_5v=100, counted=True,
        note="MAVLink downlink caps at 1470 B/s - carries telemetry, never video"),
    "soop_tuner": dict(
        what="SoOP RF front end: SAWbird+ IR (LNA+SAW) + 1620 MHz patch, at the antenna",
        lands_on=["J12"], conn="U.FL coax into J12; micro-USB power from PV1/PV2 (+5V_PAYLOAD, U20)", bec=True,
        needs_board_change=None, gbp=70, status="later",
        ma_5v=180, counted=False,
        note="the LNA+SAW stage the board could not source, bought built. 180 mA [D] at "
             "3.3-5.5 V, powered by bias tee (bench) or micro-USB from the payload BEC "
             "(aircraft) - J12 carries no bias tee and this board's buck does not carry it"),
    "fpv": dict(
        what="5.8 GHz camera + VTX, 25 mW EIRP", lands_on=[],
        conn="5 V and GND from PV1/PV2 (+5V_PAYLOAD, U20)", bec=True,
        needs_board_change=None, gbp=25, status="later",
        ma_5v=300, counted=False,
        note="a 25 mW AIO runs from 5 V, so it does NOT need the unroutable 9 V block - "
             "and from the payload BEC, not this board's buck. NOTE there is no VBAT pad "
             "on this board - anything wanting 7-26 V takes it from the battery harness"),
    "rec_camera": dict(
        what="XIAO ESP32-S3 Sense, records to its own SD", lands_on=[],
        conn="two wires to PV1/PV2 (+5V_PAYLOAD, U20)", bec=True,
        needs_board_change=None, gbp=14, status="later",
        ma_5v=250, counted=False,
        note="0.25 A, on the payload BEC (or standalone on a 1S cell). It used to be wired "
             "to P41/P46 - 250 mA on the FC's buck, which with the SAWbird+ took U8's worst "
             "corner to 154 C. Those pads remain a 5 V tap for a bench probe, not a payload"),
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
        what="PixArt PMW3901 flow", lands_on=["J14"], conn="JST-SH 6P on J14 (SPI3)",
        needs_board_change=None,
        gbp=12, status="later",
        ma_5v=0, counted=True,
        note="External PMW3901 flow breakout connects via J14 on SPI3"),
    "payload_5v_rail": dict(
        what="on-board 5 V buck for payload/servos", lands_on=["J17", "J11"], conn="+5V_PAYLOAD",
        needs_board_change=None,
        gbp=0, status="fitted",
        ma_5v=0, counted=True,
        note="TPS54332 5V/2.5A switching buck U20 powering servos on J17 and companion on J11"),
    "src": "[M] every lands_on asserted against real footprints by tools/check_modules.py",
}


# ---------------------------------------------------------------------------
# RF_BENCH - the T3b self-interference measurements, and the gate on them.
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
    # Fields each step must carry.
    fields=("bursts_per_min", "noise_floor_dbm", "utc", "sky"),
    # A step keeping this fraction of baseline bursts is a pass.
    min_fraction_of_baseline=0.5,
    mitigations=["antenna placement and separation", "ferrites on the motor leads",
                 "shielding the SAWbird",
                 "keep the SDR off the airframe entirely - the receive chain is "
                 "laptop-side, so this board allows it"],
    src="[A] min_fraction_of_baseline is a judgement call; every other field is a slot "
        "for an [M]easured value recorded by runbook T3b",
)


# ---------------------------------------------------------------------------
# RAIL_5V - what is actually left on the +5 V rail, and why it is not 1.8 A.
# ---------------------------------------------------------------------------
RAIL_5V = dict(
    irms_a=1.6,          # [D] FNR4030S100MT, C167879 - the thermal limit, and the budget
    isat_a=2.4,          # [D] saturation - a transient limit, not a load budget
    fitted_load_a=LOADS_5V_CONT_A,   # [M] derived from LOADS_5V above, continuous
    fitted_peak_a=LOADS_5V_PEAK_A,   # [M] the same list at its peak column (inductor Isat)
    headroom_a=1.6 - LOADS_5V_CONT_A,
    note="Neither fitted inductor sits on a land too small for it any more: L2 and L5 "
         "are both 4.0x4.0x3.0 mm FNR4030s on L_APV_ANR4030. L5 was on a 1210 land until "
         "2026-09-21, where check_ratings measured its terminal overhanging by 0.18 mm in "
         "Y - solderable, but the wrong land for the part, and now moot. If a future "
         "inductor is put on a 1210 land, do not 'fix' it by swapping in a part that "
         "land takes but the current does not.",
    src="[D] Irms/Isat from the FNR4030S100MT datasheet; [M] fitted_load_a IS the sum "
        "of design.LOADS_5V - one list, and INDUCTOR_LOAD_A['L2'] is the same expression",
)

# The payload breakout quotes the +5 V headroom.
PAYLOAD_BREAKOUT["headroom_a"] = RAIL_5V["headroom_a"]

# ---- bare copper pads are board features, not parts --------------------------------
# Every test point and every solder pad added above is copper.
NOT_A_PART = {ref for ref, spec in COMPONENTS.items()
              if spec[1] == "TestPoint:TestPoint_Pad_1.5x1.5mm"}


# ---- silkscreen: the function name printed beside each connector -----------------
SILK_NAMES = {
    "J18": "PYRO", "J1": "USB", "J2": "ESC", "J3": "GPS", "J5": "RC", "J6": "CAN",
    "J9": "I2C", "J11": "UART2", "J12": "ANT", "J14": "FLOW", "J15": "LED", "J16": "BUZZ",
    "J17": "SERVO", "J19": "SWD", "J20": "TOUCH",
}
SILK_TITLE = ["IRIDIUM NAV", "KRYSTIAN FILIPEK"]
SILK_TITLE_SIDE = {"IRIDIUM NAV": "bottom", "KRYSTIAN FILIPEK": "top"}

# ---- 3D models: bodies that legitimately sit off their outline or reach into the board --
MODEL_EXPECTED = {
    "J1": (0.04, 0.75),    # USB-C: the plug end projects past the board edge
    "J8": (0.00, -3.95),   # push-push microSD: the card slot extends past the silkscreen
}
MODEL_EXPECTED_SINK = {
    "J1": 0.78,            # USB-C shell legs in their slots
    "J8": 0.61,            # microSD locating posts in their holes
}

# ---- board frame: which edge is forward ------------------------------------------------
# The reference forward is the TOP edge in KiCad's top view (the USB-C / antenna / SWD edge),
# marked by the arrow on the silkscreen. The hwdef's IMU rotations are derived against it;
# a board mounted any other way sets AHRS_ORIENTATION.
BOARD_FORWARD = (0, -1)      # KiCad (x right, y down) direction of "forward"
# TDK LGA-14 axes, from the datasheet's top view: +X from the pin 1-4 side to the pin 8-11
# side, +Y from pins 5-7 to pins 12-14, +Z out of the top face.
IMU_AXES = {
    "U2": ("icm42688", ("1", "2", "3", "4"), ("8", "9", "10", "11"), ("5", "6", "7"), ("12", "13", "14")),
    "U3": ("icm42605", ("1", "2", "3", "4"), ("8", "9", "10", "11"), ("5", "6", "7"), ("12", "13", "14")),
}
SILK_ARROW = {"side": "top", "direction": BOARD_FORWARD, "length": 2.5, "label": None}
