#include <verilated_vcd_c.h>
#include "verilated.h"
#include "Vprim.h"

VerilatedVcdC *pTrace = NULL;
Vprim *pCore;

uint64_t tickcount = 0;
uint64_t clockcycle_ps = 10000; // clock cycle length in ps

uint8_t mem[0x10000];

void opentrace(const char *vcdname) {
    if (!pTrace) {
        pTrace = new VerilatedVcdC;
        pCore->trace(pTrace, 99);
        pTrace->open(vcdname);
    }
}

void tick() {
    pCore->i_clk = !pCore->i_clk;
    tickcount += clockcycle_ps / 2;
    pCore->eval();
    if(pTrace) pTrace->dump(static_cast<vluint64_t>(tickcount));
}

void reset() {
    pCore->i_reset = 1;
    pCore->i_dat = 0;
    pCore->i_ack = 0;
    pCore->i_clk = 1;
    tick();
    tick();
    pCore->i_reset = 0;
}

int handle(Vprim *pCore) {
    if (pCore->o_bs) {
        if (pCore->o_addr < 0xfffe) {
            // memory
            pCore->i_dat = 0;
            if (pCore->o_bs & 1) {
                pCore->i_dat |= mem[pCore->o_addr];
            }
            if (pCore->o_bs & 2) {
                pCore->i_dat |= mem[(pCore->o_addr+1) & 0xffff] << 8;
            }
            if (pCore->o_we && pCore->i_clk) {
                if (pCore->o_bs & 1) {
                    mem[pCore->o_addr] = pCore->o_dat;
                }
                if (pCore->o_bs & 2) {
                    mem[(pCore->o_addr+1) & 0xffff] = pCore->o_dat;
                }
            }
        } else {
        }
    }
    pCore->i_ack = (pCore->o_bs != 0);
    return 0;
}


int main(int argc, char *argv[]) {
    printf("prim simulator\n\n");

    Verilated::traceEverOn(true);
    pCore = new Vprim();

    opentrace("trace.vcd");

    reset();

    while(tickcount < 20 * clockcycle_ps) {
        handle(pCore);
        tick();
        if(Verilated::gotFinish()) {
            printf("Simulation finished\n");
            goto finish;
        }
    }

finish:
    pCore->final();

    if (pTrace) {
        pTrace->close();
        delete pTrace;
    }
    return 0;

}
