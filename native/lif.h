// FlyMSG native qualification runtime. MIT, Gianluca Mazza / contributors.
#pragma once
#include <algorithm>
#include <bit>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>
#ifdef _WIN32
#include <Windows.h>
#endif

namespace flymsg {
constexpr uint32_t fixture_magic = 0x314e4d46, output_magic = 0x314f4d46;
constexpr uint64_t max_bytes = 512ull * 1024 * 1024;
inline void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}
inline uint64_t digest(const std::vector<uint32_t>& words) {
    // Compatibility/integrity token, NOT cryptographic authentication.
    uint64_t result = 14695981039346656037ull;
    for (auto word : words) for (int i = 0; i < 4; ++i) {
        result ^= uint8_t(word >> (i * 8)); result *= 1099511628211ull;
    }
    return result;
}
inline std::vector<uint32_t> read_words(const std::filesystem::path& path) {
    const auto bytes = std::filesystem::file_size(path);
    require(bytes <= max_bytes && bytes % 4 == 0, "invalid native file size");
    std::vector<uint32_t> words(bytes / 4);
    std::ifstream file(path, std::ios::binary);
    file.read(reinterpret_cast<char*>(words.data()), std::streamsize(bytes));
    require(bool(file), "native read failed");
    return words;
}
inline void write_words(const std::filesystem::path& path, const std::vector<uint32_t>& words) {
    auto temporary = path; temporary += ".tmp";
    { std::ofstream file(temporary, std::ios::binary | std::ios::trunc);
      file.write(reinterpret_cast<const char*>(words.data()), std::streamsize(words.size() * 4));
      require(bool(file), "native write failed"); }
    #ifdef _WIN32
    require(MoveFileExW(temporary.c_str(), path.c_str(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)!=0, "native atomic replacement failed");
    #else
    std::filesystem::rename(temporary, path);
    #endif
}
class Runtime {
public:
    std::vector<uint32_t> input, state;
    uint32_t step = 0;
    explicit Runtime(std::vector<uint32_t> fixture) : input(std::move(fixture)) {
        require(std::endian::native == std::endian::little, "little endian host required");
        require(input.size() >= 40 && input[0] == fixture_magic && input[1] == 1, "incompatible fixture");
        const uint64_t n=input[2], steps=input[3], per=input[4], d=input[5], ns=input[7], nt=input[8];
        require(n && steps && per && d && steps % per == 0 && ns <= n && nt <= n, "invalid fixture dimensions");
        require(steps + uint64_t(input[6]) < uint64_t(INT32_MAX), "deadline overflow");
        require(input[34] == input.size() && uint64_t(input[35])*4 + input.size()*4 <= max_bytes, "fixture budget exceeded");
        const uint64_t sizes[] = {n+1, input[36], input[36], n,n,n,n,n,steps*ns*2};
        uint64_t cursor=40;
        for (uint32_t k=16;k<=24;++k) {
            require(input[k] == cursor, "invalid input offset"); cursor += sizes[k-16];
            require(cursor <= input.size(), "input range overflow");
        }
        require(cursor == input.size(), "unexpected fixture tail");
        const uint64_t state_sizes[] = {n,n,n,n,d*n,(steps/per)*n,n,steps*nt,n};
        cursor=0;
        for(uint32_t k=25;k<=33;++k) { require(input[k]==cursor,"invalid state offset"); cursor+=state_sizes[k-25]; }
        require(cursor == input[35],"invalid state size");
        for(uint32_t k=9;k<16;++k) require(std::isfinite(std::bit_cast<float>(input[k])),"nonfinite constant");
        require(input[input[16]] == 0 && input[input[16]+n] == input[36], "invalid edge pointers");
        std::vector<bool> seen_trace(nt,false), seen_stim(ns,false);
        for(uint32_t i=0;i<n;++i) {
            auto begin=input[input[16]+i], end=input[input[16]+i+1];
            require(begin<=end && end<=input[36],"edge pointer range");
            uint32_t previous=0;
            for(auto q=begin;q<end;++q) {
                auto source=input[input[17]+q];
                require(source<n && (q==begin || source>=previous),"unordered source index"); previous=source;
                require(std::isfinite(std::bit_cast<float>(input[input[18]+q])),"nonfinite edge");
            }
            require(input[input[19]+i]<=1 && input[input[20]+i]<=1,"invalid neuron mask");
            const auto tc=int32_t(input[input[22]+i]), sc=int32_t(input[input[23]+i]);
            require(tc>=-1 && (tc<0 || uint32_t(tc)<nt) && sc>=-1 && (sc<0 || uint32_t(sc)<ns),"column out of range");
            if(tc>=0){require(!seen_trace[tc],"duplicate trace column");seen_trace[tc]=true;}
            if(sc>=0){require(!seen_stim[sc],"duplicate stimulus column");seen_stim[sc]=true;}
            require(bool(input[input[19]+i])==(sc>=0),"stimulus mask mismatch");
            require(std::isfinite(std::bit_cast<float>(input[input[21]+i])),"nonfinite threshold jump");
        }
        require(std::all_of(seen_trace.begin(),seen_trace.end(),[](bool v){return v;}) && std::all_of(seen_stim.begin(),seen_stim.end(),[](bool v){return v;}),"incomplete column map");
        for(uint64_t i=0;i<steps*ns;++i) {
            auto at=input[24]+i*2;
            double count=std::bit_cast<double>(uint64_t(input[at]) | uint64_t(input[at+1])<<32);
            require(std::isfinite(count) && count>=0 && count<=9007199254740992.0 && std::floor(count)==count,"invalid kick count");
        }
        state.resize(input[35],0);
        for(uint32_t i=0;i<n;++i) { state[input[25]+i]=input[13]; state[input[31]+i]=uint32_t(-1); }
    }
    float get(uint32_t slot,uint32_t i) const { return std::bit_cast<float>(state[input[slot]+i]); }
    void set(uint32_t slot,uint32_t i,float value) { state[input[slot]+i]=std::bit_cast<uint32_t>(value); }
    float constant(uint32_t at) const {return std::bit_cast<float>(input[at]);}
    void advance_to(uint32_t target) {
        require(target>=step && target<=input[3],"invalid advance boundary");
        const uint32_t n=input[2],d=input[5];
        for(;step<target;++step) {
            for(uint32_t i=0;i<n;++i) {
                const bool frozen=state[input[28]+i]>step;
                float vi=(get(25,i)-constant(13))*constant(9)+get(26,i)*constant(11)+constant(13);
                float gi=get(26,i)*constant(10);
                set(25,i,frozen?constant(13):vi); if(!frozen) set(26,i,gi);
                set(27,i,get(27,i)*constant(12));
                state[input[33]+i]=(get(25,i)>constant(14)+get(27,i) && !input[input[20]+i]);
            }
            for(uint32_t i=0;i<n;++i) {
                float delivered=0;
                for(auto q=input[input[16]+i];q<input[input[16]+i+1];++q)
                    if(state[input[29]+(step%d)*n+input[input[17]+q]]) delivered += std::bit_cast<float>(input[input[18]+q]);
                if(state[input[28]+i]<=step) set(26,i,get(26,i)+delivered);
                auto col=int32_t(input[input[23]+i]);
                if(col>=0) {
                    auto at=input[24]+(uint64_t(step)*input[7]+uint32_t(col))*2;
                    double count=std::bit_cast<double>(uint64_t(input[at]) | uint64_t(input[at+1])<<32);
                    set(25,i,float(double(get(25,i))+double(constant(15))*count));
                }
            }
            for(uint32_t i=0;i<n;++i) {
                const uint32_t emitted=state[input[33]+i];
                if(emitted) {
                    set(25,i,constant(13)); set(26,i,0); set(27,i,get(27,i)+std::bit_cast<float>(input[input[21]+i]));
                    if(!input[input[19]+i]) state[input[28]+i]=step+input[6];
                    ++state[input[30]+(step/input[4])*n+i];
                    if(int32_t(state[input[31]+i])<0) state[input[31]+i]=step;
                    const auto col=int32_t(input[input[22]+i]);
                    if(col>=0) state[input[32]+uint64_t(step)*input[8]+uint32_t(col)]=1;
                }
                state[input[29]+(step%d)*n+i]=emitted;
            }
        }
    }
    void snapshot(const std::filesystem::path& path) const {
        std::vector<uint32_t> words{output_magic,step,uint32_t(state.size())};
        words.insert(words.end(),state.begin(),state.end()); write_words(path,words);
    }
    void checkpoint(const std::filesystem::path& path) const {
        const auto identity=digest(input), checksum=digest(state);
        std::vector<uint32_t> words{0x31434d46,1,step,uint32_t(state.size()),uint32_t(identity),uint32_t(identity>>32),uint32_t(checksum),uint32_t(checksum>>32)};
        // Bind cursor in the checksum too.
        words[6]^=step;
        words.insert(words.end(),state.begin(),state.end()); write_words(path,words);
    }
    void restore(const std::filesystem::path& path) {
        auto words=read_words(path); require(words.size()>=8,"truncated checkpoint");
        const auto identity=digest(input);
        require(words[0]==0x31434d46 && words[1]==1 && words[2]<=input[3] && words[3]==state.size() && words.size()==state.size()+8,"incompatible checkpoint");
        require(words[4]==uint32_t(identity) && words[5]==uint32_t(identity>>32),"checkpoint fixture identity mismatch");
        std::vector<uint32_t> candidate(words.begin()+8,words.end()); auto checksum=digest(candidate);
        require((words[6]^words[2])==uint32_t(checksum) && words[7]==uint32_t(checksum>>32),"checkpoint integrity mismatch");
        state=std::move(candidate);step=words[2];
    }
};
} // namespace flymsg
