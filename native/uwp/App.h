#pragma once
#include <windows.h>
#include <winrt/Windows.ApplicationModel.Activation.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.UI.Xaml.Controls.h>
#include <winrt/Windows.UI.Xaml.h>
#include "App.g.h"
namespace winrt::Flymsg::implementation {
struct App : AppT<App> {
  App();
  void OnLaunched(
      Windows::ApplicationModel::Activation::LaunchActivatedEventArgs const &);
};
} // namespace winrt::Flymsg::implementation
namespace winrt::Flymsg::factory_implementation {
struct App : AppT<App, implementation::App> {};
} // namespace winrt::Flymsg::factory_implementation
