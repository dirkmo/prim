#include <verilated_vcd_c.h>
#include "verilated.h"
#include "Vprim.h"
#include "Vprim_Prim.h"
#include <string>
#include <vector>
#include <utility>
#include <cstdlib>
#include <random>

using namespace std;

VerilatedVcdC *pTrace = NULL;
Vprim *pCore;

uint64_t tickcount = 0;
uint64_t clockcycle_ps = 10000; // clock cycle length in ps

uint8_t mem[0x10000];
FILE *json_trace = nullptr;
uint64_t max_cycles = 1000;
vector<pair<unsigned, unsigned>> writes, reads;
unsigned wait_cycles = 0;
bool random_waits = false;
std::mt19937 wait_rng(0);

static vector<unsigned> cpu_state() {
    auto *cpu = pCore->Prim;
    vector<unsigned> state = {cpu->r_pc, cpu->r_dsp, cpu->r_rsp,
        cpu->r_carry, cpu->T, cpu->N, cpu->r_ir, cpu->r_phase};
    for (unsigned i = 0; i < 16; ++i) {
        state.push_back(cpu->r_dstack[i]);
        state.push_back(cpu->r_rstack[i]);
    }
    return state;
}

// Architectural snapshots at retirement, independent of fetch/memory latency.
static void trace_step(unsigned pc, unsigned ir) {
    if (!json_trace) return;
    auto *cpu = pCore->Prim;
    fprintf(json_trace,
        "{\"kind\":\"step\",\"at\":%u,\"ir\":%u,\"pc\":%u,\"dsp\":%u,\"rsp\":%u,\"carry\":%u,\"ds\":[",
        pc, ir, cpu->r_pc, cpu->r_dsp, cpu->r_rsp, cpu->r_carry);
    // Default DSS/RSS=4. T and N cache the first two data stack cells.
    for (unsigned i = 0; i < 16; ++i) {
        unsigned value = i == 0 ? cpu->T : i == 1 ? cpu->N :
            cpu->r_dstack[(cpu->r_dsp + 16 - i) & 15];
        fprintf(json_trace, "%s%u", i ? "," : "", value);
    }
    fprintf(json_trace, "],\"rs\":[");
    for (unsigned i = 0; i < 16; ++i)
        fprintf(json_trace, "%s%u", i ? "," : "", cpu->r_rstack[(cpu->r_rsp + 16 - i) & 15]);
    fprintf(json_trace, "],\"reads\":[");
    for (size_t i = 0; i < reads.size(); ++i)
        fprintf(json_trace, "%s[%u,%u]", i ? "," : "", reads[i].first, reads[i].second);
    fprintf(json_trace, "],\"writes\":[");
    for (size_t i = 0; i < writes.size(); ++i)
        fprintf(json_trace, "%s[%u,%u]", i ? "," : "", writes[i].first, writes[i].second);
    fprintf(json_trace, "]}\n");
    writes.clear();
    reads.clear();
}

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
    pCore->i_halt = 0;
    pCore->i_run = 0;
    pCore->i_step = 0;
    pCore->i_debug_reset = 0;
    pCore->i_reset = 1;
    pCore->i_dat = 0;
    pCore->i_ack = 0;
    pCore->i_clk = 0;
    tick();
    tick();
    pCore->i_reset = 0;
}

