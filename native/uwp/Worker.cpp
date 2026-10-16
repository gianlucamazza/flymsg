// XAML-hosted worker; no rendering clock participates in simulation. The job
// loop runs on its own thread and publishes a telemetry copy; the dashboard
// reads that copy on a UI timer and never touches a job's state.
#include "../dx12.h"
#include "App.h"
// the generated implementation needs App.h first; kept apart so include
// sorting cannot reorder it
#include "App.g.cpp"

#include <algorithm>
#include <atomic>
#include <bcrypt.h>
#include <chrono>
#include <iomanip>
#include <memory>
#include <mutex>
#include <optional>
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
#include <winrt/Windows.UI.Xaml.Controls.Primitives.h>
#include <winrt/Windows.UI.Xaml.Media.h>
#include <winrt/Windows.UI.Xaml.Shapes.h>
#include <winrt/Windows.UI.h>

using namespace winrt;
using namespace Windows::ApplicationModel;
using namespace Windows::ApplicationModel::Core;
using namespace Windows::Data::Json;
using namespace Windows::Storage;
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
// retries: 20 ms attempts at replacing a file a reader holds open
void write_json(const fs::path &path, const JsonObject &doc, int retries = 50) {
  auto tmp = path;
  tmp += ".tmp";
  std::ofstream file(tmp, std::ios::binary | std::ios::trunc);
  const auto text = to_string(doc.Stringify());
  file.write(text.data(), std::streamsize(text.size()));
  file.close();
  flymsg::require(bool(file), "status temporary write");
  // A reader (Device Portal fetching the file) briefly holds it open and the
  // replacement fails with a sharing error; retry (a second by default).
  for (int attempt = 0;; ++attempt) {
    if (MoveFileExW(tmp.c_str(), path.c_str(),
                    MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH))
      return;
    const auto error = GetLastError();
    if (!(error == ERROR_SHARING_VIOLATION || error == ERROR_ACCESS_DENIED ||
          error == ERROR_LOCK_VIOLATION) ||
        attempt >= retries)
      throw std::runtime_error("status atomic replacement, Win32 error " +
                               std::to_string(error));
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
  }
}
// Device Portal uploads are not atomic: a control file may be seen empty or
// partial. One that does not parse yet and was written in the last 10 s is
// still arriving and is read on a later pass; older, it is malformed.
std::optional<JsonObject> try_read(const fs::path &path) {
  try {
    return read_json(path);
  } catch (...) {
    return std::nullopt;
  }
}
bool arriving(const fs::path &path) {
  if (try_read(path))
    return false;
  try {
    return fs::file_time_type::clock::now() - fs::last_write_time(path) <
           std::chrono::seconds(10);
  } catch (...) {
    return true;
  }
}
std::string field(const JsonObject &doc, const wchar_t *name) {
  return to_string(doc.GetNamedString(name));
}
// What the dashboard shows: a copy the job thread replaces under a lock.
struct Telemetry {
  struct Done {
    std::string id, outcome;
    double advance_ms = 0;
    uint32_t steps = 0;
  };
  std::string job, state = "idle", error;
  fs::path folder;
  uint32_t step = 0, total = 0;
  double rate = 0, memory = 0, limit = 0;
  std::vector<Done> history; // newest first, at most 8
  std::vector<double> bins;  // spikes per count bin of the last completed job
  std::vector<std::pair<uint32_t, uint32_t>> top; // (neuron row, spikes)
  uint64_t activity_generation = 0; // bumped for each completed job
};
struct Worker {
  std::atomic<bool> shutdown{false}, suspended{false}, started{false};
  std::mutex mutex, telemetry_mutex;
  Telemetry telemetry;
  std::chrono::steady_clock::time_point rate_at{};
  uint32_t rate_step = 0;
  Telemetry snapshot() {
    std::lock_guard guard(telemetry_mutex);
    return telemetry;
  }
  void finished(const std::string &id, const std::string &outcome,
                double advance_ms, uint32_t steps) {
    std::lock_guard guard(telemetry_mutex);
    auto &h = telemetry.history;
    h.insert(h.begin(), {id, outcome, advance_ms, steps});
    if (h.size() > 8)
      h.pop_back();
  }
  // Spikes per count bin and the ten most active neurons, from the counts the
  // completed job holds (bin-major, as flymsg.native.read_output decodes them).
  void activity(const flymsg::Runtime &runtime) {
    const auto &in = runtime.input;
    const uint32_t n = in[2], bins = in[3] / in[4], at = in[30];
    std::vector<double> per_bin(bins, 0.0);
    std::vector<uint32_t> per_neuron(n, 0);
    for (uint32_t b = 0; b < bins; ++b)
      for (uint32_t i = 0; i < n; ++i) {
        const auto c = runtime.state[at + size_t(b) * n + i];
        per_bin[b] += c;
        per_neuron[i] += c;
      }
    std::vector<std::pair<uint32_t, uint32_t>> top;
    for (uint32_t i = 0; i < n; ++i)
      if (per_neuron[i])
        top.push_back({i, per_neuron[i]});
    const auto keep = std::min<size_t>(10, top.size());
    std::partial_sort(top.begin(), top.begin() + keep, top.end(),
                      [](auto &a, auto &b) { return a.second > b.second; });
    top.resize(keep);
    std::lock_guard guard(telemetry_mutex);
    telemetry.bins = std::move(per_bin);
    telemetry.top = std::move(top);
    ++telemetry.activity_generation;
  }
  SuspendingDeferral deferral{nullptr};
  fs::path root;
  void suspend(SuspendingEventArgs const &args) {
    std::lock_guard guard(mutex);
    deferral = args.SuspendingOperation().GetDeferral();
    suspended = true;
  }
  void finish_deferral() {
    std::lock_guard guard(mutex);
    if (deferral) {
      deferral.Complete();
      deferral = nullptr;
    }
  }
  void start() {
    if (started.exchange(true))
      return;
    root = fs::path(ApplicationData::Current().LocalFolder().Path().c_str());
    fs::create_directories(root / L"inbox");
    // detached: the process ends with the app; a suspension stops at a boundary
    std::thread([this] {
      init_apartment(apartment_type::multi_threaded);
      loop();
      uninit_apartment();
    }).detach();
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
    // the batch outputs this worker writes: a host asking for one it does not
    // list is talking to an older worker and stops the job
    JsonArray outputs;
    outputs.Append(JsonValue::CreateStringValue(L"state"));
    outputs.Append(JsonValue::CreateStringValue(L"counts"));
    doc.Insert(L"batch_outputs", outputs);
    doc.Insert(L"app_memory_bytes",
               JsonValue::CreateNumberValue(
                   double(Windows::System::MemoryManager::AppMemoryUsage())));
    doc.Insert(L"app_memory_limit_bytes",
               JsonValue::CreateNumberValue(double(
                   Windows::System::MemoryManager::AppMemoryUsageLimit())));
    // inside a suspending deferral the platform's deadline matters more
    write_json(folder / L"status.json", doc, suspended ? 10 : 50);
    std::lock_guard guard(telemetry_mutex);
    auto &t = telemetry;
    const auto now = std::chrono::steady_clock::now();
    if (t.job != id || phase != "running") {
      rate_at = now;
      rate_step = step;
    } else if (now - rate_at >= std::chrono::seconds(1)) {
      // steps per second over the last second or more, smoothed
      const double fresh = (step - rate_step) /
                           std::chrono::duration<double>(now - rate_at).count();
      t.rate = t.rate > 0 ? 0.7 * t.rate + 0.3 * fresh : fresh;
      rate_at = now;
      rate_step = step;
    }
    if (t.job != id)
      t.rate = 0;
    t.job = id;
    t.folder = folder;
    t.state = phase;
    t.step = step;
    t.error = error;
    t.memory = double(Windows::System::MemoryManager::AppMemoryUsage());
    t.limit = double(Windows::System::MemoryManager::AppMemoryUsageLimit());
  }
  // The gamepad's cancel: the same flymsg.worker_cancel/v1 file a host would
  // upload, so a cancel takes the protocol's one path. Called on the UI thread:
  // it never throws and never waits long, so a failed write leaves the job
  // running rather than ending the app.
  void request_cancel() noexcept {
    try {
      const auto t = snapshot();
      if (t.state != "running" || t.folder.empty())
        return;
      JsonObject doc;
      doc.Insert(L"schema",
                 JsonValue::CreateStringValue(L"flymsg.worker_cancel/v1"));
      doc.Insert(L"job_id", JsonValue::CreateStringValue(to_hstring(t.job)));
      write_json(t.folder / L"cancel.json", doc, 5);
    } catch (...) {
    }
  }
  bool cancelled(const fs::path &folder, const std::string &id) {
    if (!fs::exists(folder / L"cancel.json"))
      return false;
    // parsed once: a cancel still uploading is seen on a later check
    const auto doc = try_read(folder / L"cancel.json");
    return doc && field(*doc, L"schema") == "flymsg.worker_cancel/v1" &&
           field(*doc, L"job_id") == id;
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
    if (doc.HasKey(L"batch")) {
      execute_batch(folder, doc, id, hash, backend, shader);
      return;
    }
    flymsg::Runtime runtime(flymsg::read_words(fixture));
    {
      std::lock_guard guard(telemetry_mutex);
      telemetry.total = runtime.input[3];
    }
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
    auto reported = std::chrono::steady_clock::now() - std::chrono::seconds(1);
    const auto stop = [&](uint32_t cursor) {
      // progress at most four times a second: each update is a file replacement
      const auto now = std::chrono::steady_clock::now();
      if (now - reported >= std::chrono::milliseconds(250)) {
        status(folder, id, "running", cursor);
        reported = now;
      }
      return shutdown || suspended || cancelled(folder, id);
    };
    // wall time and steps of this execution's advance, for throughput only
    const auto first_step = runtime.step;
    const auto began = std::chrono::steady_clock::now();
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
    const double advance_ms = std::chrono::duration<double, std::milli>(
                                  std::chrono::steady_clock::now() - began)
                                  .count();
    status(folder, id, "checkpointing", runtime.step);
    const auto published = runtime.checkpoint(folder / L"checkpoint.bin");
    if (published != "completed") {
      status(folder, id, "failed", runtime.step,
             "checkpoint temporary did not grow");
      try {
        finished(id, "failed", advance_ms, runtime.step - first_step);
      } catch (...) {
      }
      return;
    }
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
    write_json(folder / L"checkpoint.json", saved, suspended ? 10 : 50);
    if (runtime.step == runtime.input[3]) {
      runtime.snapshot(folder / L"output.bin");
      JsonObject result;
      result.Insert(L"output_sha256", JsonValue::CreateStringValue(to_hstring(
                                          sha256(folder / L"output.bin"))));
      result.Insert(L"fixture_sha256",
                    JsonValue::CreateStringValue(to_hstring(hash)));
      result.Insert(L"backend",
                    JsonValue::CreateStringValue(to_hstring(backend)));
      result.Insert(L"advance_ms", JsonValue::CreateNumberValue(advance_ms));
      result.Insert(L"advance_steps",
                    JsonValue::CreateNumberValue(runtime.step - first_step));
      write_json(folder / L"result.json", result);
      status(folder, id, "completed", runtime.step);
      try { // the dashboard's view of a valid result never fails the job
        activity(runtime);
        finished(id, "completed", advance_ms, runtime.step - first_step);
      } catch (...) {
      }
    } else {
      const auto outcome = suspended ? "suspended" : "cancelled";
      status(folder, id, outcome, runtime.step);
      try {
        finished(id, outcome, advance_ms, runtime.step - first_step);
      } catch (...) {
      }
    }
  }
  // Several runs of one network (flymsg.native.export_batch): fixture.bin is
  // the base, batch.bin the runs. They run in order; each completed run leaves
  // output_<k>.bin and result_<k>.json, and a resumed job skips those, so an
  // interruption costs at most the run it stopped. Progress counts steps over
  // the whole batch.
  void execute_batch(const fs::path &folder, const JsonObject &doc,
                     const std::string &id, const std::string &hash,
                     const std::string &backend, const fs::path &shader) {
    const auto spec = doc.GetNamedObject(L"batch");
    const auto batch_path = folder / L"batch.bin";
    flymsg::require(sha256(batch_path) == field(spec, L"sha256"),
                    "batch hash mismatch");
    const auto base = flymsg::read_words(folder / L"fixture.bin");
    const auto batch = flymsg::read_words(batch_path);
    const uint32_t runs = flymsg::batch_runs(batch);
    flymsg::require(runs == uint32_t(spec.GetNamedNumber(L"runs")),
                    "batch run count mismatch");
    // "counts" asks for the sparse readout (Runtime::counts), "state" or no key
    // for the whole state
    const auto kind =
        spec.HasKey(L"output") ? field(spec, L"output") : std::string("state");
    flymsg::require(kind == "state" || kind == "counts",
                    "unknown batch output");
    const bool sparse = kind == "counts";
    const uint64_t steps = base[3];
    {
      std::lock_guard guard(telemetry_mutex);
      telemetry.total = uint32_t(std::min<uint64_t>(steps * runs, UINT32_MAX));
    }
    auto reported = std::chrono::steady_clock::now() - std::chrono::seconds(1);
    double advance_ms = 0, prepare_ms = 0, write_ms = 0;
    uint64_t advanced = 0;
    std::optional<flymsg::Runtime> last;
    for (uint32_t k = 0; k < runs; ++k) {
      const auto name = std::to_wstring(k);
      if (fs::exists(folder / (L"result_" + name + L".json")))
        continue; // done before an interruption
      const auto prepared = std::chrono::steady_clock::now();
      flymsg::Runtime runtime(flymsg::batch_fixture(base, batch, k));
      flymsg::require(runtime.input[3] == steps, "batch runs differ in length");
      const auto estimated = (base.size() + batch.size()) * 4ull +
                             runtime.input.size() * 8ull +
                             runtime.state.size() * 16ull + 64ull * 1024 * 1024;
      const auto limit = Windows::System::MemoryManager::AppMemoryUsageLimit();
      const auto usage = Windows::System::MemoryManager::AppMemoryUsage();
      flymsg::require(limit > usage && estimated < limit - usage,
                      "batch run exceeds available app memory budget");
      const uint64_t done = k * steps;
      const auto stop = [&](uint32_t cursor) {
        const auto now = std::chrono::steady_clock::now();
        if (now - reported >= std::chrono::milliseconds(250)) {
          status(folder, id, "running",
                 uint32_t(std::min<uint64_t>(done + cursor, UINT32_MAX)));
          reported = now;
        }
        return shutdown || suspended || cancelled(folder, id);
      };
      const auto began = std::chrono::steady_clock::now();
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
      const double ms = std::chrono::duration<double, std::milli>(
                            std::chrono::steady_clock::now() - began)
                            .count();
      if (runtime.step != runtime.input[3]) { // stopped inside run k
        const auto outcome = suspended ? "suspended" : "cancelled";
        status(folder, id, outcome,
               uint32_t(std::min<uint64_t>(done + runtime.step, UINT32_MAX)));
        try {
          finished(id, outcome, advance_ms, uint32_t(advanced));
        } catch (...) {
        }
        return;
      }
      const auto written = std::chrono::steady_clock::now();
      const auto output =
          folder / ((sparse ? L"counts_" : L"output_") + name + L".bin");
      if (sparse)
        runtime.counts(output);
      else
        runtime.snapshot(output);
      JsonObject result;
      result.Insert(L"output_sha256",
                    JsonValue::CreateStringValue(to_hstring(sha256(output))));
      result.Insert(L"output", JsonValue::CreateStringValue(to_hstring(kind)));
      result.Insert(L"advance_ms", JsonValue::CreateNumberValue(ms));
      result.Insert(L"advance_steps",
                    JsonValue::CreateNumberValue(double(steps)));
      // the run's time outside the advance: rebuilding its fixture and
      // runtime, then writing and hashing its output
      const std::chrono::duration<double, std::milli>
          prepare = began - prepared,
          write = std::chrono::steady_clock::now() - written;
      result.Insert(L"prepare_ms",
                    JsonValue::CreateNumberValue(prepare.count()));
      result.Insert(L"write_ms", JsonValue::CreateNumberValue(write.count()));
      prepare_ms += prepare.count();
      write_ms += write.count();
      write_json(folder / (L"result_" + name + L".json"), result);
      advance_ms += ms;
      advanced += steps;
      if (k + 1 == runs) // only the last run's counts feed the dashboard
        last.emplace(std::move(runtime));
    }
    JsonObject result;
    result.Insert(L"runs", JsonValue::CreateNumberValue(runs));
    result.Insert(L"fixture_sha256",
                  JsonValue::CreateStringValue(to_hstring(hash)));
    result.Insert(L"batch_sha256",
                  JsonValue::CreateStringValue(spec.GetNamedString(L"sha256")));
    result.Insert(L"backend",
                  JsonValue::CreateStringValue(to_hstring(backend)));
    // this execution's advance only; per-run timings are in result_<k>.json
    result.Insert(L"advance_ms", JsonValue::CreateNumberValue(advance_ms));
    result.Insert(L"advance_steps",
                  JsonValue::CreateNumberValue(double(advanced)));
    result.Insert(L"prepare_ms", JsonValue::CreateNumberValue(prepare_ms));
    result.Insert(L"write_ms", JsonValue::CreateNumberValue(write_ms));
    result.Insert(L"output", JsonValue::CreateStringValue(to_hstring(kind)));
    write_json(folder / L"result.json", result);
    status(folder, id, "completed",
           uint32_t(std::min<uint64_t>(steps * runs, UINT32_MAX)));
    try {
      if (last)
        activity(*last);
      finished(id, "completed", advance_ms, uint32_t(advanced));
    } catch (...) {
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
          // checked after the terminal states, so finished jobs are not parsed
          if (arriving(folder / L"job.json"))
            continue;
          if (fs::exists(folder / L"resume.json")) {
            const auto resume = try_read(folder / L"resume.json");
            if (!resume && arriving(folder / L"resume.json"))
              continue;
            flymsg::require(
                resume &&
                    field(*resume, L"schema") == "flymsg.worker_resume/v1" &&
                    field(*resume, L"job_id") == folder.filename().string(),
                "resume identity mismatch");
            fs::remove(folder / L"resume.json");
          }
          execute(folder);
        } catch (flymsg::GpuFault const &error) {
          try {
            status(folder, folder.filename().string(), "failed", 0,
                   error.what());
            finished(folder.filename().string(), "failed", 0, 0);
          } catch (...) {
          }
          ExitProcess(1);
        } catch (std::exception const &error) {
          try {
            status(folder, folder.filename().string(), "failed", 0,
                   error.what());
            finished(folder.filename().string(), "failed", 0, 0);
          } catch (...) {
          }
        } catch (hresult_error const &error) {
          try {
            status(folder, folder.filename().string(), "failed", 0,
                   to_string(error.message()));
            finished(folder.filename().string(), "failed", 0, 0);
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
Worker &worker() {
  static Worker instance;
  return instance;
}
namespace xaml = Windows::UI::Xaml;
namespace controls = Windows::UI::Xaml::Controls;
xaml::Media::SolidColorBrush brush(uint8_t r, uint8_t g, uint8_t b) {
  return xaml::Media::SolidColorBrush(
      Windows::UI::ColorHelper::FromArgb(255, r, g, b));
}
controls::TextBlock label(double size,
                          xaml::Media::SolidColorBrush const &color) {
  controls::TextBlock text;
  text.FontSize(size);
  text.Foreground(color);
  text.TextWrapping(xaml::TextWrapping::Wrap);
  return text;
}
std::wstring wide(const std::string &s) { return std::wstring(to_hstring(s)); }
std::wstring fixed(double value, int digits) {
  std::wostringstream out;
  out << std::fixed << std::setprecision(digits) << value;
  return out.str();
}
std::wstring duration(double seconds) {
  if (!(seconds >= 0) || seconds > 1e7)
    return L"-";
  const auto s = uint64_t(seconds + 0.5);
  std::wostringstream out;
  if (s >= 3600)
    out << s / 3600 << L" h " << (s % 3600) / 60 << L" min";
  else if (s >= 60)
    out << s / 60 << L" min " << s % 60 << L" s";
  else
    out << s << L" s";
  return out.str();
}
// The 3D viewer is the project's web page in the console's browser. Its address
// is configuration, not code: LocalState/viewer.json, written by the host,
// {"schema": "flymsg.worker_viewer/v1", "url": "http://..."}. Y opens it, and
// so does an uploaded LocalState/open_viewer.json (consumed), for a host-driven
// session.
std::optional<std::wstring> viewer_url() noexcept {
  try {
    const auto doc = try_read(worker().root / L"viewer.json");
    if (!doc || field(*doc, L"schema") != "flymsg.worker_viewer/v1")
      return std::nullopt;
    const std::wstring url(doc->GetNamedString(L"url"));
    if (url.rfind(L"http://", 0) != 0 && url.rfind(L"https://", 0) != 0)
      return std::nullopt;
    return url;
  } catch (...) {
    return std::nullopt;
  }
}
void open_viewer() noexcept {
  try {
    if (const auto url = viewer_url())
      Windows::System::Launcher::LaunchUriAsync(Windows::Foundation::Uri(*url));
  } catch (...) {
  }
}
// The dashboard: built once, refreshed four times a second from a telemetry
// copy on the UI thread. It reads; only the gamepad's B writes, and only the
// cancel file a host could upload.
xaml::UIElement dashboard() {
  const auto white = brush(235, 240, 245), dim = brush(150, 165, 180),
             accent = brush(90, 200, 160), warn = brush(240, 120, 100),
             panel = brush(24, 36, 48);
  // rows: header, two columns (job | activity or history), controls
  controls::Grid root;
  root.Background(brush(16, 24, 32));
  root.Padding(
      {48, 27, 48, 27}); // title-safe 5% of the 960 x 540 the console lays out
  root.RowSpacing(14);
  root.ColumnSpacing(24);
  for (auto height :
       {xaml::GridLengthHelper::Auto(),
        xaml::GridLengthHelper::FromValueAndType(1, xaml::GridUnitType::Star),
        xaml::GridLengthHelper::Auto()}) {
    controls::RowDefinition row;
    row.Height(height);
    root.RowDefinitions().Append(row);
  }
  for (double share : {5.0, 6.0}) {
    controls::ColumnDefinition column;
    column.Width(xaml::GridLengthHelper::FromValueAndType(
        share, xaml::GridUnitType::Star));
    root.ColumnDefinitions().Append(column);
  }
  auto place = [&](xaml::FrameworkElement const &e, int row, int column,
                   int span = 1) {
    controls::Grid::SetRow(e, row);
    controls::Grid::SetColumn(e, column);
    controls::Grid::SetColumnSpan(e, span);
    root.Children().Append(e);
  };
  auto card = [&](int row, int column) {
    controls::Border border;
    border.Background(panel);
    border.CornerRadius({8, 8, 8, 8});
    border.Padding({18, 14, 18, 14});
    controls::StackPanel stack;
    stack.Spacing(8);
    border.Child(stack);
    place(border, row, column);
    return stack;
  };

  controls::StackPanel header;
  header.Spacing(2);
  auto title = label(26, white);
  title.Text(L"FlyMSG neural worker");
  auto build = label(12, dim);
  std::wstring adapter;
  try {
    adapter = flymsg::hardware_adapter();
  } catch (...) {
    adapter = L"unknown";
  }
  build.Text(L"commit " + wide(FLYMSG_COMMIT).substr(0, 12) + L"   GPU " +
             (adapter.empty() ? L"none" : adapter) +
             L"   jobs in LocalState\\inbox");
  header.Children().Append(title);
  header.Children().Append(build);
  place(header, 0, 0, 2);

  auto job = card(1, 0);
  auto state = label(22, accent), id = label(13, dim),
       detail = label(15, white), memory = label(12, dim),
       error = label(12, warn);
  controls::ProgressBar progress;
  progress.Height(8);
  progress.Foreground(accent);
  controls::ProgressBar memory_bar;
  memory_bar.Height(4);
  memory_bar.Maximum(1.0);
  memory_bar.Foreground(dim);
  auto history_title = label(15, white), history = label(13, dim);
  history_title.Text(L"Recent jobs");
  history_title.Margin({0, 16, 0, 0});
  for (auto element : std::initializer_list<xaml::UIElement>{
           state, id, progress, detail, memory, memory_bar, error,
           history_title, history})
    job.Children().Append(element);

  auto side = card(1, 1);
  auto side_title = label(15, white);
  controls::Grid bars; // one column per bar, bottom-aligned
  bars.Height(150);
  bars.ColumnSpacing(1);
  auto top = label(11, dim);
  side_title.Text(L"Last completed job: spikes per bin");
  for (auto element :
       std::initializer_list<xaml::UIElement>{side_title, bars, top})
    side.Children().Append(element);

  auto hint = label(12, dim);
  hint.Text(L"Gamepad   B  cancel the running job");
  place(hint, 2, 0, 2);

  auto shown = std::make_shared<uint64_t>(0);
  // buttons arrive as key events, so a short press is never missed
  Windows::UI::Core::CoreWindow::GetForCurrentThread().KeyDown(
      [](auto &&, Windows::UI::Core::KeyEventArgs const &args) {
        using Windows::System::VirtualKey;
        if (args.VirtualKey() == VirtualKey::GamepadB) {
          worker().request_cancel();
          args.Handled(true);
        } else if (args.VirtualKey() == VirtualKey::GamepadY) {
          open_viewer();
          args.Handled(true);
        }
      });
  xaml::DispatcherTimer timer;
  timer.Interval(std::chrono::milliseconds(250));
  timer.Tick([=](auto &&, auto &&) {
    try { // a host's request to open the viewer, consumed once
      const auto request = worker().root / L"open_viewer.json";
      if (fs::exists(request)) {
        fs::remove(request);
        open_viewer();
      }
    } catch (...) {
    }
    hint.Text(viewer_url()
                  ? L"Gamepad   B  cancel the running job      Y  open "
                    L"the 3D viewer"
                  : L"Gamepad   B  cancel the running job");
    const auto t = worker().snapshot();
    const bool idle = t.job.empty();
    state.Text(idle ? L"Idle" : wide(t.state));
    id.Text(idle ? L"waiting for a job" : L"job " + wide(t.job).substr(0, 8));
    const auto busy =
        idle ? xaml::Visibility::Collapsed : xaml::Visibility::Visible;
    progress.Visibility(busy);
    detail.Visibility(busy);
    progress.Maximum(std::max<double>(1.0, t.total));
    progress.Value(t.step);
    std::wstring line =
        L"step " + std::to_wstring(t.step) + L" of " + std::to_wstring(t.total);
    if (t.state == "running" && t.rate > 0) {
      const double left = (double(t.total) - t.step) / t.rate;
      line += L"\n" + fixed(t.rate, 0) + L" steps/s   ETA " +
              (left < 1 ? std::wstring(L"under 1 s") : duration(left));
    }
    detail.Text(line);
    // read here, so the figure is live between jobs too
    const double used =
                     double(Windows::System::MemoryManager::AppMemoryUsage()),
                 limit = double(
                     Windows::System::MemoryManager::AppMemoryUsageLimit());
    memory_bar.Value(limit > 0 ? used / limit : 0.0);
    memory.Text(L"app memory " + fixed(used / 1048576.0, 0) + L" MB of " +
                fixed(limit / 1073741824.0, 1) + L" GB");
    error.Text(t.error.empty() ? L"" : L"error: " + wide(t.error));

    if (t.activity_generation != *shown) { // rebuild for a new job's counts
      bars.Children().Clear();
      bars.ColumnDefinitions().Clear();
      const size_t columns = std::min<size_t>(t.bins.size(), 100);
      std::vector<double> merged(columns, 0.0);
      for (size_t b = 0; b < t.bins.size(); ++b)
        merged[b * columns / t.bins.size()] += t.bins[b];
      double peak = 0;
      for (auto v : merged)
        peak = std::max(peak, v);
      for (size_t c = 0; c < columns; ++c) {
        controls::ColumnDefinition column;
        column.Width(xaml::GridLengthHelper::FromValueAndType(
            1, xaml::GridUnitType::Star));
        bars.ColumnDefinitions().Append(column);
        xaml::Shapes::Rectangle bar;
        bar.Height(peak > 0 ? std::max(1.0, 150.0 * merged[c] / peak) : 1.0);
        bar.VerticalAlignment(xaml::VerticalAlignment::Bottom);
        bar.Fill(accent);
        controls::Grid::SetColumn(bar, int(c));
        bars.Children().Append(bar);
      }
      std::wstring most =
          t.top.empty() ? L"no spikes" : L"most active rows (spikes):";
      for (auto [row, spikes] : t.top)
        most += L"  " + std::to_wstring(row) + L" (" + std::to_wstring(spikes) +
                L")";
      top.Text(most);
      *shown = t.activity_generation;
    }
    if (t.activity_generation == 0)
      top.Text(L"no completed job yet");
    std::wstring rows;
    for (auto const &d : t.history)
      rows += wide(d.outcome) + L"   " + wide(d.id).substr(0, 8) + L"   " +
              std::to_wstring(d.steps) + L" steps" +
              (d.advance_ms > 0
                   ? L"   " + fixed(d.steps / (d.advance_ms / 1000.0), 0) +
                         L" steps/s"
                   : L"") +
              L"\n";
    history.Text(rows.empty() ? L"none yet" : rows);
  });
  timer.Start();
  return root;
}
} // namespace
namespace winrt::Flymsg::implementation {
App::App() {
  // a gamepad UI, not a pointer one: no mouse-mode cursor on the console
  RequiresPointerMode(
      Windows::UI::Xaml::ApplicationRequiresPointerMode::WhenRequested);
  Suspending([](auto const &, SuspendingEventArgs const &args) {
    worker().suspend(args);
  });
  Resuming([](auto const &, auto const &) { worker().suspended = false; });
}
void App::OnLaunched(
    Windows::ApplicationModel::Activation::LaunchActivatedEventArgs const &) {
  auto window = Windows::UI::Xaml::Window::Current();
  if (!window.Content()) {
    worker().start(); // jobs run whatever happens to the dashboard
    window.Content(dashboard());
  }
  window.Activate();
}
} // namespace winrt::Flymsg::implementation
int __stdcall wWinMain(HINSTANCE, HINSTANCE, PWSTR, int) {
  // Application::Start initialises the thread itself; an apartment already set
  // here makes it fail at launch
  Windows::UI::Xaml::Application::Start(
      [](auto &&) { make<winrt::Flymsg::implementation::App>(); });
}
