import sys
print("Python:", sys.version[:6])
print()

results = {}
ok, fail = [], []

checks = [
    ("torch",        lambda: __import__("torch").__version__),
    ("numpy",        lambda: __import__("numpy").__version__),
    ("pandas",       lambda: __import__("pandas").__version__),
    ("scipy",        lambda: __import__("scipy").__version__),
    ("cryptography", lambda: __import__("cryptography").__version__),
    ("oqs (shim)",   lambda: __import__("oqs").get_version()),
    ("kyber E2E",    lambda: _test_kyber()),
    ("Pillow",       lambda: __import__("PIL").__version__),
    ("skimage",      lambda: __import__("skimage").__version__),
    ("zstandard",    lambda: __import__("zstandard").__version__),
    ("lz4",          lambda: __import__("lz4").__version__),
    ("brotli",       lambda: "ok"),
    ("matplotlib",   lambda: __import__("matplotlib").__version__),
    ("seaborn",      lambda: __import__("seaborn").__version__),
    ("psutil",       lambda: __import__("psutil").__version__),
    ("pyyaml",       lambda: __import__("yaml").__version__),
    ("tqdm",         lambda: __import__("tqdm").__version__),
]


def _test_kyber():
    from kyber_py.kyber import Kyber512, Kyber768, Kyber1024
    for cls, name in [(Kyber512, "512"), (Kyber768, "768"), (Kyber1024, "1024")]:
        pk, sk = cls.keygen()
        key, ct = cls.encaps(pk)
        key2 = cls.decaps(sk, ct)
        assert key == key2, f"Kyber{name} secret mismatch"
    return "Kyber512/768/1024 all OK"


def _test_oqs_compat():
    import oqs
    kem = oqs.KeyEncapsulation("Kyber1024")
    pk = kem.generate_keypair()
    ct, ss1 = kem.encap_secret(pk)
    ss2 = kem.decap_secret(ct)
    assert ss1 == ss2, "oqs shim secret mismatch"
    return f"oqs shim OK (version={oqs.get_version()})"


checks.append(("oqs API compat", _test_oqs_compat))

for name, fn in checks:
    try:
        result = fn()
        ok.append((name, result))
    except Exception as e:
        fail.append((name, str(e)))

print("=== INSTALLED AND IMPORTABLE ===")
for name, ver in ok:
    print(f"  OK   {name}: {ver}")

if fail:
    print()
    print("=== FAILED ===")
    for name, err in fail:
        print(f"  FAIL {name}: {err}")
else:
    print()
    print(f"All {len(ok)} checks passed!")
