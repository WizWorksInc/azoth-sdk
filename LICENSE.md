# Licensing

This repository vendors third-party prebuilt binaries for the azoth engine. It is not itself a
single licensed work, and no license is granted over the collection as a whole. Each vendored
dependency is governed solely by the license that ships in its own directory under lib/ or exe/
(the LICENSE.md file, together with any LICENSES/ directory and any NOTICE, third-party, or
code-license file beside it). Those upstream terms control, and nothing here overrides them.

The README.md inventory lists the exact version and license for every item. In summary, the
vendored dependencies fall into two groups.

Open source, freely redistributable:

- SDL3, under the zlib license.
- MoltenVK, the Khronos Vulkan loader, KTX, and Slang (library and tools), under Apache-2.0. KTX
  and Slang also carry an SPDX LICENSES/ directory that is kept in full.
- WinPixEventRuntime, under the MIT license.

Proprietary, redistributable in binary form under the vendor's terms:

- XeSS (Intel), under the Intel Simplified Software License.
- FSR (AMD FidelityFX), under AMD's binary redistribution license.

Both proprietary items permit redistribution of the binaries as provided, without modification, on
the condition that the vendor's copyright notice and license text travel with them. That condition
is met by keeping each vendor's LICENSE.md (and any third-party notice) in place beside the
binaries.

The repository's own metadata (README.md, this file, .gitattributes, and .gitignore) and all files in vendor is authored by
WizWorks and may be used freely.
