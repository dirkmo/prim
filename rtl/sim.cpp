#include <verilated_vcd_c.h>
#include "verilated.h"
#include "Vprim.h"
#include "Vprim_Prim.h"
#include <string>

using namespace std;

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
    pCore->i_clk = 0;
    pCore->eval();
    pCore->i_clk = 1;
    pCore->eval();
    tickcount += clockcycle_ps;
    if(pTrace) pTrace->dump(static_cast<vluint64_t>(tickcount));
    pCore->i_clk = 0;
    pCore->eval();
}

void reset() {
    pCore->i_reset = 1;
    pCore->i_dat = 0;
    pCore->i_ack = 0;
    pCore->i_clk = 0;
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
            if (pCore->o_we) {
                if (pCore->o_bs & 1) {
                    mem[pCore->o_addr] = pCore->o_dat;
                }
                if (pCore->o_bs & 2) {
                    mem[(pCore->o_addr+1) & 0xffff] = pCore->o_dat >> 8;
                }
            }
        } else {
        }
    }
    pCore->i_ack = pCore->o_bs != 0;
    return 0;
}

int program_load(const char *fn, uint16_t offset) {
    // for (int i = 0; i < 0x10000; mem[i++] = OP_SIM_END);
    memset(mem, 0xff, sizeof(mem));
    FILE *f = fopen(fn, "rb");
    if (!f) {
        fprintf(stderr, "Failed to open file\n");
        return -1;
    }
    fseek(f, 0, SEEK_END);
    size_t size = ftell(f);
    fseek(f, 0, SEEK_SET);
    fread(&mem[offset], sizeof(uint8_t), size, f);
    fclose(f);
    return 0;
}

string getbasename(string asm_fn) {
    int pos = asm_fn.rfind(".");
    return asm_fn.substr(0, pos);
}

int parse_cmdline(int argc, char *argv[]) {
    int c;
    bool loaded = false;
    while ((c = getopt(argc, argv, "i:")) != -1) {
        switch (c) {
            case 'i': {
                printf("Load image '%s'\n", optarg);
                if (program_load(optarg, 0)) {
                    fprintf(stderr, "ERROR: Failed to load file '%s'\n", optarg);
                    return -1;
                }
                loaded = true;
                break;
            }
            default: ;
        }
    }
    return !loaded;
}


static void dump_state(const char *prefix) {
    printf("%s pc=%04x dsp=%u rsp=%u T=%04x N=%04x R=%04x ir=%02x\n",
           prefix,
           static_cast<unsigned>(pCore->Prim->r_pc),
           static_cast<unsigned>(pCore->Prim->r_dsp),
           static_cast<unsigned>(pCore->Prim->r_rsp),
           static_cast<unsigned>(pCore->Prim->T),
           static_cast<unsigned>(pCore->Prim->N),
           static_cast<unsigned>(pCore->Prim->R),
           static_cast<unsigned>(pCore->Prim->r_ir));
}

int main(int argc, char *argv[]) {
    printf("prim simulator\n\n");

    if (parse_cmdline(argc, argv)) {
        fprintf(stderr, "%s <-i image>\n", argv[0]);
        fprintf(stderr, "  -i <image>      path to binary image\n");
        return -1;
    }

    Verilated::traceEverOn(true);
    pCore = new Vprim();

    opentrace("trace.vcd");

    reset();

    while(tickcount < 1000 * clockcycle_ps) {
        handle(pCore);
        tick();
        if (pCore->Prim->r_ir == 0x22 && pCore->Prim->r_phase == 0) {
            dump_state("state:");
            printf("Simulation halted on BREAK\n");
            goto finish;
        }
        if(Verilated::gotFinish()) {
            printf("Simulation finished\n");
            goto finish;
        }
    }

    dump_state("state:");
    printf("Simulation timeout\n");

finish:
    pCore->final();

    if (pTrace) {
        pTrace->close();
        delete pTrace;
    }
    return 0;

}
