// =====================================================================
//  NAVCORE-SoOP  -  rudimentary assembly model
//
//  Accurate in DIMENSION, deliberately crude in DETAIL. Every number
//  marked [M] is measured from the KiCad board; [D] is from a datasheet
//  or the SpeedyBee manual; [A] is an assumption you should check
//  against the frame you actually buy.
//
//  Open in OpenSCAD (free, openscad.org), press F5 to preview, drag to
//  rotate. F6 renders, then File > Export > STL/OFF/AMF for other tools.
//
//  For the REAL board geometry with actual component shapes, open
//  NAVCORE-SoOP.step alongside this in FreeCAD - this file models the
//  board as a plain slab on purpose.
// =====================================================================

$fn = 48;                       // facet count; drop to 24 if preview is slow

// ---- what to show ---------------------------------------------------
show_props     = true;
show_battery   = false;         // on by default it hides the whole stack
show_frame     = true;
show_top_plate = true;          // off for a plan view of the stack
// FLOW IS DEFERRED - the camera is not fitted in this build (see FLOW in
// tools/design.py). Left switchable and left ON by default so the clearance
// it needs stays visible: the lens-above-skid margin is the constraint that
// decides where a camera CAN go, and losing it from the model is how a build
// gets committed to a frame that cannot take one later.
// FALSE. This is the DEFERRED OV9281 flow camera (design.FLOW.fitted = False), and it
// wants the SAME belly slot as the downward rangefinder that IS fitted. Drawing both put
// 2299 mm^3 of one inside the other - check_cad_fit found it the moment the belly sensor
// was modelled, which is the correct answer rather than a modelling bug: there is ONE
// position under the bottom plate with a clear view of the ground, and modules compete
// for it. See design.BELLY_SENSOR. Set true only when the flow camera displaces the
// rangefinder, not alongside it.
show_camera    = false;         // DEFERRED OV9281 flow camera - competes for the belly slot
show_skids     = true;          // TPU landing skids at the motor pattern
// FALSE, because it does not fit and is not fitted. design.PI is tagged
// "DEFERRED, not fitted", and the geometry says why: the top plate is 50 mm wide, the
// 138 x 47 mm battery takes 47 of that, and the 65 x 30 mm Radxa needs 30 more. Drawn
// at pi_y_off = 25 the two overlapped by 13.5 mm in y - 1165 mm^3 of battery inside
// the companion board. Set this true only alongside a real decision about where the
// companion goes; the top plate is not it. See docs/SENSORS.md.
show_rec_cam   = true;         // XIAO ESP32S3 Sense on the nose, recording to microSD
show_pi        = false;         // Radxa Zero 3W companion - DEFERRED, does not fit here
explode        = 0;             // try 28 for an exploded view

// ---- NAVCORE-SoOP flight controller  [M] ----------------------------
                                // U6's COB at 2.30 as this said before -
                                // check_build.py was counting both
                                // inductors as 1.0 mm via a silent default

// ---- SpeedyBee BLS 60A 4-in-1 ESC  [D] ------------------------------

// ---- stack hardware  [D] --------------------------------------------

// ---- airframe -------------------------------------------------------
// GENERATED from tools/design.py by tools/gen_scad_frame.py. These numbers used to be
// written out here by hand and had drifted from what check_build.py was testing:
// wheelbase 300 vs 295, arm 4.0 vs 6.0, plate 2.0 vs 3.0, top plate 32 vs 35. Whichever
// file you opened decided the answer. Regenerate rather than edit.
include <frame.scad>
// frame.scad is GENERATED from design.py AND the real board - it now carries the
// part dimensions too (fc_*, esc_*, skid_*, cam_*, pi_*). They used to be duplicated
// here, and fc_bot_parts drifted to 2.50 against a measured 3.00.

plate_t        = bottom_plate_t;   // the plate this model draws

// arm_w was 12 and commented "cosmetic: arm render width, no check uses it". BOTH
// halves were wrong. arm() is called from frame(), frame() is exported as a part, and
// check_cad_fit.py measures it - so arm_w sets the frame-vs-props and frame-vs-skids
// separations directly. And 12 mm is not the arm: the DXF gives 31.08 mm across.
// Using the bounding-box width makes the modelled arm wider than the real tapered one,
// which is the CONSERVATIVE direction for a clearance check - it can report less room
// than exists, never more. Same convention as fc_l/fc_w using the Edge.Cuts bbox.
arm_w          = arm_plate_w;      // [M] 31.08 mm, from frame.scad

