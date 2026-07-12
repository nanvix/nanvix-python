# Contributing

Contributions are welcome! To get started:

1. Fork the repository and create a feature branch.
2. Run the SDK setup command from [building.md](building.md), then
   `./z build && ./z test` to verify your changes locally.
3. If adding a new pip package, append it to the appropriate
   requirements file and create a matching
   `tests/func/test_NNN_<package>.py` test file.
4. Open a pull request — CI builds and tests microvm standalone at 256 MB
   on Linux and Windows.

## Further Reading

- [Building from Source](building.md)
- [Statically Linked C Extensions](extensions.md)
- [Testing](testing.md)
- [Supported Packages](packages.md)
- [CI / CD](ci.md)
- [Standalone Runtime Bundle](release.md)
