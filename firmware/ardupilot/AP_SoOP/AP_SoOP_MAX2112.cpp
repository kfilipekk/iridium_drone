#include "AP_SoOP_MAX2112.h"

extern const AP_HAL::HAL& hal;

bool AP_SoOP_MAX2112::write_regs(uint8_t first, const uint8_t *v, uint8_t n)
{
    uint8_t buf[16];
    if (n + 1 > sizeof(buf)) {
        return false;
    }
    buf[0] = first;                         //the register address auto-increments
    memcpy(&buf[1], v, n);
    return _dev->transfer(buf, n + 1, nullptr, 0);
}

bool AP_SoOP_MAX2112::read_status(uint8_t &s1, uint8_t &s2)
{
    uint8_t reg = 0x0C, out[2];
    if (!_dev->transfer(&reg, 1, out, 2)) {
        return false;
    }
    s1 = out[0];
    s2 = out[1];
    return true;
}

bool AP_SoOP_MAX2112::init(uint8_t bus, double lo_hz, uint8_t bbg)
{
    _dev = hal.i2c_mgr->get_device(bus, ADDR);
    if (!_dev) {
        return false;
    }

    uint8_t regs[SOOP_MAX2112_NREGS];
    if (soop_max2112_regs(lo_hz, F_REF, bbg, regs, &_lo) != 0) {
        return false;
    }
    hal.scheduler->delay(1);                //registers only after 100 us from power-up
    {
        //the baro shares I2C2: hold the bus for the writes
        WITH_SEMAPHORE(_dev->get_semaphore());
        _dev->set_retries(3);
        if (!write_regs(0x00, regs, sizeof(regs))) {
            return false;
        }
        //"the F-divider LSB word must also be loaded last to initiate the VCO autoselect"
        if (!write_regs(0x04, &regs[4], 1)) {
            return false;
        }
    }
    for (uint8_t i = 0; i < 20; i++) {       //autoselect takes a few ms
        hal.scheduler->delay(5);
        if (check_lock()) {
            return true;
        }
    }
    return false;
}

bool AP_SoOP_MAX2112::check_lock()
{
    if (!_dev) {
        return false;
    }
    uint8_t s1, s2;
    bool ok;
    {
        WITH_SEMAPHORE(_dev->get_semaphore());
        ok = read_status(s1, s2);
    }
    if (!ok) {
        _locked = false;
        return false;
    }
    _locked = soop_max2112_locked(s1, s2, &_vco, &_adc);
    return _locked;
}