// ---- Z DATUMS -------------------------------------------------------
// The stack does NOT sit on the bottom plate. This model said it did, drawing
// the arms from z = 0 so they occupied the bottom plate AND the ESC at once -
// check_cad_fit.py measured 4118 mm^3 of ESC inside the frame.
//
// The evidence is the DXF parse already recorded in design.FRAME_CAD: the plate
// carrying the 30.5 mm stack pattern is 48.50 x 106.59 mm - a narrow strip, not
// the 200 x 230 bottom plate. So the stack bolts to a separate mid plate above
// the arm layer, and the true order bottom-up is:
z_bot_plate = 0;
z_arm       = bottom_plate_t;                   // arms sit ON the bottom plate
z_mid_plate = z_arm + arm_t;                    // mid plate clamps the arms
z_stack     = z_mid_plate + medium_plate_t;     // ESC starts here
stack_h     = esc_pcb + esc_parts + gap + fc_bot_parts + fc_pcb + fc_top_parts;

// WHERE inner_h IS MEASURED FROM is not settled by a 2D DXF, and the two readings
// differ by 8.0 mm, so the model takes the WORSE one: standoffs measured from the
// BOTTOM plate, which leaves the least room above the mid plate. If the real frame
// measures them from the mid plate there is simply 8 mm more headroom than shown.
// Standoff length is a few-pound purchase in 25/30/35/40 mm, so this is a buying
// decision, not a frame constraint - see the note on FRAME in tools/design.py.
top_plate_z    = standoff_len;                  // COMPUTED, from frame.scad
fc_top_z       = z_stack + stack_h;      // top of the FC's tallest part
headroom       = top_plate_z - fc_top_z;

// =====================================================================
motor_off = wheelbase / 2 / sqrt(2);     // offset on each axis, square X

// RECTANGULAR, and a different rectangle per plate. This took (w, t) and drew a
// SQUARE of side w for all three plates, from bottom_plate_w = 50 - a placeholder whose
// own comment admitted it ("must be >= fc_w"). The real plates are 48.50 x 106.59,
// 42.50 x 160.26 and 48.50 x 107.62, all parsed from the manufacturer DXF and sitting
// unused in design.PLATES the whole time. The top plate alone was out by 3.2x in length.
module plate(w, l, t) {
    difference() {
        linear_extrude(t) offset(r = 4) square([w - 8, l - 8], center = true);
        // plate_hole_dia, NOT screw_dia. Cutting the hole at exactly the screw
        // diameter makes the two surfaces coincident, and the bolt then reads as
        // solidly inside the plate - 132.5 mm^3 of it, near enough the whole bolt.
        // A real M3 clearance hole is 3.2 mm.
        for (sx = [-1, 1], sy = [-1, 1])
            translate([sx * hole_pitch/2, sy * hole_pitch/2, -1])
                cylinder(d = plate_hole_dia, h = t + 2);
    }
}

module arm() {
    hull() {
        cylinder(d = arm_w, h = arm_t);
        translate([motor_off * sqrt(2), 0, 0]) cylinder(d = arm_w, h = arm_t);
    }
}

module frame() {
    color("#22252a") {
        translate([0, 0, z_bot_plate]) plate(bot_plate_w, bot_plate_l, plate_t);
        for (a = [45, 135, 225, 315])
            rotate([0, 0, a]) translate([0, 0, z_arm]) arm();
        // mid plate: the 48.50 x 106.59 strip that actually carries the stack
        translate([0, 0, z_mid_plate])
            plate(fc_plate_w, fc_plate_l, medium_plate_t);
        // TOP PLATE. 42.50 x 160.26 - the long one. It reaches 80.13 mm out along Y,
        // and it sits at z = standoff_len, ABOVE the prop plane, so it is the part of
        // the frame that comes nearest a prop disc. That was invisible while it was
        // drawn as a 50 mm square.
        //
        // MEASURE ON ARRIVAL: this plate's own M3 holes are at x = +/-14.60 and
        // +/-11.00 (design.PLATES), which is NOT the 30.5 mm stack pattern the standoffs
        // above the FC use, and design.FRAME_CAD puts the nearest candidate at
        // |y| >= 27.90 mm. So how the stack's upper standoffs land on this plate is
        // genuinely unresolved. The holes drawn here are the 30.5 pattern, kept so the
        // stack_screws pair still reads as designed - do not take them as confirmation.
        if (show_top_plate) translate([0, 0, top_plate_z])
            plate(top_plate_w, top_plate_l, plate_t);
        // Corner posts. These were drawn as solid 5 mm cylinders running the whole
        // way from the mid plate to the top plate, straight THROUGH both boards -
        // check_cad_fit.py measured 610 mm^3 of ESC and 386 mm^3 of FC inside them.
        //
        // That is not how a 30x30 stack mounts. An M3 BOLT passes up through the
        // boards' 4.0 mm holes (with grommets), and the 5 mm spacer body only
        // occupies the run ABOVE the stack, between the FC and the top plate. The
        // bolt itself is stack_screws(), at screw_dia = 3.0 mm.
        // BORED, not solid. A standoff is a tube the bolt runs through, and these
        // sit at the same (x, y) as stack_screws() by definition - so a solid post
        // swallows the bolt. That was the 132.5 mm^3 check_cad_fit.py reported, and
        // the arithmetic identifies it exactly: 4 x pi/4 x 3^2 x 4.7 mm of post =
        // 132.9 mm^3. It was NOT the plates, which the failure message blamed; a
        // label is not a measurement.
        for (sx = [-1, 1], sy = [-1, 1])
            translate([sx * hole_pitch/2, sy * hole_pitch/2, fc_top_z])
                color("#8d949c") difference() {
                    cylinder(d = 5, h = top_plate_z - fc_top_z);
                    translate([0, 0, -1])
                        cylinder(d = plate_hole_dia, h = top_plate_z - fc_top_z + 2);
                }
    }
}

