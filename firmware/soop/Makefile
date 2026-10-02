#build the on-board Iridium chain: burst DSP, SGP4 + ephemeris
#make arm - cross-compile every flight source for the STM32H743 (Cortex-M7, hard float)
#make clean
CC      ?= cc
ARMGCC  ?= arm-none-eabi-gcc
CFLAGS  ?= -O2 -std=c99 -Wall -Wextra -pedantic -Wno-unused-variable

HOST         = soop_host
SGP4_TEST    = sgp4_host_test
NAV_HOST     = nav_host
DSP_HOST     = dsp_host
IMPORT       = iq_import
ANT_HOST     = ant_host
ARM_SRC      = soop_solve.c sgp4.c soop_ephem.c soop_nav.c soop_guard.c soop_dsp.c soop_ant.c
ARMFLAGS     = -mcpu=cortex-m7 -mthumb -mfpu=fpv5-d16 -mfloat-abi=hard

.PHONY: all host arm clean
all: host

host: $(HOST) $(SGP4_TEST) $(NAV_HOST) $(DSP_HOST) $(IMPORT) $(ANT_HOST)

$(HOST): main_host.c soop_solve.c soop_solve.h sgp4.c sgp4.h
	$(CC) $(CFLAGS) -o $@ main_host.c soop_solve.c sgp4.c -lm

$(SGP4_TEST): sgp4_host_test.c sgp4.c sgp4.h
	$(CC) $(CFLAGS) -o $@ sgp4_host_test.c sgp4.c -lm

$(NAV_HOST): nav_host.c soop_nav.c soop_nav.h soop_ephem.c soop_ephem.h soop_guard.c soop_guard.h sgp4.c sgp4.h soop_signal.h
	$(CC) $(CFLAGS) -o $@ nav_host.c soop_nav.c soop_ephem.c soop_guard.c sgp4.c -lm

$(DSP_HOST): dsp_host.c soop_dsp.c soop_dsp.h soop_signal.h
	$(CC) $(CFLAGS) -o $@ dsp_host.c soop_dsp.c -lm

$(ANT_HOST): ant_host.c soop_ant.c soop_ant.h
	$(CC) $(CFLAGS) -o $@ ant_host.c soop_ant.c

$(IMPORT): iq_import.c soop_signal.h
	$(CC) $(CFLAGS) -o $@ iq_import.c -lm

#STM32H743: Cortex-M7, double-precision FPU (fpv5-d16), hard float ABI
arm: $(ARM_SRC)
	for f in $(ARM_SRC); do \
		$(ARMGCC) -c $(CFLAGS) $(ARMFLAGS) -o $${f%.c}.o $$f || exit 1; \
	done

clean:
	rm -f $(HOST) $(SGP4_TEST) $(NAV_HOST) $(DSP_HOST) $(IMPORT) $(ANT_HOST) *.o