// A transfer completes on each rising edge with BS != 0 and ACK == 1.
// The next transfer may begin immediately, without a low-CS gap.
int handle(Vprim *core) {
    static bool pending = false;
    static unsigned address, data, bs, we, remaining;
    static vector<unsigned> held_state;
    core->i_ack = 0;
    core->i_dat = 0xdead; // Invalid until ACK; unused read lanes are also poisoned.
    if (pending && (address != core->o_addr || bs != core->o_bs ||
                    we != core->o_we || data != core->o_dat || held_state != cpu_state())) {
        fprintf(stderr, "Memory protocol error: request or CPU state changed before ACK\n");
        return 2;
    }
    if (!core->o_bs) return 0;
    if (core->Prim->r_phase == 2) {
        fprintf(stderr, "Memory protocol error: repeated request during EXECUTE\n");
        return 2;
    }
    if (!pending) {
        address = core->o_addr;
        data = core->o_dat;
        bs = core->o_bs;
        we = core->o_we;
        remaining = random_waits ?
            std::uniform_int_distribution<unsigned>(0, wait_cycles)(wait_rng) : wait_cycles;
        held_state = cpu_state();
        pending = true;
    }
    if (remaining) {
        --remaining;
        return 0;
    }
    if (json_trace || address < 0xfffe) {
        if (we) {
            if (bs & 1) {
                mem[address] = data & 0xff;
                if (json_trace) writes.emplace_back(address, mem[address]);
            }
            if (bs & 2) {
                mem[(address + 1) & 0xffff] = data >> 8;
                if (json_trace) writes.emplace_back((address + 1) & 0xffff, data >> 8);
            }
        } else {
            core->i_dat = 0xa500;
            if (bs & 1) {
                core->i_dat = (core->i_dat & 0xff00) | mem[address];
                if (json_trace) reads.emplace_back(address, mem[address]);
            }
            if (bs & 2) {
                core->i_dat = (core->i_dat & 0xff) | (mem[(address + 1) & 0xffff] << 8);
                if (json_trace) reads.emplace_back((address + 1) & 0xffff, mem[(address + 1) & 0xffff]);
            }
        }
    }
    core->i_ack = 1;
    pending = false;
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
    if (size > sizeof(mem) - offset || fread(&mem[offset], 1, size, f) != size) {
        fclose(f);
        fprintf(stderr, "Invalid or oversized image\n");
        return -1;
    }
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
    while ((c = getopt(argc, argv, "i:j:c:w:s:")) != -1) {
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
            case 'j':
                json_trace = fopen(optarg, "w");
                if (!json_trace) return -1;
                break;
            case 'w': {
                char *end = nullptr;
                unsigned long value = strtoul(optarg, &end, 10);
                if (*end || optarg[0] == '-' || value > 10000) return -1;
                wait_cycles = static_cast<unsigned>(value);
                break;
            }
            case 's': {
                char *end = nullptr;
                unsigned long value = strtoul(optarg, &end, 10);
                if (*end || optarg[0] == '-' || value > 0xffffffffUL) return -1;
                wait_rng.seed(static_cast<unsigned>(value));
                random_waits = true;
                break;
            }
            case 'c': {
                char *end = nullptr;
                max_cycles = strtoull(optarg, &end, 10);
                if (!max_cycles || *end || optarg[0] == '-') return -1;
                break;
            }
            default: return -1;
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
    int result = 0;
    printf("prim simulator\n\n");

    if (parse_cmdline(argc, argv)) {
        fprintf(stderr, "%s -i image [-j retirement.jsonl] [-c max_cycles] [-w wait_cycles] [-s seed]\n", argv[0]);
        fprintf(stderr, "  -i <image>      path to binary image\n");
        return -1;
    }

    Verilated::traceEverOn(true);
    pCore = new Vprim();

    if (!json_trace) opentrace("trace.vcd");

    reset();

    while(tickcount < max_cycles * clockcycle_ps) {
        result = handle(pCore);
        if (result) goto finish;
        // Python step() treats these as debugger markers, not instructions.
        if (json_trace && pCore->Prim->r_phase == 0 && pCore->i_ack &&
            ((pCore->i_dat & 0xff) == 0x22 || (pCore->i_dat & 0xff) == 0xff)) {
            fprintf(json_trace, "{\"kind\":\"halt\",\"pc\":%u,\"ir\":%u}\n",
                pCore->Prim->r_pc, pCore->i_dat & 0xff);
            goto finish;
        }
        const bool retiring = pCore->Prim->r_phase == 2;
        const unsigned at = pCore->Prim->r_pc;
        const unsigned ir = pCore->Prim->r_ir;
        tick();
        if (retiring) trace_step(at, ir);
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
    result = 1;

finish:
    if (json_trace) fclose(json_trace);
    pCore->final();

    if (pTrace) {
        pTrace->close();
        delete pTrace;
    }
    return result;

}
