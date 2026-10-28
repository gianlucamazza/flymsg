#include "lif.h"
#include <iostream>
#ifdef FLYMSG_DX12
#include "dx12.h"
#endif
int main(int argc, char **argv) {
  try {
    std::string fixture, output, resume, checkpoint, shader, batch, counts,
        publish, input_block;
    uint32_t run = 0;
    uint32_t target = 0;
    bool target_set = false;
    uint64_t publish_nbytes = 0;
    bool publish_nbytes_set = false;
    for (int i = 1; i < argc; ++i) {
      const std::string key = argv[i];
      if (key == "--help") {
        std::cout << "--fixture FILE --output FILE [--advance STEP] [--resume "
                     "FILE] [--input-block FILE] [--checkpoint FILE] [--gpu "
                     "SHADER] [--batch FILE "
                     "--run K] [--counts FILE] [--publish FILE --publish-bytes "
                     "N]\n";
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
      else if (key == "--input-block")
        input_block = value;
      else if (key == "--checkpoint")
        checkpoint = value;
      else if (key == "--gpu")
        shader = value;
      else if (key == "--batch")
        batch = value;
      else if (key == "--counts")
        counts = value;
      else if (key == "--publish")
        publish = value;
      else if (key == "--publish-bytes") {
        size_t consumed = 0;
        const auto parsed = std::stoull(value, &consumed);
        flymsg::require(consumed == value.size() && value[0] != '-',
                        "invalid publish size");
        publish_nbytes = parsed;
        publish_nbytes_set = true;
      } else if (key == "--run") {
        size_t consumed = 0;
        const auto parsed = std::stoull(value, &consumed);
        flymsg::require(consumed == value.size() && parsed <= UINT32_MAX &&
                            value[0] != '-',
                        "invalid run");
        run = uint32_t(parsed);
      } else if (key == "--advance") {
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
    if (!publish.empty() || publish_nbytes_set) {
      flymsg::require(!publish.empty() && publish_nbytes_set,
                      "publish path and byte count are both required");
      flymsg::require(publish_nbytes <= flymsg::max_bytes,
                      "invalid publish size");
      std::vector<char> payload(static_cast<size_t>(publish_nbytes));
      const auto decision =
          flymsg::publish_bytes(publish, payload.data(), publish_nbytes);
      std::cout << decision << "\n";
      return 0;
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
    if (!input_block.empty())
      runtime.schedule_inputs(flymsg::read_words(input_block));
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
    if (!counts.empty())
      runtime.counts(counts);
    if (!checkpoint.empty()) {
      const auto decision = runtime.checkpoint(checkpoint);
      if (decision != "completed") {
        std::cout << decision << "\n";
        return 1;
      }
    }
    std::cout << "completed step " << runtime.step << " backend "
              << (shader.empty() ? "cpu" : "dx12") << "\n";
  } catch (const std::exception &error) {
    std::cerr << error.what() << "\n";
    return 1;
  }
}
