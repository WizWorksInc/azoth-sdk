# azoth-sdk

Two top-level trees:

- lib: libraries the engine links that are generally heavy to compile yourself.
- exe: standalone tool programs the engine or its build invoke.

## lib layout

```
lib/
  <library>/
    bin/
      <arch>/
        <os>/
          static/    release archives, plus debug archives suffixed d
          shared/    release dynamic libs, plus debug dynamic libs suffixed d
    include/         one header tree, shared across every arch and os
    VERSION.txt      the exact upstream version
    LICENSE.md       the upstream license, verbatim
```

Example layout:

```
lib/SDL3/
  bin/
    x64/
      win32/shared/    SDL3.dll  SDL3.lib  SDL3.pdb
      darwin/shared/   libSDL3.dylib  default.metallib
    aarch64/
      win32/shared/    SDL3.dll  SDL3.lib  SDL3.pdb
      darwin/shared/   libSDL3.dylib  default.metallib
  include/SDL3/        the SDL3 headers
  VERSION.txt
  LICENSE.md
```

## exe layout

Tool programs are native per platform.

```
exe/
  <program>-<version>/
    bin/
      <arch>/
        <os>/          the program and its runtime files, arranged as the program expects
    VERSION.txt
    LICENSE.md
```

## Naming

Architecture folder:

| Token | Meaning |
| --- | --- |
| x64 | 64-bit x86 (AMD64) |
| aarch64 | 64-bit ARM |

OS folder:

| Token | Meaning |
| --- | --- |
| win32 | Windows |
| darwin | macOS |
| linux | Linux |
| unix | stands in for darwin and linux only when both ship the identical artifact kind |

Link kind folder:

| Token | Contents |
| --- | --- |
| static | static archives, the whole code linked in: .a, and the static form of a Windows .lib |
| shared | dynamic libraries and what pairs with them: .dylib, .so, .dll with its import .lib, .pdb |

## Inventory

Vendored libraries (lib/):

| Library | Version | Platforms | Link | License |
| --- | --- | --- | --- | --- |
| SDL3 | 3.4.12 | win32, darwin (x64, aarch64) | shared | zlib |
| MoltenVK | 1.4.1 | darwin (x64, aarch64) | shared | Apache-2.0 |
| vulkan-loader | 1.4.350.1 | darwin (x64, aarch64) | shared | Apache-2.0 |
| WinPixEventRuntime | 1.0.240308001 | win32 (x64, aarch64) | shared | MIT |
| KTX | 4.4.2 | win32, darwin, linux (x64, aarch64) | shared | Apache-2.0 |
| XeSS | 3.0.1 | win32 (x64) | shared | Intel Simplified, proprietary |
| FSR | 2.3.0 | win32 (x64) | shared | AMD, binary redistribution |
| slang | 2026.12 | win32, darwin, linux (x64, aarch64) | shared | Apache-2.0 |

Vendored tools (exe/):

| Program | Version | Hosts | License |
| --- | --- | --- | --- |
| slang | 2026.12 | darwin, linux, win32 (x64, aarch64) | Apache-2.0 |

## Source checksums

The upstream artifacts each library was extracted from (SHA-256):

```
KTX-Software-4.4.2-Windows-x64.exe       1f323b0fec19794f5e6c0425a61d4b1da396872a10be862d105f4f4b2d2957fe
KTX-Software-4.4.2-Windows-arm64.exe     86d6edba47f3df597f3b9bceda6e4da8b4205b43c8386519e1c0d2ce804c4284
KTX-Software-4.4.2-Darwin-x86_64.pkg     efecc685ab891a6e119a9fdc8cbe038e135f9a367eb2f5d8a059553f947f1fea
KTX-Software-4.4.2-Darwin-arm64.pkg      500bd8f9d63358c3f3a0d83b724c8574436a72c37dc0e4bad90ec1ca38032c3c
KTX-Software-4.4.2-Linux-x86_64.tar.bz2  a8781bad05f9624edbf910b7f258cd0a4ba7d3e63b49ecc0a0ab440bf6a0a245
KTX-Software-4.4.2-Linux-arm64.tar.bz2   60382e7b842177b8048bd58ccdc770383f8ef65b94452a25d3afdb55f2405c5a
XeSS_SDK_3.0.1.zip                       b1a833677884b644a605276194c64706591dc2c41d66a2ff46808fedfab02df9
winpixeventruntime.1.0.240308001.nupkg   726acc93d6968e2146261a1e415521747d50ad69894c2b42b5d0d4c29fd66ec4
FidelityFX-Samples-v2.3.0-prebuilt.zip   f90890b9323bb2f4f2404ac4cdc9395e8495ecdac6f7aa0bcdf1ad1848422273
```
