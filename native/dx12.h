#pragma once
#include "lif.h"
#include <functional>
#include <string>
namespace flymsg {
struct GpuFault : std::runtime_error {
  using std::runtime_error::runtime_error;
};
// The GPU lane's hardware adapter name, empty when there is none.
std::wstring hardware_adapter();
void advance_gpu(Runtime &runtime, uint32_t target, const std::string &shader,
                 const std::function<bool(uint32_t)> &stop = {},
                 const std::function<bool(uint32_t)> &inject = {},
                 const std::string &expected_adapter = "");
} // namespace flymsg
