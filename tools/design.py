#!/usr/bin/env python3
#NAVCORE-SoOP - single source of truth for components and nets

R  = "Device:R";  C  = "Device:C";  L = "Device:L"; FB = "Device:FerriteBead"
LED = "Device:LED"; SW = "Switch:SW_Push"; XTAL = "Device:Crystal_GND24"

F_R0402  = "Resistor_SMD:R_0402_1005Metric"
F_R0603  = "Resistor_SMD:R_0603_1608Metric"
F_C0402  = "Capacitor_SMD:C_0402_1005Metric"
F_C0805  = "Capacitor_SMD:C_0805_2012Metric"
F_C1206  = "Capacitor_SMD:C_1206_3216Metric"
F_L1210  = "Inductor_SMD:L_1210_3225Metric"
#power-inductor lands, sized to the parts that actually go on them
F_ANR4030 = "Inductor_SMD:L_APV_ANR4030"   #4.0 x 4.0 x 3.0 mm, courtyard 4.60 x 4.50
F_ANR5040 = "Inductor_SMD:L_APV_ANR5040"   #5.0 x 5.0 x 4.0 mm, courtyard 5.60 x 5.50
F_L0805  = "Inductor_SMD:L_0805_2012Metric"
F_LED    = "LED_SMD:LED_0603_1608Metric"
F_SW     = "Button_Switch_SMD:SW_SPST_B3U-1000P"
F_UFL    = "jlc:U.FL_Hirose_U.FL-R-SMT-1_Vertical_6L"   #keepout off B.Cu - see the footprint

#components
#ref : (symbol, footprint, value, lcsc, dnp)
COMPONENTS = {
 #core
 #C5271084 is STM32H743VIT6TR
    "U1" : ("jlc_parts:STM32H743VIT6_C114409", "jlc:LQFP-100_L14.0-W14.0-P0.50-LS16.0-BL", "STM32H743VIT6", "C5271084", False),
 "U2" : ("jlc_parts:ICM-42688-P",           "jlc:LGA-14_L3.0-W2.5-P0.50-TL",            "ICM-42688-P",   "C1850418", False),
 "U3" : ("jlc_parts:ICM-42605",             "jlc:LGA-14_L3.0-W2.5-P0.50-TL",            "ICM-42605",     "C2655099", False),
 "U4" : ("jlc_parts:MS561101BA03-50",       "jlc:SENSORS-SMD_MS5611-01BA03",            "MS5611",        "C15639",   False),
 "U5" : ("jlc_parts:W25Q128JVPIQTR",        "jlc:WSON-8-1EP_6x5mm_P1.27mm_EP3.4x4.3mm", "W25Q128JVPIQ",  "C190862",  False),
 #power
 #U8 is a TI LMR33630ARNXR (VQFN-12 HotRod, RNX), swapped in place
 "U8" : ("jlc_parts:LMR33630ARNXR",         "jlc:VQFN-12_L3.0-W2.0-P0.65-BL_TI_RNX",    "LMR33630A",     "C2861505",  False),
 "U9" : ("jlc_parts:TLV75733PDYDR",         "jlc:SOT-23-5_L2.9-W1.6-P0.95-LS2.8-BL-EP", "TLV75733P",     "C22399950",False),
 "U10": ("jlc_parts:TLV75533PDBVR",         "jlc:SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR",    "TLV75533",      "C404027",  False),
 #io
 "U11": ("jlc_parts:SN65HVD230DR",          "jlc:SOIC-8_L4.9-W3.9-P1.27-LS6.0-BL",      "SN65HVD230",    "C12084",   False),
 "U12": ("jlc_parts:USBLC6-2SC6_C2687116",  "jlc:SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL",    "USBLC6-2SC6",   "C2687116", False),
 "J1" : ("jlc_parts:TYPE-C_16PIN_2MD(073)", "jlc:USB-C-SMD_TYPE-C-16PIN-2MD-073",       "USB-C",         "C2765186", False),
 "J2" : ("jlc_parts:SM08B-GHS-TB(LF)(SN)", "jlc:CONN-SMD_SM08B-GHS-TB-LF-SN",       "ESC 8P",        "C42376901",  False),  #Shou Han GH clone; the JST part (C265111) is out of stock
 "J3" : ("jlc_parts:XY-SM06B-GHS-TB",       "jlc:CONN-SMD_XY-SM06B-GHS-TB",            "GPS+I2C",       "C51940119",False),
 "J5" : ("jlc_parts:BX-GH1_25-4PWT",        "jlc:CONN-SMD_4P-P1.25_BX-GH1.25-4PWT","RC IN",   "C18077720",False),
 "J6" : ("jlc_parts:BX-GH1_25-4PWT",        "jlc:CONN-SMD_4P-P1.25_BX-GH1.25-4PWT","CAN 4P",  "C18077720",False),
 "J8" : ("jlc_parts:TF-01A",                "jlc:TF-SMD_TF-01A",                        "microSD",       "C91145",   False),
 #Y1 is a passive crystal and the part number matters more than it looks
 "Y1" : ("jlc_parts:X32258MSB4SI",          "jlc:CRYSTAL-SMD_4P-L3.2-W2.5-BL",          "8MHz",          "C2682774", False),
 "D1" : ("jlc_parts:SMBJ22A_C113993",          "jlc:SMB_L4.6-W3.6-LS5.3-RD",                          "SMBJ22A",       "C113993",False),
 #SoOP receiver
 "U13": ("jlc_parts:MAX2112ETI+T",          "jlc:TQFN-28_L5.0-W5.0-P0.50-BL-EP3.3",      "MAX2112",       "C596391",  False),
 "U14": ("jlc_parts:OPA2374M{slash}TR",     "jlc:SOP-8_L4.9-W3.9-P1.27-LS6.0-BL",       "OPA2374",       "C444392",  False),
 "U15": ("jlc_parts:PSA4-5043+",            "jlc:SOT-343-4_L2.0-W1.3-P1.30-LS2.1-BR",           "PSA4-5043+",    "C5240848", True),
 "U16": ("jlc_parts:PSA4-5043+",            "jlc:SOT-343-4_L2.0-W1.3-P1.30-LS2.1-BR",           "PSA4-5043+",    "C5240848", True),
 #Y2 is an active 4-pad clipped-sine TCXO feeding U13's reference through C58
 "Y2" : ("jlc_parts:T132S4-25000ML33DTL",     "jlc:OSC-SMD_4P-L3.2-W2.5-BL",              "25MHz TCXO",    "C5563878", False),
 "FL1": ("jlc_parts:TA1575IG",                   "jlc:FILTER-SMD_6P-L3.0-W3.0-P1.19-TR",                       "SAW 1620MHz",   "",         True),
}

def add(ref, sym, fp, val, lcsc="", dnp=False):
    COMPONENTS[ref] = (sym, fp, val, lcsc, dnp)

#passives
_p = []
def RES(ref, val, fp=F_R0402, dnp=False): add(ref, R, fp, val, "", dnp); _p.append(ref)
def CAP(ref, val, fp=F_C0402, dnp=False): add(ref, C, fp, val, "", dnp); _p.append(ref)
#the default land is the 4x4 one, not F_L1210
def IND(ref, val, fp=F_ANR4030, dnp=False): add(ref, L, fp, val, "", dnp); _p.append(ref)

#MCU decoupling: one 100n per VDD pin + bulk
for i, r in enumerate(["C1","C2","C3","C4","C5"]): CAP(r, "100n")
CAP("C6", "4u7", F_C0805); CAP("C7", "4u7", F_C0805)
CAP("C8", "2u2", F_C0402); CAP("C9", "2u2", F_C0402)     #VCAP1/2
CAP("C10","100n"); CAP("C11","1u")                        #VDDA
CAP("C12","100n"); CAP("C13","1u")                        #VREF+
CAP("C14","100n")                                         #NRST
Y1_CL_PF        = 20.0
Y1_STRAY_PF     = 5.0
Y1_CL_CONFIRMED = True
#LCSC codes known to be passive crystals in this footprint
Y1_PASSIVE_LCSC = {"C2682774"}      #X32258MSB4SI, YXC, CL 20 pF, 120 ohm ESR

#regulator enable thresholds, and what the input rail is allowed to reach
EN_THRESHOLD_V = {
    "TPS54331": (1.25, True, "[D] TI TPS54331 datasheet"),
    "TPS54202": (1.21, True, "[D] SLVSD26 5.5 Electrical Characteristics, V(EN_RISING) typ 1.21 V (max 1.28); the same 1.21 V is used in the datasheet's own UVLO equations"),
    "LMR33630A": (1.231, True, "[D] SNVSAN3F 7.5 Electrical Characteristics, VEN-H rising 1.2 / 1.231 / 1.26 V"),
}

VBAT_PART_VMAX = {
    "LMR33630A": (36.0, 38.0, True,
                  "[D] SNVSAN3F 7.1 Absolute Maximum Ratings, VIN to PGND -0.3 to 38 V; 7.3 Recommended Operating Conditions"),
    "WST4041": (30.0, 40.0, True,
                "[D] WST4041 WINSOK datasheet: VDS -40 V, VGS +-20 V absolute max "
                "(docs/datasheets/WST4041_WINSOK.pdf)"),
}

#transient-suppressor clamping voltage at the datasheet's peak pulse current the 3.3 V rails
LDO_DROP_V = 5.0 - 3.3

LOADS_3V3 = [   #through U9, TLV75733P
    ("STM32H743 core + IO at 480 MHz", 0.240, 0.240, "[A] docs/HARDWARE.md budget row, "
                                                     "less the sensors that are on +3V3A"),
    ("W25Q128 config flash",           0.004, 0.025, "[D] W25Q128JV: ~4 mA read, 25 mA "
                                                     "during program/erase"),
    #not zero continuous
    ("microSD card (logging)",         0.040, 0.100, "[A] ~40 mA average while ArduPilot "
                                                     "logs; [D] 100 mA write peak"),
    #U11 (CAN) runs from +3V3_CAN through U21, not from this rail
    ("status LEDs D2/D3",              0.010, 0.010, "[A] 2 x ~5 mA through their resistors"),
    ("TMP119 temp sensor (U19)",       0.000, 0.000, "[D] TMP119: 3.5 uA active, "
                                                     "1.25 uA at the 1 Hz default rate"),
    ("PMW3901 flow breakout (J14)",    0.020, 0.030, "[A] the sensor plus the breakout's "
                                                     "LDO and LED"),
    ("INA180A2 antenna sense (U25)",   0.000, 0.000, "[D] INA180: 260 uA maximum quiescent"),
]
LOADS_3V3A = [  #through U10, TLV75533
    ("ICM-42688-P",                    0.001, 0.002, "[D] ~0.88 mA 6-axis continuous"),
    ("ICM-42605",                      0.001, 0.002, "[D] ~0.75 mA 6-axis continuous"),
    ("MS5611 barometer",               0.001, 0.002, "[D] 1.4 mA peak during conversion"),
    #the SoOP receiver
    ("MAX2112 tuner (U13)",            0.100, 0.100, "[D] MAX2112 Rev 3: 100 mA supply "
                                                     "current, VCC 3.3 V"),
    ("OPA2374 baseband amps (U14)",    0.002, 0.002, "[D] OPA2374: 585 uA per amplifier"),
    ("25 MHz TCXO (Y2)",               0.002, 0.002, "[L] JLCPCB C22381771: 3.3 V, "
                                                     "clipped sine, ~2 mA"),
]

LDO_SPEC = {
    #U9 since the Rev C review
    "TLV75733P": ("SOT-23-5 (DYD, exposed pad)", 92.5, 60.3,
                  "[D] TI TLV757P datasheet (docs/datasheets/TLV757P-TI.pdf) 5.4 Thermal Information, DYD",
                  125.0, 1.0,
                  "[D] TJ 125 C recommended operating maximum; 1 A output; VIN 1.45-5.5 V"),
    "AP2112K-3.3": ("SOT-23-5", 184.0, 100.8,
                    "[D] AP2112 datasheet Absolute Maximum Ratings: theta_JA SOT-23-5 184 C/W, explicitly '(No Heatsink)'",
                    150.0, 0.600,
                    "[D] TJ 150 C operating junction maximum; 600 mA minimum guaranteed "
                    "output"),
    "TLV75533":    ("SOT-23-5 (DBV)", 231.1, 100.8,
                    "[D] SBVS293 5.4 Thermal Information, DBV RthetaJA 231.1 C/W JEDEC "
                    "and 100.8 C/W on TI's EVM. docs/datasheets/TLV755P-SBVS293.pdf",
                    125.0, 0.500,
                    "[D] TJ 125 C recommended operating maximum; 500 mA output"),
}

#(clamping_V, standoff_V, breakdown_min_V, Ipp_A, src)
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
RES("R1", "10k")                                          #BOOT0 pulldown
IND("L1", "600R@100MHz", F_L0805)                          #VDDA ferrite

#buck 5V
CAP("C17","10u", F_C1206); CAP("C18","10u", F_C1206)      #VBAT bulk
CAP("C19","100n", F_C0402)                                 #VIN hf
RES("R3","preset")   #EN only - C20 (soft-start) deleted: TPS54202 is internal
RES("R4","392k"); RES("R5","78k7")                         #EN divider
CAP("C21","100n")                                          #boot cap
IND("L2", "10uH", F_ANR4030)   #4x4 land - the FNR4030 never fitted a 1210
CAP("C22","22u", F_C1206); CAP("C23","22u", F_C1206)      #5V out
CAP("C78","1u")                                           #U8 VCC bypass, pin 5
RES("R6","10k2"); RES("R7","3k24")                         #-> overridden, see _VALUE_FIX
#R8/C24/C25 COMP network deleted - TPS54202 compensates internally

#LDOs
CAP("C26","1u"); CAP("C27","1u")                           #U9 (TLV757P) in/out
CAP("C28","1u"); CAP("C29","2u2")                          #TLV75533 out; 2u2
CAP("C30","100n")                                          #3V3A local

#sensors
CAP("C31","100n"); CAP("C32","100n")                       #IMU1 VDD/VDDIO
CAP("C33","100n"); CAP("C34","100n")                       #IMU2
CAP("C35","100n")                                          #baro
CAP("C36","100n")                                          #flash
RES("R9","4k7"); RES("R10","4k7")                          #I2C1 pullups
RES("R11","4k7"); RES("R12","4k7")                         #I2C2 pullups

CAP("C41","100n")                                          #HVD230 VCC, on +3V3_CAN below
RES("R14","10k")                                           #HVD230 Rs slope
RES("R15","120R")                                          #termination (DNP by default)
COMPONENTS["R15"] = (R, F_R0402, "120R", "", True)

#USB
RES("R16","5k1"); RES("R17","5k1")                         #CC1/CC2
CAP("C42","1u", F_C0805)                                   #VBUS

#battery sense
RES("R18","10k", F_R0603); RES("R19","1k")                  #11:1 divider (R18 is 0603 for 6S 100mW headroom)
CAP("C43","100n"); CAP("C44","100n")                       #v/I sense filters

#LEDs + buzzer
RES("R20","1k"); RES("R21","1k")
add("D2", LED, F_LED, "BLUE"); add("D3", LED, F_LED, "GREEN")
add("SW1", SW, F_SW, "BOOT"); add("SW2", SW, F_SW, "RESET")

#microSD
CAP("C45","10u", F_C0805); CAP("C46","100n")
for i,(r) in enumerate(["R22","R23","R24","R25","R26","R27"]): RES(r, "47k")  #SDMMC pullups

#RF section passives
for r,v in [("C49","100n"),("C50","100n"),("C51","1u"),
            ("C52","100p"),("C56","100p"),("C57","100n")]:
    CAP(r, v, F_C0402)
for r,v in [("R28","0R"),("R29","0R"),("R31","4k7"),
            ("R34","330R"),("R35","1k"),("R36","4k7"),("R37","4k7")]:
    RES(r, v, F_R0402)
CAP("C58","10n", F_C0402)     #series DC-cut, Y2 output -> U13 XTAL [D] TCXO: 0.01 uF min
CAP("C59", "100n", F_C0402)

#the bias tee's two critical parts
RF_PARTS = dict(
    ant_esd=dict(
        part="PESD5V0C1BSFYL", lcsc="C477955",
        cj_pf=0.2, cj_max_pf=0.4, standoff_v=5.0,
        src="[D] Nexperia PESD5V0C1BSF: Cd = 0.2 pF, 5 V standoff, +-20 kV IEC 61000-4-2, DSN0603-2"),
    bias_choke=dict(
        part="LQW15AN27NH00D", lcsc="C113111",
        inductance_nh=27.0, srf_ghz=3.5, srf_min_ghz=2.0, dcr_ohm=0.52,
        x_min_ohm=250.0, f_carrier_ghz=1.6265,
        src="[D] Murata LQW15AN27N: SRF 3.5 GHz, DCR 0.52 ohm; [M] X at 1.6265 GHz = "
            "2*pi*f*L = 276 ohm; [M] C113111, 0402, 4497 in stock 2026-09-30"),
)
#connector orientation
MATING_FACE = {
    "J1": (0.0, +1.0),   #USB-C
    "J2": (0.0, +1.0),   #ESC JST-GH 8P
    "J3": (0.0, +1.0),   #GPS/I2C JST-GH 6P
    "J8": (0.0, +1.0),   #microSD card slot
    "J5": (0.0, +1.0),   #RC receiver JST-GH 4P
    "J6": (0.0, +1.0),   #DroneCAN JST-GH 4P
    "J9": (0.0, +1.0),   #I2C port JST-GH 4P
    "J11": (0.0, +1.0),  #SERIAL2 lidar port JST-GH 4P
    "J12": (0.0, +1.0),  #MMCX RF Antenna
    "J14": (0.0, +1.0),  #optical flow JST-GH 6P
    "J17": (0.0, +1.0),  #servo 1, 1x3 right-angle header
    "J23": (0.0, +1.0),  #servo 2
    "J21": (0.0, +1.0),  #companion TELEM JST-GH 6P
    "J22": (0.0, +1.0),  #payload 5V JST-GH 3P
}

