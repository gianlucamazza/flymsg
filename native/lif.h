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
constexpr uint32_t fixture_magic = 0x314e4d46, output_magic = 0x314f4d46,
                   counts_magic = 0x31534d46; // FMS1: sparse counts
constexpr uint64_t max_bytes = 512ull * 1024 * 1024;
inline void require(bool condition, const char *message) {
  if (!condition)
    throw std::runtime_error(message);
}
inline uint64_t digest(const std::vector<uint32_t> &words) {
  // Compatibility/integrity token, NOT cryptographic authentication.
  uint64_t result = 14695981039346656037ull;
  for (auto word : words)
    for (int i = 0; i < 4; ++i) {
      result ^= uint8_t(word >> (i * 8));
      result *= 1099511628211ull;
    }
  return result;
}
inline std::vector<uint32_t> read_words(const std::filesystem::path &path) {
  const auto bytes = std::filesystem::file_size(path);
  require(bytes <= max_bytes && bytes % 4 == 0, "invalid native file size");
  std::vector<uint32_t> words(bytes / 4);
  std::ifstream file(path, std::ios::binary);
  file.read(reinterpret_cast<char *>(words.data()), std::streamsize(bytes));
  require(bool(file), "native read failed");
  return words;
}
inline void write_words(const std::filesystem::path &path,
                        const std::vector<uint32_t> &words) {
  auto temporary = path;
  temporary += ".tmp";
  {
    std::ofstream file(temporary, std::ios::binary | std::ios::trunc);
    file.write(reinterpret_cast<const char *>(words.data()),
               std::streamsize(words.size() * 4));
    require(bool(file), "native write failed");
  }
#ifdef _WIN32
  require(MoveFileExW(temporary.c_str(), path.c_str(),
                      MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) != 0,
          "native atomic replacement failed");
#else
  std::filesystem::rename(temporary, path);
#endif
}
inline double word_double(const std::vector<uint32_t> &words, uint64_t at) {
  return std::bit_cast<double>(uint64_t(words[at]) | uint64_t(words[at + 1])
                                                         << 32);
}
constexpr uint32_t batch_magic = 0x314e4246; // FBN1
// Runs of one network: the base fixture's words before its kicks, each run's
// changed words among them and its own kicks (flymsg.native.export_batch), so
// the network is read once. The rebuilt words go through the same validation
// as any fixture.
inline uint32_t batch_runs(const std::vector<uint32_t> &batch) {
  require(batch.size() >= 4 && batch[0] == batch_magic && batch[1] == 1 &&
              batch[2] > 0,
          "invalid batch");
  return batch[2];
}
inline std::vector<uint32_t> batch_fixture(const std::vector<uint32_t> &base,
                                           const std::vector<uint32_t> &batch,
                                           uint32_t run) {
  require(run < batch_runs(batch), "batch run out of range");
  const uint64_t cut = batch[3];
  require(base.size() >= 40 && base[24] == cut && cut <= base.size(),
          "batch does not match its base");
  uint64_t at = 4;
  for (uint32_t k = 0;; ++k) {
    require(at < batch.size(), "truncated batch");
    const uint64_t pairs = batch[at];
    require(at + 1 + 2 * pairs < batch.size(), "truncated batch pairs");
    const uint64_t kicks_at = at + 1 + 2 * pairs;
    const uint64_t kicks = batch[kicks_at];
    require(kicks_at + 1 + kicks <= batch.size(), "truncated batch kicks");
    if (k == run) {
      require((cut + kicks) * 4 <= max_bytes, "batch run exceeds budget");
      std::vector<uint32_t> words(base.begin(), base.begin() + cut);
      for (uint64_t i = 0; i < pairs; ++i) {
        const uint64_t offset = batch[at + 1 + 2 * i];
        require(offset < cut, "batch patch outside the network words");
        words[offset] = batch[at + 2 + 2 * i];
      }
      words.insert(words.end(), batch.begin() + kicks_at + 1,
                   batch.begin() + kicks_at + 1 + kicks);
      return words;
    }
    at = kicks_at + 1 + kicks;
  }
}
class Runtime {
public:
  std::vector<uint32_t> input, state;
  uint32_t step = 0;
  // Version 2 extension (graded neurons, electrically coupled groups); offsets
  // into `input` and `state`, all zero for version 1 fixtures.
  uint64_t ng = 0, nc = 0, ncomp = 0, nmat = 0, width = 0;
  uint64_t x_gcol = 0, x_lo = 0, x_span = 0, x_scale = 0, x_gpos = 0,
           x_nodes = 0, x_off = 0, x_moff = 0, x_mat = 0, x_amp = 0;
  uint64_t s_ring = 0, s_new = 0, s_vsum = 0, s_buf = 0, s_pulse = 0;
  explicit Runtime(std::vector<uint32_t> fixture) : input(std::move(fixture)) {
    require(std::endian::native == std::endian::little,
            "little endian host required");
    require(input.size() >= 40 && input[0] == fixture_magic &&
                (input[1] == 1 || input[1] == 2),
            "incompatible fixture");
    const uint64_t n = input[2], steps = input[3], per = input[4], d = input[5],
                   ns = input[7], nt = input[8];
    require(n && steps && per && d && steps % per == 0 && ns <= n && nt <= n,
            "invalid fixture dimensions");
    require(steps + uint64_t(input[6]) < uint64_t(INT32_MAX),
            "deadline overflow");
    require(input[34] == input.size() &&
                uint64_t(input[35]) * 4 + input.size() * 4 <= max_bytes,
            "fixture budget exceeded");
    const uint64_t sizes[] = {n + 1, input[36], input[36],     n, n, n,
                              n,     n,         steps * ns * 2};
    uint64_t cursor = 40;
    for (uint32_t k = 16; k <= 24; ++k) {
      require(input[k] == cursor, "invalid input offset");
      cursor += sizes[k - 16];
      require(cursor <= input.size(), "input range overflow");
    }
    if (input[1] == 2) {
      require(input[37] == cursor && cursor + 5 <= input.size(),
              "invalid extension offset");
      ng = input[cursor];
      nc = input[cursor + 1];
      ncomp = input[cursor + 2];
      nmat = input[cursor + 3];
      width = input[cursor + 4];
      require(ng <= n && nc <= n && ncomp <= nc && (ng || nc),
              "invalid extension dimensions");
      cursor += 5;
      const uint64_t ext_sizes[] = {n,  ng,        ng,        ng,       n,
                                    nc, ncomp + 1, ncomp + 1, nmat * 2, nc * 2};
      uint64_t *ext_offsets[] = {&x_gcol,  &x_lo,  &x_span, &x_scale, &x_gpos,
                                 &x_nodes, &x_off, &x_moff, &x_mat,   &x_amp};
      for (int k = 0; k < 10; ++k) {
        *ext_offsets[k] = cursor;
        cursor += ext_sizes[k];
        require(cursor <= input.size(), "extension range overflow");
      }
    } else
      require(input[37] == 0 && input[38] == 0, "unexpected extension");
    require(cursor == input.size(), "unexpected fixture tail");
    const uint64_t state_sizes[] = {
        n, n, n, n, d * n, (steps / per) * n, n, steps * nt, n};
    cursor = 0;
    for (uint32_t k = 25; k <= 33; ++k) {
      require(input[k] == cursor, "invalid state offset");
      cursor += state_sizes[k - 25];
    }
    if (input[1] == 2) {
      require(input[38] == cursor, "invalid extension state offset");
      s_ring = cursor;
      s_new = s_ring + d * ng;
      s_vsum = s_new + ng;
      s_buf = s_vsum + 2 * (steps / per) * ng;
      s_pulse = s_buf + nc;
      cursor = s_pulse + nc;
    }
    require(cursor == input[35], "invalid state size");
    for (uint32_t k = 9; k < 16; ++k)
      require(std::isfinite(std::bit_cast<float>(input[k])),
              "nonfinite constant");
    require(input[input[16]] == 0 && input[input[16] + n] == input[36],
            "invalid edge pointers");
    std::vector<bool> seen_trace(nt, false), seen_stim(ns, false);
    for (uint32_t i = 0; i < n; ++i) {
      auto begin = input[input[16] + i], end = input[input[16] + i + 1];
      require(begin <= end && end <= input[36], "edge pointer range");
      uint32_t previous = 0;
      for (auto q = begin; q < end; ++q) {
        auto source = input[input[17] + q];
        require(source < n && (q == begin || source >= previous),
                "unordered source index");
        previous = source;
        require(std::isfinite(std::bit_cast<float>(input[input[18] + q])),
                "nonfinite edge");
      }
      require(input[input[19] + i] <= 1 && input[input[20] + i] <= 1,
              "invalid neuron mask");
      const auto tc = int32_t(input[input[22] + i]),
                 sc = int32_t(input[input[23] + i]);
      require(tc >= -1 && (tc < 0 || uint32_t(tc) < nt) && sc >= -1 &&
                  (sc < 0 || uint32_t(sc) < ns),
              "column out of range");
      if (tc >= 0) {
        require(!seen_trace[tc], "duplicate trace column");
        seen_trace[tc] = true;
      }
      if (sc >= 0) {
        require(!seen_stim[sc], "duplicate stimulus column");
        seen_stim[sc] = true;
      }
      require(bool(input[input[19] + i]) == (sc >= 0),
              "stimulus mask mismatch");
      require(std::isfinite(std::bit_cast<float>(input[input[21] + i])),
              "nonfinite threshold jump");
    }
    require(std::all_of(seen_trace.begin(), seen_trace.end(),
                        [](bool v) { return v; }) &&
                std::all_of(seen_stim.begin(), seen_stim.end(),
                            [](bool v) { return v; }),
            "incomplete column map");
    for (uint64_t i = 0; i < steps * ns; ++i) {
      auto at = input[24] + i * 2;
      double count = std::bit_cast<double>(uint64_t(input[at]) |
                                           uint64_t(input[at + 1]) << 32);
      require(std::isfinite(count) && count >= 0 &&
                  count <= 9007199254740992.0 && std::floor(count) == count,
              "invalid kick count");
    }
    if (input[1] == 2)
      validate_extension(n);
    state.resize(input[35], 0);
    for (uint32_t i = 0; i < n; ++i) {
      state[input[25] + i] = input[13];
      state[input[31] + i] = uint32_t(-1);
    }
  }
  void validate_extension(uint64_t n) const {
    std::vector<bool> seen(ng, false);
    for (uint64_t i = 0; i < n; ++i) {
      const auto k = int32_t(input[x_gcol + i]);
      require(k >= -1 && (k < 0 || uint64_t(k) < ng), "graded column range");
      if (k >= 0) {
        require(!seen[k], "duplicate graded column");
        seen[k] = true;
      }
    }
    require(std::all_of(seen.begin(), seen.end(), [](bool v) { return v; }),
            "incomplete graded map");
    for (uint64_t k = 0; k < ng; ++k) {
      const float lo = std::bit_cast<float>(input[x_lo + k]),
                  span = std::bit_cast<float>(input[x_span + k]),
                  scale = std::bit_cast<float>(input[x_scale + k]);
      require(std::isfinite(lo) && std::isfinite(span) && span > 0 &&
                  std::isfinite(scale) && scale >= 0,
              "invalid graded parameters");
    }
    for (uint64_t k = 0; k < nc; ++k) {
      const auto i = input[x_nodes + k];
      require(i < n && int32_t(input[x_gpos + i]) == int32_t(k),
              "invalid coupled neuron map");
    }
    uint64_t coupled = 0;
    for (uint64_t i = 0; i < n; ++i)
      coupled += int32_t(input[x_gpos + i]) >= 0;
    require(coupled == nc && input[x_off] == 0 && input[x_off + ncomp] == nc &&
                input[x_moff] == 0 && input[x_moff + ncomp] == nmat,
            "invalid coupled groups");
    for (uint64_t c = 0; c < ncomp; ++c) {
      const uint64_t m = input[x_off + c + 1] - input[x_off + c];
      require(input[x_off + c + 1] > input[x_off + c] &&
                  input[x_moff + c + 1] - input[x_moff + c] == 3 * m * m,
              "invalid coupled group size");
    }
    for (uint64_t q = 0; q < nmat; ++q)
      require(std::isfinite(word_double(input, x_mat + 2 * q)),
              "nonfinite step matrix");
    bool crossing = false;
    for (uint64_t k = 0; k < nc; ++k) {
      const double a = word_double(input, x_amp + 2 * k);
      require(std::isfinite(a) && a >= 0, "invalid spike amplitude");
      crossing = crossing || a > 0;
    }
    require((width > 0) == crossing, "invalid spike term");
  }
  float get(uint32_t slot, uint32_t i) const {
    return std::bit_cast<float>(state[input[slot] + i]);
  }
  void set(uint32_t slot, uint32_t i, float value) {
    state[input[slot] + i] = std::bit_cast<uint32_t>(value);
  }
  float constant(uint32_t at) const { return std::bit_cast<float>(input[at]); }
  void advance_to(uint32_t target) {
    require(target >= step && target <= input[3], "invalid advance boundary");
    const uint32_t n = input[2], d = input[5];
    const double rest = double(constant(13));
    for (; step < target; ++step) {
      // exact step of each coupled group from the state before the update, in
      // float64: potentials relative to rest, then conductances of
      // non-refractory neurons
      for (uint64_t c = 0; c < ncomp; ++c) {
        const uint64_t a = input[x_off + c], m = input[x_off + c + 1] - a;
        for (uint64_t r = 0; r < m; ++r) {
          const uint64_t row = input[x_moff + c] + r * 3 * m;
          double acc = 0.0;
          for (uint64_t q = 0; q < m; ++q)
            acc += word_double(input, x_mat + 2 * (row + q)) *
                   (double(get(25, input[x_nodes + a + q])) - rest);
          for (uint64_t q = 0; q < m; ++q) {
            const auto j = input[x_nodes + a + q];
            if (state[input[28] + j] <= step)
              acc += word_double(input, x_mat + 2 * (row + m + q)) *
                     double(get(26, j));
          }
          for (uint64_t q = 0; q < m; ++q)
            if (int32_t(state[s_pulse + a + q]) > 0)
              acc += word_double(input, x_mat + 2 * (row + 2 * m + q)) *
                     word_double(input, x_amp + 2 * (a + q));
          state[s_buf + a + r] = std::bit_cast<uint32_t>(float(rest + acc));
        }
      }
      for (uint64_t k = 0; k < nc; ++k)
        if (int32_t(state[s_pulse + k]) > 0)
          --state[s_pulse + k];
      for (uint32_t i = 0; i < n; ++i) {
        const bool frozen = state[input[28] + i] > step;
        float vi = (get(25, i) - constant(13)) * constant(9) +
                   get(26, i) * constant(11) + constant(13);
        float gi = get(26, i) * constant(10);
        set(25, i, frozen ? constant(13) : vi);
        if (!frozen)
          set(26, i, gi);
        if (nc && int32_t(input[x_gpos + i]) >= 0 && !frozen)
          state[input[25] + i] = state[s_buf + input[x_gpos + i]];
        set(27, i, get(27, i) * constant(12));
        const int32_t k = ng ? int32_t(input[x_gcol + i]) : -1;
        state[input[33] + i] = (get(25, i) > constant(14) + get(27, i) &&
                                !input[input[20] + i] && k < 0);
        if (k >= 0) {
          float f = (get(25, i) - std::bit_cast<float>(input[x_lo + k])) /
                    std::bit_cast<float>(input[x_span + k]);
          f = std::max(0.0f, std::min(f, 1.0f));
          const float release =
              input[input[20] + i]
                  ? 0.0f
                  : f * std::bit_cast<float>(input[x_scale + k]);
          state[s_new + k] = std::bit_cast<uint32_t>(release);
        }
      }
      for (uint32_t i = 0; i < n; ++i) {
        float delivered = 0;
        for (auto q = input[input[16] + i]; q < input[input[16] + i + 1]; ++q)
          if (state[input[29] + (step % d) * n + input[input[17] + q]])
            delivered += std::bit_cast<float>(input[input[18] + q]);
        if (state[input[28] + i] <= step)
          set(26, i, get(26, i) + delivered);
        if (ng) {
          // graded release from d steps ago, after the spikes, sources
          // ascending
          float released = 0;
          bool touched = false;
          for (auto q = input[input[16] + i]; q < input[input[16] + i + 1];
               ++q) {
            const auto k = int32_t(input[x_gcol + input[input[17] + q]]);
            if (k < 0)
              continue;
            const float a =
                std::bit_cast<float>(state[s_ring + (step % d) * ng + k]);
            if (a == 0.0f)
              continue;
            released += std::bit_cast<float>(input[input[18] + q]) * a;
            touched = true;
          }
          if (touched && state[input[28] + i] <= step)
            set(26, i, get(26, i) + released);
        }
        auto col = int32_t(input[input[23] + i]);
        if (col >= 0) {
          auto at = input[24] + (uint64_t(step) * input[7] + uint32_t(col)) * 2;
          double count = std::bit_cast<double>(uint64_t(input[at]) |
                                               uint64_t(input[at + 1]) << 32);
          set(25, i, float(double(get(25, i)) + double(constant(15)) * count));
        }
      }
      for (uint32_t i = 0; i < n; ++i) {
        const uint32_t emitted = state[input[33] + i];
        if (emitted) {
          set(25, i, constant(13));
          set(26, i, 0);
          set(27, i, get(27, i) + std::bit_cast<float>(input[input[21] + i]));
          if (!input[input[19] + i])
            state[input[28] + i] = step + input[6];
          ++state[input[30] + (step / input[4]) * n + i];
          if (int32_t(state[input[31] + i]) < 0)
            state[input[31] + i] = step;
          if (width && int32_t(input[x_gpos + i]) >= 0)
            state[s_pulse + input[x_gpos + i]] = uint32_t(width);
          const auto col = int32_t(input[input[22] + i]);
          if (col >= 0)
            state[input[32] + uint64_t(step) * input[8] + uint32_t(col)] = 1;
        }
        state[input[29] + (step % d) * n + i] = emitted;
      }
      for (uint64_t k = 0; k < ng; ++k) {
        state[s_ring + (step % d) * ng + k] = state[s_new + k];
      }
      for (uint32_t i = 0; ng && i < n; ++i) {
        const int32_t k = int32_t(input[x_gcol + i]);
        if (k < 0)
          continue;
        const uint64_t at = s_vsum + 2 * ((step / input[4]) * ng + k);
        const double sum = word_double(state, at) + double(get(25, i));
        const uint64_t bits = std::bit_cast<uint64_t>(sum);
        state[at] = uint32_t(bits);
        state[at + 1] = uint32_t(bits >> 32);
      }
    }
  }
  void snapshot(const std::filesystem::path &path) const {
    std::vector<uint32_t> words{output_magic, step, uint32_t(state.size())};
    words.insert(words.end(), state.begin(), state.end());
    write_words(path, words);
  }
  // The readout a battery uses, sparse: a whole-CNS run fires a few thousand of
  // its neurons, so its dense counts (bins x n) are mostly zeros. Words: magic,
  // step, n, bins, then the nonzero counts as (bin * n + neuron, count) pairs
  // after their number, then the first spikes as (neuron, step) pairs after
  // theirs. flymsg.native.read_counts decodes it.
  void counts(const std::filesystem::path &path) const {
    const uint64_t n = input[2], bins = input[3] / input[4];
    std::vector<uint32_t> words{counts_magic, step, uint32_t(n), uint32_t(bins),
                                0};
    for (uint64_t k = 0; k < bins * n; ++k)
      if (const auto c = state[input[30] + k]) {
        words.push_back(uint32_t(k));
        words.push_back(c);
        ++words[4];
      }
    const auto firsts = words.size();
    words.push_back(0);
    for (uint64_t i = 0; i < n; ++i)
      if (const auto f = int32_t(state[input[31] + i]); f >= 0) {
        words.push_back(uint32_t(i));
        words.push_back(uint32_t(f));
        ++words[firsts];
      }
    write_words(path, words);
  }
  void checkpoint(const std::filesystem::path &path) const {
    const auto identity = digest(input), checksum = digest(state);
    std::vector<uint32_t> words{0x31434d46,
                                1,
                                step,
                                uint32_t(state.size()),
                                uint32_t(identity),
                                uint32_t(identity >> 32),
                                uint32_t(checksum),
                                uint32_t(checksum >> 32)};
    // Bind cursor in the checksum too.
    words[6] ^= step;
    words.insert(words.end(), state.begin(), state.end());
    write_words(path, words);
  }
  void restore(const std::filesystem::path &path) {
    auto words = read_words(path);
    require(words.size() >= 8, "truncated checkpoint");
    const auto identity = digest(input);
    require(words[0] == 0x31434d46 && words[1] == 1 && words[2] <= input[3] &&
                words[3] == state.size() && words.size() == state.size() + 8,
            "incompatible checkpoint");
    require(words[4] == uint32_t(identity) &&
                words[5] == uint32_t(identity >> 32),
            "checkpoint fixture identity mismatch");
    std::vector<uint32_t> candidate(words.begin() + 8, words.end());
    auto checksum = digest(candidate);
    require((words[6] ^ words[2]) == uint32_t(checksum) &&
                words[7] == uint32_t(checksum >> 32),
            "checkpoint integrity mismatch");
    state = std::move(candidate);
    step = words[2];
  }
};
} // namespace flymsg
