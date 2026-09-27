#ifndef SOOP_SIGNAL_H
#define SOOP_SIGNAL_H

#define SOOP_SYMBOL_RATE     25000.0      //symbols/s
#define SOOP_CH_SPACING      41666.667    //Hz between simplex channels
#define SOOP_F_RING_ALERT    1626270833.0 //Hz, Ring Alert (IRA)
#define SOOP_N_SIMPLEX       5            //four messaging channels below Ring Alert
#define SOOP_PREAMBLE_SYMS   64           //downlink carrier preamble
#define SOOP_MAX_BURST_S     0.02032      //the simplex slot

#define SOOP_FS              500000.0     //complex samples/s from the ADC pair
#define SOOP_LO_OFFSET_HZ    62500.0      //LO above Ring Alert; exactly FS/8

#endif //SOOP_SIGNAL_H
