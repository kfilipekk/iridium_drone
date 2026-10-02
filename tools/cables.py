#the aircraft's cables: what each one is, the way it runs, and the length to buy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design
import gen_scad_mounts

_F = design.FRAME
_MID_TOP = _F["bottom_t"] + _F["arm_t"] + _F["medium_t"]      #the ESC stands here
_T, _N, _L, _R = (gen_scad_mounts.G[k] for k in ("tower", "nose", "lidar", "range"))
#the tie behind the receiver pocket (gen_scad_mounts: rx_y + rx_l + 4)
_RX_TIE_Y = _N["rx_y"] + _N["rx_l"] / 2 + 0.2 + _N["rx_wall"] + 4.0

#what the leads are made of
LEADS = {
    #pre-crimped JST leads are loose 28 AWG wires, not a jacketed cable
    "gh": dict(od=1.0, rmin_x=5.0,
               src="[A] 28 AWG hook-up wire on pre-crimped JST-GH/SH leads, 1.0 mm over "
                   "the insulation; [A] 5 x OD bend for stranded wire laid flat"),
    #MMCX pigtails come in RG178 or RG316
    "rg178": dict(od=1.8, rmin_x=10.0,
                  src="[D] RG178 B/U: 1.8 mm over the FEP jacket; [A] 10 x OD bend, the "
                      "dynamic figure - most RG178 sheets give 5 x OD static"),
}
#diameter of n equal circles packed in the smallest circle
BUNDLE_X = {1: 1.0, 2: 2.0, 3: 2.155, 4: 2.414, 5: 2.701, 6: 3.0, 7: 3.0, 8: 3.305}

#where a side-entry plug's wires leave it
PLUG_AXIS = 2.2         #[A]
#plug bodies at the far end, front face to where the wire leaves
FAR_BODY = dict(gh=5.0, sh=4.0, zh=4.0, sma_ra=12.0, solder=0.0, servo=0.0)  #[A] mouldings
#overall length on top of the routed run
SLACK = dict(frac=0.10, min=10.0, src="[A] 10 % of the run, at least 10 mm")
#standard lengths a listing offers, overall
STOCK = dict(gh=(50, 100, 150, 200, 300), rg178=(100, 150, 200, 300),
             src="[L] JST-GH/SH pre-made leads and MMCX/U.FL pigtails, AliExpress and "
                 "Holybro listings")

#clearance margins
MARGIN = dict(
    prop=10.0,       #[A] twice the CAD fit check's 5 mm for rigid parts
    carbon=1.0,      #[A] a cut carbon edge chafes through insulation
    board=1.0,       #[A] ESC, FC and the mated plugs
    battery=2.0,     #[A] the pack slides in under a strap
    printed=0.5,     #[A] printed mounts: smooth, and the cables are tied to them
    antenna=5.0,     #[A] keep wires out of the near field of the helix and ELRS whips
    ground=10.0,     #[A] above the skid contact plane
)


#the ESC's 8-pin JST-SH socket: on its port edge under J2
def _sh_esc():
    return (-design.ESC["L"] / 2 - FAR_BODY["sh"], 5.4,
            _MID_TOP + design.ESC["pcb"] + 2.9 / 2)


#the M10Q's GH-6P, on the module's forward edge
def _gps_plug():
    g = design.MOUNTED["gps"]
    return (0.0, _T["gps_y"] - g["W"] / 2 - FAR_BODY["gh"], _T["gps_bot"] + 2.5)


#the right-angle SMA plug on the HC610's SMA
def _sma_ra():
    return (FAR_BODY["sma_ra"], _T["helix_y"], _T["seat_z"] - 14.0)


#the RP3's solder pads at its aft end
def _rx_pads():
    rx = design.MOUNTED["rx"]
    return (0.0, _N["rx_y"] + rx["L"] / 2 - 1.0, _N["z"] - _N["t"] - 1.21)


#the LD06's ZH1.5-4P on its forward face
def _ld06_plug():
    ld = design.OFFBOARD["lidar"]
    return (0.0, _L["y"] - ld["W_mm"] / 2 - FAR_BODY["zh"], -_L["t"] - 4.0)


#the cradle's lead slot, on its aft face at the lid end (gen_scad_mounts)
def _tfs20_slot():
    return (0.0, _R["y"] + _R["yl"] / 2, -_R["body_h"] + 1.5)