MATING_PLUG = {
    "J1":  (9.0,   "[A] USB-C plug overmould, typical 9 mm"),
    "J2":  (12.9,  "[D] JST GHR 8P: 8 x 1.25 + 2.90"),
    "J3":  (10.4,  "[D] JST GHR 6P: 6 x 1.25 + 2.90"),
    "J5":  (7.9,   "[D] JST GHR 4P: 4 x 1.25 + 2.90"),
    "J6":  (7.9,   "[D] JST GHR 4P"),
    "J8":  (15.0,  "[A] microSD card, 15 mm across"),
    "J9":  (7.9,   "[D] JST GHR 4P"),
    "J11": (7.9,   "[D] JST GHR 4P"),
    "J12": (5.11,  "[D] MMCX right-angle cable plug"),
    "J14": (10.4,  "[D] JST GHR 6P: 6 x 1.25 + 2.90"),
    "J17": (8.0,   "[A] JR/Futaba 3-pin servo plug, 7.6-8.0 mm wide"),
    "J23": (8.0,   "[A] JR/Futaba 3-pin servo plug, 7.6-8.0 mm wide"),
    "J21": (10.4,  "[D] JST GHR 6P: 6 x 1.25 + 2.90"),
    "J22": (6.65,  "[D] JST GHR 3P: 3 x 1.25 + 2.90"),
}

MATING_PLUG_BODY = {
    "J1": 6.0, "J2": 5.0, "J3": 5.0, "J5": 5.0, "J6": 5.0, "J8": 14.0,
    "J9": 5.0, "J11": 5.0, "J12": 6.0, "J14": 5.0, "J17": 14.5, "J23": 14.5,
    "J21": 5.0, "J22": 5.0,
}

MATING_CLEARANCE = {
    "J1": 9.0,    #USB-C plug overmould
    "J2": 6.0,    #JST-GH plug plus wire bend
    "J3": 6.0,    #GPS/I2C JST-GH 6P
    "J5": 6.0,    #RC JST-GH 4P
    "J6": 6.0,    #DroneCAN JST-GH 4P
    "J8": 14.0,   #microSD ejection
    "J9": 6.0,    #I2C JST-GH 4P
    "J11": 6.0,   #lidar JST-GH 4P
    "J12": 6.0,   #MMCX coax cable straight run
    "J14": 6.0,   #flow JST-GH 6P
    "J17": 17.0,  #servo plug 14.5 mm on the overhanging pins
    "J23": 17.0,
    "J21": 6.0,   #companion JST-GH 6P
    "J22": 6.0,   #payload 5V JST-GH 3P
}

MATING_PLUG_UNDER = {r: 0.0 for r in MATING_FACE}

CONNECTOR_RETENTION = {
    "J2": ("latch", "JST-GH positive lock"),
    "J3": ("latch", "JST-GH positive lock"),
    "J5": ("latch", "JST-GH positive lock"),
    "J6": ("latch", "JST-GH positive lock"),
    "J8": ("latch", "microSD socket's card latch"),
    "J9": ("latch", "JST-GH positive lock"),
    "J11": ("latch", "JST-GH positive lock"),
    "J12": ("snap", "MMCX positive snap-lock"),
    "J14": ("latch", "JST-GH positive lock"),
    "J17": ("friction", "JR standard servo plug friction fit + printed clip"),
    "J23": ("friction", "JR standard servo plug friction fit + printed clip"),
    "J19": ("bench", "Tag-Connect TC2030-NL pogo-pin cable for recovery"),
    "J21": ("latch", "JST-GH positive lock"),
    "J22": ("latch", "JST-GH positive lock"),
    "J1": ("bench", "USB-C, for setup - unplugged before flight"),
}

#vertical mating
#connectors permanently mated vertically under the top plate during flight
VERTICAL_MATING = {}


#parts that must see something, not merely fit
GROUND_FACING = {
}

CAMERA = dict(name="OV9281 global-shutter module", mod_w=30.0, mod_t=12.0,
              lens_dia=8.0, lens_len=3.5,
              src="[D] Arducam B0162 module; [A] mount position undecided")
BELLY_SENSOR = dict(
    #derived, not a literal
    depth_available_mm=None,        #filled in below, once SKID exists - see the note
    typical_module_h=12.0,          #[L] TFS20-L / 3901-L0X class
    #plan footprint of the bracketed module, for the CAD
    l_mm=36.0, w_mm=16.0,
    occupant="Benewake TFS20-L (downward rangefinder, I2C 0x10 on J3)",
    future="a Matek 3901-L0X would take this slot and REPLACE the TFS20-L, since it "
           "carries its own VL53L0X - one module, one cable, flow AND range",
    mount="printed bracket under the bottom plate; needs a clear cone to the ground and must stay above the skid contact line so a landing does not crush it",
    src="[M] depth computed from design.SKID; [M] the 12 mm module envelope at this position passes the CAD fit check's ground clearance with 31.50 mm of margin")

PAYLOAD_BREAKOUT = dict(
    harness="2 wires: P41 (+5V) and P46 (GND) to the XIAO's 5V and GND pins",
    connector="optional 2-pin JST so the camera pod unplugs",
    current_a=0.25, headroom_a=None,
    alt="1S LiPo on the XIAO's BAT+/BAT- pads (built-in 370 mA charger, own USB-C) "
        "for zero connection to the FC - costs a second charging routine",
    not_on_fc="a socketed XIAO needs ~12 mm; the FC has 3.0 mm below and 5.4 mm above",
    future="+5V + GND from P41/P46 for a later 5.8 GHz VTX (there is no VBAT pad on this board - PF1 is a power flag, not a footprint) - separate decision",
    cost_gbp=1.0,
    src="[M] clearances from design.required_standoff(); [D] XIAO has BAT+/BAT- pads and a 1S charger; [M] 0.25 A against the +5V rail's 0.41 A headroom")

#a XIAO ESP32S3 Sense on the nose, writing to its own microSD
CAMERA_REC = dict(name="XIAO ESP32S3 Sense", L=21.0, W=17.5, H=13.0, g=6.0,
                  power="5V", current_a=0.25, storage="microSD <=32GB FAT32",
                  fw="ESP32-CAM_MJPEG2SD, ~20 fps AVI",
                  mount="nose; SO1-V6-AN-Cam-Mount.stl is 62.6 x 28.8 and made for a "
                        "19x19 analogue cam, so it needs a simple printed bracket",
                  radio_off=True,
                  #how far forward of centre it sits, in mm
                  nose_y_mm=78.0,
                  src="[D] Seeed: XIAO form factor 21 x 17.5 mm, OV2640/OV3660, microSD, 8 MB PSRAM; [L] ~GBP 10-14 AliExpress")

#the MOTOR / ARM / SKID bolt pattern - one number
M3_WASHER = dict(t=0.5, od=7.0, bore=3.2,
                 src="[D] DIN 125-A M3: 3.2 mm bore, 7.0 mm OD, 0.5 mm thick")
MOTOR_JOINT = dict(
    pitch_mm=19.0,          #[D] BrotherHobby Avenger 2806.5: M3 at 19 x 19
    screw="M3",             #[D] same source
    screw_dia=3.0,
    #what the screw passes through, head first
    layers=(
        ("M3 washer", ("M3_WASHER", "t"), 3.2,
         "[D] DIN 125-A M3 - spreads the head's load on the TPU plate"),
        ("printed skid", ("SKID", "t"), 3.2,
         "[M] design.SKID - printed, so the hole is ours to specify; 3.2 mm is standard "
         "M3 close clearance for a 3.0 mm screw"),
        ("frame arm", ("FRAME", "arm_t"), 3.2,
         "[D] So1-V6 arm 6.0 mm; [A] 3.2 mm hole - the frame's motor holes are published "
         "as the 19x19 PATTERN, not as diameters"),
    ),
    engages="motor tapped boss",
    tap_dia=3.0,
    engage_mm=4.0,          #[A] 1 x diameter for M3 in aluminium - see fasteners.py
    boss_depth_mm=None,     #not published anywhere - see the overshoot warning below
    src="[D] BrotherHobby Avenger 2806.5 product data (M3, 19x19); "
        "[M] arm and skid thicknesses referenced from this file",
)


#(16.0, 19.0) -> '16x16 / 19x19', for doc tables and check messages
def fmt_pattern(pitches_mm):
    return " / ".join(f"{p:.0f}x{p:.0f}" for p in sorted(pitches_mm))

#the skid is a part you print
SKID = dict(t=3.5, drop=45.0, hole_pitch=MOTOR_JOINT["pitch_mm"], printed=True,
            #the printed part: a plate under the arm on the motor's screws
            plate=34.0, relief_d=10.0, strut_w=6.0, strut_d=8.0, strut_x0=8.0, splay_deg=10.0,
            foot=(12.0, 10.0), flare=3.0, material="TPU 95A", density=1.21, infill=0.8,
            #drop raised 25 -> 40 mm to give the LD06 a home, then 45 mm
            src="[D] 19x19 pitch is the motor's bolt pattern (BrotherHobby Avenger); [M] 3.5 mm thickness is a design choice for a printed part")

#belly depth is SKID's drop plus its pad thickness
BELLY_SENSOR["depth_available_mm"] = SKID["drop"] + SKID["t"]
#the ESC this board bolts to
TOP_PLATE_MOUNT = dict(
    #the kit's own standoffs are 22 mm (front, on the mid plate) and 30 mm
    kit_front=22.0, kit_rear=30.0,
    front_standoff=25.0, rear_standoff=33.0, post_od=5.0,
    front_posts=((-14.6, -27.88), (14.6, -27.88), (-14.6, -52.88), (14.6, -52.88)),
    rear_posts=((-14.6, 27.88), (14.6, 27.88), (-11.0, 80.75), (11.0, 80.75)),
    plate_centre_y=dict(fc=-29.16, bottom=31.09, top=4.78),
    src="[D] cad/frame-dxf.json (So1-V6-7inDC-2025-JUL-07.dxf sha 398556cd), hole patterns per plate")


#the stack against the top plate the kit actually gives it
def required_standoff(board, headroom=None):
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
                    f"TOP_PLATE_MOUNT ({front:.0f} mm front standoffs on the mid plate)")

#what touches this board's faces at the four stack holes, outermost first
FC_HOLE_HARDWARE = dict(
    top=[dict(name="M3 nylon washer, under the stack bolt's head", reach_d=7.0, t=0.8,
              conductive=False),
         dict(name="M3 steel cap head", reach_d=5.5, t=3.0, conductive=True)],
    bottom=[dict(name="M3 nylon hex spacer, ESC to FC (fasteners.py sizes it)",
                 reach_d=5.5 / 0.8660254, t=15.0,
                 conductive=False)],
    shank_d=3.0,
    #copper keeps clear of a metal 5.5 mm-AF hex too (3.18 mm to its corners, plus margin)
    pad_clear=3.3,
    src="[D] ISO 4762 M3 head 5.5 mm; DIN 125 M3 washer 7.0 mm OD; [L] nylon washers 0.8 mm thick; [D] a 5.5 mm-AF hex reaches 6.35 mm across its corners")

BOARD_T = 1.6                       #[M] 6-layer stackup, tools/design.py
STANDOFF_STOCK = (25, 30, 35, 40, 45)   #[L] common M3 aluminium standoff lengths
NYLON_SPACER_STOCK = (8, 10, 12, 15, 20)  #[L] common M3 nylon female-female hex lengths

#the soft mount between this board and the ESC
MOUNTING = dict(gap=3.0, grommet_d=6.0, screw="M3", screw_dia=3.0,
                hole_d=4.0, plate_hole_d=3.2,
                pitch=30.5,
                src="[A] M3 silicone grommet compressed to 3.0 mm; "
                    "[M] 30.5 mm pitch and 4.0 mm holes from design.BOARD")

ESC = dict(name="SpeedyBee BLS 60A", L=45.6, W=44.0, pcb=1.6, parts=6.2,
           mount=30.5, conn="JST-SH 8P", cells="3-6S", amps=60,
           H=7.8, g=23.5, cont_A=60.0, burst_A=80.0, proto="DSHOT300/600",
           cur_scale_mv_per_A=40.0,
           #the 8-pin JST-SH order as the ESC'S manual documents IT
           pin_order=("GND", "VBAT", "M1", "M2", "M3", "M4", "CUR", "TEL"),
           src="[D] SpeedyBee BLS 60A manual; [L] 23.5 g from speedybee.com's product page")
assert ESC["amps"] == ESC["cont_A"], "ESC amps and cont_A are the same rating"

#between the ESC and this board's underside
FOAM = dict(
    baro=dict(t=3.0, size=(8.0, 6.0), over=("U4",), part_h=1.0,
              material="open-cell PU foam, a small block over the MS5611",
              why="shields the baro's port from light, prop wash and the ESC's warm air "
                  "without sealing it"),
    imu_shroud=dict(t=1.5, size=(30.0, 20.0), over=("U2", "U3", "U4"), part_h=0.91,
                    material="closed-cell foam pad, adhesive-backed, on the ESC's top face",
                    why="a radiation and convection break between the ESC and the IMUs; "
                        "it does not touch the board"),
    src="[D] MS5611 1.0 mm, ICM-42688-P 0.91 mm package height; [A] foam thicknesses chosen "
        "to leave >= 1 mm of air to the facing part",
)

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
PI = dict(name="Radxa Zero 3W (1GB) - DEFERRED, not fitted", L=65.0, W=30.0, t=1.2,
          hole_dia=2.75, hole_pitch=None,
          soc="RK3566 quad Cortex-A55 @ 1.6 GHz",
          power_a=2.0,
          g=12.0,
          csi="J7, FPC-22P-0.5mm, 4-lane MIPI CSI - the same connector as a Pi Zero, so "
              "a 22-to-15-pin Zero cable mates a 15-pin OV9281 module",
          src="[D] radxa.com/docs: 65 x 30 mm, 1x4-lane MIPI CSI, 5V/2A; [D] radxa_zero_3w_v1.12_schematic.pdf for the CSI connector")

#the aircraft flies without it - see FLOW below
FLOW = dict(
    fitted=False,
    camera="OV9281 global shutter, 22-pin CSI - NOT ordered in this pass",
    arrives_as="MAVLink OPTICAL_FLOW from the companion, FLOW_TYPE 5",
    onboard_fallback="there is no on-board flow part",
    operational_note="EK3_SRC2 and EK3_SRC3 both use VELXY 5 (flow)",
    src="[M] drift table computed from a = g*sin(theta); [M] flow_only p95 446 m in sitl/")

#the CAMERA interface, and the work it still NEEDS
CAMERA_IFACE = dict(
    connector="J7 FPC-22P-0.5mm, 4-lane MIPI CSI",
    pwdn_gpio="gpio3 RK_PC6 (CAMERAB_PDN_L, J7 pin 18)",
    i2c="I2C2_M1 on J7 pins 21/22",
    status="NOT WORKING OUT OF THE BOX - needs a kernel rebuild and a custom DT overlay",
    blocking=False,
    src="[D] radxa_zero_3w_v1.12_schematic.pdf; [L] radxa forum thread 26386; [D] github.com/radxa/overlays has no ov9281 overlay, checked 2026-09-02")

#rejected companions, kept so the questions are not reopened from scratch
PI_REJECTED = [
    dict(name="Orange Pi Zero 2W", price_gbp=25.0,
         why="No MIPI CSI connector AT all. The 24-pin 'function' connector sitting where the Pi Zero's CSI socket would be carries 100M Ethernet, 2x USB 2.0",
         src="[D] OrangePi_Zero2w_H618_User-Manual_v1.1.pdf, searched in full"),
    dict(name="Raspberry Pi Zero 2 W", price_gbp=14.40,
         why="Deferred, not rejected - the zero-risk camera path, and the cheapest, but sold out at The Pi Hut and Pimoroni with the open market at GBP 70",
         src="[L] thepihut.com GBP 14.40 / pimoroni GBP 12.00, both out of stock "
             "2026-09-02; [D] RP-008358-DS-1"),
]


STACK_BELOW = [
    ("SpeedyBee BLS 60A ESC", 3.0, 45.6 / 2, 44.0 / 2,
     "[D] SpeedyBee manual + [A] 3.0 mm compressed grommet gap"),
]


