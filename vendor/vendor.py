from __future__ import annotations

import argparse
import glob as globlib
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "manifest.json"
PREBUILT_RUNNER = "ubuntu-latest"
BUILD_RUNNERS = {
    ("x64", "darwin"): "macos-14",
    ("aarch64", "darwin"): "macos-14",
    ("x64", "win32"): "windows-latest",
    ("aarch64", "win32"): "windows-latest",
    ("x64", "linux"): "ubuntu-latest",
    ("aarch64", "linux"): "ubuntu-24.04-arm",
}
OSX_ARCH = {"x64": "x86_64", "aarch64": "arm64"}
MSVC_ARCH = {"x64": "x64", "aarch64": "ARM64"}
LINUX_TRIPLE = {"x64": "x86_64-linux-gnu", "aarch64": "aarch64-linux-gnu"}
PKG_ARCH = {"x64": "x64", "aarch64": "arm64"}


def load() -> dict:
    with open(MANIFEST, encoding="utf-8") as f:
        return json.load(f)


def slug(v: str) -> str:
    return v.replace(".", "_")


def canonical_version(version: str, package: str) -> str:
    # The release input is a bare version like 2026.07.0. Strip a redundant
    # leading package name or a leading v so the derived names never double up,
    # which is what produced tags like sdk-azoth-sdk-2026.07.0.
    v = version.strip()
    if v.startswith(package + "-"):
        v = v[len(package) + 1:]
    if v[:1] == "v" and v[1:2].isdigit():
        v = v[1:]
    return v


class _Defaults(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def sub(text: str, tokens: dict) -> str:
    return text.format_map(_Defaults(tokens))


def emit_output(key: str, value: str) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")
    print(value)


def cmd_matrix(args: argparse.Namespace) -> int:
    data = load()
    include = []
    for name, lib in data["libraries"].items():
        if args.kind == "build" and lib["source"] == "build":
            for p in lib["platforms"]:
                runner = BUILD_RUNNERS[(p["arch"], p["os"])]
                include.append({"library": name, "arch": p["arch"], "os": p["os"], "runner": runner})
        elif args.kind == "fetch" and lib["source"] == "prebuilt":
            for akey in lib["assets"]:
                arch, os_ = akey.split("/")
                include.append({"library": name, "arch": arch, "os": os_, "runner": PREBUILT_RUNNER})
    emit_output("matrix", json.dumps({"include": include}))
    return 0


def token_map(arch: str, os_: str, version: str, extra: dict | None) -> dict:
    t = {
        "arch": arch, "os": os_, "version": version, "vslug": slug(version),
        "osx_arch": OSX_ARCH[arch], "msvc_arch": MSVC_ARCH[arch],
        "linux_triple": LINUX_TRIPLE[arch], "pkg_arch": PKG_ARCH[arch],
    }
    if extra:
        t.update(extra)
    return t


def per_os(value, os_):
    if isinstance(value, dict) and set(value) & {"win32", "darwin", "linux"}:
        return value.get(os_)
    return value


def norm_entries(entries) -> list[tuple[str, str | None, bool]]:
    result = []
    for e in entries or []:
        if isinstance(e, str):
            result.append((e, None, False))
        else:
            result.append((e["glob"], e.get("as"), bool(e.get("optional"))))
    return result


def run(cmd: str, env: dict, cwd: Path | None = None) -> None:
    print(f"$ {cmd}", flush=True)
    subprocess.run(cmd, shell=True, check=True, env=env, cwd=cwd)


def download(url: str, dest: Path) -> None:
    print(f"downloading {url}", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "azoth-vendor"})
    with urllib.request.urlopen(req) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def extract_zip(archive: Path, dest: Path) -> None:
    # zipfile drops Unix modes and writes symlink entries as regular files holding
    # the target path, so restore both from the high bits of external_attr.
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                link = dest / info.filename
                if not str(link.parent.resolve()).startswith(str(dest.resolve())):
                    sys.exit(f"unsafe symlink path in {archive.name}: {info.filename}")
                link.parent.mkdir(parents=True, exist_ok=True)
                if link.is_symlink() or link.exists():
                    link.unlink()
                link.symlink_to(z.read(info).decode())
                continue
            out = Path(z.extract(info, dest))
            if not info.is_dir() and mode & 0o7777:
                out.chmod(mode & 0o7777)
    verify_zip_metadata(archive, dest)


