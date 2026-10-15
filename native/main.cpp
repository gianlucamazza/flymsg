#include "lif.h"
#include <iostream>
#ifdef FLYMSG_DX12
#include "dx12.h"
#endif
int main(int argc, char **argv) {
  try {
    std::string fixture, output, resume, checkpoint, shader, batch;
    uint32_t run = 0;
    uint32_t target = 0;
    bool target_set = false;
    for (int i = 1; i < argc; ++i) {
      const std::string key = argv[i];
      if (key == "--help") {
        std::cout << "--fixture FILE --output FILE [--advance STEP] [--resume "
                     "FILE] [--checkpoint FILE] [--gpu SHADER] [--batch FILE "
                     "--run K]\n";
        return 0;
      }
      flymsg::require(i + 1 < argc, "missing argument value");
      const std::string value = argv[++i];
      if (key == "--fixture")
        fixture = value;
      else if (key == "--output")
        output = value;
      else if (key == "--resume")
        resume = value;
      else if (key == "--checkpoint")
        checkpoint = value;
      else if (key == "--gpu")
        shader = value;
      else if (key == "--batch")
        batch = value;
      else if (key == "--run") {
        size_t consumed = 0;
        const auto parsed = std::stoull(value, &consumed);
        flymsg::require(consumed == value.size() && parsed <= UINT32_MAX &&
                            value[0] != '-',
                        "invalid run");
        run = uint32_t(parsed);
      }
      else if (key == "--advance") {
        size_t consumed = 0;
        const auto parsed = std::stoull(value, &consumed);
        flymsg::require(consumed == value.size() && parsed <= UINT32_MAX &&
                            value[0] != '-',
                        "invalid step");
        target = uint32_t(parsed);
        target_set = true;
      } else
        throw std::runtime_error("unknown argument: " + key);
    }
    flymsg::require(!fixture.empty() && !output.empty(),
                    "fixture and output required");
    // with --batch, --fixture is the batch's base and --run picks the run
    flymsg::Runtime runtime(
        batch.empty() ? flymsg::read_words(fixture)
                      : flymsg::batch_fixture(flymsg::read_words(fixture),
                                              flymsg::read_words(batch), run));
    if (!resume.empty())
      runtime.restore(resume);
    if (!target_set)
      target = runtime.input[3];
    if (!shader.empty()) {
#ifdef FLYMSG_DX12
      flymsg::advance_gpu(runtime, target, shader);
#else
      throw std::runtime_error(
          "BLOCKED: DX12 backend unavailable in this build");
#endif
    } else
      runtime.advance_to(target);
    runtime.snapshot(output);
    if (!checkpoint.empty())
      runtime.checkpoint(checkpoint);
    std::cout << "completed step " << runtime.step << " backend "
              << (shader.empty() ? "cpu" : "dx12") << "\n";
  } catch (const std::exception &error) {
    std::cerr << error.what() << "\n";
    return 1;
  }
}