module motors() {
    for (sx = [-1, 1], sy = [-1, 1])
        translate([sx * motor_off, sy * motor_off, z_arm + arm_t]) {
            color("#9aa3ab") cylinder(d = motor_dia, h = motor_h);
            color("#3a3f47") translate([0, 0, motor_h]) cylinder(d = 6, h = 4);
        }
}

module props() {
    for (sx = [-1, 1], sy = [-1, 1])
        translate([sx * motor_off, sy * motor_off, z_arm + arm_t + motor_h + 4])
            color("#2f3339", 0.30) cylinder(d = prop_dia, h = 1.2);
}

// ESC sits directly on the bottom plate, FC above it
esc_z = z_stack;
fc_z  = esc_z + esc_pcb + esc_parts + gap + fc_bot_parts + explode;

module esc() {
    translate([0, 0, esc_z + explode * 0.4]) {
        // WITH its 30.5 mm mounting holes. They were missing, so the corner posts
        // had nowhere to pass and registered as interference.
        color("#2b3037") difference() {
            linear_extrude(esc_pcb)
                offset(r = 2) square([esc_l - 4, esc_w - 4], center = true);
            for (sx = [-1, 1], sy = [-1, 1])
                translate([sx * hole_pitch/2, sy * hole_pitch/2, -1])
                    cylinder(d = hole_dia, h = esc_pcb + 2);
        }
        color("#3d444d") translate([0, 0, esc_pcb]) difference() {
            linear_extrude(esc_parts)
                offset(r = 2) square([esc_l - 12, esc_w - 12], center = true);
            for (sx = [-1, 1], sy = [-1, 1])
                translate([sx * hole_pitch/2, sy * hole_pitch/2, -1])
                    cylinder(d = grommet_dia, h = esc_parts + 2);
        }
    }
}

module fc() {
    translate([0, 0, fc_z]) {
        // PCB
        color("#1e4a3c") difference() {
            linear_extrude(fc_pcb) offset(r = 2) square([fc_l - 4, fc_w - 4], center = true);
            for (sx = [-1, 1], sy = [-1, 1])
                translate([sx * hole_pitch/2, sy * hole_pitch/2, -1])
                    cylinder(d = hole_dia, h = fc_pcb + 2);
        }
        // Component envelope, top and bottom - a blob, not real parts. The blob spans
        // +/-15.55 mm and the mounting holes are at +/-15.25, so a solid blob swallows
        // them and the stack bolt reads as passing through components. It does not:
        // checked against the board, NOTHING comes within 2.7 mm of a hole centre, so
        // the standoff footprints are clear. The holes are cut here to match.
        color("#14332a") translate([0, 0, fc_pcb]) difference() {
            linear_extrude(fc_top_parts) offset(r = 1)
                square([fc_l - 14, fc_w - 14], center = true);
            for (sx = [-1, 1], sy = [-1, 1])
                translate([sx * hole_pitch/2, sy * hole_pitch/2, -1])
                    cylinder(d = grommet_dia, h = fc_top_parts + 2);
        }
        color("#14332a") translate([0, 0, -fc_bot_parts]) difference() {
            linear_extrude(fc_bot_parts) offset(r = 1)
                square([fc_l - 16, fc_w - 16], center = true);
            for (sx = [-1, 1], sy = [-1, 1])
                translate([sx * hole_pitch/2, sy * hole_pitch/2, -1])
                    cylinder(d = grommet_dia, h = fc_bot_parts + 2);
        }
        // USB-C, at the board edge  [M] 0.80 mm inboard
        color("#b8bcc2")
            translate([0, fc_w/2 - 4.2, fc_pcb]) cube([9, 8, 3.2], center = false);
    }
}

