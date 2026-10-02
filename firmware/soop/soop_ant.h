//soop_ant - is the active antenna on the end of the coax
#ifndef SOOP_ANT_H
#define SOOP_ANT_H

#ifdef __cplusplus
extern "C" {
#endif

enum { SOOP_ANT_OFF = 0, SOOP_ANT_OPEN = 1, SOOP_ANT_OK = 2, SOOP_ANT_SHORT = 3 };

typedef struct {
    float open_ma;          //below this the feed is open
    float short_ma;         //at or above this it is shorted
    float settle_s;         //how long a reading must hold to change the state
    float retry_after_s;    //a short this long turns the feed off
    float retry_off_s;      //... for this long, then on again
    int   feed_enabled;     //0: never power the antenna
} soop_ant_cfg_t;

typedef struct {
    soop_ant_cfg_t cfg;
    int    state;           //SOOP_ANT_
    int    candidate;
    double cand_since;
    double short_since;
    double off_until;
    int    en;              //what the enable pin should be
    unsigned retries;
} soop_ant_t;

//defaults for this board: 2.2 ohm x 50 puts 15 mA at 1.65 V
void soop_ant_default_cfg(soop_ant_cfg_t *cfg);
void soop_ant_init(soop_ant_t *a, const soop_ant_cfg_t *cfg, double t);

//one step at board time t (s)
int soop_ant_step(soop_ant_t *a, double t, float ma, int fault);

//feed current from the INA180's output voltage
float soop_ant_ma(float volts, float sense_ohm, float gain);

const char *soop_ant_name(int state);

#ifdef __cplusplus
}
#endif

#endif
