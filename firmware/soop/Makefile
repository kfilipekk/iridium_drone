#build the on-board Doppler solver and SGP4 propagator
#make arm - cross-compile solver + SGP4 for the STM32H743 (Cortex-M7, hard float)
#make clean
CC      ?= cc
ARMGCC  ?= arm-none-eabi-gcc
CFLAGS  ?= -O2 -std=c99 -Wall -Wextra -pedantic -Wno-unused-variable

HOST         = soop_host
SGP4_TEST    = sgp4_host_test
SOOP_OBJ     = soop_solve.o
SGP4_OBJ     = sgp4.o

.PHONY: all host arm clean
all: host

host: $(HOST) $(SGP4_TEST)

$(HOST): main_host.c soop_solve.c soop_solve.h sgp4.c sgp4.h
	$(CC) $(CFLAGS) -o $@ main_host.c soop_solve.c sgp4.c -lm

$(SGP4_TEST): sgp4_host_test.c sgp4.c sgp4.h
	$(CC) $(CFLAGS) -o $@ sgp4_host_test.c sgp4.c -lm

#STM32H743: Cortex-M7, double-precision FPU (fpv5-d16), hard float ABI
arm: soop_solve.c soop_solve.h sgp4.c sgp4.h
	$(ARMGCC) -c $(CFLAGS) -mcpu=cortex-m7 -mthumb -mfpu=fpv5-d16 -mfloat-abi=hard \
		-o $(SOOP_OBJ) soop_solve.c
	$(ARMGCC) -c $(CFLAGS) -mcpu=cortex-m7 -mthumb -mfpu=fpv5-d16 -mfloat-abi=hard \
		-o $(SGP4_OBJ) sgp4.c

clean:
	rm -f $(HOST) $(SGP4_TEST) $(SOOP_OBJ) $(SGP4_OBJ)
