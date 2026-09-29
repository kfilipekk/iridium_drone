#include "AP_SoOP_MAX2112.h"

#include <math.h>

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

    //n.F with R = 1: f_LO = F_REF * (N + F / 2^20)
    const double ratio = lo_hz / F_REF;
    const uint32_t N = uint32_t(ratio);
    const uint32_t F = uint32_t(lround((ratio - N) * 1048576.0)) & 0xFFFFF;
    if (N < 19 || N > 251) {
        return false;
    }
    _lo = F_REF * (N + F / 1048576.0);

    const uint8_t regs[12] = {
        uint8_t(0x80 | ((N >> 8) & 0x7F)),  //0x00 FRAC = 1, N[14:8]
        uint8_t(N & 0xFF),                  //0x01 N[7:0]
        uint8_t(0x10 | ((F >> 16) & 0x0F)), //0x02 CPMP = 00, CPLIN = 01, F[19:16]
        uint8_t((F >> 8) & 0xFF),           //0x03 F[15:8]
        uint8_t(F & 0xFF),                  //0x04 F[7:0] - loading it starts VCO autoselect
        0x01,                               //0x05 XD = /1, R = 1
        0x00,                               //0x06 D24 = 0 (LO >= 1125 MHz), CPS = 0, ICP = 0: 600 uA
        uint8_t((0x19 << 3) | 0x04),        //0x07 VCO start 11001, VAS = 1, ADL = 0, ADE = 0
        12,                                 //0x08 LPF: 4 MHz + (12 - 12) x 290 kHz, the minimum
        uint8_t(bbg & 0x0F),                //0x09 STBY = 0, PWDN = 0, baseband gain
        0x00,                               //0x0A everything powered
        0x08,                               //0x0B CPTST = 000, TURBO = 1, LDMUX = 000
    };
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
    const bool vas_done = (s1 & 0x20) && (s1 & 0x40);   //VASE and VASA
    const bool ld = s1 & 0x10;
    _vco = s2 >> 3;
    _adc = s2 & 0x07;
    //ADC[2:0] (Table 17): 000 and 111 are out of lock
    _locked = vas_done && ld && _adc != 0 && _adc != 7;
    return _locked;
}
