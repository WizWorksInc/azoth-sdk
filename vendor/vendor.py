from __future__ import annotations

import argparse
import glob as globlib
import hashlib
import json
import os
import shutil
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


def extract(archive: Path, kind: str, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if kind in ("zip", "nupkg"):
        with zipfile.ZipFile(archive) as z:
            z.extractall(dest)
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
    if os_ == "darwin" and thin(src, dest, osx_arch):
        pass
    else:
        shutil.copy2(src, dest)
    if os.access(src, os.X_OK):
        dest.chmod(dest.stat().st_mode | 0o111)


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
    if lic:
        hits = resolve_one(exdir, sub(lic["in"], tokens))
        if hits:
            (root / lic["to"]).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(hits[0], root / lic["to"])

    licdir = per_os(out.get("license_dir"), os_)
    if licdir:
        hits = [h for h in resolve_one(exdir, sub(licdir["from"], tokens)) if h.is_dir()]
        if hits:
            shutil.copytree(hits[0], root / licdir["to"], dirs_exist_ok=True)

    (root / "VERSION.txt").write_text(version + "\n", encoding="utf-8")


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

    archive_path = work / ("dl" + os.path.splitext(asset["url"])[1] or "dl.bin")
    download(asset["url"], archive_path)
    exdir = work / "ex"
    extract(archive_path, asset["archive"], exdir)

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


def cmd_package(args: argparse.Namespace) -> int:
    data = load()
    version = args.version
    name = data["sdk"]["package"]
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
            if p.is_file():
                z.write(p, p.relative_to(out))

    sums = out / "SHA256SUMS"
    with open(sums, "w", encoding="utf-8") as f:
        for a in (tgz, zipf):
            h = hashlib.sha256(a.read_bytes()).hexdigest()
            f.write(f"{h}  {a.name}\n")

    emit_output("package", str(tgz))
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
