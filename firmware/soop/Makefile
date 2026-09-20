# Build the on-board Doppler solver.
#
#   make host   - host binary for cross-checking against the Python solver
#   make arm    - cross-compile the solver for the STM32H743 (Cortex-M7, hard float)
#   make clean
#
# `make arm` proves the solver COMPILES and LINKS as a freestanding object for the target
# (no heap, no libc beyond libm). It is not the flight build: wiring it to I/Q capture,
# the SGP4 ephemeris and the EKF route is what remains. See docs/KNOWN-ISSUES.md.
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

# STM32H743: Cortex-M7, single/double-precision FPU (fpv5-d16), hard float ABI.
arm: soop_solve.c soop_solve.h
	$(ARMGCC) -c $(CFLAGS) -mcpu=cortex-m7 -mthumb -mfpu=fpv5-d16 -mfloat-abi=hard \
		-o $(OBJ) soop_solve.c

clean:
	rm -f $(HOST) $(OBJ)