#off-board parts
OFFBOARD = dict(
    gps=dict(part="M10 + QMC5883L", conn="JST-GH 6P on J3",
             pinout=["5V", "USART2_TX", "USART2_RX", "I2C1_SCL", "I2C1_SDA", "GND"],
             note="this is the standard ArduPilot GPS order, so a stock M10 cable mates "
                  "pin-for-pin. Verify against the netlist, not against memory.",
             src="[M] design.py nets: J3.2/3 USART2, J3.4/5 I2C1, J3.6-8 GND"),
    rangefinder_down=dict(part="Benewake TFS20-L", variant="I2C", addr=0x10,
                          lands_on="J9 (dedicated I2C port)", vcc="3.3 V",
                          wrong_variant_note="the UART variant would need a spare UART on a connector, and there is none: J21 is the companion's and J11 the lidar's",
                          src="[D] AP_RangeFinder Benewake TFS20L driver, I2C 0x10"),
    rangefinder_up=dict(part="VL53L1X module (GY-53-L1X)", addr=0x29,
                        lands_on="J9 (dedicated I2C port)", vcc="3.3 V",
                        free_because="U7 is deleted - the on-board VL53L1X would "
                                     "otherwise own 0x29 and collide",
                        src="[D] VL53L1X fixed default address 0x29"),
    buzzer=dict(part="5V PASSIVE piezo", lands_on="P161-P163 (soldered)", drive="PA15 TIM2_CH1 ALARM",
                must_be="passive",
                note="a TIMER channel means ArduPilot generates the tone patterns, so an "
                     "ACTIVE buzzer (own oscillator) loses every arming/failsafe pattern",
                src="[M] hwdef.dat: PA15 TIM2_CH1 TIM2 GPIO(32) ALARM"),
    led=dict(part="WS2812B strip", lands_on="P151-P153 (soldered)", volts=5,
             note="the on-board 74LVC1G17 outputs 5 V logic - a 12 V strip (WS2815) will "
                  "not light",
             src="[M] design.py: U17 drives WS2812_OUT at 5 V into P152"),
    rx=dict(part="ELRS 2.4 GHz receiver - MUST BE ESP-BASED", lands_on="J5 (USART6)",
            mcu="ESP", min_fw="3.5.0",
            gcs_note="ELRS MAVLink needs SERIAL7_PROTOCOL 2, SERIAL7_BAUD 460, RSSI_TYPE 5",
            src="[D] expresslrs.org/software/mavlink: ESP-based TX and RX only, firmware >=3.5.0, TX backpack >=1.5.0; STM32 devices cannot support MAVLink mode",
            note="solder pads, not a connector - no mating risk"),
    #replaces the 8-sensor ToF ring
    lidar=dict(part="LDROBOT LD06 - 12 m, 25 klux, INDOOR USE ONLY",
               lands_on="SERIAL2 (USART1) - the lidar's TX to TP6 (USART1_RX)",
               wires="TX only; PWM unconnected - the unit self-spins at a default rate",
               #mechanical/electrical from the LDROBOT LD06 datasheet, read
               L_mm=38.59, W_mm=38.59, H_mm=33.30, g=42.0,
               ma_run=180, ma_startup=300, volts=5.0, conn_on_lidar="ZH1.5T-4P",
               #full [D] spec table, LDROBOT LD06 datasheet:
               range_m=(0.02, 12.0),          #20 mm blind zone - nothing closer reads
               accuracy_mm=(30, 45),          #typical, max at 70 % target reflectivity
               resolution_mm=15,
               scan_hz=(5, 10, 13),           #min, typical, max - PWM-controlled
               sample_hz=4500,
               angular_res_deg=1.0, angular_err_deg=2.0,
               #the height of the optical window above the mounting base
               scan_plane_height_mm=None,
    gbp=13.99,
    #position on the belly: set from MOUNTS
    mount_y_mm=None,
               wiring={"TX": "J11.3 (USART1_RX)", "5V": "J11.1", "GND": "J11.4"},
               params={"SERIAL2_PROTOCOL": 11, "SERIAL2_BAUD": 230, "PRX1_TYPE": 16,
                       "PRX1_ORIENT": 1, "BRD_SER2_RTSCTS": 0},
               orient_note="PRX1_ORIENT 1 = upside-down underneath, which is how this airframe carries it - a top mount is blocked by the battery",
               baud={"LD06/LD19/STL": 230400, "LD14P": 115200},
               indoor_only=True, klux=25, indoor_lux=(300, 500),
               outdoor_swap="LD19 / STL-19P / STL-06P (60 klux) or LD14P (80 klux, "
                            "115200 baud) - same driver, drop-in",
               buying_check="confirm the bundle contains the LIDAR unit, not a cable or adapter board, and that it is LDROBOT protocol - a look-alike clone is a Lua-driver project",
               src="[D] AP_Proximity_LD06.cpp: 47-byte frame, 0x54 start, CRC8 0x4D; [D] ArduPilot LD06 wiring page: TX only, PWM unconnected, self-spins"),
    esc=dict(part="SpeedyBee BLS 60A", conn="JST-GH 8P on J2 (side entry, latching)",
             note="J2 pins 1-8 follow the SpeedyBee order, so the cable is straight through; the ESC end is its own JST-SH 8P. Buzz the cable before VBAT",
             src="[D] SpeedyBee manual + [M] design.py nets"),
    src="[M] every 'lands_on' traced to design.py nets")

#payload provisions: what a future module can actually have
PAYLOAD = dict(
    pwm=[("PWM5", "PB9", "TP3", "SERVO5_FUNCTION"),
         ("PWM6", "PA3", "TP4", "SERVO6_FUNCTION")],
    #J21's UART7 is the companion's
    serial=[(2, "USART1", "J11", "EARMARKED for the 360 lidar "
                                 "(PRX1_TYPE 16); free only until that is fitted")],
    serial_unrouted=[(4, "USART3"),   #PD8/PD9 stop at the MCU
                     (5, "UART8"),    #declared in hwdef, no nets in the design at all
                     (6, "EMPTY")],   #UART4 gave PB8 to servo PWM7; SERIAL6 has no UART
    serial_earmarked=[(1, "companion computer, MAVLink2 + OPTICAL_FLOW on J21"),
                      (2, "360 lidar, PRX1_TYPE 16")],
    power_5v=["J21.1", "J22.1", "P151", "J5.1", "J9.1", "J11.1"],
    gnd=["J21.6", "J22.2", "P153", "J5.4", "J9.4", "J11.4"],
    #a servo drawing real current must not come off the flight controller's 5 V rail
    power_note="signal is 3.3 V logic, which every hobby servo and ESC accepts as a valid PWM high",
    mass_budget_g=885.0,   #payload at 40% hover throttle, from the build check
    src="[D] hwdef.dat PWM/SERIAL_ORDER + [M] defaults.parm claims + [M] the build check "
        "power and payload figures")

#the airframe, one source of truth

#tbs source one V5 7" DC - and the reason for it is the provenance, not the geometry
FRAME = dict(name='TBS Source One V5 7in DC', wb=320.0, size=(200.0, 230.0),
             #22, not 30
             inner_h=25.0,
             bottom_t=2.5, medium_t=2.0, upper_t=2.0, arm_t=6.0, cam_plate_t=2.0,
             stack="30.5x30.5 M3 and 20x20 - VERIFIED from the manufacturer DXF",
             #numeric, not the string "16x16 / 19x19"
             motor_patterns_mm=(16.0, 19.0),
             strap=(20.0, 300.0), price_gbp=35.90, g=143.5,
             src="[D] github.com/tbs-trappy/source_one So1-V6-7inDC-2025-JUL-07.dxf, stack patterns parsed directly 2026-09-02; [L] hobbyrc.co.uk for standoffs 30/22 mm")
assert FRAME["inner_h"] == TOP_PLATE_MOUNT["front_standoff"], \
    "FRAME.inner_h must be the kit's front standoff (TOP_PLATE_MOUNT) - one number"
assert abs(FRAME["arm_t"] + FRAME["medium_t"]
           - (TOP_PLATE_MOUNT["rear_standoff"] - TOP_PLATE_MOUNT["front_standoff"])) < 1e-6, \
    "the two standoff sets stand on plates 8 mm apart and hold one flat top plate"

#the fit question, answered from the DXF - not deferred to calipers
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
#weight and bolt pattern are from BrotherHobby's own Avenger 2806.5 product data
MOTOR = dict(name="2806.5 1300KV", kv=1300, g=41.0, thrust_g=1250,
             hole_pitch_mm=MOTOR_JOINT["pitch_mm"],
             shaft_thread="M5", poles="12N14P",
             #body envelope, for the CAD
             dia_mm=28.0, h_mm=15.0,
             src="[D] 41 g, M3 19x19, M5 prop adapter thread, 12N14P (BrotherHobby Avenger product data); [A] 1250 g thrust")
BATT = dict(name="Zeee 4S 6500mAh", L=138, W=47, H=48, g=615, conn="EC5", hard=True,
            cells=4, src="[L] retailer listing")
#the ESC, the smoke stopper and the pigtails are all XT60
POWER_CONN = dict(airframe="XT60", pack=BATT["conn"], adapter_needed=True,
                  src="[L] Zeee hardcase packs ship EC5; [D] SpeedyBee BLS 60A is XT60")
#confirmed against the manufacturer, not a marketplace listing
PROP = dict(name="7040", dia_mm=178.43, g=7.9, bore_mm=5.0, mount="M5",
            src="[D] Gemfan Flash 7040-3 published spec: 5 mm centre hole, 178.43 mm disc, 7.9 g, PC. Bore matches the [D] M5 motor shaft")


#mounts: every part off the board has a printed mount and screws coordinates as the CAD

#heat-set inserts: CNC Kitchen's published sizes
INSERTS = {
    "M2":   dict(dia=2.0, L=3.0, od=3.6, bore=3.2),
    "M2.5": dict(dia=2.5, L=4.0, od=4.6, bore=4.0),
}
INSERT_WALL = 1.6
INSERT_SRC = ("[L] CNC Kitchen heat-set insert range as listed by kb-3d.com: M2 x 3.0 in a 3.2 mm bore, M2.5 x 4.0 in 4.0 mm")
#hardware this close to the compass (inside the GPS) is brass or nylon
NONMAG_RADIUS_MM = 50.0

#the parts the mounts carry: envelopes
MOUNTED = dict(
    gps=dict(name="Matek M10Q-5883 (M10 GNSS + QMC5883L)", L=20.0, W=20.0, H=12.4, g=8.0,
             src="[L] Matek M10Q-5883 listings (RMRC, GetFPV): 20 x 20 x 12.4 mm, 8 g; no "
                 "mounting holes, so it sits in a pocket under a screwed lid"),
    #the Iridium antenna: an active quadrifilar helix
    iridium_antenna=dict(name="Tallysman HC610 active Iridium helix", dia=33.3, dia_top=28.5,
                         H=54.2, g=24.0, hole_pcd=20.0, hole_depth=6.0, sma_hole=12.0,
                         src="[D] Tallysman HC610 datasheet: RHCP quadrifilar helix, 3.7 dBic at zenith, pre-filter then 28 dB LNA, NF 2.0 dB"),
    rx=dict(name="RadioMaster RP3 (ELRS 2.4 GHz, two antennas)", L=22.0, W=13.0, H=4.0,
            g=1.6, src="[L] RadioMaster RP3 listing: 22 x 13 x 4 mm; no holes, so it sits "
                       "in a pocket under a screwed cover"),
    elrs_antenna=dict(name="ELRS 2.4 GHz T antenna", L=65.0, dia=3.0,
                      src="[L] the RP3's two T antennas, ~65 mm; [A] 3 mm across the "
                          "sleeve"),
    xiao=dict(name=CAMERA_REC["name"], L=17.5, W=13.0, H=21.0, lens_dia=8.0,
              src=CAMERA_REC["src"] + "; stands on edge, board facing forward, so the "
                                      "Sense lens looks ahead"),
    lidar=dict(name="LDROBOT LD06", hole_diag_mm=(28.2, 28.2), hole_depth_mm=5.8,
               src="[D] LDROBOT LD06 datasheet: two M2.5 holes in the base on a 28.2 x 28.2 "
                   "mm diagonal, 5.8 mm deep with 4.8 mm counterbores"),
    range_down=dict(name="Benewake TFS20-L", L=15.0, W=21.0, H=7.87, g=1.35,
                    src="[D] Benewake TFS20-L datasheet: 21 x 15 mm board, 7.87 mm tall, "
                        "1.35 g, no mounting holes, so it sits in a cradle under a lid"),
    remote_id=dict(name="Holybro Remote ID (PCB, ArduRemoteID)", L=35.3, W=23.5, H=6.0, g=6.0,
                   src="[L] docs.holybro.com Remote ID: PCB 35.3 x 23.5 mm, 4 g, JST-GH 4P CAN, "
                       "IPEX antenna; [A] 6 mm over its parts and 2 g for the antenna"),
)

_TOP_Z = FRAME["bottom_t"] + TOP_PLATE_MOUNT["rear_standoff"] + FRAME["upper_t"]
_MID_Z = FRAME["bottom_t"] + FRAME["arm_t"]            #the mid plate's underside
#the battery on the top plate, pushed forward
BATT_POS = dict(y=-6.0, z=_TOP_Z,
                src="[M] the 138 mm pack runs y -75 to +63; the top plate runs -75.4 to "
                    "+84.9 (cad/frame-dxf.json) and the Iridium helix starts at +67.4")

#each mount: where it sits, what it carries
MOUNTS = dict(
    antenna_tower=dict(
        carries=("iridium_antenna", "gps"),
        foot=dict(x=36.0, y=24.0, t=4.0, y0=TOP_PLATE_MOUNT["rear_posts"][3][1]),
        #narrow enough that the foot screws' heads clear it
        column=dict(x=15.0, y=16.0, wall=2.4, y0=84.0),
        #the helix stands on the seat, its SMA down the hollow column
        seat=dict(x=40.0, y_front=68.0, y_back=104.0, t=4.0, z=64.0, y0=84.0),
        #the arm runs aft to the GPS pod, a T with its web below
        arm=dict(x=44.0, y_end=178.0, t=4.0, web=3.0, web_h=16.0),
        #the GPS 80 mm behind the helix's axis, its top between the heights
        gps=dict(y0=164.0, top_z=105.5, pod_y=28.0, pocket=8.0, lid_t=2.0, lid_cbore=2.0,
                 wall=2.0),
        #the coax (J12's MMCX pigtail onto the helix's SMA) and the GPS lead are tied
        tie_y=135.0,
        joints=[dict(where="antenna tower to top plate, at the rear posts", size="M3", qty=2,
                     at=[(x, y, _TOP_Z) for x, y in TOP_PLATE_MOUNT["rear_posts"][2:]],
                     layers=[("tower foot", "foot.t"), ("top plate", FRAME["upper_t"])],
                     into="standoff"),
                dict(where="Iridium helix to the tower seat", size="M2.5", qty=2,
                     at=[(0.0, 74.0, 64.0), (0.0, 94.0, 64.0)],
                     layers=[("tower seat", "seat.t")], into="thread",
                     limit="iridium_antenna.hole_depth"),
                dict(where="GPS pod to the tower arm", size="M2", qty=2,
                     layers=[("tower arm", "arm.t")], into="insert"),
                dict(where="GPS lid to its pod", size="M2", qty=2,
                     layers=[("lid, under the recessed head", "gps.lid_under_head")],
                     into="insert")],
        print_note="seat and arm on the bed; PETG"),
    nose_mount=dict(
        carries=("xiao", "rx", "elrs_antenna"),
        plate=dict(x=48.0, y0=-47.0, y1=-106.0, t=3.0),     #the front arms start at x=25
        cradle=dict(y0=-97.0, wall=2.0, lid_t=2.0),
        rx_pocket=dict(y0=-71.0, wall=1.6, cover_t=1.5),    #aft of the post screw heads
        #one antenna vertical, one horizontal pointing forward
        antenna_v=dict(x=19.0, y=-90.0),
        antenna_h=dict(x=-19.0, y=-106.0, z=0.0),
        joints=[dict(where="nose mount to mid plate, under the front posts", size="M3",
                     qty=2, at=[(x, y, _MID_Z) for x, y in TOP_PLATE_MOUNT["front_posts"][2:]],
                     layers=[("nose mount plate", "plate.t"),
                             ("mid plate", FRAME["medium_t"])], into="standoff"),
                dict(where="XIAO lid to its cradle", size="M2", qty=2,
                     layers=[("lid", "cradle.lid_t")], into="insert"),
                dict(where="RP3 cover to the nose mount", size="M2", qty=2,
                     layers=[("cover", "rx_pocket.cover_t")], into="insert")],
        print_note="the face against the mid plate on the bed"),
    lidar_bracket=dict(
        carries=("lidar",),
        plate=dict(x=44.0, y0=3.0, y1=48.0, t=5.0, cbore=3.2),
        #24, not centred on the posts
        lidar_y0=24.0,
        joints=[dict(where="lidar bracket to bottom plate, at the rear posts", size="M3",
                     qty=2, at=[(x, y, 0.0) for x, y in TOP_PLATE_MOUNT["rear_posts"][:2]],
                     layers=[("bracket, under the recessed head", "plate.t-plate.cbore"),
                             ("bottom plate", FRAME["bottom_t"])], into="standoff"),
                dict(where="lidar bracket to bottom plate, front pair of the 20x20 M2 holes",
                     size="M2", qty=2, at=[(-10.0, 43.5, 0.0), (10.0, 43.5, 0.0)],
                     layers=[("bracket, under the recessed head", "plate.t-plate.cbore"),
                             ("bottom plate", FRAME["bottom_t"])], into="nut"),
                dict(where="LD06 to its bracket", size="M2.5", qty=2,
                     layers=[("LD06 base", "lidar.hole_depth_mm")], into="insert")],
        print_note="flat"),
    range_cradle=dict(
        carries=("range_down",),
        y0=63.5, x=28.0, y=26.0, top_t=1.5, lid_t=1.5,
        joints=[dict(where="TFS20-L lid, cradle and bottom plate, rear pair of the 20x20 "
                           "M2 holes", size="M2", qty=2,
                     at=[(-10.0, 63.5, 0.0), (10.0, 63.5, 0.0)],
                     layers=[("lid", "lid_t"), ("cradle", "body_h"),
                             ("bottom plate", FRAME["bottom_t"])], into="nut")],
        print_note="top down"),
    #the Remote ID board on the rear-port arm's top face
    rid_tray=dict(
        carries=("remote_id",),
        r=63.6, arm=(-1, 1), base_t=2.0, wall=1.6, cover_t=1.5, gap=0.2, tie_u=(-10.0, 10.0),
        joints=[dict(where="Remote ID cover to its tray", size="M2", qty=2,
                     layers=[("cover", "cover_t")], into="insert")],
        print_note="base on the bed; the cover top down"),
)
OFFBOARD["lidar"]["mount_y_mm"] = MOUNTS["lidar_bracket"]["lidar_y0"]