module stack_screws() {
    // FROM THE MID PLATE UP, not from z = 0. Drawn from the bottom plate, these ran
    // straight through the carbon arms: the four bolts sit at (+/-15.25, +/-15.25),
    // which is radius 21.57 mm on the 45 deg diagonal - exactly the arm centrelines.
    // check_cad_fit.py measured 214 mm^3 of bolt inside the frame.
    //
    // That is not how the frame goes together. The arms are clamped between the
    // bottom and mid plates by their own fasteners; the 30.5 mm stack pattern is on
    // the mid plate, and the stack bolts run from there upward.
    for (sx = [-1, 1], sy = [-1, 1])
        translate([sx * hole_pitch/2, sy * hole_pitch/2, z_mid_plate])
            color("#c0c5cb")
                cylinder(d = screw_dia, h = top_plate_z + plate_t - z_mid_plate);
}

module battery() {
    translate([0, 0, top_plate_z + plate_t + batt_h/2])
        color("#5a2f2f", 0.35) cube([batt_l, batt_w, batt_h], center = true);
}

// ---- flow camera module  [A] 12 mm deep, under the BOTTOM plate ------
// The analysis stands: props sit above a downward cone and cannot enter it,
// so the constraint is DEPTH - the lens must sit above the skid contact line
// so it is not crushed on landing. At the current 40 mm skid drop + 3.5 mm pad and a
// 12 mm module there is 31.5 mm of margin - check_cad_fit.py's GROUND_PARTS check
// measures it against the contact plane rather than this comment asserting it.
// (Read "25 mm skid drop ... 13 mm of margin" until 2026-09-05, three drops out of date.)

module camera() {
    // hangs UNDER THE BOTTOM PLATE, lens pointing straight down. It was drawn
    // under the FC, where it passed straight through the ESC - both centred, a
    // 6.5 mm interference - and it could not see the ground through the plate
    // anyway. Below the plate it looks at the ground past the ESC's edge.
    translate([0, 0, -cam_mod_t]) {
        color("#20242a") linear_extrude(cam_mod_t)
            offset(r = 1) square([cam_mod_w, cam_mod_w], center = true);
        // lens barrel poking out of the module bottom (3.5 mm, per design.CAMERA.lens_len)
        color("#0d0f11") translate([0, 0, -3.5]) cylinder(d = 8, h = 3.5);
    }
}

// ---- nose recording camera: XIAO ESP32S3 Sense ----------------------
// Sits on the nose, lens forward, recording to its own microSD. It needs 5 V and a
// ground from the payload pads and NOTHING else - no UART, no radio. See CAMERA_REC
// in tools/design.py for why its WiFi stays off in flight.
module rec_cam() {
    translate([0, -rec_cam_y, z_mid_plate + medium_plate_t]) {
        color("#23272e") linear_extrude(rec_cam_h)
            offset(r = 1) square([rec_cam_l - 2, rec_cam_w - 2], center = true);
        // lens barrel, pointing forward (-Y)
        color("#0d0f11") translate([0, -rec_cam_w/2, rec_cam_h/2])
            rotate([90, 0, 0]) cylinder(d = 8, h = 3);
    }
}

// ---- belly sensor: downward rangefinder / flow module -----------------
// Under the bottom plate, looking at the ground. The FC cannot do this job - U6 and U7
// face the ESC 3 mm away, and U6 is 15.5 mm off centre so the frame's 10 mm centre
// pass-through would not help even with the stack inverted. See design.BELLY_SENSOR.
module belly_sensor() {
    translate([0, 18, z_bot_plate - belly_h])
        color("#2a2f36") linear_extrude(belly_h)
            offset(r = 1) square([belly_l - 2, belly_w - 2], center = true);
}

module lidar360() {
    // LDROBOT LD06, mounted UPSIDE-DOWN under the bottom plate (PRX1_ORIENT 1). A top
    // mount is blocked by the battery and prop-height is blocked by the arms; the belly
    // is the only place it fits, and only once skid drop went 25 -> 40 mm (35 was
    // tried and rejected - see the SKID note in tools/design.py).
    //
    // The body is drawn to the datasheet's 38.59 x 38.59 x 33.30 mm. It must clear the
    // ground plane at z = -cam_drop - skid_t, or a landing crushes it - which is exactly
    // what check_cad_fit measures rather than this file asserting it.
    translate([0, lidar_y, z_bot_plate - lidar_h])
        color("#3b4048") linear_extrude(lidar_h)
            offset(r = 2) square([lidar_l - 4, lidar_w - 4], center = true);
}

