// zdis - disassembler for ZX-16 binaries (C++17).
//
//   zdis program.bin            plain assembly, can be fed back to zasm.py
//   zdis -l program.bin         listing with addresses and raw bytes
//
// Words that are not valid instructions (for example strings) are printed
// as ".byte" lines, so the output always assembles back to the same bytes.
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

namespace {

enum class Form { None, R, RR, RI, I, Load, Store };
struct OpInfo {
    const char* name;
    Form form;
};

const OpInfo OPS[] = {
    {"nop", Form::None},  {"halt", Form::None}, {"ldi", Form::RI},    {"mov", Form::RR},
    {"add", Form::RR},    {"sub", Form::RR},    {"and", Form::RR},    {"or", Form::RR},
    {"xor", Form::RR},    {"shl", Form::RR},    {"shr", Form::RR},    {"addi", Form::RI},
    {"cmp", Form::RR},    {"cmpi", Form::RI},   {"ld", Form::Load},   {"st", Form::Store},
    {"ldb", Form::Load},  {"stb", Form::Store}, {"jmp", Form::I},     {"jz", Form::I},
    {"jnz", Form::I},     {"jlt", Form::I},     {"jge", Form::I},     {"call", Form::I},
    {"ret", Form::None},  {"push", Form::R},    {"pop", Form::R},     {"out", Form::R},
    {"mul", Form::RR},    {"div", Form::RR},    {"mod", Form::RR},    {"outn", Form::R},
    {"in", Form::R},      {"sleep", Form::R},
};
const unsigned OP_COUNT = sizeof(OPS) / sizeof(OPS[0]);

std::string hex(unsigned v, int width) {
    char buf[16];
    std::snprintf(buf, sizeof buf, "0x%0*x", width, v);
    return buf;
}

int sgn(unsigned v) { return v >= 0x8000 ? static_cast<int>(v) - 0x10000 : static_cast<int>(v); }

std::string reg(unsigned r) { return "r" + std::to_string(r); }

std::string mem(unsigned base, unsigned off) {
    if (off == 0) return "[" + reg(base) + "]";
    int s = sgn(off);
    return "[" + reg(base) + (s < 0 ? "-" : "+") + std::to_string(s < 0 ? -s : s) + "]";
}

std::string raw_bytes(const uint8_t* b, size_t n) {
    std::string s = ".byte ";
    for (size_t i = 0; i < n; i++) s += (i ? ", " : "") + hex(b[i], 2);
    return s;
}

std::string disasm(const uint8_t* b) {
    unsigned op = b[0], a = b[1] >> 4, bb = b[1] & 15, imm = b[2] | (b[3] << 8);
    if (op >= OP_COUNT) return raw_bytes(b, 4);
    const OpInfo& info = OPS[op];
    Form f = info.form;
    bool uses_a = f != Form::None && f != Form::I;
    bool uses_b = f == Form::RR || f == Form::Load || f == Form::Store;
    bool uses_imm = f == Form::RI || f == Form::I || f == Form::Load || f == Form::Store;
    if (a > 7 || bb > 7 || (!uses_a && a) || (!uses_b && bb) || (!uses_imm && imm)) return raw_bytes(b, 4);

    std::string name = info.name;
    switch (f) {
        case Form::None: return name;
        case Form::R: return name + " " + reg(a);
        case Form::RR: return name + " " + reg(a) + ", " + reg(bb);
        case Form::RI: {
            std::string v = name == "ldi" ? (imm >= 256 ? hex(imm, 4) : std::to_string(imm)) : std::to_string(sgn(imm));
            return name + " " + reg(a) + ", " + v;
        }
        case Form::I: return name + " " + hex(imm, 4);
        case Form::Load: return name + " " + reg(a) + ", " + mem(bb, imm);
        case Form::Store: return name + " " + mem(a, imm) + ", " + reg(bb);
    }
    return raw_bytes(b, 4);
}

}  // namespace

int main(int argc, char** argv) {
    bool listing = false;
    const char* path = nullptr;
    for (int i = 1; i < argc; i++) {
        std::string arg = argv[i];
        if (arg == "-l" || arg == "--listing") listing = true;
        else if (arg == "-h" || arg == "--help") { std::puts("usage: zdis [-l] program.bin"); return 0; }
        else path = argv[i];
    }
    if (!path) { std::fputs("usage: zdis [-l] program.bin\n", stderr); return 64; }

    std::ifstream in(path, std::ios::binary);
    if (!in) { std::fprintf(stderr, "zdis: cannot open %s\n", path); return 66; }
    std::vector<uint8_t> data((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());

    for (size_t addr = 0; addr < data.size(); addr += 4) {
        size_t n = data.size() - addr < 4 ? data.size() - addr : 4;
        std::string text = n == 4 ? disasm(&data[addr]) : raw_bytes(&data[addr], n);
        if (listing) {
            std::string bytes;
            for (size_t i = 0; i < n; i++) {
                char buf[4];
                std::snprintf(buf, sizeof buf, "%02x ", data[addr + i]);
                bytes += buf;
            }
            std::printf("%04zx:  %-12s  %s\n", addr, bytes.c_str(), text.c_str());
        } else {
            std::printf("    %s\n", text.c_str());
        }
    }
    return 0;
}