#mass, one source of truth
#the printed skid's heights (z from the bottom plate's underside, as drone.scad)
def skid_geometry():
    import math
    S = SKID
    top = FRAME["bottom_t"]                       #arm underside = the plate's top face
    contact = -(S["drop"] + S["t"])
    z0 = top - S["t"]                             #plate underside, where the struts start
    z1 = contact + S["flare"]                     #strut ends, where the foot flares out
    reach = S["strut_x0"] + (z0 - z1) * math.tan(math.radians(S["splay_deg"]))
    return dict(top=top, contact=contact, z0=z0, z1=z1, reach=reach,
                half=max(S["plate"] / 2, reach + S["foot"][0] / 2))


#four skids, from their geometry (plate less its holes, splayed struts, 45 deg feet)
def skid_mass_g():
    import math
    S, g = SKID, skid_geometry()
    plate = (S["plate"] ** 2 - 4 * math.pi * 1.6 ** 2 - math.pi * (S["relief_d"] / 2) ** 2) * S["t"]
    struts = 2 * S["strut_w"] * S["strut_d"] * (g["z0"] - g["z1"]) / math.cos(
        math.radians(S["splay_deg"]))
    a1, a2 = S["strut_w"] * S["strut_d"], S["foot"][0] * S["foot"][1]
    am = (S["strut_w"] + S["foot"][0]) / 2 * (S["strut_d"] + S["foot"][1]) / 2
    feet = 2 * S["flare"] / 6 * (a1 + 4 * am + a2)
    return 4 * (plate + struts + feet) / 1000 * S["density"] * S["infill"]


MASS_ITEMS = [
    ("frame",                            FRAME["g"],      FRAME["src"]),
    ("4x motors",                        4 * MOTOR["g"],  MOTOR["src"]),
    ("ESC",                              ESC["g"],        ESC["src"]),
    ("this board",                       20,              "[A]"),
    ("4x props",                         4 * PROP["g"],   PROP["src"]),
    ("battery",                          BATT["g"],       BATT["src"]),
    ("GPS",                              MOUNTED["gps"]["g"], MOUNTED["gps"]["src"]),
    ("RX",                               MOUNTED["rx"]["g"], MOUNTED["rx"]["src"]),
    ("Iridium antenna (HC610)",          MOUNTED["iridium_antenna"]["g"],
     MOUNTED["iridium_antenna"]["src"]),
    ("XIAO nose camera",                 CAMERA_REC["g"], CAMERA_REC["src"]),
    ("printed mounts, inserts, screws",  45,              "[A] PETG at ~30% infill"),
    #PI["src"] is the DATASHEET source for the 65x30 mm outline and the 5V/2A rating
    (PI["name"],                         PI["g"],
     "[A] ~12 g, not published by Radxa - same 65x30 mm PCB class as a Pi Zero (11 g) "
     "with eMMC pads and a heavier SoC"),
    ("camera+cable (deferred, budgeted)", 10,             "[A]"),
    ("TFS20-L",                          1.4,             "[D]"),
    ("LD06 360 lidar (deferred, budgeted)", OFFBOARD["lidar"]["g"],
     "[D] LDROBOT LD06 datasheet - REPLACES the superseded 25 g ToF ring + mux"),
    ("Remote ID (Holybro, rear-port arm)", MOUNTED["remote_id"]["g"], MOUNTED["remote_id"]["src"]),
    ("skids",                            round(skid_mass_g(), 1),
     "[M] design.SKID geometry x TPU 1.21 g/cm3 x [A] 80% infill (skid_mass_g)"),
    ("wiring/straps",                    60,              "[A]"),
]
AUW_G    = sum(g for _n, g, _s in MASS_ITEMS)
THRUST_G = 4 * MOTOR["thrust_g"]

#payload at 40% hover throttle - the conservative figure
PAYLOAD["mass_budget_g"] = max(0.0, THRUST_G * 0.4 - AUW_G)


#nets
#pins may be given by number or by name ("U1.PA5")
NETS = {}
def net(name, *pins): NETS.setdefault(name, []).extend(pins)

#power rails
net("GND",
    "U1.10","U1.26","U1.49","U1.74","U1.99","U1.19",           #VSS + VSSA
    "U2.6","U3.6","U4.3","U5.4","U5.9",   #U5 pad 9: the WSON exposed pad
    #pin 7 of both IMUs
    "U2.7","U3.7",
    "U8.1","U8.6","U8.11","U9.2","U9.6","U10.2","U11.2","U12.2",   #U8: PGND 1/11 + AGND 6; U9 pad 6 its thermal pad
    "J1.A1B12","J1.B1A12","J1.13","J1.14",
    "J2.1","J2.9","J2.10", "J3.6","J3.7","J3.8",
    "J5.4","J5.5","J5.6", "J6.4","J6.5","J6.6",
    "J8.6","J8.10","J8.11","J8.12","J8.13",
    "Y1.2","Y1.4", "D1.2",
    "C1.2","C2.2","C3.2","C4.2","C5.2","C6.2","C7.2","C8.2","C9.2",
    "C10.2","C11.2","C12.2","C13.2","C14.2","C15.2","C16.2",
    "C17.2","C18.2","C19.2","C22.2","C23.2",
    "C26.2","C27.2","C28.2","C29.2","C30.2","C31.2","C32.2","C33.2","C34.2",
    "C35.2","C36.2","C41.2","C42.2",
    "C43.2","C44.2","C45.2","C46.2",
    "R1.2","R5.2","R7.2","R14.2","R19.2","SW1.2","SW2.2","D2.2","D3.2",
    "U4.4","U4.5",                                              #CSB + internal -> GND = addr 0x77
    )
#the battery input is protected by Q4
net("VBAT_IN", "J2.2", "D1.1", "Q4.3")            #D1 pin 1 = cathode; Q4 pin 3 = drain
net("VBAT", "Q4.2", "C17.1","C18.1","C19.1","U8.2","U8.10","R4.1","R18.1")  #Q4 p2 = source
net("+5V",  "C22.1","C23.1","U9.1","C26.1","U10.1","C28.1",
            "J3.1","J5.1","R6.1")
net("+3V3", "U9.5","C27.1","U1.11","U1.27","U1.50","U1.75","U1.100",
            "C1.1","C2.1","C3.1","C4.1","C5.1","C6.1","C7.1",
            "U5.8","C36.1",
            "J8.4","C45.1","C46.1","L1.1",
            "R9.1","R10.1","R11.1","R12.1","R20.1","R21.1",
            "R22.1","R23.1","R24.1","R25.1","R26.1","R27.1","SW1.1")
net("+3V3A","U10.5","C29.1","C30.1","U2.5","U2.8","C31.1","C32.1",
            "U3.5","U3.8","C33.1","C34.1","U4.1","U4.2","C35.1")   #U4.2=PS high -> I2C
net("VDDA", "L1.2","U1.21","U1.20","C10.1","C11.1","C12.1","C13.1")

#MCU housekeeping
net("VCAP1","U1.48","C8.1")
net("VCAP2","U1.73","C9.1")
net("NRST", "U1.14","C14.1","SW2.1")
net("BOOT0","U1.94","R1.1","SW1.1")
net("OSC_IN", "U1.PH0-OSC_IN","Y1.1","C15.1")
net("OSC_OUT","U1.PH1-OSC_OUT","Y1.3","C16.1")
net("VBAT_MCU","U1.6","+3V3_TIE")   #VBAT pin of MCU tied to +3V3 (no coin cell)
NETS["VBAT_MCU"] = ["U1.6"]; NETS["+3V3"].append("U1.6")
del NETS["VBAT_MCU"]

#SWD
net("SWDIO","U1.PA13"); net("SWCLK","U1.PA14")

#motors + battery sense (ESC connector)
net("M1","J2.3","U1.PB0"); net("M2","J2.4","U1.PB1")
net("M3","J2.5","U1.PA0"); net("M4","J2.6","U1.PA1")
net("BATT_V_DIV","R18.2","R19.1","C43.1","U1.PC0")
net("ESC_CUR","J2.7","C44.1","U1.PC1")
#ESC telemetry travels ESC -> FC, so it has to land on a receive pin
net("ESC_TEL","J2.8","U1.PE0")                                  #UART8_RX <- BLHeli_32/AM32 rpm

#IMU1 (SPI1)
net("SPI1_SCK","U1.PA5","U2.13"); net("SPI1_MISO","U1.PA6","U2.1")
net("SPI1_MOSI","U1.PD7","U2.14"); net("IMU1_CS","U1.PC15","U2.12")
#IMU2 (SPI4)
net("SPI4_SCK","U1.PE12","U3.13"); net("SPI4_MISO","U1.PE13","U3.1")
net("SPI4_MOSI","U1.PE14","U3.14"); net("IMU2_CS","U1.PE11","U3.12")
#PC13 was MatekH743's third-IMU chip select
#SPI3: flow + flash
net("SPI3_SCK","U1.PB3","U5.6"); net("SPI3_MISO","U1.PB4","U5.2")
net("SPI3_MOSI","U1.PB5","U5.5")
net("EXT_CS2","U1.PE2","U5.1")
net("FLASH_WP","U5.7","+3V3_T2"); NETS["FLASH_WP"]=["U5.7"]; NETS["+3V3"].append("U5.7")
net("FLASH_HOLD","U5.3"); NETS["+3V3"].append("U5.3"); del NETS["FLASH_HOLD"]
del NETS["FLASH_WP"]
#I2C
net("I2C1_SCL","U1.PB6","R9.2","J3.4")
net("I2C1_SDA","U1.PB7","R10.2","J3.5")
net("I2C2_SCL","U1.PB10","R11.2","U4.8")
net("I2C2_SDA","U1.PB11","R12.2","U4.7")
#TOF_XSHUT (PD11) and TOF_INT (PD10) deleted with U7
net("USART2_TX","U1.PD5","J3.2"); net("USART2_RX","U1.PD6","J3.3")   #GPS1
net("UART7_TX","U1.PE8");  net("UART7_RX","U1.PE7")        #companion (J21)
net("UART7_CTS","U1.PE10"); net("UART7_RTS","U1.PE9")
net("USART6_TX","U1.PC6","J5.2"); net("RC_IN","U1.PC7","J5.3")
#PB8/PB9 were UART4, never brought out
net("CAN1_RX","U1.PD0","U11.4"); net("CAN1_TX","U1.PD1","U11.1")
net("CAN1_SILENT","U1.PD3","R14.1","U11.8")
net("CANH","U11.7","J6.2","R15.1"); net("CANL","U11.6","J6.3","R15.2")
#USB
net("VBUS","J1.A4B9","J1.B4A9","U12.5","C42.1")
net("USB_DP_CON","J1.A6","J1.B6","U12.1"); net("USB_DM_CON","J1.A7","J1.B7","U12.3")
net("USB_DP","U12.6","U1.PA12"); net("USB_DM","U12.4","U1.PA11")
net("CC1","J1.A5","R16.1"); net("CC2","J1.B5","R17.1")
NETS["GND"] += ["R16.2","R17.2"]
#microSD (SDMMC1)
net("SD_D0","U1.PC8","J8.7","R22.2");  net("SD_D1","U1.PC9","J8.8","R23.2")
net("SD_D2","U1.PC10","J8.1","R24.2"); net("SD_D3","U1.PC11","J8.2","R25.2")
net("SD_CK","U1.PC12","J8.5");         net("SD_CMD","U1.PD2","J8.3","R26.2")
net("SD_CD","J8.9","R27.2")
#LEDs / buzzer / WS2812
net("LED0","U1.PE3","R20.2"); net("LED0_K","R20.2","D2.1")
NETS["LED0"]=["U1.PE3","R20.2"]; NETS["LED0_K"]=["R20.2","D2.1"]
net("LED1","U1.PE4","R21.2"); NETS["LED1_K"]=["R21.2","D3.1"]
net("BUZZER","U1.PA15"); net("WS2812","U1.PA8")
#unpopulated MatekH743 features (kept defined so ERC is clean)
net("MAX7456_CS","U1.PB12")     #pull high, no OSD fitted
net("SPI2_SCK","U1.PB13"); net("SPI2_MISO","U1.PB14"); net("SPI2_MOSI","U1.PB15")
net("PWM5","U1.PB9"); net("PWM6","U1.PA3")   #PB9 faces TP3; PA2 faced the RF corner
net("PWM8","U1.PD13")   #PD14/PD15 (PWM9/10) gave TIM4_CH3/CH4 to PWM7 and PWM5
net("PWM11","U1.PE5"); net("PWM12","U1.PE6")
net("USART1_TX","U1.PA9"); net("USART1_RX","U1.PA10")
net("USART3_TX","U1.PD8"); net("USART3_RX","U1.PD9")
net("PE1_SPARE","U1.PE1")       #UART8_TX, unused: ESC telemetry is receive-only
net("PB2_SPARE","U1.PB2")
net("PC3_SPARE","U1.PC3_C")
#SoOP analogue front end (SoOP config, DNP)
net("SOOP_I_ADC","U1.PC4","U14.1")
net("SOOP_Q_ADC","U1.PA4","U14.7")
#PC5 is free
net("SPARE_ADC","U1.PA7")


#RF front end (SoOP config, all DNP)
net("ANT_IN",   "J12.1","C52.1"); NETS["GND"] += ["J12.2", "J12.3", "J12.4", "J12.5"]
net("RFIN",     "C52.2","U13.4")
NETS["GND"] += ["U13.3","U13.10","U13.11","U13.29"]
net("VCC_RF",   "U13.1","U13.2","U13.6","U13.7","U13.13","U13.16","U13.25",
                "C49.1","C50.1","C51.1","R28.2")
NETS["+3V3A"] += ["R28.1"]; NETS["GND"] += ["C49.2","C50.2","C51.2"]
net("TUNER_REF",  "Y2.3", "C58.1")            #TCXO clipped-sine output
net("TUNER_XTAL", "C58.2", "U13.14")          #AC-coupled into the XTAL pin
NETS["+3V3A"] += ["Y2.4", "C59.1"]            #VDD + decoupling, on the quiet rail
NETS["GND"]  += ["Y2.2", "Y2.1", "C59.2"]    #both ground pins to ground
net("TUNER_ADDR","U13.28","R29.2"); NETS["GND"] += ["R29.1"]
NETS["I2C2_SDA"] += ["U13.26"]; NETS["I2C2_SCL"] += ["U13.27"]
#PLL loop filter
CAP("C81", "1n", F_C0402); RES("R57", "470R", F_R0402)
net("VTUNE","U13.9","C56.1","R57.2"); NETS["GND"] += ["C56.2"]
net("CPOUT","U13.12","R34.1","C81.1","R57.1"); net("LOOP","R34.2","C57.1")
NETS["GND"] += ["C57.2", "C81.2"]
net("VCOBYP","U13.8"); net("REFOUT","U13.15")
#GC1 needs 0.5-2.7 V (0.5 V = maximum gain)
RES("R58", "4k7", F_R0402)
net("GC1","U13.5","R35.2","R58.2"); NETS["GND"] += ["R35.1"]; NETS["VCC_RF"] += ["R58.1"]
#1 nF beside the LO/VCO (pins 6-7) and synthesizer (pin 13) supplies
for _c, _pin in (("C84", 6), ("C86", 13)):
    CAP(_c, "1n", F_C0402)
    NETS["GND"] += [f"{_c}.2"]; NETS["VCC_RF"] += [f"{_c}.1"]
#MAX2112 baseband -> OPA2374 difference amplifiers -> ADC the comment here read "resistor
for r, v in [("R47","4k7"), ("R48","10k"), ("R49","10k"), ("R50","10k"),
             ("R51","10k"), ("R52","10k"), ("R53","10k")]:
    RES(r, v, F_R0402)
CAP("C75", "1u", F_C0402)
CAP("C76", "100p", F_C0402); CAP("C77", "100p", F_C0402)

#i channel: IOUT+ -> R36 -> +in A (R51 to VREF)
net("IOUT_P","U13.19","R36.1"); net("IOUT_N","U13.20","R37.1")
net("OPA_IN1P","R36.2","U14.3","R51.1"); net("OPA_IN1N","R37.2","U14.2","R50.1")
NETS["SOOP_I_ADC"] += ["R50.2", "C76.2"]             #feedback, out A -> -IN A
NETS["OPA_IN1N"] += ["C76.1"]                        #C76 across R50: anti-alias
#q channel: QOUT+ -> R47 -> +in B (R49 to VREF)
net("QOUT_P","U13.17","R47.1"); net("QOUT_N","U13.18","R31.1")
net("OPA_IN2P","R47.2","U14.5","R49.1"); net("OPA_IN2N","R31.2","U14.6","R48.1")
NETS["SOOP_Q_ADC"] += ["R48.2", "C77.2"]             #feedback, out B -> -IN B
NETS["OPA_IN2N"] += ["C77.1"]                        #C77 across R48: anti-alias
#the mid-rail reference both channels share
net("BB_VREF","R52.2","R53.1","C75.1","R51.2","R49.2")
NETS["+3V3A"] += ["R52.1", "U14.8"]; NETS["GND"] += ["R53.2", "C75.2", "U14.4"]
#DC-offset servo capacitors
net("IDC_P","U13.21","C61.1"); net("IDC_N","U13.22","C61.2")
net("QDC_P","U13.23","C63.1"); net("QDC_N","U13.24","C63.2")

