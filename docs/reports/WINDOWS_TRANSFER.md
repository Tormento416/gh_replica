# Windows transfer preparation

Requested destination: `D:\HRIS_project`. The intended structure is a `gh_replica` backbone checkout and a sibling `platform-modules` directory containing the fourteen module Git repositories.

The cloud executor cannot mount or write the Windows drive shown in File Explorer. A screenshot confirms the requested location but does not supply filesystem access. The project is therefore prepared as a verified ZIP transfer copy; source checkouts remain intact until the destination is confirmed.

## Path updates

- Scaffold and evidence commands now use the sibling `../platform-modules` path.
- Documentation and agent continuation rules no longer depend on a cloud workspace mount.
- Module verification uses the running Python interpreter rather than requiring a command named `python3` on Windows.
- `scripts/dev.py` runs setup, checks, demo, evidence and other local tasks without requiring Make.
- Virtual environments are rebuilt on the destination. Linux environments and interpreter paths are not copied.

## Transfer contents

Source, plans, reports, frozen dependency lock, tests, CI configuration, uncommitted changes, all fifteen Git metadata directories, build distributions, the sample composition and the Linux dependency wheelhouse are retained. Credentials, SSH keys, .env files, tool caches and virtual environments are excluded. The unchanged reference repositories are not project deliverables and remain outside the bundle.

The archive contains `START_HERE.txt`, `verify_transfer.py` and a per-file SHA-256 manifest. Extract directly into the requested root, verify the manifest, then follow the Windows commands in `docs/DEVELOPMENT.md`.

## Verification boundary

Linux tests, transfer integrity and a relocated extraction can be checked in the cloud. Successful writing to the Windows destination, native Windows execution and the final local Git status require access on that machine. No successful local move or native Windows test is claimed merely because the archive was created.
