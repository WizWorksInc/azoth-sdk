# azoth-sdk

Pinned, prebuilt binary dependencies for the azoth engine. This repository holds the exact
library and tool builds the engine links against, laid out so a checkout on any supported host
already has the right headers and binaries for its architecture and OS. No source, no build step.

This is the public set. NDA and license-restricted SDKs live in a separate private repository
that follows the same layout.

## What lives here

Two top-level trees:

- lib: libraries the engine links (headers plus static and shared binaries).
- exe: standalone tool programs the engine or its build invoke, for example the Slang shader compiler.

Only artifacts an upstream already ships as precompiled binaries are stored here. Where an upstream
does not provide a given architecture, OS, or link kind, that cell is left out rather than kept as an
empty folder.

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

Worked out for the platforms SDL actually ships:

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

Tool programs are native per platform, so their bin/ splits by arch and OS the same way lib/ does,
without the link-kind level. A tool cell holds the program and every file it needs to run.

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

A Windows .lib is two different things and is placed by role, not by extension. A static-library .lib
(the whole archive of object code) goes in static/. An import .lib (a small stub that resolves a
.dll's exports at link time, while the code loads from the .dll at runtime) goes in shared/ beside
its .dll. Rule of thumb: an import .lib has a same-named .dll next to it and is tiny, a static .lib
does not and is large.

Debug artifacts carry a trailing d on the file name (SDL3d.lib, SDL3d.dll) and sit beside their
release counterparts in the same folder.

## Population policy

An upstream release rarely fills the whole matrix. The rule is to store what is already compiled
and skip the rest:

- Take only precompiled binaries an upstream publishes. Do not build from source to fill a gap.
- Omit any arch, OS, or link kind the upstream does not ship. No placeholder folders.
- Record the exact version in VERSION.txt and the upstream license in LICENSE.md.
- Include every legal file the license requires alongside the binaries, not just the main license.
  A NOTICE or third-party notices file sits beside LICENSE.md under its upstream name, and a project
  that ships an SPDX LICENSES/ directory (KTX, Slang) keeps that whole directory.

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

MoltenVK is the Vulkan-over-Metal driver the engine loads at runtime on macOS (end-user Macs do not
have it), so it must ship with the app. Apache-2.0, so it lives here in the open-source set. The
universal dylib is thinned per architecture like SDL3, and each cell carries the ICD manifest
(MoltenVK_icd.json, which points at ./libMoltenVK.dylib) so the Vulkan loader can find it. Only the
MoltenVK config headers are kept; the Vulkan headers come from the engine's vk-dynamic.

vulkan-loader is the Khronos Vulkan loader (libvulkan) for macOS, thinned per architecture the same
way. It has no upstream prebuilt release, so it was extracted from the LunarG Vulkan SDK 1.4.350.1
(Apache-2.0). Pair it with MoltenVK when you want the loader plus ICD path (validation-layer support),
or load MoltenVK directly without it, which is the leaner shipping config.

Notes on the upscalers:

- XeSS carries the super-resolution, frame-generation, low-latency, and DX11 runtimes with their import libraries and headers (Windows x64).
- FSR is the signed DX12 redistributable DLLs only. The FidelityFX developer API and its Vulkan backend are built from source by the engine, so this prebuilt has no headers.
- XeSS (Intel) and FSR (AMD) are proprietary but redistributable in binary form. Intel's Simplified Software License and AMD's FidelityFX license each grant binary redistribution as long as the vendor's license text ships alongside, which it does. They are not open source, so they sit apart from the zlib, Apache, and MIT dependencies, but they are legal to keep in this public set. DLSS (NVIDIA) is not, and lives in Not vendored below.

## Not vendored

- LZ4 1.10.0: the only Windows prebuilt is a MinGW build, an import library in the .dll.a format that the engine's MSVC and clang-cl ABI cannot link, with no runtime DLL alongside it. The engine builds LZ4 from source.
- FBX SDK (Autodesk): proprietary, the download sits behind Autodesk's license agreement, and its redistribution terms are restrictive. It belongs in the private and restricted repo, not this public set, so it is left for a deliberate decision.
- NVIDIA DLSS 310.7.0: the NVIDIA RTX SDKs license permits redistribution only when the SDK is incorporated in object code form into a shipping application with material added functionality, and section 4b forbids distributing the SDK as a standalone product. A standalone binary repository is exactly that, so DLSS is not vendored here. The engine resolves it at build time from NVIDIA (github.com/NVIDIA/DLSS) under the user's own acceptance of the license.
- Microsoft DirectStorage 1.3.0: the DirectStorage SDK license makes the runtime distributable only inside an application that adds significant functionality, and section 3e forbids providing the software as a standalone offering. Same reasoning as DLSS. The engine resolves it at build time from the NuGet package.
- Source and header only dependencies the engine compiles itself, none of which publish prebuilt binaries: fmt, simdjson, Jolt, FreeType, HarfBuzz, meshoptimizer, fastgltf, tinyobjloader, stb, ccmath, CLI11, Vulkan Memory Allocator, vk-dynamic, metal-cpp, D3D12 Memory Allocator, glad, fcontext, Dear ImGui, fpng, the Tracy client, and the cpptrace, libdwarf, and zstd chain.

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

## Worked example: SDL3

Version 3.4.12, from the libsdl-org/SDL release-3.4.12 assets.

| Cell | Provided | Source asset |
| --- | --- | --- |
| include/SDL3 | yes | SDL3-devel-3.4.12-VC.zip |
| x64/win32/shared | yes | SDL3-devel-3.4.12-VC.zip |
| aarch64/win32/shared | yes | SDL3-devel-3.4.12-VC.zip |
| x64/darwin/shared | yes | SDL3-3.4.12.dmg |
| aarch64/darwin/shared | yes | SDL3-3.4.12.dmg |
| any static | no, SDL ships shared only | |
| any linux | no, source only upstream | |
| debug variants | no, release builds only | |

macOS handling. SDL ships one universal xcframework. The fat macOS dylib was thinned per
architecture, its install name reset to @rpath/libSDL3.dylib, and ad-hoc re-signed, so each cell
holds a single-architecture dylib consistent with the other platforms. SDL's default.metallib is
carried alongside so the Metal path stays intact.

Source checksums (SHA-256):

```
SDL3-devel-3.4.12-VC.zip  8793a153c7eba93b1eb8022fd2356383ec446b2584e43724a72ef68d682813ab
SDL3-3.4.12.dmg           c77d36d9393bb5481e38d222b75a1a63ab16274457b3d18c63fef90aaf5fc93b
```

## Worked example: Slang (tools and library)

Version 2026.12, from the shader-slang/slang v2026.12 assets. Slang appears in both trees because
it is used two ways.

The tools (slangc, slangd, slangi) are per-platform native programs, gathered under one exe folder
whose bin/ splits by arch and OS. Each cell is the runnable tool bundle for that host:

```
exe/
  slang-2026_12/
    bin/
      x64/
        win32/     slangc.exe and the slang DLLs
        linux/     slangc and the .so libraries
        darwin/    slangc and the .dylib libraries
      aarch64/
        win32/  linux/  darwin/
    VERSION.txt
    LICENSE.md
    LICENSES/
```

Each os cell holds the executables flat, next to the shared libraries they load. That works because
slangc looks in its own directory: its rpath includes @loader_path on macOS and $ORIGIN on Linux,
and the Windows loader searches the program directory.

The library tree (lib/slang) holds the Slang runtime for linking into the engine: the API headers,
the libslang shared libraries, and the Windows import libraries. The tool tree (exe/slang-2026_12)
holds slangc and its siblings for offline shader compilation. Both carry the same shared libraries,
one copy to link against and one to run the tools with, and Git LFS stores each unique file a single
time.

LLVM is omitted from both trees. The release ships libslang-llvm, the CPU and host-target
downstream, at 106 to 152 MB per slice. The engine compiles shaders to SPIR-V, DXIL, and Metal, none of which load it,
confirmed by compiling a shader with the library removed. Dropping it holds each bundle to tens of
MB rather than 150 or more. To restore host-target compilation, copy the slang-llvm library back
beside the tools.

The neural standard module (slang-standard-module, the cooperative-matrix and neural-graphics
modules) is omitted too. slangc does not need it to compile normal shaders, no engine shader imports
it, and it is platform-specific so LFS cannot share it. Restore it from the release tarball if the
engine adopts Slang neural graphics, which is separate from DLSS Ray Reconstruction.

Source checksums (SHA-256):

```
slang-2026.12-macos-aarch64.tar.gz    018a425a8d6a34b172324db2cf5097e3789d232136f1e6e01976eb4196045cb2
slang-2026.12-macos-x86_64.tar.gz     f26018f15c1af196861dc7316c33fba2fc843bdf6fd2724a04825463f711a48e
slang-2026.12-linux-x86_64.tar.gz     2409ecc7b6710783e05fd59792558c275c637e3e3c37fb5054fcfc858e570d82
slang-2026.12-linux-aarch64.tar.gz    0a7b9bc0a6aaa43aee045fb0dfce73f6b01ea4dcac7912ea15e0b707d42c09bf
slang-2026.12-windows-x86_64.tar.gz   73a372c128f13189052cde6e0e91975e1eee7b7ae31c3b4f9c2cf35d3a8759d8
slang-2026.12-windows-aarch64.tar.gz  d150c67d223d418dd3a724e92ff0ef87b7b2222259a281e75f8c506c73a91f37
```