#fixes
#LED chains: MCU -> resistor -> LED anode -> GND
for k in ("LED0","LED0_K","LED1","LED1_K"): NETS.pop(k, None)
net("LED0_A","+3V3_dummy"); NETS.pop("LED0_A")
NETS["+3V3"] += ["D2.2","D3.2"]
for r in ("R20.1","R21.1"):
    if r in NETS["+3V3"]: NETS["+3V3"].remove(r)
net("LED0_K","D2.1","R20.1"); net("LED0","R20.2","U1.PE3")
net("LED1_K","D3.1","R21.1"); net("LED1","R21.2","U1.PE4")
for g in ("D2.2","D3.2"):
    if g in NETS["GND"]: NETS["GND"].remove(g)

#LMR33630 RNX 5V buck - full wiring
net("BUCK_BOOT","U8.4","C21.1")                   #boot (TPS54202 pin 6)
net("BUCK_PH",  "U8.12","U8.3","C21.2","L2.1")    #SW 12 + NC 3, tied per SNVSAN3F 10.1
net("BUCK_VCC", "U8.5","C78.1")                   #VCC, new pin - the internal 5 V LDO
NETS["GND"] += ["C78.2"]
NETS["+5V"] += ["L2.2"]
net("BUCK_EN",  "U8.9","R4.2","R5.1")             #EN (TPS54202 pin 5)
net("BUCK_FB",  "U8.7","R6.2","R7.1")             #FB (TPS54202 pin 4)
NETS.pop("R3", None)

#LDO enables tied to their inputs (always-on)
NETS["+5V"]  += ["U9.3","U10.3"]

COMPONENTS.pop("R2", None)

for n in ("BOOT0","+3V3","GND"):
    NETS[n] = [x for x in NETS[n] if x not in ("SW1.1","SW1.2")]
NETS["BOOT0"] += ["SW1.2"]; NETS["+3V3"] += ["SW1.1"]
#no U8 pin sits on +5V: the switch node reaches it through L2 only
COMPONENTS.pop("R3", None)

#MAX2112 bypass / DC-offset caps
#C60 is a supply bypass
for r, v in [("C60","100n"),("C61","47n"),("C63","47n")]:
    CAP(r, v, F_C0402)
NETS["VCOBYP"] += ["C60.1"]; NETS["GND"] += ["C60.2"]
#C61 spans IDC_P/IDC_N and C63 spans QDC_P/QDC_N - wired

#power flags: tell ERC these rails are actually driven
PWR_FLAGS = {"VBAT":"PF1", "+5V":"PF2", "+3V3":"PF3", "+3V3A":"PF4",
             "GND":"PF5", "VDDA":"PF6", "VBUS":"PF7", "VCC_RF":"PF8",
             "VBAT_IN":"PF9"}
for netname, ref in PWR_FLAGS.items():
    add(ref, "power:PWR_FLAG", "", "PWR_FLAG", "", netname == "VCC_RF")
    NETS[netname].append(f"{ref}.1")
NOT_A_PART = set()

#test points
#only signals worth the copper get a pad
TESTPOINT_NETS = ["PWM5", "PWM6"]
TESTPOINT_REFS = ["TP3", "TP4"]
for ref, netname in zip(TESTPOINT_REFS, TESTPOINT_NETS):
    add(ref, "Connector:TestPoint", "TestPoint:TestPoint_Pad_1.5x1.5mm", netname, "", False)
    NETS[netname].append(f"{ref}.1")

#J21: Companion Computer Port (JST-GH 6P)
#Pixhawk DS-009 standard TELEM pinout
add("J21", "jlc_parts:XY-SM06B-GHS-TB", "jlc:CONN-SMD_XY-SM06B-GHS-TB",
    "COMPANION", "C51940119", False)
NETS["+5V"].append("J21.1")
NETS["UART7_TX"].append("J21.2")
NETS["UART7_RX"].append("J21.3")
NETS["UART7_CTS"].append("J21.4")
NETS["UART7_RTS"].append("J21.5")
NETS["GND"] += ["J21.6", "J21.7", "J21.8"]

#SoOP RF front end moved off this board
INCLUDE_ONBOARD_LNA = False       #U15/U16/FL1/L3/L4 - see the ANT_IN comment
assert not INCLUDE_ONBOARD_LNA, ("the on-board LNA/SAW chain was deleted, not disabled - "
                                 "re-adding it needs the 1620 MHz SAW sourced first")
for _r in ("U15", "U16", "FL1", "L3", "L4"):
    COMPONENTS.pop(_r, None)

#keep the SoOP receiver interface reachable from the board edge even though the RF front end
for _i, _n in enumerate(["SOOP_I_ADC", "SOOP_Q_ADC"], start=9):
    if _n in NETS:
        _r = f"TP{_i}"
        add(_r, "Connector:TestPoint", "TestPoint:TestPoint_Pad_1.5x1.5mm", _n, "", False)
        NETS[_n].append(f"{_r}.1")

#additional parts

F_SOT23   = "jlc:SOT-23-3_L2.9-W1.3-P1.90-LS2.4-BR"
F_SOD123  = "jlc:SOD-123F_L2.7-W1.6-LS3.8-RD"
F_SOT235  = "jlc:SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR"
PAD15     = "TestPoint:TestPoint_Pad_1.5x1.5mm"

add("Q1", "jlc_parts:AO3400A",        F_SOT23,  "AO3400A", "C20917", False)
add("D4", "jlc_parts:1N4148W_C81598", F_SOD123, "1N4148W", "C81598", False)
RES("R38", "100R")       #gate series
RES("R39", "10k")        #gate pulldown - keeps the buzzer quiet while the MCU boots
#J16 is no longer a JST-SH socket
add("P161", "Connector:TestPoint", PAD15, "BUZ_5V",  "", False)
add("P162", "Connector:TestPoint", PAD15, "BUZ_OUT", "", False)
add("P163", "Connector:TestPoint", PAD15, "BUZ_GND", "", False)

net("BUZZ_GATE", "R38.2", "Q1.1", "R39.1")
NETS["BUZZER"] += ["R38.1"]                       #from U1.PA15
NETS["GND"]    += ["Q1.2", "R39.2", "P163.1"]
net("BUZZ_DRAIN", "Q1.3", "D4.2", "P162.1")                #D4 pin2 = anode
NETS["+5V"]    += ["D4.1", "P161.1"]                       #D4 pin1 = cathode

#J19: Tag-Connect TC2030-NL 6-pad pogo connection for SWD + NRST recovery
add("J19", "Connector:TC2030",
    "Connector:Tag-Connect_TC2030-IDC-NL_2x03_P1.27mm_Vertical", "TC2030-NL", "", False)
NETS["+3V3"] += ["J19.1"]
NETS["SWDIO"] += ["J19.2"]
NETS["NRST"] += ["J19.3"]
NETS["SWCLK"] += ["J19.4"]
NETS["GND"] += ["J19.5", "J19.6"]

#second LMR33630A (TI VQFN-12 HotRod, 3A, 400 kHz), identical to U8
add("U20", "jlc_parts:LMR33630ARNXR", "jlc:VQFN-12_L3.0-W2.0-P0.65-BL_TI_RNX",
    "LMR33630A", "C2861505", False)
IND("L5", "10uH", F_ANR5040)
CAP("C66", "100n")                 #VIN hf (50V rated in PART_LCSC)
CAP("C68", "100n")                 #bootstrap
CAP("C79", "1u")                   #internal VCC bypass
CAP("C69", "22u", F_C1206)         #output bulk
CAP("C70", "22u", F_C1206)
RES("R40", "100k"); RES("R41", "22k")       #EN divider
RES("R42", "100k"); RES("R43", "24k9")      #1.000 V reference -> 5.016 V output
#J22: JST-GH 3P payload power port (+5V_PAYLOAD) for a VTX or camera
add("J22", "jlc_parts:SM03B-GHS-TB(LF)(SN)", "jlc:CONN-TH_SM03B-GHS-TB-LF-SN",
    "PAYLOAD 5V", "C514175", False)

NETS["VBAT"] += ["U20.2", "U20.10", "C66.1", "R40.1"]
net("BUCK_PAYLOAD_BOOT", "U20.4", "C68.1")
net("BUCK_PAYLOAD_PH",   "U20.12", "U20.3", "C68.2", "L5.1")
net("BUCK_PAYLOAD_VCC",  "U20.5", "C79.1")
net("BUCK_PAYLOAD_EN",   "U20.9", "R40.2", "R41.1")
net("BUCK_PAYLOAD_FB",   "U20.7", "R42.2", "R43.1")
net("+5V_PAYLOAD", "L5.2", "C69.1", "C70.1", "R42.1", "J22.1")
PWR_FLAGS["+5V_PAYLOAD"] = "PF10"
add("PF10", "power:PWR_FLAG", "", "PWR_FLAG", "", False)
NETS["+5V_PAYLOAD"].append("PF10.1")
NETS["GND"] += ["U20.1", "U20.6", "U20.11", "C66.2", "C79.2", "C69.2", "C70.2",
                "R41.2", "R43.2", "J22.2", "J22.3", "J22.4", "J22.5"]

#the MCU drives 3.3V; a 5V WS2812 strip wants >=0.7*VDD = 3.5V on DIN
add("U17", "jlc_parts:SN74LVC1G17DBVR", F_SOT235, "74LVC1G17", "C7836", False)
CAP("C65", "100n")
#J15 is no longer a JST-SH socket
add("P151", "Connector:TestPoint", PAD15, "LED_5V",  "", False)
add("P152", "Connector:TestPoint", PAD15, "LED_DIN", "", False)
add("P153", "Connector:TestPoint", PAD15, "LED_GND", "", False)
NETS["WS2812"] += ["U17.2"]                       #a input, from U1.PA8
net("WS2812_OUT", "U17.4", "P152.1")              #y output at 5V
NETS["+5V"] += ["U17.5", "C65.1"]
NETS["+5V_PAYLOAD"] += ["P151.1"]
NETS["GND"] += ["U17.3", "C65.2", "P153.1"]

add("Q3", "jlc_parts:AO3400A", F_SOT23, "AO3400A", "C20917", False)
RES("R45", "10k")                       #gate pulldown: payload on unless asserted
CAP("C73", "10n")                       #EN filter

net("PAYLOAD_EN", "U1.PA7", "Q3.1", "R45.1")
NETS["GND"] += ["Q3.2", "R45.2", "C73.2"]
NETS["BUCK_PAYLOAD_EN"] += ["Q3.3", "C73.1"]

#powers U11 (SN65HVD230) from +5V_PAYLOAD with rock-solid 3.3V
add("U21", "jlc_parts:XC6206P332MR", "jlc:SOT-23-3_L2.9-W1.6-P1.90-LS2.8-BR",
    "XC6206P332MR", "C5446", False)
CAP("C67", "1u")
CAP("C80", "1u")
NETS["+5V_PAYLOAD"] += ["U21.3", "C80.1"]
NETS["GND"] += ["U21.1", "C67.2", "C80.2"]
net("+3V3_CAN", "U21.2", "U11.3", "C67.1", "C41.1")
NETS["+5V_PAYLOAD"] += ["J6.1"]

#ESD on the ports whose cables leave the aircraft's core (Rev C review) CAN runs the length
add("D6", "jlc_parts:PESD2CANFD24LT-QR", "jlc:SOT-23-3_L2.9-W1.6-P1.90-LS2.8-BR",
    "PESD2CANFD24LT", "C6952426", False)
NETS["CANH"] += ["D6.1"]; NETS["CANL"] += ["D6.2"]; NETS["GND"] += ["D6.3"]
add("U22", "jlc_parts:SRV05-4-P-T7_C6454456", "jlc:SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BR",
    "SRV05-4", "C6454456", False)
NETS["USART2_TX"] += ["U22.1"]; NETS["USART2_RX"] += ["U22.3"]
NETS["I2C1_SCL"] += ["U22.4"];  NETS["I2C1_SDA"] += ["U22.6"]
NETS["+5V"] += ["U22.5"];       NETS["GND"] += ["U22.2"]
add("U23", "jlc_parts:SRV05-4-P-T7_C6454456", "jlc:SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BR",
    "SRV05-4", "C6454456", False)
NETS["USART6_TX"] += ["U23.1"]; NETS["RC_IN"] += ["U23.3"]      #IO3/IO4 unused
NETS["+5V"] += ["U23.5"];       NETS["GND"] += ["U23.2"]
#the arrays' Vcc pins clamp to the rail
CAP("C88", "100n"); CAP("C89", "100n")
NETS["+5V"] += ["C88.1", "C89.1"]; NETS["GND"] += ["C88.2", "C89.2"]

#fiducials: the assembler's camera needs them for the 0.5 mm LQFP and the LGAs
for _f in ("FID1", "FID2", "FID3"):
    add(_f, "Mechanical:Fiducial", "Fiducial:Fiducial_1mm_Mask2mm", "Fiducial", "", False)

#breaks out SPI3 + PC13 (EXT_CS1) onto a 6-pin JST-GH connector
add("J14", "jlc_parts:XY-SM06B-GHS-TB",
    "jlc:CONN-SMD_XY-SM06B-GHS-TB", "FLOW 6P", "C51940119", False)
NETS["+3V3"] += ["J14.1"]
NETS["SPI3_SCK"] += ["J14.2"]
NETS["SPI3_MISO"] += ["J14.3"]
NETS["SPI3_MOSI"] += ["J14.4"]
net("EXT_CS1", "U1.PC13", "J14.5")   #PC13 faces J14; PD4 was across the board
NETS["GND"] += ["J14.6", "J14.7", "J14.8"]
net("FLOW_MOTION", "U1.PD11")

#two 1x3 2.54 mm right-angle male headers, side by side on the fore edge
SERVO_HDR = ("jlc_parts:KH-2_54PH-1X3P-L13_5-WT", "jlc:HDR-SMD_3P-P2.54-H-M_KH-2.54PH-1X3P-L13.5-WT")
add("J17", *SERVO_HDR, "SERVO1", "C20610212", False)
add("J23", *SERVO_HDR, "SERVO2", "C20610212", False)
net("PWM7",  "U1.PB8", "J17.1")   #PB8 on U1's south edge, nearer J17 than PD12
net("PWM8",  "U1.PD13", "J23.1")
NETS["GND"] += ["J17.3", "J23.3"]

#both servos share +5V_PAYLOAD
NETS["+5V_PAYLOAD"] += ["J17.2", "J23.2", "D8.1", "C92.1"]
add("D8", "jlc_parts:PTVS5V0S1UR", "jlc:SOD-123FL_L2.7-W1.8-LS3.8-RD", "PTVS5V0S1UR", "C5380694", False)
NETS["GND"].append("D8.2")
CAP("C92", "22u", F_C1206)
NETS["GND"].append("C92.2")

#+5V -> load switch U24 -> 2.2 ohm sense -> 10u/100n/10p -> 27 nH choke L6 -> ANT_IN
add("U24", "jlc_parts:AP22653W6-7", "jlc:SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BR",
    "AP22653", "C2158037", False)
NETS["+5V"].append("U24.1")
NETS["GND"].append("U24.2")
net("BIAS_EN", "U24.3", "U1.PC5", "R59.2")      #EN, active high: MCU PC5, pulled up
net("BIAS_FAULT", "U24.4", "U1.PD10", "R60.2")  #FAULT#, open drain: MCU PD10, pulled up to +3V3
net("BIAS_ILIM", "U24.5", "R61.1")
net("+5V_BIAS_SW", "U24.6", "R62.1", "U25.3")
#the switch's own bypass at IN and at OUT (DS41186, Power Supply Considerations)
CAP("C95", "100n"); NETS["+5V"].append("C95.1"); NETS["GND"].append("C95.2")
CAP("C96", "100n"); NETS["+5V_BIAS_SW"].append("C96.1"); NETS["GND"].append("C96.2")
RES("R59", "10k"); NETS["+5V"].append("R59.1")
RES("R60", "10k"); NETS["+3V3"].append("R60.1")
RES("R61", "210k"); NETS["GND"].append("R61.2")

#feed current: INA180A2 (gain 50) across R62, into ADC3 on PC2_C
RES("R62", "2R2")
add("U25", "jlc_parts:INA180A2IDBVR", "jlc:SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BL",
    "INA180A2", "C192764", False)
NETS["+5V_BIAS"] = ["R62.2", "U25.4", "C93.1", "C90.1", "C91.1", "L6.1"]
net("ANT_CURRENT", "U25.1", "U1.PC2_C")
NETS["GND"].append("U25.2")
NETS["+3V3"] += ["U25.5", "C94.1"]
CAP("C93", "10u", F_C0805); NETS["GND"].append("C93.2")
CAP("C94", "100n");         NETS["GND"].append("C94.2")
CAP("C90", "100n");         NETS["GND"].append("C90.2")
CAP("C91", "10p");          NETS["GND"].append("C91.2")
add("L6", L, "jlc:L0402", "27nH", "C113111", False)
NETS["ANT_IN"] += ["L6.2"]