def verify_zip_metadata(archive: Path, dest: Path) -> None:
    # Fail loudly rather than staging tools that lost their exec bit or symlinks.
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            mode = info.external_attr >> 16
            out = dest / info.filename
            if not (out.is_symlink() or out.exists()):
                continue
            if stat.S_ISLNK(mode) and not out.is_symlink():
                sys.exit(f"extract lost the symlink {info.filename} from {archive.name}")
            if not stat.S_ISLNK(mode) and mode & 0o111 and not os.access(out, os.X_OK):
                sys.exit(f"extract lost the exec bit on {info.filename} from {archive.name}")


def extract(archive: Path, kind: str, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if kind in ("zip", "nupkg"):
        extract_zip(archive, dest)
    elif kind.startswith("tar"):
        with tarfile.open(archive) as t:
            t.extractall(dest)
    elif kind == "dmg":
        mnt = dest / "_mnt"
        if shutil.which("hdiutil"):
            mnt.mkdir(parents=True, exist_ok=True)
            run(f'hdiutil attach -nobrowse -mountpoint "{mnt}" "{archive}"', os.environ.copy())
            shutil.copytree(mnt, dest / "dmg", dirs_exist_ok=True, symlinks=True)
            run(f'hdiutil detach "{mnt}"', os.environ.copy())
        else:
            run(f'7z x -y -o"{dest}" "{archive}"', os.environ.copy())
    elif kind == "7z":
        run(f'7z x -y -o"{dest}" "{archive}"', os.environ.copy())
    elif kind == "pkg":
        # A macOS flat package is a xar holding component .pkg dirs, each with the
        # real files in a gzipped cpio Payload. Unpack both layers.
        run(f'7z x -y -o"{dest}" "{archive}"', os.environ.copy())
        for payload in sorted(dest.rglob("Payload")):
            run(f'bsdtar -xf "{payload}" -C "{payload.parent}"', os.environ.copy())
    else:
        sys.exit(f"unknown archive kind: {kind}")


def dump_tree(root: Path) -> None:
    print(f"contents of {root}:", flush=True)
    for p in sorted(root.rglob("*")):
        if p.is_file():
            print("  " + str(p.relative_to(root)))


def resolve_one(root: Path, pattern: str) -> list[Path]:
    return [Path(p) for p in globlib.glob(str(root / pattern), recursive=True)]


LICENSE_NAME = re.compile(r"^(licen[sc]e|copying|notice|unlicense)([._-].*)?$", re.IGNORECASE)


def discover_license(exdir: Path) -> Path | None:
    # Fallback when an output declares no explicit license: pick the shallowest
    # file whose name looks like a license, so a library's own top-level license
    # wins over any third-party ones bundled deeper in the archive.
    cands = [p for p in exdir.rglob("*") if p.is_file() and LICENSE_NAME.match(p.name)]
    if not cands:
        return None
    return min(cands, key=lambda p: (len(p.relative_to(exdir).parts), len(p.name)))


def thin(path: Path, dest: Path, arch: str) -> bool:
    tool = shutil.which("lipo") or shutil.which("llvm-lipo")
    if not tool:
        return False
    info = subprocess.run([tool, "-info", str(path)], capture_output=True, text=True).stdout
    if "Non-fat" in info:
        return False
    if arch not in info:
        return False
    r = subprocess.run([tool, str(path), "-thin", arch, "-output", str(dest)])
    return r.returncode == 0


def place(src: Path, bindir: Path, as_name: str | None, os_: str, osx_arch: str) -> None:
    bindir.mkdir(parents=True, exist_ok=True)
    dest = bindir / (as_name or src.name)
    if dest.is_symlink() or dest.exists():
        dest.unlink()
    if src.is_symlink():
        # Recreate the link. copy2 would dereference it, duplicating the whole
        # dylib and dropping the soname indirection the loader resolves through.
        dest.symlink_to(os.readlink(src))
    else:
        if not (os_ == "darwin" and thin(src, dest, osx_arch)):
            shutil.copy2(src, dest)
        if os.access(src, os.X_OK):
            dest.chmod(dest.stat().st_mode | 0o111)
    verify_placed(src, dest)


def verify_placed(src: Path, dest: Path) -> None:
    if src.is_symlink() and not dest.is_symlink():
        sys.exit(f"staged {dest} lost the symlink from {src}")
    if not src.is_symlink() and os.access(src, os.X_OK) and not os.access(dest, os.X_OK):
        sys.exit(f"staged {dest} lost the exec bit from {src}")


def target_root(stage: Path, out: dict, version: str) -> Path:
    if out["tree"] == "lib":
        return stage / "lib" / out["name"]
    return stage / "exe" / f"{out['name']}-{slug(version)}"


def apply_output(exdir: Path, out: dict, arch: str, os_: str, version: str,
                 stage: Path, tokens: dict) -> None:
    root = target_root(stage, out, version)
    link = out.get("link")
    bindir = root / "bin" / arch / os_ / (link or "")

    entries = norm_entries(per_os(out.get("in"), os_))
    for pattern, as_name, optional in entries:
        hits = resolve_one(exdir, sub(pattern, tokens))
        if not hits:
            if optional:
                continue
            dump_tree(exdir)
            sys.exit(f"no match for '{pattern}' [{out['name']} {arch}/{os_}]")
        for f in sorted(hits):
            place(f, bindir, as_name, os_, tokens["osx_arch"])

    inc = per_os(out.get("include"), os_)
    if inc:
        hits = resolve_one(exdir, sub(inc["from"], tokens))
        dirs = [h for h in hits if h.is_dir()]
        if dirs:
            shutil.copytree(dirs[0], root / inc["to"], dirs_exist_ok=True)
        elif hits:
            (root / inc["to"]).mkdir(parents=True, exist_ok=True)
            for h in hits:
                shutil.copy2(h, root / inc["to"] / h.name)

    lic = per_os(out.get("license"), os_)
    licdir = per_os(out.get("license_dir"), os_)
    carried = False
    if lic:
        hits = resolve_one(exdir, sub(lic["in"], tokens))
        if not hits:
            sys.exit(f"license '{lic['in']}' not found for {out['name']} [{arch}/{os_}]")
        (root / lic["to"]).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(hits[0], root / lic["to"])
        carried = True

    if licdir:
        # Supplementary bundle of per-dependency license texts. Not every archive
        # ships it, so absence is fine as long as a primary license is carried.
        hits = [h for h in resolve_one(exdir, sub(licdir["from"], tokens)) if h.is_dir()]
        if hits:
            shutil.copytree(hits[0], root / licdir["to"], dirs_exist_ok=True)
            carried = True

    if not carried:
        found = discover_license(exdir)
        if found is None:
            sys.exit(f"no license found for {out['name']} [{arch}/{os_}]; add a 'license' to the manifest")
        shutil.copy2(found, root / "LICENSE")

    (root / "VERSION.txt").write_text(version + "\n", encoding="utf-8")


def asset_sources(asset: dict) -> list[dict]:
    # An asset is one or more archives merged into a single extraction tree. The
    # single-archive form carries url/archive on the asset itself. The multi
    # archive form lists them under "sources" (for example DLLs from a release
    # bundle plus headers from the source tag). Outputs glob across the merger.
    return asset["sources"] if "sources" in asset else [asset]


def cmd_fetch(args: argparse.Namespace) -> int:
    data = load()
    lib = data["libraries"].get(args.library)
    if lib is None or lib["source"] != "prebuilt":
        sys.exit(f"not a prebuilt library: {args.library}")
    akey = f"{args.arch}/{args.os}"
    asset = lib["assets"].get(akey)
    if asset is None:
        sys.exit(f"{args.library} has no asset for {akey}")

    version = lib["version"]
    tokens = token_map(args.arch, args.os, version, asset.get("tokens"))
    work = Path(args.work or (HERE / ".work" / f"{args.library}-{args.arch}-{args.os}")).resolve()
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    stage = Path(args.stage).resolve()

    exdir = work / "ex"
    for i, src in enumerate(asset_sources(asset)):
        archive_path = work / f"dl{i}{os.path.splitext(src['url'])[1] or '.bin'}"
        download(src["url"], archive_path)
        extract(archive_path, src["archive"], exdir)

    for out in lib["outputs"]:
        apply_output(exdir, out, args.arch, args.os, version, stage, tokens)
        print(f"fetched {out['tree']}:{out['name']} [{args.arch}/{args.os}]")
    return 0


def clone(upstream: dict, src: Path, env: dict) -> None:
    shutil.rmtree(src, ignore_errors=True)
    recurse = " --recurse-submodules --shallow-submodules" if upstream.get("submodules") else ""
    run(f'git clone --depth 1 --branch {upstream["tag"]}{recurse} "{upstream["git"]}" "{src}"', env)


def cmd_build(args: argparse.Namespace) -> int:
    data = load()
    lib = data["libraries"].get(args.library)
    if lib is None or lib["source"] != "build":
        sys.exit(f"not a buildable library: {args.library}")

    version = lib["version"]
    tokens = token_map(args.arch, args.os, version, None)
    src = Path(args.src or (HERE / ".work" / f"{args.library}-{args.arch}-{args.os}")).resolve()
    stage = Path(args.stage).resolve()
    jobs = str(os.cpu_count() or 4)

    env = os.environ.copy()
    env.update(
        SRC=str(src), STAGE=str(stage), ARCH=args.arch, OS=args.os,
        OSX_ARCH=OSX_ARCH[args.arch], MSVC_ARCH=MSVC_ARCH[args.arch],
        LINUX_TRIPLE=LINUX_TRIPLE[args.arch], VERSION=version, JOBS=jobs,
        PREFIX=str(src / "_install"),
    )

    clone(lib["upstream"], src, env)
    steps = lib["build"].get(args.os)
    if not steps:
        sys.exit(f"{args.library} has no build recipe for {args.os}")
    for step in steps:
        run(step, env, cwd=src)

    for out in lib["outputs"]:
        apply_output(src, out, args.arch, args.os, version, stage, tokens)
        print(f"built {out['tree']}:{out['name']} [{args.arch}/{args.os}]")
    return 0


def lib_platforms(lib: dict) -> str:
    if lib["source"] == "build":
        return ", ".join(f"{p['arch']}/{p['os']}" for p in lib["platforms"])
    return ", ".join(lib["assets"].keys())


def origin_link(url: str) -> tuple[str, str]:
    # (label, href) for the release table. Prefer the exact upstream tag page.
    m = re.match(r"https?://github\.com/([^/]+/[^/]+)", url)
    if m:
        repo = m.group(1)
        tag = re.search(r"/releases/download/([^/]+)/", url) or \
            re.search(r"/archive/refs/tags/(.+?)(?:\.tar\.gz|\.tgz|\.zip|\.tar\.bz2|\.tar\.xz)$", url)
        href = f"https://github.com/{repo}/releases/tag/{tag.group(1)}" if tag else f"https://github.com/{repo}"
        return repo, href
    m = re.match(r"https?://www\.nuget\.org/api/v2/package/([^/]+)/([^/]+)", url)
    if m:
        return f"NuGet {m.group(1)}", f"https://www.nuget.org/packages/{m.group(1)}/{m.group(2)}"
    return re.sub(r"^https?://([^/]+).*$", r"\1", url), url


def lib_origin(lib: dict) -> str:
    if lib["source"] == "build":
        repo = re.sub(r"^https?://github\.com/", "", lib["upstream"]["git"])
        repo = repo[:-4] if repo.endswith(".git") else repo
        tag = lib["upstream"]["tag"]
        return f"[{repo} @ {tag}](https://github.com/{repo}/tree/{tag})"
    entries = []
    for asset in lib["assets"].values():
        for src in asset_sources(asset):
            label, href = origin_link(src["url"])
            entry = f"[{label}]({href})"
            if entry not in entries:
                entries.append(entry)
    return ", ".join(entries)


def release_body(data: dict) -> str:
    # Only the vendored dependency inventory: what we pinned and where from.
    rows = [
        "## Vendored libraries",
        "",
        "| Library | Version | License | Type | Platforms | Source |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for name, lib in data["libraries"].items():
        lic = lib.get("license_id")
        if not lic:
            sys.exit(f"{name} has no license_id in the manifest")
        kind = "prebuilt" if lib["source"] == "prebuilt" else "built from source"
        rows.append(
            f"| {name} | {lib['version']} | {lic} | {kind} | {lib_platforms(lib)} | {lib_origin(lib)} |"
        )
    return "\n".join(rows) + "\n"


def cmd_package(args: argparse.Namespace) -> int:
    data = load()
    name = data["sdk"]["package"]
    version = canonical_version(args.version, name)
    stages = Path(args.stages).resolve()
    out = Path(args.out).resolve()
    tree = out / f"{name}-{version}"
    shutil.rmtree(out, ignore_errors=True)
    tree.mkdir(parents=True, exist_ok=True)

    for d in sorted(stages.glob("*")):
        if d.is_dir():
            for top in ("lib", "exe"):
                if (d / top).is_dir():
                    shutil.copytree(d / top, tree / top, dirs_exist_ok=True, symlinks=True)

    tgz = out / f"{name}-{version}.tar.gz"
    with tarfile.open(tgz, "w:gz") as t:
        t.add(tree, arcname=tree.name)
    zipf = out / f"{name}-{version}.zip"
    with zipfile.ZipFile(zipf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(tree.rglob("*")):
            rel = str(p.relative_to(out))
            if p.is_symlink():
                # is_file follows the link, so store the link itself. Otherwise the
                # zip ships a full duplicate of every versioned dylib it points at.
                info = zipfile.ZipInfo(rel)
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(info, os.readlink(p))
            elif p.is_file():
                z.write(p, rel)

    sums = out / "SHA256SUMS"
    with open(sums, "w", encoding="utf-8") as f:
        for a in (tgz, zipf):
            h = hashlib.sha256(a.read_bytes()).hexdigest()
            f.write(f"{h}  {a.name}\n")

    body = out / "RELEASE_BODY.md"
    body.write_text(release_body(data), encoding="utf-8")

    emit_output("package", str(tgz))
    emit_output("version", version)
    emit_output("tag", f"sdk-{version}")
    emit_output("name", f"{name} {version}")
    print(f"packaged {tgz.name}, {zipf.name}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub_ap = ap.add_subparsers(dest="cmd", required=True)

    m = sub_ap.add_parser("matrix")
    m.add_argument("--kind", required=True, choices=["fetch", "build"])
    m.set_defaults(func=cmd_matrix)

    f = sub_ap.add_parser("fetch")
    f.add_argument("--library", required=True)
    f.add_argument("--arch", required=True, choices=["x64", "aarch64"])
    f.add_argument("--os", required=True, choices=["darwin", "win32", "linux"])
    f.add_argument("--stage", required=True)
    f.add_argument("--work", default="")
    f.set_defaults(func=cmd_fetch)

    b = sub_ap.add_parser("build")
    b.add_argument("--library", required=True)
    b.add_argument("--arch", required=True, choices=["x64", "aarch64"])
    b.add_argument("--os", required=True, choices=["darwin", "win32", "linux"])
    b.add_argument("--stage", required=True)
    b.add_argument("--src", default="")
    b.set_defaults(func=cmd_build)

    p = sub_ap.add_parser("package")
    p.add_argument("--stages", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--version", required=True)
    p.set_defaults(func=cmd_package)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
