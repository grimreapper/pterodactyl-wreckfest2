# Release verification

## v1.1.0

Release: <https://github.com/grimreapper/pterodactyl-wreckfest2/releases/tag/v1.1.0>

Accepted source commit:
`6a1f810f0fe41c5034674b07eb9a0f0b826b8b56`

Published asset digests:

```text
2dde0586414fc372b610f1e319f14d7979ac41cbb4e29053b8c219f8cf37d1b3  egg-wreckfest2.json
18c143d113bc884d8fd9516a501301789a622c8065124bb316f62a29eaaff1a7  wreckfest2-pterodactyl-egg.zip
```

The accepted revision passed 28 tests, Bash syntax validation, deterministic
archive rebuilding, and release checksum verification. Disposable live
acceptance covered a clean anonymous installation, exact complete Steam
manifests, Wreckfest 2 build `26269859`, runtime readiness, the UDP game
listener, a five-minute stability soak, controlled restart recovery, and
configuration-preserving reinstall. Server-browser discovery and a real client
join/reconnect were not automated and remain outside the verified scope.

To verify a downloaded release locally:

```sh
sha256sum --check SHA256SUMS
python3 -m unittest -q
bash -n install.sh start.sh
python3 build_artifacts.py --output-dir dist
(cd dist && sha256sum --check SHA256SUMS)
```

No downloaded or generated game payload is distributed by this project.