#ESD protection on ANT_IN, 0.2 pF:
add("D7", "Device:D_TVS", "jlc:DSN0603-2_L0.6-W0.3-P0.40-BI", "PESD5V0C1BSF", "C477955", False)
NETS["ANT_IN"].append("D7.1")
NETS["GND"].append("D7.2")

add("D_USB", "jlc_parts:B5819W_C8598",
    "jlc:SOD-123_L2.7-W1.6-LS3.7-RD-1", "B5819W", "C8598", False)
NETS["VBUS"] += ["D_USB.2"]
NETS["+5V"] += ["D_USB.1"]
#PA7, not PE15
del NETS["SPARE_ADC"]                   #PA7 now has a job

#reverse-polarity protection and the edge connectors

#Q4 is a P-FET that blocks a reversed pack
add("J12", "jlc_parts:DL-MMCX-KWE-90", "jlc:MMCX-TH_DL-MMCX-KWE-90", "MMCX-KWE-90", "C2894793", False)

#U19: the board measures its own temperature
#U9's junction is the one number on this board that nothing at a desk can compute
add("U19", "jlc_parts:TMP119AIYBGR", "jlc:DSBGA-6_L1.5-W1.0-R2-C3-P0.40-BL",
    "TMP119", "C22428347", False)
CAP("C74", "100n")                       #U19 supply decoupling
NETS["I2C1_SDA"] += ["U19.A1"]
NETS["I2C1_SCL"] += ["U19.A2"]
NETS["+3V3"] += ["U19.B1", "C74.1"]
NETS["GND"] += ["U19.B2", "C74.2", "U19.C1"]   #C1 = ADD0 low -> address 0x48

add("Q4", "jlc_parts:WST4041", F_SOT23, "WST4041", "C148357", False)
add("DZ1", "jlc_parts:BZT52C15", "jlc:SOD-123_L2.7-W1.6-LS3.7-RD",
    "BZT52C15", "C173427", False)
RES("R46", "100k")
net("VBAT_GATE", "Q4.1", "DZ1.2", "R46.1")   #Q4 pin 1 = gate; DZ1 pin 2 = anode
NETS["VBAT"] += ["DZ1.1"]                        #DZ1 pin 1 = cathode, on the source
NETS["GND"] += ["R46.2"]                         #gate pull-down to ground

add("J9", "jlc_parts:BX-GH1_25-4PWT",
    "jlc:CONN-SMD_4P-P1.25_BX-GH1.25-4PWT", "I2C 4P", "C18077720", False)
NETS["+5V"] += ["J9.1"]
NETS["I2C1_SCL"] += ["J9.2"]
NETS["I2C1_SDA"] += ["J9.3"]
NETS["GND"] += ["J9.4", "J9.5", "J9.6"]       #pin 4 = signal, 5/6 = anchor tabs

#J11 is SERIAL2 (USART1) with its own power and ground
add("J11", "jlc_parts:BX-GH1_25-4PWT",
    "jlc:CONN-SMD_4P-P1.25_BX-GH1.25-4PWT", "SERIAL2 4P", "C18077720", False)
NETS["+5V_PAYLOAD"] += ["J11.1"]
NETS["USART1_TX"] += ["J11.2"]
NETS["USART1_RX"] += ["J11.3"]
NETS["GND"] += ["J11.4", "J11.5", "J11.6"]

#placement intent
#connector -> TVS -> series R -> MCU
F_TVS4, S_TVS4 = "Package_SON:USON-10_2.5x1.0mm_P0.5mm", "Power_Protection:TPD4E05U06DQA"
F_RN4, S_RN4 = "Resistor_SMD:R_Array_Convex_4x0402", "Device:R_Pack04"
TVS4_IO = ("1", "2", "4", "5")          #[D] TPD4E05U06 DQA: four independent clamps
SERIES = {}                             #MCU-side net -> (series part, connector-side net)


#move jpin off net_name onto net_name_J, the series element between
def _protect(net_name, jpin, part, j_pin, mcu_pin, clamp):
    NETS[net_name].remove(jpin)
    jn = net_name + "_J"
    NETS.setdefault(jn, []).extend([jpin, f"{part}.{j_pin}", clamp])
    NETS[net_name].append(f"{part}.{mcu_pin}")
    SERIES[net_name] = (part, jn)


#A clamp on the net itself, with no series element
def _clamp(net_name, clamp):
    NETS[net_name].append(clamp)


#A connector-side net's function: M1_J is M1 through its series resistor
def port_net(n):
    return n[:-2] if n.endswith("_J") and n[:-2] in SERIES else n


for ref in ("U26", "U27", "U28", "U29", "U30"):
    add(ref, S_TVS4, F_TVS4, "TPD4E05U06", "C138714", False)
    NETS["GND"] += [f"{ref}.3", f"{ref}.8"]
for ref in ("RN1",):
    add(ref, S_RN4, F_RN4, "33R x4", "C25501", False)
#J2, the ESC: four DShot lines through RN1
for k, (m, jp) in enumerate((("M1", "J2.3"), ("M2", "J2.4"), ("M3", "J2.5"), ("M4", "J2.6"))):
    #j-side pads 5-8 face U26 pins 1-5 in the same order
    _protect(m, jp, "RN1", str(5 + k), str(4 - k), f"U26.{TVS4_IO[k]}")
RES("R70", "100R"); RES("R71", "2k2")
#current on U27's outer channel
_protect("ESC_TEL", "J2.8", "R70", "1", "2", "U27.2")
_protect("ESC_CUR", "J2.7", "R71", "1", "2", "U27.1")      #with C44, a 2.2k corner well above 100 Hz
#J21, the companion's UART7, and J14, the flow port's SPI3
for k, n in enumerate(("UART7_TX", "UART7_RX", "UART7_CTS", "UART7_RTS")):
    _clamp(n, f"U28.{TVS4_IO[k]}")
for k, n in enumerate(("SPI3_SCK", "SPI3_MISO", "SPI3_MOSI", "EXT_CS1")):
    _clamp(n, f"U29.{TVS4_IO[k]}")
#J11 (lidar) and J23 (servo 2), side by side on the south edge, share U30
RES("R72", "100R"); RES("R73", "100R"); RES("R74", "100R")
_protect("USART1_TX", "J11.2", "R72", "1", "2", "U30.1")
_protect("USART1_RX", "J11.3", "R73", "1", "2", "U30.2")
_protect("PWM8", "J23.1", "R74", "1", "2", "U30.4")
#J17 (servo 1), on its own
add("D9", "Device:D_TVS", "jlc:DSN0603-2_L0.6-W0.3-P0.40-BI", "PESD5V0C1BSF", "C477955", False)
NETS["GND"].append("D9.2")
RES("R75", "100R")
_protect("PWM7", "J17.1", "R75", "1", "2", "D9.1")

#[D] TPD4E05U06 Table 4-2: pins 6, 7, 9 and 10 are not connected
TVS4_FLOW = {"1": "10", "2": "9", "4": "7", "5": "6"}
for ref in ("U26", "U27", "U28", "U29", "U30"):
    for io, nc in TVS4_FLOW.items():
        on = next((n for n, v in NETS.items() if f"{ref}.{io}" in v), None)
        if on:
            NETS[on].append(f"{ref}.{nc}")

#every off-board connector's signals
ESD = dict(
    clamps=("U12", "U22", "U23", "D6", "D7", "U26", "U27", "U28", "U29", "U30", "D9"),
    max_mm=10.0,      #[A] a clamp this near its pin, behind the series R
    #where the board leaves no nearer place, the limit for that port and why
    port_max_mm={"J21": (13.0, "J21 (top) and J14 (bottom) share the east edge; the RF corner "
                               "fills both sides inboard of them, so U28/U29 sit 11-12.5 mm off"),
                 "J14": (13.0, "as J21"),
                 "J3": (11.0, "U22 clamps J3 and J9 together, between the two (Rev C)")},
    exempt={"J8": "the microSD socket takes a card, not a cable",
            "J19": "Tag-Connect SWD pads, bench only, a cable held by hand",
            "J22": "power and ground only"},
    exempt_nets={"CC1": "USB-C role detection, 5.1k to ground; USB is a bench port, unplugged "
                        "in flight", "CC2": "as CC1"},
    src="[A] connector-level ESD: the clamp at the connector, as close as the board allows",
)

#the respin carried one (3-4 x 150R switched from a spare pin)

ADJACENCY = {
    #MCU VDD decoupling - one per supply pin, as close as the package allows
    "C1": ("U1", "11", 2.0), "C2": ("U1", "27", 2.0), "C3": ("U1", "50", 2.0),
    "C4": ("U1", "75", 2.0), "C5": ("U1", "100", 2.0),
    "C6": ("U1", "11", 4.0), "C7": ("U1", "75", 4.0),          #bulk, looser
    #the H743's internal LDO
    "C8": ("U1", "48", 1.5), "C9": ("U1", "73", 1.5),
    #analogue supply and reference
    "C10": ("U1", "21", 2.0), "C11": ("U1", "21", 3.0),
    "C12": ("U1", "20", 2.0), "C13": ("U1", "20", 3.0),
    "L1":  ("U1", "21", 4.0),
    "C14": ("U1", "14", 3.0),                                   #NRST
    #crystal load caps
    "C15": ("Y1", "1", 2.5), "C16": ("Y1", "3", 2.5),
    "Y1": ("U1", "12", 5.0),
    #sensors
    "C31": ("U2", "5", 1.5), "C32": ("U2", "8", 1.5),
    "C33": ("U3", "5", 1.5), "C34": ("U3", "8", 1.5),
    "C35": ("U4", "1", 1.5),
    "C36": ("U5", "8", 1.5),
    #ESD clamps: at the connector, before the trace runs into the board
    "D6": ("J6", "2", 4.0), "U22": ("J3", "2", 6.0), "U23": ("J5", "2", 5.0),
    "C88": ("U22", "5", 1.5), "C89": ("U23", "5", 1.5),
    #Rev D: servo rail clamp and bulk cap between the two servo headers
    "D8": ("J17", "2", 6.0), "C92": ("J23", "2", 6.0),
    "U25": ("U24", "6", 5.0), "R62": ("U24", "6", 3.0), "C93": ("R62", "2", 2.5),
    "C95": ("U24", "1", 1.5), "C96": ("U24", "6", 1.5),
    "C94": ("U25", "5", 1.5),
    #Rev D: Active bias-tee and RF protection at J12
    "D7": ("J12", "1", 2.5), "L6": ("J12", "1", 3.5), "C52": ("J12", "1", 5.0),
    "C90": ("L6", "1", 2.0), "C91": ("L6", "1", 2.0), "U24": ("L6", "1", 5.0),
    #U19 is a temperature sensor and its whole value is where it sits
    "U19": ("U9", "1", 5.0),
    "C74": ("U19", "B1", 3.5),
    #the OPA2374 difference-amplifier network
    "R36": ("R37", "1", 8.0),  "R47": ("R31", "1", 6.0),
    "R48": ("U14", "6", 8.0),
    "R49": ("U14", "5", 8.0),  "R50": ("U14", "2", 8.0),
    "R51": ("U14", "3", 8.0),
    "C76": ("R50", "1", 12.0), "C77": ("R48", "1", 8.0),   #in parallel with them
    "R52": ("U14", "8", 12.0),                #VREF divider: a DC reference, 1 uF at
    "R53": ("R52", "2", 3.0),                 #the far end makes distance irrelevant
    "C75": ("R53", "1", 3.0),
    "C61": ("U13", "21", 3.5), "C63": ("U13", "23", 3.5),
    "C60": ("U13", "8", 2.0),
    "C41": ("U11", "3", 1.5),
    #J1's two VBUS pads are A4B9 and B4A9; C42 sits by B4A9
    "C42": ("J1", "B4A9", 4.0),
    "C45": ("J8", "4", 3.0), "C46": ("J8", "4", 2.0),
    #regulators
    "C26": ("U9", "1", 2.0), "C27": ("U9", "5", 2.0),
    "C28": ("U10", "1", 2.0), "C29": ("U10", "5", 2.0), "C30": ("U10", "5", 3.0),
    "C65": ("U17", "5", 1.5),
    "C17": ("U8", "2", 3.0), "C18": ("U8", "2", 3.0), "C19": ("U8", "2", 1.5),
    "C78": ("U8", "5", 2.0),
    "C21": ("U8", "4", 1.5),
    "R6": ("U8", "7", 2.5), "R7": ("U8", "7", 2.5),
    "R4": ("U8", "9", 3.0), "R5": ("U8", "9", 3.0),
    "L2": ("U8", "12", 3.0), "C22": ("U8", "12", 5.0), "C23": ("U8", "12", 5.0),
    #payload 5V buck (U20 TI LMR33630A VQFN-12)
    "C66": ("U20", "2", 1.5), "C68": ("U20", "4", 3.0),
    "C79": ("U20", "5", 2.5),
    "R42": ("U20", "7", 2.5), "R43": ("U20", "7", 2.5),
    "R40": ("U20", "9", 3.0), "R41": ("U20", "9", 3.0),
    "L5": ("U20", "12", 5.5), "C69": ("U20", "12", 5.0), "C70": ("U20", "12", 5.0),
    "C73": ("U20", "9", 3.0),      #EN filter
    "C67": ("U21", "2", 2.0),      #CAN 3.3V LDO output cap
    "C80": ("U21", "3", 3.0),      #CAN 3.3V LDO input cap
    "D_USB": ("J1", "A4B9", 6.0),  #USB desk power diode near USB-C
    #I2C pull-ups belong near the master, not scattered
    "R9": ("U1", "92", 4.0), "R10": ("U1", "93", 4.0),
    "R11": ("U1", "46", 4.0), "R12": ("U1", "47", 4.0),
    #buzzer / level shifter local parts
    "R38": ("Q1", "1", 2.0), "R39": ("Q1", "1", 2.0), "D4": ("Q1", "3", 3.0),
    #battery sense divider next to the MCU ADC pins
    "R18": ("U1", "15", 5.0), "R19": ("U1", "15", 4.0),
    "C43": ("U1", "15", 2.0), "C44": ("U1", "16", 2.0),
}
#port protection: each clamp at its connector
ADJACENCY.update({
    "U26": ("J2", "3", 6.0), "U27": ("J2", "7", 6.0), "RN1": ("U26", "1", 3.0),
    "R70": ("U27", "1", 3.0), "R71": ("U27", "2", 3.0),
    "U28": ("J21", "2", 6.0), "U29": ("J14", "2", 6.0),
    "U30": ("J11", "2", 6.0), "R72": ("U30", "1", 3.0), "R73": ("U30", "2", 3.0),
    "R74": ("U30", "4", 4.0), "D9": ("J17", "1", 4.0), "R75": ("D9", "1", 3.0),
})

ADJACENCY["D1"]  = ("J2",  "2", 5.0)     #TVS at the power entry, not the buck
ADJACENCY["SW2"] = ("U1", "14", 6.0)     #reset button near NRST
ADJACENCY["SW1"] = ("U1", "94", 6.0)     #boot button near BOOT0

ADJACENCY["U12"] = ("J1", "A6", 5.0)     #USB ESD belongs at the connector, not adrift

#limits refined after the first placement pass
for _r in ("C31","C32","C33","C34","C35","C36","C65","C41"):
    if _r in ADJACENCY:
        t, pd, _m = ADJACENCY[_r]; ADJACENCY[_r] = (t, pd, 3.5)
for _r, _lim in (("C22", 3.0), ("C23", 3.0), ("C69", 3.0), ("C70", 3.0),
                 ("L2", 2.5)):
    if _r in ADJACENCY:
        t, pd, _m = ADJACENCY[_r]; ADJACENCY[_r] = (t, pd, _lim)

#geometry
#one definition
BOARD = dict(X0=99.25, Y0=99.4, W=46.5, H=47.2, R=0.5, MOUNT=30.5, HOLE_D=4.0)

#the perimeter, connectors first
#every perimeter port's mouth points along its footprint's local +y
CONN_BODY = {
    "CONN-SMD_XY-SM06B-GHS-TB":         (5.53, 3.22, "[M] STEP bbox in the Rev C GLB"),
    "CONN-SMD_4P-P1.25_BX-GH1.25-4PWT": (4.13, 2.83, "[M] STEP bbox in the Rev C GLB"),
    "CONN-SMD_SM08B-GHS-TB-LF-SN":      (6.63, 2.70, "[M] STEP bbox (C265111)"),
    "CONN-TH_SM03B-GHS-TB-LF-SN":       (3.50, 2.37, "[M] STEP bbox (C514175)"),
    "USB-C-SMD_TYPE-C-16PIN-2MD-073":   (4.47, 4.86, "[M] STEP bbox in the Rev C GLB"),
    "TF-SMD_TF-01A":                    (8.05, 9.63, "[M] STEP bbox in the Rev C GLB"),
    "MMCX-TH_DL-MMCX-KWE-90":           (1.80, 4.80, "[M] STEP bbox (C2894793)"),
    "HDR-SMD_3P-P2.54-H-M_KH-2.54PH-1X3P-L13.5-WT":
                                        (3.81, 6.10, "[D] C20610212 land drawing: 2.5 mm "
                                                     "insulator at y 3.6-6.1, pins to 12.15"),
}

