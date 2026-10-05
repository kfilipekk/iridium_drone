//AP_SoOP_MAX2112
#pragma once

#include <AP_HAL/AP_HAL.h>
#include <AP_HAL/I2CDevice.h>

#include "soop_max2112.h"

class AP_SoOP_MAX2112
{
public:
    //bus is the ArduPilot I2C bus index (I2C_ORDER I2C2 I2C1 makes I2C2 bus 0)
    bool init(uint8_t bus, double lo_hz, uint8_t bbg);

    //re-read the lock detector and the VTUNE ADC
    bool check_lock();

    double lo_hz() const { return _lo; }
    uint8_t vco() const { return _vco; }
    uint8_t vtune_adc() const { return _adc; }
    bool locked() const { return _locked; }

    static const uint8_t ADDR = 0x60;
    static constexpr double F_REF = 25.0e6;            //Y2

private:
    bool write_regs(uint8_t first, const uint8_t *v, uint8_t n);
    bool read_status(uint8_t &s1, uint8_t &s2);

    AP_HAL::OwnPtr<AP_HAL::I2CDevice> _dev;
    double  _lo;
    uint8_t _vco, _adc;
    bool    _locked;
};
