// Minimal CoreApplication worker; no rendering clock participates in
// simulation.
#include "../dx12.h"
#include <atomic>
#include <bcrypt.h>
#include <chrono>
#include <iomanip>
#include <mutex>
#include <sstream>
#include <thread>
#include <winrt/Windows.ApplicationModel.Activation.h>
#include <winrt/Windows.ApplicationModel.Core.h>
#include <winrt/Windows.ApplicationModel.h>
#include <winrt/Windows.Data.Json.h>
#include <winrt/Windows.Foundation.Collections.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Storage.h>
#include <winrt/Windows.System.h>
#include <winrt/Windows.UI.Core.h>

using namespace winrt;
using namespace Windows::ApplicationModel;
using namespace Windows::ApplicationModel::Core;
using namespace Windows::Data::Json;
using namespace Windows::Storage;
using namespace Windows::UI::Core;
namespace fs = std::filesystem;
namespace {
std::string sha256(const fs::path &path) {
  std::ifstream file(path, std::ios::binary);
  flymsg::require(bool(file), "missing hash asset");
  BCRYPT_ALG_HANDLE algorithm = nullptr;
  BCRYPT_HASH_HANDLE hash = nullptr;
  unsigned char result[32]{};
  flymsg::require(BCryptOpenAlgorithmProvider(
                      &algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0) >= 0,
                  "SHA256 provider");
  if (BCryptCreateHash(algorithm, &hash, nullptr, 0, nullptr, 0, 0) < 0) {
    BCryptCloseAlgorithmProvider(algorithm, 0);
    throw std::runtime_error("SHA256 context");
  }
  try {
    std::vector<char> chunk(1 << 20);
    while (file.read(chunk.data(), chunk.size()) || file.gcount())
      flymsg::require(BCryptHashData(hash,
                                     reinterpret_cast<PUCHAR>(chunk.data()),
                                     ULONG(file.gcount()), 0) >= 0,
                      "SHA256 update");
    flymsg::require(!file.bad() && BCryptFinishHash(hash, result, 32, 0) >= 0,
                    "SHA256 final");
  } catch (...) {
    BCryptDestroyHash(hash);
    BCryptCloseAlgorithmProvider(algorithm, 0);
    throw;
  }
  BCryptDestroyHash(hash);
  BCryptCloseAlgorithmProvider(algorithm, 0);
  std::ostringstream out;
  out << std::hex << std::setfill('0');
  for (auto b : result)
    out << std::setw(2) << unsigned(b);
  return out.str();
}
JsonObject read_json(const fs::path &path) {
  flymsg::require(fs::file_size(path) < 1024 * 1024, "job JSON too large");
  std::ifstream file(path, std::ios::binary);
  std::string raw((std::istreambuf_iterator<char>(file)), {});
  return JsonObject::Parse(to_hstring(raw));
}
void write_json(const fs::path &path, const JsonObject &doc) {
  auto tmp = path;
  tmp += ".tmp";
  std::ofstream file(tmp, std::ios::binary | std::ios::trunc);
  const auto text = to_string(doc.Stringify());
  file.write(text.data(), std::streamsize(text.size()));
  file.close();
  flymsg::require(bool(file) && MoveFileExW(tmp.c_str(), path.c_str(),
                                            MOVEFILE_REPLACE_EXISTING |
                                                MOVEFILE_WRITE_THROUGH),
                  "status atomic replacement");
}
std::string field(const JsonObject &doc, const wchar_t *name) {
  return to_string(doc.GetNamedString(name));
}
struct App : implements<App, IFrameworkViewSource, IFrameworkView> {
  CoreWindow window{nullptr};
  std::atomic<bool> shutdown{false}, suspended{false};
  std::thread worker;
  std::mutex mutex;
  SuspendingDeferral deferral{nullptr};
  fs::path root;
  IFrameworkView CreateView() { return *this; }
  void Initialize(CoreApplicationView const &view) {
    view.Activated([this](auto const &, auto const &) { window.Activate(); });
    CoreApplication::Suspending(
        [this](auto const &, SuspendingEventArgs const &args) {
          std::lock_guard guard(mutex);
          deferral = args.SuspendingOperation().GetDeferral();
          suspended = true;
        });
    CoreApplication::Resuming(
        [this](auto const &, auto const &) { suspended = false; });
  }
  void SetWindow(CoreWindow const &value) {
    window = value;
    window.Closed([this](auto const &, auto const &) { shutdown = true; });
  }
  void Load(hstring const &) {}
  void finish_deferral() {
    std::lock_guard guard(mutex);
    if (deferral) {
      deferral.Complete();
      deferral = nullptr;
    }
  }
  void Run() {
    root = fs::path(ApplicationData::Current().LocalFolder().Path().c_str());
    fs::create_directories(root / L"inbox");
    worker = std::thread([this] {
      init_apartment(apartment_type::multi_threaded);
      loop();
      uninit_apartment();
    });
    while (!shutdown)
      window.Dispatcher().ProcessEvents(
          CoreProcessEventsOption::ProcessOneAndAllPending);
  }
  void Uninitialize() {
    shutdown = true;
    if (worker.joinable())
      worker.join();
    finish_deferral();
  }
  void status(const fs::path &folder, const std::string &id,
              const std::string &phase, uint32_t step,
              const std::string &error = "") {
    JsonObject doc;
    doc.Insert(L"schema",
               JsonValue::CreateStringValue(L"flymsg.worker_status/v1"));
    doc.Insert(L"job_id", JsonValue::CreateStringValue(to_hstring(id)));
    doc.Insert(L"state", JsonValue::CreateStringValue(to_hstring(phase)));
    doc.Insert(L"step", JsonValue::CreateNumberValue(step));
    doc.Insert(L"error", JsonValue::CreateStringValue(to_hstring(error)));
    doc.Insert(L"source_commit",
               JsonValue::CreateStringValue(to_hstring(FLYMSG_COMMIT)));
    doc.Insert(L"app_memory_bytes",
               JsonValue::CreateNumberValue(
                   double(Windows::System::MemoryManager::AppMemoryUsage())));
    doc.Insert(L"app_memory_limit_bytes",
               JsonValue::CreateNumberValue(double(
                   Windows::System::MemoryManager::AppMemoryUsageLimit())));
    write_json(folder / L"status.json", doc);
  }
  bool cancelled(const fs::path &folder, const std::string &id) {
    if (!fs::exists(folder / L"cancel.json"))
      return false;
    auto doc = read_json(folder / L"cancel.json");
    return field(doc, L"schema") == "flymsg.worker_cancel/v1" &&
           field(doc, L"job_id") == id;
  }
  void execute(const fs::path &folder) {
    const auto doc = read_json(folder / L"job.json");
    const auto id = field(doc, L"job_id");
    flymsg::require(id == folder.filename().string(),
                    "job directory identity mismatch");
    status(folder, id, "validating", 0);
    flymsg::require(field(doc, L"schema") == "flymsg.neural_job/v1" &&
                        field(doc, L"semantics") == "flymsg.lif/ordered-f32-v1",
                    "incompatible job contract");
    const auto fixture = folder / L"fixture.bin";
    const auto backend = field(doc, L"backend");
    const auto hash = sha256(fixture);
    flymsg::require(hash == field(doc, L"fixture_sha256"),
                    "fixture hash mismatch");
    const auto shader = fs::path(Windows::ApplicationModel::Package::Current()
                                     .InstalledLocation()
                                     .Path()
                                     .c_str()) /
                        L"Assets/lif.cso";
    flymsg::require(backend == "cpu" || backend == "dx12", "unknown backend");
    if (backend == "dx12")
      flymsg::require(sha256(shader) == field(doc, L"shader_sha256"),
                      "shader hash mismatch");
    flymsg::Runtime runtime(flymsg::read_words(fixture));
    const auto estimated = runtime.input.size() * 8ull +
                           runtime.state.size() * 16ull + 64ull * 1024 * 1024;
    const auto limit = Windows::System::MemoryManager::AppMemoryUsageLimit();
    const auto usage = Windows::System::MemoryManager::AppMemoryUsage();
    flymsg::require(limit > usage && estimated < limit - usage,
                    "job exceeds available app memory budget");
    if (fs::exists(folder / L"checkpoint.bin")) {
      const auto saved = read_json(folder / L"checkpoint.json");
      flymsg::require(field(saved, L"fixture_sha256") == hash &&
                          field(saved, L"backend") == backend &&
                          field(saved, L"source_commit") == FLYMSG_COMMIT &&
                          field(saved, L"package") ==
                              to_string(Package::Current().Id().FullName()),
                      "checkpoint package/backend identity mismatch");
      flymsg::require(field(saved, L"checkpoint_sha256") ==
                          sha256(folder / L"checkpoint.bin"),
                      "checkpoint SHA256 mismatch");
      if (backend == "dx12")
        flymsg::require(field(saved, L"shader_sha256") == sha256(shader),
                        "checkpoint shader mismatch");
      runtime.restore(folder / L"checkpoint.bin");
    }
    const auto stop = [&](uint32_t cursor) {
      status(folder, id, "running", cursor);
      return shutdown || suspended || cancelled(folder, id);
    };
    if (backend == "dx12") {
      const auto adapter = field(doc, L"expected_adapter");
      flymsg::require(!adapter.empty(), "GPU job requires adapter identity");
      flymsg::advance_gpu(runtime, runtime.input[3], shader.string(), stop,
                          adapter);
    } else
      while (runtime.step < runtime.input[3]) {
        runtime.advance_to(std::min(runtime.input[3], runtime.step + 64));
        if (stop(runtime.step))
          break;
      }
    status(folder, id, "checkpointing", runtime.step);
    runtime.checkpoint(folder / L"checkpoint.bin");
    JsonObject saved;
    saved.Insert(L"fixture_sha256",
                 JsonValue::CreateStringValue(to_hstring(hash)));
    saved.Insert(L"backend", JsonValue::CreateStringValue(to_hstring(backend)));
    saved.Insert(L"source_commit",
                 JsonValue::CreateStringValue(to_hstring(FLYMSG_COMMIT)));
    saved.Insert(L"package", JsonValue::CreateStringValue(
                                 Package::Current().Id().FullName()));
    saved.Insert(L"checkpoint_sha256",
                 JsonValue::CreateStringValue(
                     to_hstring(sha256(folder / L"checkpoint.bin"))));
    saved.Insert(L"shader_sha256",
                 JsonValue::CreateStringValue(
                     to_hstring(backend == "dx12" ? sha256(shader) : "")));
    write_json(folder / L"checkpoint.json", saved);
    if (runtime.step == runtime.input[3]) {
      runtime.snapshot(folder / L"output.bin");
      JsonObject result;
      result.Insert(L"output_sha256", JsonValue::CreateStringValue(to_hstring(
                                          sha256(folder / L"output.bin"))));
      result.Insert(L"fixture_sha256",
                    JsonValue::CreateStringValue(to_hstring(hash)));
      result.Insert(L"backend",
                    JsonValue::CreateStringValue(to_hstring(backend)));
      write_json(folder / L"result.json", result);
      status(folder, id, "completed", runtime.step);
    } else {
      status(folder, id, suspended ? "suspended" : "cancelled", runtime.step);
    }
  }
  void loop() {
    while (!shutdown) {
      if (suspended) {
        finish_deferral();
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
        continue;
      }
      for (auto const &entry : fs::directory_iterator(root / L"inbox")) {
        if (shutdown || suspended)
          break;
        if (!entry.is_directory())
          continue;
        const auto folder = entry.path();
        if (!fs::exists(folder / L"job.json"))
          continue;
        try {
          if (fs::exists(folder / L"status.json")) {
            const auto prior =
                field(read_json(folder / L"status.json"), L"state");
            if (prior == "completed" || prior == "failed" ||
                prior == "cancelled")
              continue;
            if ((prior == "suspended" || prior == "awaiting_recovery") &&
                !fs::exists(folder / L"resume.json"))
              continue;
            if (prior == "running" || prior == "checkpointing") {
              if (!fs::exists(folder / L"resume.json")) {
                status(folder, folder.filename().string(), "awaiting_recovery",
                       0, "explicit recovery required after interruption");
                continue;
              }
            }
          }
          if (fs::exists(folder / L"resume.json")) {
            auto resume = read_json(folder / L"resume.json");
            flymsg::require(
                field(resume, L"schema") == "flymsg.worker_resume/v1" &&
                    field(resume, L"job_id") == folder.filename().string(),
                "resume identity mismatch");
            fs::remove(folder / L"resume.json");
          }
          execute(folder);
        } catch (flymsg::GpuFault const &error) {
          try {
            status(folder, folder.filename().string(), "failed", 0,
                   error.what());
          } catch (...) {
          }
          ExitProcess(1);
        } catch (std::exception const &error) {
          try {
            status(folder, folder.filename().string(), "failed", 0,
                   error.what());
          } catch (...) {
          }
        } catch (hresult_error const &error) {
          try {
            status(folder, folder.filename().string(), "failed", 0,
                   to_string(error.message()));
          } catch (...) {
          }
        }
        finish_deferral();
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(250));
    }
    finish_deferral();
  }
};
} // namespace
int __stdcall wWinMain(HINSTANCE, HINSTANCE, PWSTR, int) {
  init_apartment(apartment_type::single_threaded);
  CoreApplication::Run(make<App>());
}