#where each port goes
FLOORPLAN_REV_D = {
    #aft (N): GPS toward the tower, the antenna in the RF corner
    "J3":  dict(edge="N", side="F", at=122.50, front=-0.05, desc="GPS+I2C GH-6P"),
    "J12": dict(edge="N", side="F", at=143.00, front=+2.30, desc="MMCX antenna"),
    "J9":  dict(edge="N", side="B", at=116.90, front=-0.45, desc="I2C GH-4P"),
    "J6":  dict(edge="N", side="B", at=128.10, front=-0.45, desc="DroneCAN GH-4P"),
    #fore (S): the two servos side by side, RC and lidar underneath
    "J17": dict(edge="S", side="F", at=117.75, front=0.00,  desc="servo 1"),
    "J23": dict(edge="S", side="F", at=127.25, front=0.00,  desc="servo 2"),
    "J5":  dict(edge="S", side="B", at=116.90, front=-0.45, desc="RC GH-4P"),
    "J11": dict(edge="S", side="B", at=128.10, front=-0.45, desc="lidar GH-4P"),
    #starboard (E): companion and USB on top, flow underneath
    "J21": dict(edge="E", side="F", at=116.30, front=-0.05, desc="companion GH-6P"),
    "J1":  dict(edge="E", side="F", at=129.00, front=+0.50, desc="USB-C"),
    "J14": dict(edge="E", side="B", at=116.30, front=-0.05, desc="flow GH-6P"),
    #port (W): ESC and payload power on top, the microSD underneath
    "J2":  dict(edge="W", side="F", at=117.60, front=-0.55, desc="ESC GH-8P"),
    "J22": dict(edge="W", side="F", at=130.30, front=-0.90, desc="payload GH-3P"),
    "J8":  dict(edge="W", side="B", at=123.50, front=+1.00, desc="microSD"),
}

_VALUE_FIX = {"R6": "100k", "R7": "24k9", "R42": "100k", "R43": "24k9",
              "R4": "100k", "R5": "22k", "R40": "100k", "R41": "22k"}
for _r, _v in _VALUE_FIX.items():
    if _r in COMPONENTS:
        _s, _f, _, _l, _d = COMPONENTS[_r]
        COMPONENTS[_r] = (_s, _f, _v, _l, _d)

PASSIVE_LCSC = {
    ("100n", F_C0402): "C1525",   ("1u",   F_C0402): "C52923",
    ("47n",  F_C0402): "C82219",  #MAX2112 IDC/QDC offset caps, datasheet < 47 nF
    ("2u2",  F_C0402): "C12530",  ("4u7",  F_C0805): "C354262",
    ("10n",  F_C0402): "C15195",  ("30p",  F_C0402): "C107004",
    ("47p",  F_C0402): "C60137",  ("3n3",  F_C0402): "C26404",
    #C17/C18, the VBAT bulk caps
    ("10u",  F_C0805): "C1713",   ("10u",  F_C1206): "C13585",
    ("1u",   F_C0805): "C91185",  ("22u",  F_C1206): "C5177178",
    ("0R",   F_R0402): "C17168",  ("100p", F_C0402): "C1546",
    ("1n",   F_C0402): "C1523",
    ("100R", F_R0402): "C25076",  ("120R", F_R0402): "C25862",
    ("2k2",  F_R0402): "C25879",
    ("1k",   F_R0402): "C11702",  ("4k7",  F_R0402): "C25900",
    ("330R", F_R0402): "C25104",  ("470R", F_R0402): "C25117",
    ("5k1",  F_R0402): "C25905",  ("6k8",  F_R0402): "C25917",
    ("10k",  F_R0402): "C25744",  ("22k",  F_R0402): "C25767",
    ("10k",  F_R0603): "C25804",
    ("27k",  F_R0402): "C25771",  ("47k",  F_R0402): "C25792",
    ("100k", F_R0402): "C25741",
    ("210k", F_R0402): "C58827",   #U24 RLIM; UNI-ROYAL 0402WGF2103TCE, 1%
    ("2R2",  F_R0402): "C25101",   #R62 bias-feed sense; UNI-ROYAL 0402WGF220KTCE, 1%
    ("10p",  F_C0402): "C32949",   #C91; Samsung CL05C100JB5NNNC 10pF 50V C0G
    ("37k4", F_R0402): "C25888",
    ("24k9", F_R0402): "C25874",
    ("10uH", F_L1210): "C167879",     #FNR4030 on a 1210 land - does not fit
    ("10uH", F_ANR4030): "C167879",   #FNR4030S100MT, Isat 2.4 A, Irms 1.6 A
    ("10uH", F_ANR5040): "C354610",   #CKCS5040-10uH/M, Isat 2.5 A, Irms 2.1 A
    ("600R@100MHz", F_L0805): "C18305",
    ("BLUE", F_LED):   "C965807", ("GREEN", F_LED): "C965804",
    ("BOOT", F_SW):    "C231329", ("RESET", F_SW): "C231329",
}

