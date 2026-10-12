#pragma once
#include "lif.h"
#include <functional>
namespace flymsg {
struct GpuFault : std::runtime_error { using std::runtime_error::runtime_error; };
void advance_gpu(Runtime& runtime,uint32_t target,const std::string& shader, const std::function<bool(uint32_t)>& stop = {}, const std::string& expected_adapter = "");
}