module skid() {
    // one TPU skid leg: two plates at the MOTOR's 19x19 pattern, sandwiched
    // between motor and arm; drops cam_drop below the arm bottom. The contact
    // line is BELOW THE GROUND PLANE (z = -cam_drop - skid_t measured from the
    // arm underside): the model is drawn with the arms at z 0..arm_t, so the
    // skid pads reach down to negative z, which is what holds the aircraft up.
    // The first version placed the pads at POSITIVE z - the drone floated with
    // its skids at prop height.
    // The legs bolt to the MOTOR's 19x19 pattern, so they stand at the motor, not
    // at the origin. This module drew them at +/-9.5 mm from the centre with no
    // motor_off translation, which put all sixteen legs in a cluster under the
    // camera - the 601 mm^3 "camera vs landing gear" interference was that bug,
    // not a real clash.
    contact_z = -cam_drop - skid_t;
    // TO THE ARM UNDERSIDE, not the arm top. This module's own comment says the skid
    // "drops cam_drop below the arm bottom", but leg_len included arm_t and ran the
    // legs up to z_arm + arm_t - and two of the four bolt positions sit exactly on an
    // arm centreline (the 19x19 pattern is axis-aligned, the arms radiate at 45 deg,
    // so (+9.5, +9.5) is on the diagonal). The legs therefore passed through 300 mm^3
    // of carbon. The skid plate is sandwiched at the motor; the legs come down past
    // the arm's sides.
    leg_len   = z_arm + cam_drop + skid_t;    // contact line -> arm UNDERSIDE
    for (sx = [-1, 1], sy = [-1, 1])
        translate([sx * skid_hole_pitch/2, sy * skid_hole_pitch/2, contact_z])
            color("#c8c8c8") cylinder(d = 4, h = leg_len);
}

module skids() {
    for (sx = [-1, 1], sy = [-1, 1])
        translate([sx * motor_off, sy * motor_off, 0]) skid();
}

// ---- Radxa Zero 3W companion  [D] 65 x 30 ---------------------------
// Radxa publishes 65 x 30 mm and NOTHING about the mounting holes. Resellers
// claim "same holes as the Pi Zero 2 W", but the one figure any of them gives -
// 61 mm diagonal - does not match the Pi Zero's hypot(58,23) = 62.4 mm, so the
// claim is unconfirmed and the posts are NOT drawn. Measure the board.
//
// Envelope only, deliberately: an invented hole pattern is how a tray gets cut
// wrong. See PI and PI_REJECTED in tools/design.py.
pi_hole_dia  = 2.75;            // [U] diameter assumed; pattern UNPUBLISHED
pi_y_off = 25;

module pi() {
    // Pi on the top plate, long axis along X.
    translate([0, pi_y_off, top_plate_z + plate_t]) {
        color("#1a7a4a") linear_extrude(pi_t)
            offset(r = 1) square([pi_l, pi_w], center = true);
        // NO mounting posts: Radxa does not publish the hole pattern.
    }
}

// ---------------------------- assembly -------------------------------
if (show_frame) { frame(); motors(); }
if (show_props) props();
esc();
fc();
stack_screws();
if (show_rec_cam) rec_cam();
belly_sensor();
lidar360();
if (show_battery && show_frame) battery();
if (show_camera) camera();
if (show_skids) skids();
if (show_pi) pi();

// ---- printed sanity check -------------------------------------------
echo(str("stack height mm = ",
         esc_pcb + esc_parts + gap + fc_bot_parts + fc_pcb + fc_top_parts));
echo(str("mid plate ", fc_plate_w, " x ", fc_plate_l,
         " mm carries the board ", fc_l, " x ", fc_w));
echo(str("prop-to-prop gap mm = ", motor_off * 2 - prop_dia));
echo(str("standoff to buy mm = ", standoff_len, " (kit ships 30 - it does NOT fit)"));
echo(str("clearance above FC to top plate mm = ",
         top_plate_z - (fc_z + fc_pcb + fc_top_parts)));
// lens margin: camera module bottom (lens tip) must stay ABOVE the skid
// contact line, or it is crushed on landing. The camera hangs under the
// BOTTOM plate (lens tip at -cam_mod_t-3.5), the skid contact line is at
// -(cam_drop+skid_t): margin = cam_drop + skid_t - cam_mod_t - 3.5.
echo(str("camera lens above skid contact line mm = ",
         cam_drop + skid_t - cam_mod_t - 3.5));
