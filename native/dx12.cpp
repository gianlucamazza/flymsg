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
} // namespace
void advance_gpu(Runtime &runtime, uint32_t target, const std::string &shader,
                 const std::function<bool(uint32_t)> &stop,
                 const std::string &expected_adapter) {
  require(target >= runtime.step && target <= runtime.input[3],
          "invalid GPU target");
  if (target == runtime.step)
    return;
  const auto groups = (uint64_t(runtime.input[2]) + 63) / 64;
  require(groups <= 65535, "GPU fixture exceeds dispatch limit");
  ComPtr<IDXGIFactory4> factory;
  check(CreateDXGIFactory1(IID_PPV_ARGS(&factory)), "DXGI factory");
  ComPtr<IDXGIAdapter1> adapter;
  ComPtr<ID3D12Device> device;
  DXGI_ADAPTER_DESC1 description{};
  for (UINT i = 0; factory->EnumAdapters1(i, &adapter) != DXGI_ERROR_NOT_FOUND;
       ++i) {
    check(adapter->GetDesc1(&description), "adapter description");
    if (!(description.Flags & DXGI_ADAPTER_FLAG_SOFTWARE) &&
        SUCCEEDED(D3D12CreateDevice(adapter.Get(), D3D_FEATURE_LEVEL_11_0,
                                    IID_PPV_ARGS(&device))))
      break;
    adapter.Reset();
  }
  require(bool(device), "BLOCKED: hardware D3D12 adapter required");
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
  D3D12_ROOT_PARAMETER parameters[3]{};
  parameters[0].ParameterType = D3D12_ROOT_PARAMETER_TYPE_32BIT_CONSTANTS;
  parameters[0].Constants = {0, 0, 2};
  parameters[1].ParameterType = D3D12_ROOT_PARAMETER_TYPE_SRV;
  parameters[1].Descriptor = {0, 0};
  parameters[2].ParameterType = D3D12_ROOT_PARAMETER_TYPE_UAV;
  parameters[2].Descriptor = {0, 0};
  D3D12_ROOT_SIGNATURE_DESC root_desc{};
  root_desc.NumParameters = 3;
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
  auto inputs =
      buffer(device.Get(), runtime.input.size() * 4, D3D12_HEAP_TYPE_UPLOAD,
             D3D12_RESOURCE_STATE_GENERIC_READ);
  auto initial = buffer(device.Get(), bytes, D3D12_HEAP_TYPE_UPLOAD,
                        D3D12_RESOURCE_STATE_GENERIC_READ);
  auto state = buffer(device.Get(), bytes, D3D12_HEAP_TYPE_DEFAULT,
                      D3D12_RESOURCE_STATE_COPY_DEST, true);
  auto readback = buffer(device.Get(), bytes, D3D12_HEAP_TYPE_READBACK,
                         D3D12_RESOURCE_STATE_COPY_DEST);
  upload(inputs.Get(), runtime.input);
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
    for (uint32_t tick = runtime.step; tick < target;) {
      const auto end = std::min(target, tick + 64);
      list->SetComputeRootSignature(root.Get());
      list->SetPipelineState(pipeline.Get());
      list->SetComputeRootShaderResourceView(1, inputs->GetGPUVirtualAddress());
      list->SetComputeRootUnorderedAccessView(2, state->GetGPUVirtualAddress());
      for (; tick < end; ++tick)
        for (uint32_t phase = 0; phase < 4; ++phase) {
          const uint32_t constants[] = {tick, phase};
          list->SetComputeRoot32BitConstants(0, 2, constants, 0);
          list->Dispatch(UINT(groups), 1, 1);
          D3D12_RESOURCE_BARRIER barrier{};
          barrier.Type = D3D12_RESOURCE_BARRIER_TYPE_UAV;
          barrier.UAV.pResource = state.Get();
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
