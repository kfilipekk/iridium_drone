#include "soop_ant.h"

void soop_ant_default_cfg(soop_ant_cfg_t *cfg)
{
    cfg->open_ma = 3.0f;
    cfg->short_ma = 28.0f;
    cfg->settle_s = 0.5f;
    cfg->retry_after_s = 5.0f;
    cfg->retry_off_s = 10.0f;
    cfg->feed_enabled = 1;
}

void soop_ant_init(soop_ant_t *a, const soop_ant_cfg_t *cfg, double t)
{
    a->cfg = *cfg;
    a->state = cfg->feed_enabled ? SOOP_ANT_OPEN : SOOP_ANT_OFF;
    a->candidate = a->state;
    a->cand_since = t;
    a->short_since = -1.0;
    a->off_until = 0.0;
    a->en = cfg->feed_enabled ? 1 : 0;
    a->retries = 0;
}

static int classify(const soop_ant_cfg_t *c, float ma, int fault)
{
    if (fault || ma >= c->short_ma) {
        return SOOP_ANT_SHORT;
    }
    return ma < c->open_ma ? SOOP_ANT_OPEN : SOOP_ANT_OK;
}

int soop_ant_step(soop_ant_t *a, double t, float ma, int fault)
{
    if (!a->cfg.feed_enabled) {
        a->state = SOOP_ANT_OFF;
        a->en = 0;
        return 0;
    }
    if (!a->en) {
        //resting after a short: the readings mean nothing with the feed off
        if (t < a->off_until) {
            return 0;
        }
        a->en = 1;
        a->candidate = a->state;
        a->cand_since = t;
        a->short_since = -1.0;
        return 1;
    }
    int raw = classify(&a->cfg, ma, fault);
    if (raw != a->candidate) {
        a->candidate = raw;
        a->cand_since = t;
    }
    if (t - a->cand_since >= a->cfg.settle_s) {
        a->state = a->candidate;
    }
    if (a->state == SOOP_ANT_SHORT) {
        if (a->short_since < 0.0) {
            a->short_since = t;
        }
        if (t - a->short_since >= a->cfg.retry_after_s) {
            a->en = 0;
            a->off_until = t + a->cfg.retry_off_s;
            a->retries++;
        }
    } else {
        a->short_since = -1.0;
    }
    return a->en;
}

float soop_ant_ma(float volts, float sense_ohm, float gain)
{
    return volts / (sense_ohm * gain) * 1000.0f;
}

const char *soop_ant_name(int state)
{
    switch (state) {
    case SOOP_ANT_OFF:   return "off";
    case SOOP_ANT_OPEN:  return "open";
    case SOOP_ANT_OK:    return "ok";
    case SOOP_ANT_SHORT: return "short";
    }
    return "?";
}