#the XIAO's 5V/GND pins on its port edge
def _xiao_pins():
    return (-6.0, _N["cam_y"] + design.MOUNTED["xiao"]["W"] / 2 + 0.3 + _N["cw"], -8.0)


CABLES = {
    "J2": dict(
        to="SpeedyBee BLS 60A, its 8-pin JST-SH, directly below",
        lead="JST-GH 8P to JST-SH 8P, pin 1 to pin 1", type="gh", wires=8, far="sh",
        end=_sh_esc(), end_dir=(1.0, 0.0, 0.0),
        end_src="[A] the ESC turned so its socket is on the port edge, under J2; "
                "[D] JST-SH 2.9 mm tall; [D] ESC 45.6 mm (design.ESC)",
        #out to port, down past the board edge, back in to the ESC
        via=[(-36.7, 5.4, 29.5), (-36.7, 5.4, 13.55)],
        touches={},
        buy=100),
    "J3": dict(
        to="Matek M10Q-5883 in the GPS pod at the back of the antenna tower",
        lead="JST-GH 6P to JST-GH 6P, straight through (ArduPilot GPS order)",
        type="gh", wires=6, far="gh",
        end=_gps_plug(), end_dir=(0.0, 1.0, 0.0),
        end_src="[A] the GH socket on the module's forward edge, 2.5 mm above its "
                "underside; [M] pod and module from design.MOUNTS / MOUNTED",
        #aft under the top plate between the rear posts, up behind the tower foot
        via=[(0.0, 45.0, 29.5), (-4.0, 74.0, 30.0), (-9.0, 96.0, 33.0), (-9.0, 97.0, 50.0),
             (-25.0, 99.0, 57.0), (-25.0, 102.0, 66.0), (-19.5, 112.0, 66.0),
             (-19.5, _T["tie_y"], 66.0), (0.0, 140.0, 66.0), (0.0, 140.0, 95.6)],
        touches={"gps pod": "leaves through the pod's front slot",
                 "gps": "ends in the module's socket"},
        buy=300),
    "J12": dict(
        to="Tallysman HC610's SMA male, inside the tower column",
        lead="MMCX plug (straight) to SMA female (right angle), RG178", type="rg178",
        wires=1, far="sma_ra",
        end=_sma_ra(), end_dir=(-1.0, 0.0, 0.0),
        end_src="[A] right-angle SMA plug: cable 12 mm off the SMA axis and 4 mm below its end (z 54 in cad/mounts.scad)",
        #aft beside the FC
        via=[(20.5, 38.0, 29.3), (27.0, 48.0, 32.0), (31.0, 58.0, 44.0), (31.0, 84.0, 50.0)],
        touches={},
        buy=150),
    "J5": dict(
        to="RadioMaster RP3 in the nose mount's pocket (solder pads)",
        lead="JST-GH 4P to bare ends, soldered to the RP3", type="gh", wires=4,
        far="solder",
        end=_rx_pads(), end_dir=(0.0, -1.0, 0.0),
        end_src="[M] pocket from design.MOUNTS['nose_mount']; [A] pads at the RP3's aft end; the wires pulled up against the plate by the tie, inside the slot",
        #forward over the mid plate, past its front end
        via=[(-5.6, -36.0, 23.5), (-7.0, -48.0, 15.0), (-9.5, -78.0, 14.5),
             (-27.5, -92.0, 13.0), (-27.5, -92.0, 1.5), (-18.5, -60.0, 3.0),
             (-8.0, -47.0, 4.29), (0.0, _RX_TIE_Y, 4.29)],
        touches={"nose plate": "tied to its underside behind the pocket",
                 "rx pocket": "ends at the receiver's pads", "rx": "soldered to it"},
        buy=200),
    "J11": dict(
        to="LDROBOT LD06 under the bottom plate, on the lidar bracket",
        lead="JST-GH 4P to JST-ZH 1.5 mm 4P", type="gh", wires=4, far="zh",
        end=_ld06_plug(), end_dir=(0.0, 1.0, 0.0),
        end_src="[A] the LD06's ZH socket on its forward face, 4 mm below its base",
        #J11 faces forward and the lidar is aft
        via=[(5.6, -36.0, 23.5), (9.0, -44.0, 15.0), (24.0, -40.0, 14.0),
             (31.0, -12.0, 13.5), (31.0, 0.0, 6.0), (31.0, 0.0, -9.0),
             (8.0, -10.0, -9.0), (0.0, -10.0, -9.0)],
        touches={},
        buy=200),
    "J9": dict(
        to="Benewake TFS20-L in the range cradle under the bottom plate",
        lead="JST-GH 4P to the TFS20-L's own 4-pin lead ([A] GH 1.25)", type="gh", wires=4, far="gh",
        end=_tfs20_slot(), end_dir=(0.0, -1.0, 0.0),
        end_src="[M] the cradle's lead slot (gen_scad_mounts); [A] the sensor's socket "
                "just inside it",
        #aft under the FC and the top plate
        via=[(-5.6, 40.0, 23.5), (-4.0, 64.0, 16.0), (-4.0, 92.0, 8.0), (-4.0, 96.0, 0.0),
             (-2.0, 92.0, _tfs20_slot()[2]), (0.0, 84.0, _tfs20_slot()[2])],
        touches={"range cradle": "ends at its lead slot", "range lid": "part of the cradle"},
        buy=150),
    "J22": dict(
        to="XIAO ESP32S3 Sense recording camera, in the nose cradle",
        lead="JST-GH 3P to bare ends (+5V_PAYLOAD and GND), soldered to the XIAO",
        type="gh", wires=3, far="solder",
        end=_xiao_pins(), end_dir=(0.0, -1.0, 0.0),
        end_src="[M] cradle from design.MOUNTS['nose_mount']; [A] J22 feeds the XIAO "
                "(MODULES rec_camera: +5V_PAYLOAD, which J22 now carries)",
        #out to port, down the gap between the two port arms
        via=[(-36.0, -7.3, 29.5), (-36.0, -4.0, 20.0), (-36.0, -4.0, -6.0),
             (-20.0, -40.0, -8.0), (-6.0, -66.0, -8.0)],
        touches={"cam cradle": "ends at the XIAO's pins, through its aft wall"},
        buy=200),
    #ports whose far end has no position yet: only the board end is checked
    "J14": dict(
        to="optical flow under the belly - UNDEFINED (design.FLOW fitted=False, no mount)",
        lead="JST-GH 6P to the flow sensor's lead", type="gh", wires=6, far="gh",
        end=None, undefined="design.FLOW is deferred and no mount carries a flow sensor; "
                            "the belly slot is the TFS20-L's",
        #the shortest way under the bottom plate: down the starboard arm gap
        via=[(36.0, 6.7, 23.5), (36.0, 1.0, 12.0), (36.0, 0.0, -3.5)],
        touches={}, buy=None),
    "J6": dict(
        to="DroneCAN node - UNDEFINED (no node position in design.py)",
        lead="JST-GH 4P to JST-GH 4P (DroneCAN standard)", type="gh", wires=4, far="gh",
        end=None, undefined="no CAN node has a position in design.MOUNTS",
        #out past the line of the rear posts
        via=[(5.6, 34.0, 23.5)], touches={}, buy=None),
    "J21": dict(
        to="companion computer - UNDEFINED (design.PI deferred, does not fit the top plate)",
        lead="JST-GH 6P (Pixhawk TELEM order)", type="gh", wires=6, far="gh",
        end=None, undefined="design.PI is DEFERRED, not fitted, with no envelope on the "
                            "airframe",
        #out past the top plate's starboard edge
        via=[(32.0, 6.7, 29.5)], touches={}, buy=None),
    "J17": dict(
        to="lander TVC servo 1 - not on this airframe",
        lead="the servo's own JR lead", type="gh", wires=3, far="servo",
        end=None, undefined="servos are the ESP32 lander's TVC gimbal; the drone fits none",
        #out past the forward pair of front posts
        via=[(-4.75, -59.0, 28.55)], touches={}, buy=None),
    "J23": dict(
        to="lander TVC servo 2 - not on this airframe",
        lead="the servo's own JR lead", type="gh", wires=3, far="servo",
        end=None, undefined="servos are the ESP32 lander's TVC gimbal; the drone fits none",
        via=[(4.75, -59.0, 28.55)], touches={}, buy=None),
}
#the servo plug's wires leave it nearer the board than a GH plug's
AXIS_OVERRIDE = {"J17": 1.25, "J23": 1.25, "J12": 2.0}   #J12: [A] MMCX jack centre, 4.0 tall
