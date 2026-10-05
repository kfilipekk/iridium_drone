#include "AP_SoOP_Capture.h"
#include "soop_signal.h"

static_assert(SOOP_CAPTURE_RAW_HZ <= 1000000U, "INP18 is a slow channel: 1 MSPS at most");
static_assert((SOOP_CAPTURE_OVS & (SOOP_CAPTURE_OVS - 1U)) == 0U, "the oversampler shifts by log2(OVS)");
static_assert(SOOP_CAPTURE_RAW_HZ / SOOP_CAPTURE_OVS == (unsigned)SOOP_FS, "the DSP is built for SOOP_FS");

extern const AP_HAL::HAL& hal;

//only a ChibiOS board whose hwdef asks for it
#if CONFIG_HAL_BOARD == HAL_BOARD_CHIBIOS && defined(HAL_SOOP_CAPTURE_ENABLED)
#include <hal.h>
#if defined(STM32_ADC_DUAL_MODE) && STM32_ADC_DUAL_MODE
#define AP_SOOP_CAPTURE 1
#endif
#endif

#ifdef AP_SOOP_CAPTURE

//TIM6 update is ADC external trigger 13 on the H7 (RM0433, ADC external triggers table)
#define EXTSEL_TIM6_TRGO 13U

static adcsample_t *buf;                    //2 x SOOP_CAPTURE_BLOCK 32-bit words, DMA-safe
static volatile uint32_t halves_done;       //half-buffers completed since start
static volatile uint64_t first_half_us;
static volatile uint32_t adc_errors;
static binary_semaphore_t ready;
static ADCConversionGroup grp;

static void end_cb(ADCDriver *adcp)
{
    (void)adcp;
    if (halves_done == 0) {
        first_half_us = AP_HAL::micros64();
    }
    halves_done++;
    chSysLockFromISR();
    chBSemSignalI(&ready);
    chSysUnlockFromISR();
}

static void error_cb(ADCDriver *adcp, adcerror_t err)
{
    (void)adcp;
    (void)err;
    adc_errors++;                           //overrun: the ADC outran the DMA
}

bool AP_SoOP_Capture::supported()
{
    return true;
}

bool AP_SoOP_Capture::start(bool swap_iq)
{
    _swap = swap_iq;
    buf = (adcsample_t *)hal.util->malloc_type(2 * SOOP_CAPTURE_BLOCK * sizeof(uint32_t),
                                               AP_HAL::Util::MEM_DMA_SAFE);
    if (buf == nullptr) {
        return false;
    }
    chBSemObjectInit(&ready, true);
    //PC4 is analogue by the hwdef (it is declared on ADC1)
    palSetLineMode(PAL_LINE(GPIOA, 4U), PAL_MODE_INPUT_ANALOG);

    memset(&grp, 0, sizeof(grp));
    grp.circular = true;
    grp.num_channels = 2;                   //one master (I) + one slave (Q)
    grp.end_cb = end_cb;
    grp.error_cb = error_cb;
    grp.cfgr = ADC_CFGR_EXTEN_RISING | ADC_CFGR_EXTSEL_SRC(EXTSEL_TIM6_TRGO) | ADC_CFGR_RES_16BITS;
    //average SOOP_CAPTURE_OVS triggered conversions (TROVS)
    grp.cfgr2 = ADC_CFGR2_ROVSE | ADC_CFGR2_TROVS
              | ((SOOP_CAPTURE_OVS - 1U) << ADC_CFGR2_OVSR_Pos)
              | (uint32_t(__builtin_ctz(SOOP_CAPTURE_OVS)) << ADC_CFGR2_OVSS_Pos);
    grp.ccr = ADC_CCR_DUAL_REG_SIMULT;
    grp.pcsel = (1U << 4) | (1U << 18);
    grp.smpr[0] = ADC_SMPR1_SMP_AN4(ADC_SMPR_SMP_2P5);
    grp.sqr[0] = ADC_SQR1_SQ1_N(ADC_CHANNEL_IN4);            //ADC1: PC4, I
    grp.ssmpr[1] = ADC_SMPR2_SMP_AN18(ADC_SMPR_SMP_2P5);
    grp.ssqr[0] = ADC_SQR1_SQ1_N(ADC_CHANNEL_IN18);          //ADC2: PA4, Q

    adcStart(&ADCD1, nullptr);
    halves_done = 0;
    _next_block = 0;
    _overruns = 0;
    adcStartConversion(&ADCD1, &grp, buf, 2 * SOOP_CAPTURE_BLOCK);

    //TIM6 counts the timer clock down to the raw rate
    rccEnableTIM6(true);
    rccResetTIM6();
    TIM6->PSC = 0;
    TIM6->ARR = (STM32_TIMCLK1 / SOOP_CAPTURE_RAW_HZ) - 1U;
    TIM6->CR2 = TIM_CR2_MMS_1;              //MMS = 010: update -> TRGO
    TIM6->EGR = TIM_EGR_UG;
    TIM6->CR1 = TIM_CR1_CEN;

    //the first half-buffer dates sample 0
    for (uint8_t i = 0; i < 50 && halves_done == 0; i++) {
        hal.scheduler->delay(2);
    }
    if (halves_done == 0) {
        stop();
        return false;
    }
    const double fs = double(STM32_TIMCLK1) / (TIM6->ARR + 1U) / SOOP_CAPTURE_OVS;
    _start_us = first_half_us - uint64_t(SOOP_CAPTURE_BLOCK * double(1000000) / fs);
    return true;
}

void AP_SoOP_Capture::stop()
{
    TIM6->CR1 = 0;
    adcStopConversion(&ADCD1);
}

bool AP_SoOP_Capture::next_block(int16_t *iq, uint64_t &first_sample, uint32_t timeout_ms)
{
    if (halves_done <= _next_block
        && chBSemWaitTimeout(&ready, TIME_MS2I(timeout_ms)) != MSG_OK) {
        return false;
    }
    const uint32_t done = halves_done;
    if (done <= _next_block) {
        return false;
    }
    if (done - _next_block > 1) {           //fell behind: skip to the newest half
        _overruns += done - _next_block - 1;
        _next_block = done - 1;
    }
    const uint32_t *w = (const uint32_t *)buf + (_next_block % 2) * SOOP_CAPTURE_BLOCK;
    for (uint32_t i = 0; i < SOOP_CAPTURE_BLOCK; i++) {
        //dual mode packs the master (ADC1, I) low and the slave (ADC2, Q) high
        const int16_t a = int16_t(int32_t(w[i] & 0xFFFF) - 32768);
        const int16_t b = int16_t(int32_t(w[i] >> 16) - 32768);
        iq[2 * i] = _swap ? b : a;
        iq[2 * i + 1] = _swap ? a : b;
    }
    first_sample = uint64_t(_next_block) * SOOP_CAPTURE_BLOCK;
    _next_block++;
    return true;
}

#else

bool AP_SoOP_Capture::supported() { return false; }
bool AP_SoOP_Capture::start(bool) { return false; }
void AP_SoOP_Capture::stop() {}
bool AP_SoOP_Capture::next_block(int16_t *, uint64_t &, uint32_t) { return false; }

#endif
