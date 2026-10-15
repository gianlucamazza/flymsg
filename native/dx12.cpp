#include "dx12.h"
#include <Windows.h>
#include <cstring>
#include <d3d12.h>
#include <dxgi1_4.h>
#include <iostream>
#include <wrl/client.h>

namespace flymsg {
using Microsoft::WRL::ComPtr;
namespace {
void check(HRESULT hr, const char *operation) {
  if (FAILED(hr))
    throw std::runtime_error(std::string(operation) + " HRESULT " +
                             std::to_string(uint32_t(hr)));
}
struct Event {
  HANDLE value = CreateEventW(nullptr, FALSE, FALSE, nullptr);
  Event() { require(value != nullptr, "CreateEvent failed"); }
  ~Event() { CloseHandle(value); }
};
ComPtr<ID3D12Resource> buffer(ID3D12Device *device, uint64_t bytes,
                              D3D12_HEAP_TYPE heap, D3D12_RESOURCE_STATES state,
                              bool uav = false) {
  D3D12_HEAP_PROPERTIES hp{};
  hp.Type = heap;
  D3D12_RESOURCE_DESC desc{};
  desc.Dimension = D3D12_RESOURCE_DIMENSION_BUFFER;
  desc.Width = std::max<uint64_t>(bytes, 4);
  desc.Height = 1;
  desc.DepthOrArraySize = 1;
  desc.MipLevels = 1;
  desc.SampleDesc.Count = 1;
  desc.Layout = D3D12_TEXTURE_LAYOUT_ROW_MAJOR;
  desc.Flags = uav ? D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS
                   : D3D12_RESOURCE_FLAG_NONE;
  ComPtr<ID3D12Resource> result;
  check(device->CreateCommittedResource(&hp, D3D12_HEAP_FLAG_NONE, &desc, state,
                                        nullptr, IID_PPV_ARGS(&result)),
        "create buffer");
  return result;
}
void upload(ID3D12Resource *buffer, const std::vector<uint32_t> &words) {
  void *memory = nullptr;
  D3D12_RANGE read{0, 0};
  check(buffer->Map(0, &read, &memory), "upload map");
  std::memcpy(memory, words.data(), words.size() * 4);
  buffer->Unmap(0, nullptr);
}
void transition(ID3D12GraphicsCommandList *list, ID3D12Resource *resource,
                D3D12_RESOURCE_STATES from, D3D12_RESOURCE_STATES to) {
  D3D12_RESOURCE_BARRIER b{};
  b.Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
  b.Transition = {resource, D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES, from, to};
  list->ResourceBarrier(1, &b);
}
// Outgoing synapses of every neuron as one word array: n + 1 offsets, then the
// incoming-CSR positions q of each neuron's synapses, ascending.
std::vector<uint32_t> outgoing_synapses(const Runtime &runtime) {
  const auto &in = runtime.input;
  const uint32_t n = in[2];
  const uint32_t ptr = in[16], pre = in[17];
  const uint32_t nnz = in[ptr + n];
  std::vector<uint32_t> out(n + 1 + nnz, 0);
  for (uint32_t q = 0; q < nnz; ++q)
    ++out[in[pre + q] + 1];
  for (uint32_t i = 0; i < n; ++i)
    out[i + 1] += out[i];
  std::vector<uint32_t> fill(out.begin(), out.begin() + n);
  for (uint32_t q = 0; q < nnz; ++q)
    out[n + 1 + fill[in[pre + q]]++] = q;
  for (uint32_t i = 0; i <= n; ++i)
    out[i] += n + 1; // offsets into the same array
  return out;
}
// The delivery bitset of the current delay ring (fixture or checkpoint): one
// slot per ring slot, a bit per incoming synapse whose source spiked there.
std::vector<uint32_t> bitset(const Runtime &runtime,
                             const std::vector<uint32_t> &out, uint64_t words) {
  const auto &in = runtime.input;
  const uint32_t n = in[2], d = in[5], ring = in[29];
  std::vector<uint32_t> bits(size_t(d) * words, 0);
  for (uint32_t slot = 0; slot < d; ++slot)
    for (uint32_t i = 0; i < n; ++i)
      if (runtime.state[ring + size_t(slot) * n + i] != 0)
        for (uint32_t k = out[i]; k < out[i + 1]; ++k)
          bits[slot * words + out[k] / 32] |= 1u << (out[k] % 32);
  return bits;
}
// The first hardware adapter that creates a D3D12 device: the lane's one
// selection rule, shared with the worker's dashboard.
bool hardware_device(ComPtr<ID3D12Device> &device,
                     DXGI_ADAPTER_DESC1 &description) {
  ComPtr<IDXGIFactory4> factory;
  check(CreateDXGIFactory1(IID_PPV_ARGS(&factory)), "DXGI factory");
  ComPtr<IDXGIAdapter1> adapter;
  for (UINT i = 0; factory->EnumAdapters1(i, &adapter) != DXGI_ERROR_NOT_FOUND;
       ++i) {
    check(adapter->GetDesc1(&description), "adapter description");
    if (!(description.Flags & DXGI_ADAPTER_FLAG_SOFTWARE) &&
        SUCCEEDED(D3D12CreateDevice(adapter.Get(), D3D_FEATURE_LEVEL_11_0,
                                    IID_PPV_ARGS(&device))))
      return true;
    adapter.Reset();
  }
  return false;
}
} // namespace
std::wstring hardware_adapter() {
  ComPtr<ID3D12Device> device;
  DXGI_ADAPTER_DESC1 description{};
  return hardware_device(device, description) ? description.Description
                                              : std::wstring();
}
void advance_gpu(Runtime &runtime, uint32_t target, const std::string &shader,
                 const std::function<bool(uint32_t)> &stop,
                 const std::string &expected_adapter) {
  require(target >= runtime.step && target <= runtime.input[3],
          "invalid GPU target");
  // The shader implements version 1 only: graded neurons and coupled groups
  // would need hardware qualification of their float64 paths first (#39).
  require(runtime.input[1] == 1,
          "BLOCKED: graded and electrical synapses are not in the GPU lane");
  if (target == runtime.step)
    return;
  const uint32_t n = runtime.input[2];
  const auto groups = (uint64_t(n) + 63) / 64;
  require(groups <= 65535, "GPU fixture exceeds dispatch limit");
  ComPtr<ID3D12Device> device;
  DXGI_ADAPTER_DESC1 description{};
  require(hardware_device(device, description),
          "BLOCKED: hardware D3D12 adapter required");
  if (!expected_adapter.empty())
    require(std::wstring(description.Description) ==
                std::wstring(expected_adapter.begin(), expected_adapter.end()),
            "BLOCKED: unexpected GPU adapter identity");
  D3D12_FEATURE_DATA_D3D12_OPTIONS options{};
  check(device->CheckFeatureSupport(D3D12_FEATURE_D3D12_OPTIONS, &options,
                                    sizeof(options)),
        "GPU capabilities");
  require(
      options.DoublePrecisionFloatShaderOps,
      "BLOCKED: ordered double-kick shader needs hardware double precision");
  std::wcout << L"adapter " << description.Description << L"\n";
  D3D12_COMMAND_QUEUE_DESC q{};
  q.Type = D3D12_COMMAND_LIST_TYPE_DIRECT;
  ComPtr<ID3D12CommandQueue> queue;
  check(device->CreateCommandQueue(&q, IID_PPV_ARGS(&queue)), "queue");
  ComPtr<ID3D12CommandAllocator> allocator;
  check(device->CreateCommandAllocator(q.Type, IID_PPV_ARGS(&allocator)),
        "allocator");
  ComPtr<ID3D12GraphicsCommandList> list;
  check(device->CreateCommandList(0, q.Type, allocator.Get(), nullptr,
                                  IID_PPV_ARGS(&list)),
        "command list");
  ComPtr<ID3D12Fence> fence;
  check(device->CreateFence(0, D3D12_FENCE_FLAG_NONE, IID_PPV_ARGS(&fence)),
        "fence");
  Event event;
  D3D12_ROOT_PARAMETER parameters[5]{};
  parameters[0].ParameterType = D3D12_ROOT_PARAMETER_TYPE_32BIT_CONSTANTS;
  parameters[0].Constants = {0, 0, 3};
  parameters[1].ParameterType = D3D12_ROOT_PARAMETER_TYPE_SRV;
  parameters[1].Descriptor = {0, 0};
  parameters[2].ParameterType = D3D12_ROOT_PARAMETER_TYPE_UAV;
  parameters[2].Descriptor = {0, 0};
  parameters[3].ParameterType = D3D12_ROOT_PARAMETER_TYPE_SRV;
  parameters[3].Descriptor = {1, 0};
  parameters[4].ParameterType = D3D12_ROOT_PARAMETER_TYPE_UAV;
  parameters[4].Descriptor = {1, 0};
  D3D12_ROOT_SIGNATURE_DESC root_desc{};
  root_desc.NumParameters = 5;
  root_desc.pParameters = parameters;
  ComPtr<ID3DBlob> signature, error;
  check(D3D12SerializeRootSignature(&root_desc, D3D_ROOT_SIGNATURE_VERSION_1,
                                    &signature, &error),
        "serialize root");
  ComPtr<ID3D12RootSignature> root;
  check(device->CreateRootSignature(0, signature->GetBufferPointer(),
                                    signature->GetBufferSize(),
                                    IID_PPV_ARGS(&root)),
        "root");
  std::ifstream shader_file(shader, std::ios::binary);
  require(bool(shader_file), "missing shader");
  std::vector<char> bytecode((std::istreambuf_iterator<char>(shader_file)), {});
  require(!bytecode.empty(), "empty shader");
  D3D12_COMPUTE_PIPELINE_STATE_DESC pipeline_desc{};
  pipeline_desc.pRootSignature = root.Get();
  pipeline_desc.CS = {bytecode.data(), bytecode.size()};
  ComPtr<ID3D12PipelineState> pipeline;
  check(device->CreateComputePipelineState(&pipeline_desc,
                                           IID_PPV_ARGS(&pipeline)),
        "pipeline");
  const auto bytes = runtime.state.size() * 4;
  // Event-driven delivery, exact: a spiking neuron sets the bit of each of its
  // outgoing synapses (by position q in the target's incoming CSR) in the slot
  // of its delay ring; a target sums the weights of its set bits in ascending
  // q, the order and float sequence of the pull loop, and clears only its own
  // bits.
  const auto words = (uint64_t(runtime.input[runtime.input[16] + n]) + 31) / 32;
  require(uint64_t(runtime.input[5]) * words * 4 <= max_bytes,
          "delivery bitset exceeds the native buffer budget");
  const auto outgoing = outgoing_synapses(runtime);
  const auto active_words = bitset(runtime, outgoing, words);
  // Inputs live in a default heap: an upload heap is read uncached every tick.
  auto inputs_upload =
      buffer(device.Get(), runtime.input.size() * 4, D3D12_HEAP_TYPE_UPLOAD,
             D3D12_RESOURCE_STATE_GENERIC_READ);
  auto inputs = buffer(device.Get(), runtime.input.size() * 4,
                       D3D12_HEAP_TYPE_DEFAULT, D3D12_RESOURCE_STATE_COPY_DEST);
  auto outs_upload =
      buffer(device.Get(), outgoing.size() * 4, D3D12_HEAP_TYPE_UPLOAD,
             D3D12_RESOURCE_STATE_GENERIC_READ);
  auto outs = buffer(device.Get(), outgoing.size() * 4, D3D12_HEAP_TYPE_DEFAULT,
                     D3D12_RESOURCE_STATE_COPY_DEST);
  auto active_upload =
      buffer(device.Get(), active_words.size() * 4, D3D12_HEAP_TYPE_UPLOAD,
             D3D12_RESOURCE_STATE_GENERIC_READ);
  auto active =
      buffer(device.Get(), active_words.size() * 4, D3D12_HEAP_TYPE_DEFAULT,
             D3D12_RESOURCE_STATE_COPY_DEST, true);
  auto initial = buffer(device.Get(), bytes, D3D12_HEAP_TYPE_UPLOAD,
                        D3D12_RESOURCE_STATE_GENERIC_READ);
  auto state = buffer(device.Get(), bytes, D3D12_HEAP_TYPE_DEFAULT,
                      D3D12_RESOURCE_STATE_COPY_DEST, true);
  auto readback = buffer(device.Get(), bytes, D3D12_HEAP_TYPE_READBACK,
                         D3D12_RESOURCE_STATE_COPY_DEST);
  upload(inputs_upload.Get(), runtime.input);
  upload(outs_upload.Get(), outgoing);
  upload(active_upload.Get(), active_words);
  upload(initial.Get(), runtime.state);
  uint64_t serial = 0;
  bool in_flight = false;
  auto submit = [&]() {
    check(list->Close(), "close list");
    ID3D12CommandList *lists[] = {list.Get()};
    in_flight = true;
    queue->ExecuteCommandLists(1, lists);
    check(queue->Signal(fence.Get(), ++serial), "signal");
    check(fence->SetEventOnCompletion(serial, event.value), "arm completion");
    const auto begin = GetTickCount64();
    while (fence->GetCompletedValue() < serial) {
      check(device->GetDeviceRemovedReason(), "device removed");
      require(GetTickCount64() - begin < 30000, "GPU fence timeout");
      const auto result = WaitForSingleObjectEx(event.value, 250, FALSE);
      require(result == WAIT_OBJECT_0 || result == WAIT_TIMEOUT,
              "GPU wait failed");
    }
    require(fence->GetCompletedValue() != UINT64_MAX, "device removed fence");
    in_flight = false;
    check(allocator->Reset(), "reset allocator");
    check(list->Reset(allocator.Get(), pipeline.Get()), "reset list");
  };
  uint32_t completed = runtime.step;
  try {
    list->CopyBufferRegion(state.Get(), 0, initial.Get(), 0, bytes);
    transition(list.Get(), state.Get(), D3D12_RESOURCE_STATE_COPY_DEST,
               D3D12_RESOURCE_STATE_UNORDERED_ACCESS);
    list->CopyBufferRegion(inputs.Get(), 0, inputs_upload.Get(), 0,
                           runtime.input.size() * 4);
    transition(list.Get(), inputs.Get(), D3D12_RESOURCE_STATE_COPY_DEST,
               D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE);
    list->CopyBufferRegion(outs.Get(), 0, outs_upload.Get(), 0,
                           outgoing.size() * 4);
    transition(list.Get(), outs.Get(), D3D12_RESOURCE_STATE_COPY_DEST,
               D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE);
    list->CopyBufferRegion(active.Get(), 0, active_upload.Get(), 0,
                           active_words.size() * 4);
    transition(list.Get(), active.Get(), D3D12_RESOURCE_STATE_COPY_DEST,
               D3D12_RESOURCE_STATE_UNORDERED_ACCESS);
    for (uint32_t tick = runtime.step; tick < target;) {
      const auto end = std::min(target, tick + 64);
      list->SetComputeRootSignature(root.Get());
      list->SetPipelineState(pipeline.Get());
      list->SetComputeRootShaderResourceView(1, inputs->GetGPUVirtualAddress());
      list->SetComputeRootUnorderedAccessView(2, state->GetGPUVirtualAddress());
      list->SetComputeRootShaderResourceView(3, outs->GetGPUVirtualAddress());
      list->SetComputeRootUnorderedAccessView(4,
                                              active->GetGPUVirtualAddress());
      for (; tick < end; ++tick)
        for (uint32_t phase = 0; phase < 4; ++phase) {
          const uint32_t constants[] = {tick, phase, uint32_t(words)};
          list->SetComputeRoot32BitConstants(0, 3, constants, 0);
          list->Dispatch(UINT(groups), 1, 1);
          D3D12_RESOURCE_BARRIER barrier{};
          barrier.Type = D3D12_RESOURCE_BARRIER_TYPE_UAV;
          barrier.UAV.pResource = nullptr; // state and the delivery bitset
          list->ResourceBarrier(1, &barrier);
        }
      submit();
      completed = tick;
      if (stop && stop(completed))
        break;
    }
    transition(list.Get(), state.Get(), D3D12_RESOURCE_STATE_UNORDERED_ACCESS,
               D3D12_RESOURCE_STATE_COPY_SOURCE);
    list->CopyBufferRegion(readback.Get(), 0, state.Get(), 0, bytes);
    submit();
    void *memory = nullptr;
    D3D12_RANGE range{0, bytes};
    check(readback->Map(0, &range, &memory), "readback map");
    std::memcpy(runtime.state.data(), memory, bytes);
    D3D12_RANGE written{0, 0};
    readback->Unmap(0, &written);
    runtime.step = completed;
  } catch (...) {
    // Quarantine resources referenced by an uncompleted submission. The process
    // host must exit/restart after this fault; releasing them can block
    // forever.
    if (in_flight) {
      inputs.Detach();
      inputs_upload.Detach();
      outs.Detach();
      outs_upload.Detach();
      active.Detach();
      active_upload.Detach();
      initial.Detach();
      state.Detach();
      readback.Detach();
      pipeline.Detach();
      root.Detach();
      fence.Detach();
      list.Detach();
      allocator.Detach();
      queue.Detach();
      device.Detach();
      throw GpuFault("GPU runtime quarantined; restart the worker process");
    }
    throw;
  }
}
} // namespace flymsg