PART_LCSC = {
    #VBAT high-frequency bypass
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

#part ratings
#what each LCSC part actually is, read off its own product page
RATINGS = {
 #LCSC value V dielectric tol package Tmin Tmax source
 "C1525":    ("100n",  16,  "X7R",     "10%",  "0402",  -55, 125, "[D] LCSC product page, 2026-08-29"),
 "C32949":   ("10p",   50,  "C0G",     "5%",   "0402",  -55, 125, "[L] jlcpcb.com/partdetail/C32949: CL05C100JB5NNNC 10pF 50V C0G, 2026-10-01"),
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
#parts whose ratings have not been read off a datasheet yet
RATINGS_UNVERIFIED = set()

#inductors: current ratings and real body size
INDUCTORS = {
 "C167879":  ("10uH", 2.4, 1.6, 0.130, (4.0, 4.0, 3.0), "[D] LCSC page 2026-08-29, FNR4030S100MT"),
 "C354610":  ("10uH", 2.5, 2.1, 0.064, (5.0, 5.0, 4.0), "[D] LCSC page 2026-08-29, CKCS5040-10uH/M"),
 "C18305":   ("600R@100MHz", None, None, None, (2.0, 1.25, 0.85), "[A] 0805 ferrite bead, package typical"),
}
#continuous current each inductor actually carries what the +5 V buck (U8) actually carries
#one list, two derived numbers
LOADS_5V = [
    ("U9 (+3V3) input, = LOADS_3V3",   sum(r[1] for r in LOADS_3V3),  sum(r[2] for r in LOADS_3V3),
     "[M] derived: LDO input current equals its output; MCU, flash, microSD, LEDs, TMP119"),
    ("U10 (+3V3A) input, = LOADS_3V3A", sum(r[1] for r in LOADS_3V3A), sum(r[2] for r in LOADS_3V3A),
     "[M] derived: both IMUs, the baro, the MAX2112 tuner (100 mA), OPA2374, TCXO"),
    ("M10 GPS + QMC5883L on J3",        0.050, 0.050, "[A] docs/HARDWARE.md budget row; typical M10 module ~40-50 mA"),
    ("ELRS receiver on J5",             0.100, 0.100, "[A] docs/HARDWARE.md budget row; ESP-based RX with telemetry"),
    ("TFS20-L rangefinder on J9",       0.106, 0.106, "[D] 0.35 W at 3.3 V via its inline LDO - optional (stage B2), budgeted as fitted"),
    ("GY-53-L1X upward ToF on J9",      0.020, 0.020, "[D] VL53L1X module ~20 mA - optional (stage B2), budgeted as fitted"),
    ("HC610 LNA through U24 on J12",    0.015, 0.015, "[D] Tallysman HC610: 15 mA at 2.2-12 V, fed down the coax"),
]
LOADS_5V_CONT_A = round(sum(r[1] for r in LOADS_5V), 3)
LOADS_5V_PEAK_A = round(sum(r[2] for r in LOADS_5V), 3)

INDUCTOR_LOAD_A = {"L2": LOADS_5V_CONT_A}

#package heights, the single source of truth
#height of each package above the board surface it sits on, mm
PART_HEIGHT = {
    "CONN-SMD_XY-SM06B": 4.4,   #JST GH 6P
    "CONN-SMD_SM08B-GHS": 4.35, #J2 JST GH 8P side entry; [D] JST GH: 4.25 mm
    "CONN-TH_SM03B-GHS": 4.35,  #J22 JST GH 3P side entry (SMD despite the name)
    "HDR-SMD_3P-P2.54-H-M_KH": 2.5,  #J17/J23; [D] C20610212 insulator height 2.5 mm
    "MMCX-TH_DL-MMCX-KWE-90": 4.0,   #J12; [D] DreamLNK drawing: 6.80 overall less 2.80 of pins
    "L_APV_ANR5040": 4.0,            #L5; [D] 5.0 x 5.0 x 4.0 mm
    "L0402": 0.5,                    #L6 LQW15AN; [D] Murata 0.5 mm max
    "DSN0603-2": 0.3,                #D7 PESD5V0C1BSF; [D] Nexperia DSN0603-2, 0.3 mm
    "USON-10_2.5x1.0mm": 0.55,       #TPD4E05U06 DQA; [D] TI: 0.55 mm max
    "R_Array_Convex_4x0402": 0.35,   #4D02 33R x4; [D] UniOhm 0402x4 array 0.35 mm
    "Tag-Connect_TC2030-IDC-NL": 0.0,  #J19: bare pads, the cable clips on from above
    "USB-C": 3.2, "TF-SMD": 1.9, "COB": 2.3, "DO-214": 2.3,
    "OPTO": 1.6, "SOIC": 1.8, "SOP": 1.8,
    "LQFP": 1.6, "LGA-14": 0.95, "SENSORS-SMD_MS5611": 1.1,
    "CRYSTAL-SMD_4P": 0.9, "SOD-123F": 1.1,
    "SOT-23-3": 1.45, "SOT-23-5": 1.45, "SOT-23-6": 1.45, "SOT-25": 1.45,
    "SW_SPST_B3U": 0.8, "TestPoint_Pad": 0.0,
    "L_APV_ANR4030": 3.0, "L_1210": 3.0,
    "L_0805": 1.2,        #ferrite bead
    "C_1206": 1.6, "C_0805": 1.45, "C_0402": 0.55,
    "R_0603_1608Metric": 0.55,  #standard 0603 resistor; [D] package max typical
    "R_0402": 0.45, "LED_0603": 0.55,
    #Rev B parts
    "CONN-SMD_4P-P1.00_SM04B": 2.9,   #JST SH 4P vertical (J5/J9/J11), same 2.9 as the SH 8P
    "OSC-SMD_4P": 0.9,                 #3.2 x 2.5 clipped-sine TCXO (Y2) [D] Ostar
    "SOD-123": 1.1,                    #DZ1 zener, same body as the SOD-123F already here
    "TQFN-28_L5.0": 0.8,               #U13 MAX2112, 5 x 5 QFN [D] Maxim
    "VQFN-12_L3.0": 0.9,              #U8 LMR33630ARNXR; [D] SNVSAN3F RNX0012B "0.9 mm max height"
    "U.FL_Hirose": 1.2,                #J12 vertical U.FL [D] Hirose U.FL-R-SMT-1
    #Rev C additions:
    "CONN-SMD_2P-P1.00": 2.9,          #J13/J16/J18/J20 JST-SH 2P
    "CONN-SMD_3P-P1.00": 2.9,          #J15 JST-SH 3P
    "CONN-SMD_SH1.0MM": 2.9,           #J14/J17 JST-SH 6P
    "SMB_L4.6": 2.4,                   #D1 SMBJ22A DO-214AA / SMB
    "Fuse_1206": 1.0,                  #F1 1206 PPTC fuse
    "DSBGA-6": 0.525,
    #since the Rev C review:
    "CONN-SMD_4P-P1.25_BX-GH1.25": 4.35,  #J5/J6/J9/J11 JST-GH 4P; [M] its 3D model (JST: 4.25)
    "WSON-8-1EP_6x5mm": 0.8,           #U5 W25Q128JVPIQ [D] Winbond WSON 6x5 A max 0.80 mm
    "Fiducial": 0.0,                   #a bare copper dot
}


#height in mm for a footprint name
def part_height(fp_name):
    keys = [k for k in PART_HEIGHT if k in fp_name]
    return PART_HEIGHT[max(keys, key=len)] if keys else None


#tallest fitted part on each side, measured from the board
def stack_heights(board, skip_dnp=True):
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

#maximum working voltage of each net, for the ratings check
CELLS = 5
NET_VMAX = {
    "VBAT": CELLS * 4.2,
    "VBAT_IN": CELLS * 4.2,
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
    "FLOW_MOTION": 3.3,
})

#in Rev C, both buck switchers (U8 Core 5V and U20 Payload 5V) are fully fitted
POPULATE_BLIND_SENSORS = False

#the two bucks, keyed on the fitted part
VREF_V = {
    "TPS54331": (0.800, "[D] TI TPS54331 datasheet"),
    "TPS54202": (0.596, "[D] TI TPS54202 SLVSD26C, 'typical voltage reference is designed at 0.596 V'"),
    "LMR33630A": (1.000, "[D] SNVSAN3F 7.5 Voltage Reference (FB pin), VFB ADJ option 0.985 / 1.000 / 1.015 V"),
}

#(ref, rail, vout_as_fitted_V, Rtop, Rbot, inductor)
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


#true when this rail's regulator is not fitted on the build being ordered
def buck_dnp(ref):
    return False


NET_SOURCE = {
    "VBAT_IN": "J2.2",     #battery connector, before the protection FET
    "VBAT":    "Q4.2",     #after the protection FET - Q4 pin 2 = source
    "+5V":   "L2.2",       #core 5 V buck output inductor
    "+5V_PAYLOAD": "L5.2", #payload 5 V buck output inductor
    "+3V3":  "U9.5",       #TLV757P output
    "+3V3A": "U10.5",      #TLV75533 output
    "+3V3_CAN": "U21.2",   #XC6206 output
    "+5V_BIAS_SW": "U24.6",  #bias-tee load switch output, before the sense resistor
    "VBUS":  "J1.A4B9",    #USB-C
}

NET_CURRENT = {
    #J2's VBAT pin to Q4: everything the board takes from the pack
    "VBAT_IN": 1.2,
    "VBAT": 1.2,            #the same current, after Q4: the bucks are all VBAT feeds
    "+5V":  0.95,
    "+5V_PAYLOAD": 1.5,
    "+5V_BIAS_SW": 0.155,   #AP22653 limit, RLIM 210k, max (DS41186)
    "+5V_BIAS": 0.155,
    "+3V3": 0.6,
    "+3V3A": 0.35,
    "+3V3_CAN": 0.1,
    "VBUS": 0.5,
}

#per-load continuous currents for check_power_cut.py
LOAD_CURRENT = {
    "+5V_PAYLOAD": {
        #[M] Payload 5V port J22: VTX 0.30 + XIAO camera 0.25
        "J22.1": 0.55,
        #[M] WS2812 strip average, 10% duty rule (HARDWARE.md: 60 mA cont / 600 mA peak)
        "P151.1": 0.06,
        #[D] LD06 steady 0.18 (300 mA is its start-up surge)
        "J11.1": 0.18,
        #[M] Two TVC servos on J17 and J23, pin 2 (250 mA each running)
        "J17.2": 0.25,
        "J23.2": 0.25,
        #[D] U21 is the +3V3_CAN LDO feed for the SN65HVD230
        "U21.3": 0.10,
        #[A] the DroneCAN node on J6 - the Remote ID module
        "J6.1": 0.15,
    },
    "+3V3A": {
        #[D] OPA2374: 585 uA per amplifier, two amplifiers (LOADS_3V3A row)
        "U14.8": 0.002,
        #[D] R28 feeds VCC_RF, the MAX2112 tuner's supply
        "R28.1": 0.100,
        #[L] the 25 MHz TCXO, ~2 mA (LOADS_3V3A row)
        "Y2.4": 0.002,
        #[D] the IMUs and the baro, at their LOADS_3V3A peaks, on each supply pin
        "U2.5": 0.002, "U2.8": 0.002, "U3.5": 0.002, "U3.8": 0.002,
        "U4.1": 0.002, "U4.2": 0.002,
    },
    "+3V3": {
        "J14.1": 0.030,                 #flow breakout (LOADS_3V3 row)
        "U25.5": 0.0003,                #INA180 (LOADS_3V3 row)
    },
    "VBUS": {
        "U12.5": 0.0,                   #USBLC6 ESD clamp: no DC load
    },
    #the +5V rows of LOADS_5V, per pad
    "+5V": {
        "U9.1": 0.294,                  #U9 (+3V3 LDO) input
        "U10.1": 0.107, "U10.3": 0.0,   #U10 (+3V3A LDO) input; pin 3 is EN
        "J3.1": 0.05,                   #M10 GPS + compass
        "J5.1": 0.1,                    #ELRS receiver
        "J9.1": 0.126,                  #TFS20-L 0.106 + upward ToF 0.02
        "J21.1": 0.25,                  #companion computer telemetry
        "U24.1": 0.015,                 #active bias-tee for active antenna LNA
    },
}

#the payload buck (U20, +5V_PAYLOAD)
PAYLOAD_PROFILES = {
    "drone": dict(keys=("J22.1", "P151.1", "J11.1", "U21.3", "J6.1"),
                  what="quad on GPS/SoOP: VTX + XIAO camera on J22, "
                       "LED strip, LD06 lidar, CAN transceiver and one node"),
    "lander": dict(keys=("J17.2", "J23.2", "P151.1", "U21.3", "J6.1"),
                   what="TVC lander: two TVC servos running on J17/J23 (aux servos are "
                        "one-shot deployers), LED strip, CAN transceiver and one node"),
}
PAYLOAD_ALL_WIRED = tuple(k for k in LOAD_CURRENT["+5V_PAYLOAD"] if k != "P151.1")


def payload_amps(keys):
    return round(sum(LOAD_CURRENT["+5V_PAYLOAD"][k] for k in keys), 3)


PAYLOAD_MISSION_A = {name: payload_amps(p["keys"]) for name, p in PAYLOAD_PROFILES.items()}
PAYLOAD_ALL_WIRED_A = payload_amps(PAYLOAD_ALL_WIRED)
RAIL_5V_PAYLOAD = dict(
    irms_a=2.1, isat_a=2.5,   #[D] L5 is upsized to CKCS5040-10uH/M (C354610)
    worst_mission=max(PAYLOAD_MISSION_A, key=PAYLOAD_MISSION_A.get),
    worst_mission_a=max(PAYLOAD_MISSION_A.values()),
    src="[D] CKCS5040-10uH/M Irms/Isat; [M] currents are design.LOAD_CURRENT['+5V_PAYLOAD'] "
        "keys grouped by design.PAYLOAD_PROFILES")
INDUCTOR_LOAD_A["L5"] = RAIL_5V_PAYLOAD["worst_mission_a"]

#the TVC servo rail
#the antenna feed monitor (firmware/soop/soop_ant.c) what the firmware decides from U25's
ANT_FEED = dict(
    sense_ref="R62", gain=50.0, vs=3.3, swing_v=0.02,
    lna_ma=15.0, short_circuit_ma=35.0,
    open_ma=3.0, short_ma=28.0, settle_s=0.5, retry_after_s=5.0, retry_off_s=10.0,
    adc="PC2_C, ADC3_INP0 (SYSCFG PMCR PC2SO open)",
    src="[D] TI INAx180: A2 gain 50 V/V, output swing to VS-0.02 V; [D] Tallysman HC610 15 mA at 2.2-12 V; [D] Diodes DS41186 Rev 5-2")


SERVO_RAIL = dict(
    refs=("J17", "J23"), net="+5V_PAYLOAD", count=2,
    run_a=0.250, stall_a=0.700,
    v_min=4.765, v_max=5.267,
    src="[D] docs/SENSORS.md: an 8-9 g micro (SG90 class) servo draws ~250 mA running and ~700 mA stalled")


#what each MCU pin is for, in the electrical sense
PIN_INTENT = {
    #motors and battery
    "M1": dict(mcu="out", why="DShot to ESC motor 1"),
    "M2": dict(mcu="out", why="DShot to ESC motor 2"),
    "M3": dict(mcu="out", why="DShot to ESC motor 3"),
    "M4": dict(mcu="out", why="DShot to ESC motor 4"),
    "BATT_V_DIV": dict(mcu="analog", why="11:1 pack divider into ADC1"),
    "ESC_CUR":    dict(mcu="analog", why="ESC current-sense output into ADC1"),
    "ESC_TEL":    dict(mcu="in",     why="ESC transmits telemetry to the FC - RX pin"),

    #IMU1 / IMU2 SPI
    "SPI1_SCK": dict(mcu="out", why="clock to ICM-42688-P"),
    "SPI1_MOSI": dict(mcu="out", why="MCU drives"),
    "SPI1_MISO": dict(mcu="in",  why="sensor drives"),
    "IMU1_CS":  dict(mcu="out", boot="high", why="chip select, idle high"),
    "SPI4_SCK": dict(mcu="out", why="clock to ICM-42605"),
    "SPI4_MOSI": dict(mcu="out", why="MCU drives"),
    "SPI4_MISO": dict(mcu="in",  why="sensor drives"),
    "IMU2_CS":  dict(mcu="out", boot="high", why="chip select, idle high"),

    #SPI3: optical flow + TLE flash
    "SPI3_SCK": dict(mcu="out", why="shared clock, PMW3901 + W25Q128"),
    "SPI3_MOSI": dict(mcu="out", why="MCU drives"),
    "SPI3_MISO": dict(mcu="in",  why="devices drive"),
    "EXT_CS1":  dict(mcu="out", boot="high", why="optical flow PMW3901 chip select, idle high"),
    "EXT_CS2":  dict(mcu="out", boot="high", why="W25Q128 select, idle high"),
    "FLOW_MOTION": dict(mcu="in", why="PMW3901 motion interrupt input pin"),

    #I2C
    "I2C1_SCL": dict(mcu="bidir", why="open-drain, 4k7 pull-up"),
    "I2C1_SDA": dict(mcu="bidir", why="open-drain, 4k7 pull-up"),
    "I2C2_SCL": dict(mcu="bidir", why="open-drain, 4k7 pull-up"),
    "I2C2_SDA": dict(mcu="bidir", why="open-drain, 4k7 pull-up"),

    #serial
    "USART2_TX": dict(mcu="out", why="to GPS RX"),
    "USART2_RX": dict(mcu="in",  why="from GPS TX"),
    "UART7_TX":  dict(mcu="out", why="to companion RX"),
    "UART7_RX":  dict(mcu="in",  why="from companion TX"),
    "UART7_CTS": dict(mcu="in",  why="from companion RTS"),
    "BIAS_EN":   dict(mcu="out", why="MCU enables active bias-tee"),
    "BIAS_FAULT": dict(mcu="in", why="bias-tee load switch fault flag"),
    "USART6_TX": dict(mcu="out", why="to receiver, or half-duplex CRSF"),
    "RC_IN":     dict(mcu="in",  why="receiver drives the FC"),

    "CAN1_RX":     dict(mcu="in",  why="transceiver RXD drives the MCU"),
    "CAN1_TX":     dict(mcu="out", why="MCU drives transceiver TXD"),
    "CAN1_SILENT": dict(mcu="out", boot="low",
                        why="SN65HVD230 Rs: LOW = high-speed mode, HIGH = standby"),

    #USB / SD
    "USB_DP": dict(mcu="bidir", why="USB differential pair"),
    "USB_DM": dict(mcu="bidir", why="USB differential pair"),
    "SD_D0": dict(mcu="bidir", why="SDMMC data"),
    "SD_D1": dict(mcu="bidir", why="SDMMC data"),
    "SD_D2": dict(mcu="bidir", why="SDMMC data"),
    "SD_D3": dict(mcu="bidir", why="SDMMC data"),
    "SD_CMD": dict(mcu="bidir", why="SDMMC command"),
    "SD_CK":  dict(mcu="out",   why="SDMMC clock"),
    "SD_CD":  dict(mcu="in",    why="card-detect switch to GND, 10k pull-up"),

    #notify
    "LED0":   dict(mcu="out", why="status LED via 1k"),
    "LED1":   dict(mcu="out", why="status LED via 1k"),
    "BUZZER": dict(mcu="out", boot="low",
                   why="AO3400A gate; R39 pulls down so it is silent through reset"),
    "WS2812": dict(mcu="out", why="into the 74LVC1G17 level shifter"),

    #payload 5V buck power
    "PAYLOAD_EN": dict(mcu="out", boot="low",
                       why="Q3 gate: LOW leaves the 5V Payload rail enabled, HIGH cuts it"),

    #TVC servos / secondary actuators (TIM4 on J17)
    "PWM7":  dict(mcu="out", why="TIM4_CH3 servo PWM on J17 (PB8)"),
    "PWM8":  dict(mcu="out", why="TIM4_CH2 servo PWM on J23"),

    #lander / recovery peripherals

    #brought out to test pads only, no device fitted
    "USART1_TX": dict(mcu="out", why="telem2 TX on test pad TP5"),
    "USART1_RX": dict(mcu="in",  why="telem2 RX on test pad TP6"),
    "PWM5": dict(mcu="out", why="spare servo output (TIM4_CH4, PB9) on test pad TP3"),
    "PWM6": dict(mcu="out", why="spare motor output on test pad TP4"),

    #debug
    "SWDIO": dict(mcu="bidir", why="SWD data"),
    "SWCLK": dict(mcu="in",    why="probe drives the clock"),
}


#the one board, and everything that can bolt onto it later
MODULES = {
    "esc": dict(
        what="SpeedyBee BLS 60A 4-in-1", lands_on=["J2"], conn="JST-GH 8P on J2, side entry; a GH-8P to SH-8P lead to the ESC",
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
        note="Mount settled 2026-09-04: fore or aft of the battery on the top plate"),
    "lidar_360": dict(
        what="LDROBOT LD06, 12 m, INDOOR ONLY", lands_on=["J11"],
        conn="SERIAL2 (USART1) on J11; J11.1 is +5V_PAYLOAD (U20)", bec=True,
        #price, third and final correction
        needs_board_change=None, gbp=OFFBOARD["lidar"]["gbp"], status="later",
        ma_5v=180, counted=False,
        note="[D] 180 mA running, but 300 mA at START-UP"),
    "rc_link": dict(
        what="ELRS 2.4 GHz, ESP-based", lands_on=["J5"], conn="JST-GH 4P on J5 (USART6)",
        needs_board_change=None, gbp=12, status="fitted",
        ma_5v=100, counted=True,
        note="MAVLink downlink caps at 1470 B/s - carries telemetry, never video"),
    "soop_tuner": dict(
        what="SoOP RF front end: Tallysman HC610 active helix (filter + LNA), at the antenna",
        lands_on=["J12"], conn="MMCX coax into J12; the board's bias tee (U24, L6) feeds "
                               "its LNA +5 V down the coax", bec=False,
        needs_board_change=None, gbp=115, status="later",
        ma_5v=15, counted=True,
        note="the filter+LNA stage the board could not source, bought built into the antenna. 15 mA [D] at 2.2-12 V, fed by the on-board bias tee - J12 carries +5 V"),
    "fpv": dict(
        what="5.8 GHz camera + VTX, 25 mW EIRP", lands_on=["J22"],
        conn="5 V and GND from J22 (GH-3P, +5V_PAYLOAD, U20)", bec=True,
        needs_board_change=None, gbp=25, status="later",
        ma_5v=300, counted=False,
        note="a 25 mW AIO runs from 5 V, so it does not need the unroutable 9 V block - and from the payload BEC, not this board's buck"),
    "rec_camera": dict(
        what="XIAO ESP32-S3 Sense, records to its own SD", lands_on=[],
        conn="its own 1S cell; or, flown with no VTX, J22's GH-3P (+5V_PAYLOAD) - J22 is one "
             "port, so the VTX and the camera together need a Y-lead", bec=True,
        needs_board_change=None, gbp=14, status="later",
        ma_5v=250, counted=False,
        note="0.25 A, on the payload BEC (or standalone on a 1S cell)"),
    "flow_globalshutter": dict(
        what="global-shutter flow via a companion",
        lands_on=["J21"],
        conn="SERIAL1 (UART7) on J21, MAVLink OPTICAL_FLOW",
        needs_board_change=None,
        gbp=60, status="later",
        ma_5v=0, counted=True,
        note="FLOW_TYPE 5 (MAVLink) - the companion does the vision, the H7 just consumes it"),
    "flow_pmw3901": dict(
        what="PixArt PMW3901 flow", lands_on=["J14"], conn="JST-GH 6P on J14 (SPI3)",
        needs_board_change=None,
        gbp=12, status="later",
        ma_5v=0, counted=True,
        note="External PMW3901 flow breakout connects via J14 on SPI3"),
    "payload_5v_rail": dict(
        what="on-board 5 V buck for payload/servos", lands_on=["J17", "J23", "J11"], conn="+5V_PAYLOAD",
        needs_board_change=None,
        gbp=0, status="fitted",
        ma_5v=0, counted=True,
        note="LMR33630A buck U20 (2.1 A through L5) powering the servos on J17/J23, the lidar "
             "on J11, J22 and the DroneCAN node on J6"),
    "remote_id": dict(
        what="Holybro Remote ID: direct broadcast ID, UK rule for home-built UAS >= 100 g with "
             "a camera from 1 Jan 2028", lands_on=["J6"], conn="JST-GH 4P on J6 (DroneCAN)",
        needs_board_change=None, gbp=35, status="later", ma_5v=150, counted=False, bec=True,
        note="ArduRemoteID over DroneCAN; confirm the CAA's broadcast standard before buying"),
    "src": "[M] every lands_on asserted against real footprints by the module check",
}


#RF_BENCH - the T3b self-interference measurements, and the gate on them
RF_BENCH = dict(
    results="fab/rf-bench-results.json",
    band_mhz=(1616.0, 1626.5),
    steps=[
        ("baseline", "HC610 helix on the RTL-SDR's bias tee, outdoors, clear sky, AIRCRAFT OFF",
         "the reference. Needs no aircraft - do it the week the SDR parts arrive"),
        ("board_powered", "board powered, motors off, same position and same sky",
         "any drop is the flight controller: its two switchers and the H7"),
        ("motors_spinning", "motors spinning, props off, tethered",
         "any further drop is the ESC and the four motor leads acting as antennas"),
        ("elrs_tx", "ELRS transmitting",
         "isolates front-end desense from the control link"),
    ],
    #fields each step must carry
    fields=("bursts_per_min", "noise_floor_dbm", "utc", "sky"),
    #a step keeping this fraction of baseline bursts is a pass
    min_fraction_of_baseline=0.5,
    mitigations=["antenna placement and separation", "ferrites on the motor leads",
                 "move the tuner's antenna feed further from U8/U20 in Rev E - the receive "
                 "chain is on this board, so the bench SDR only locates the source"],
    src="[A] min_fraction_of_baseline is a judgement call; every other field is a slot "
        "for an [M]easured value recorded by runbook T3b",
)


#RAIL_5V - what is actually left on the +5 V rail
RAIL_5V = dict(
    irms_a=1.6,          #[D] FNR4030S100MT, C167879 - the thermal limit
    isat_a=2.4,          #[D] saturation - a transient limit, not a load budget
    fitted_load_a=LOADS_5V_CONT_A,   #[M] derived from LOADS_5V above, continuous
    fitted_peak_a=LOADS_5V_PEAK_A,   #[M] the same list at its peak column (inductor Isat)
    headroom_a=1.6 - LOADS_5V_CONT_A,
    note="Neither fitted inductor sits on a land too small for it any more: L2 is a 4.0x4.0x3.0 mm FNR4030 on L_APV_ANR4030",
    src="[D] Irms/Isat from the FNR4030S100MT datasheet; [M] fitted_load_a is the sum of design.LOADS_5V - one list",
)

#the payload breakout quotes the +5 V headroom
PAYLOAD_BREAKOUT["headroom_a"] = RAIL_5V["headroom_a"]

#bare copper pads are board features
NOT_A_PART = {ref for ref, spec in COMPONENTS.items()
              if spec[1] in ("TestPoint:TestPoint_Pad_1.5x1.5mm",
                             "Fiducial:Fiducial_1mm_Mask2mm",
                             "Connector:Tag-Connect_TC2030-IDC-NL_2x03_P1.27mm_Vertical")}


#silkscreen: the function name printed beside each connector
SILK_NAMES = {
    "J1": "USB", "J2": "ESC", "J3": "GPS", "J5": "RC", "J6": "CAN",
    "J9": "I2C", "J11": "UART2", "J12": "ANT", "J14": "FLOW",
    "J17": "SRV1", "J23": "SRV2", "J19": "SWD", "J21": "TELEM", "J22": "P5V",
}
#what each solder pad and test point
PAD_LABELS = {
    "P151": "L5V", "P152": "DIN", "P153": "LG",
    "P161": "B5V", "P162": "BZ", "P163": "BG",
    "TP3": "S5", "TP4": "S6", "TP9": "I", "TP10": "Q",
}
#pads the silkscreen has no room to name
PAD_LABELS_UNPRINTED = {
}
#connector names the silkscreen has no room for (tools: silk_names.py, 4 mm search)
SILK_NAMES_UNPRINTED = {
    "J6": "GH-4P on the north edge, bottom; the free silk beside it is nearer TP4, so a "
          "name there would read as TP4's",
    "J12": "the only coax jack on the board, inside the RF fence",
    "J14": "GH-6P under J21 on the bottom; its pads face a column of passives",
    "J19": "Tag-Connect footprint, bench-only, used with its own cable",
    "J21": "GH-6P on the east edge; its pads face U13's passives, its body covers the rest",
    "J23": "0.5 mm from J17 and boxed in by U17 and P151: SRV1 is printed beside J17, "
           "J23 is the other servo header",
}

SILK_TITLE = ["IRIDIUM NAV", "KRYSTIAN FILIPEK"]
#Rev C's hand-placed texts
SILK_RETIRED = {"PYRO", "SERVO"}
SILK_TITLE_SIDE = {"IRIDIUM NAV": "bottom", "KRYSTIAN FILIPEK": "top"}

#3D models: bodies that legitimately sit off their outline or reach into the board
MODEL_EXPECTED = {
    "J12": (0.01, -1.22),  #the MMCX barrel overhangs the north edge
    #servo headers: the box is the housing
    "J17": (-0.01, -0.40),
    "J23": (-0.01, -0.40),
}
MODEL_EXPECTED_SINK = {
    "J1": 0.78,            #USB-C shell legs in their slots
    "J8": 0.61,            #microSD locating posts in their holes
    "J12": 2.80,           #MMCX legs through the board
}

#board frame: which edge is forward
#forward is the BOTTOM edge in KiCad's top view - the servo / RC edge
BOARD_FORWARD = (0, +1)      #KiCad (x right, y down) direction of "forward"
#TDK LGA-14 axes, from the datasheet's top view
IMU_AXES = {
    "U2": ("icm42688", ("1", "2", "3", "4"), ("8", "9", "10", "11"), ("5", "6", "7"), ("12", "13", "14")),
    "U3": ("icm42605", ("1", "2", "3", "4"), ("8", "9", "10", "11"), ("5", "6", "7"), ("12", "13", "14")),
}
SILK_ARROW = {"side": "top", "direction": BOARD_FORWARD, "length": 2.5, "label": None}
