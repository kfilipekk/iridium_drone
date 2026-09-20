#build the on-board Doppler solver
#make arm - cross-compile the solver for the STM32H743 (Cortex-M7, hard float)
#make clean
CC      ?= cc
ARMGCC  ?= arm-none-eabi-gcc
CFLAGS  ?= -O2 -std=c99 -Wall -Wextra -pedantic

HOST  = soop_host
OBJ   = soop_solve.o

.PHONY: all host arm clean
all: host

host: $(HOST)

$(HOST): main_host.c soop_solve.c soop_solve.h
	$(CC) $(CFLAGS) -o $@ main_host.c soop_solve.c -lm

#STM32H743: Cortex-M7, single/double-precision FPU (fpv5-d16)
arm: soop_solve.c soop_solve.h
	$(ARMGCC) -c $(CFLAGS) -mcpu=cortex-m7 -mthumb -mfpu=fpv5-d16 -mfloat-abi=hard \
		-o $(OBJ) soop_solve.c

clean:
	rm -f $(HOST) $(OBJ)
