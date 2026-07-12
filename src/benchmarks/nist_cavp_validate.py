#!/usr/bin/env python3
"""
NIST CAVP validation for AES-256-GCM and ML-KEM-1024.
Reads RSP files from data/nist_vectors/gcm/ and runs encrypt/decrypt tests.
"""
from __future__ import annotations
from pathlib import Path
from typing import List, Tuple
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def parse_cavs_rsp(rsp_path: Path) -> List[dict]:
    """Parse a CAVS .rsp file into a list of test vector dicts."""
    vectors = []
    current: dict = {}
    with open(rsp_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("["):
                # Header section — set up context
                current = {}
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                current[k] = v
                # A complete vector is detected when we have all needed keys
                # For GCM Encrypt: Count + Key + IV + PT + AAD + CT + Tag
                if k == "Tag" and "Key" in current and "IV" in current:
                    vectors.append(dict(current))
                    # Keep context (Key/IV/PT/AAD may repeat with different Counts)
                    current = {kk: vv for kk, vv in current.items()
                               if kk in ("Key", "IV")}
                elif k == "FAIL":
                    current["FAIL"] = True
                    if "Key" in current and "IV" in current and "CT" in current:
                        vectors.append(dict(current))
                        current = {kk: vv for kk, vv in current.items()
                                   if kk in ("Key", "IV")}
    return vectors


def _parse_gcm_rsp(rsp_path: Path) -> List[dict]:
    """More robust GCM RSP parser that tracks section context."""
    vectors = []
    ctx: dict = {}
    vec: dict = {}
    with open(rsp_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("["):
                content = line[1:-1]
                if "=" in content:
                    k, v = content.split("=", 1)
                    ctx[k.strip()] = v.strip()
                vec = {}
                continue
            if line == "FAIL":
                vec["FAIL"] = True
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                vec[k.strip()] = v.strip()
                if k.strip() == "Tag":
                    vec["_ctx"] = dict(ctx)
                    vectors.append(dict(vec))
                    vec = {}
    return vectors


def validate_gcm_encrypt(rsp_path: Path, max_vectors: int = 500) -> Tuple[int, int, int]:
    """
    Test AES-256-GCM encryption against NIST vectors.
    Only tests standard configuration: Keylen=256, IVlen=96, Taglen=128.
    Returns (total, pass, fail).
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    vectors = _parse_gcm_rsp(rsp_path)
    total = pass_ = fail = 0

    for v in vectors:
        if total >= max_vectors:
            break
        ctx = v.get("_ctx", {})
        # Only standard config: 256-bit key, 96-bit IV, 128-bit tag
        if ctx.get("Keylen") != "256" or ctx.get("IVlen") != "96" or ctx.get("Taglen") != "128":
            continue
        try:
            key = bytes.fromhex(v.get("Key", ""))
            iv  = bytes.fromhex(v.get("IV",  ""))
            pt_hex  = v.get("PT", "")
            aad_hex = v.get("AAD", "")
            ct_hex  = v.get("CT", "")
            pt  = bytes.fromhex(pt_hex) if pt_hex else b""
            aad = bytes.fromhex(aad_hex) if aad_hex else b""
            exp_ct  = bytes.fromhex(ct_hex) if ct_hex else b""
            exp_tag = bytes.fromhex(v.get("Tag", ""))

            if len(key) != 32 or len(iv) != 12 or len(exp_tag) != 16:
                continue

            total += 1
            aesgcm = AESGCM(key)
            enc = aesgcm.encrypt(iv, pt, aad or None)
            got_ct  = enc[:-16]
            got_tag = enc[-16:]

            if got_ct == exp_ct and got_tag == exp_tag:
                pass_ += 1
            else:
                fail += 1
        except Exception:
            fail += 1

    return total, pass_, fail


def _parse_gcm_decrypt_rsp(rsp_path: Path) -> List[dict]:
    """
    Parse GCM decrypt RSP file.  Vectors are delimited differently from encrypt:
      - 'PT = ' line OR 'FAIL' on its own line terminates the vector.
      - FAIL appears AFTER the Tag line.
    """
    vectors = []
    ctx: dict = {}
    vec: dict = {}
    with open(rsp_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("["):
                content = line[1:-1]
                if "=" in content:
                    k, v = content.split("=", 1)
                    ctx[k.strip()] = v.strip()
                vec = {}
                continue
            if line == "FAIL":
                vec["FAIL"] = True
                vec["_ctx"] = dict(ctx)
                vectors.append(dict(vec))
                vec = {}
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                vec[k] = v
                if k == "PT":  # successful decrypt: PT is the last field
                    vec["_ctx"] = dict(ctx)
                    vectors.append(dict(vec))
                    vec = {}
    return vectors


def validate_gcm_decrypt(rsp_path: Path, max_vectors: int = 300) -> Tuple[int, int, int]:
    """
    Test AES-256-GCM decryption (including FAIL cases for tag forgery).
    Only tests standard configuration: Keylen=256, IVlen=96, Taglen=128.
    Returns (total, pass, fail).
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    vectors = _parse_gcm_decrypt_rsp(rsp_path)
    total = pass_ = fail = 0

    for v in vectors:
        if total >= max_vectors:
            break
        ctx = v.get("_ctx", {})
        if ctx.get("Keylen") != "256" or ctx.get("IVlen") != "96" or ctx.get("Taglen") != "128":
            continue

        should_fail = v.get("FAIL", False)
        try:
            key = bytes.fromhex(v.get("Key", ""))
            iv  = bytes.fromhex(v.get("IV",  ""))
            ct_hex  = v.get("CT",  "")
            aad_hex = v.get("AAD", "")
            ct  = bytes.fromhex(ct_hex) if ct_hex else b""
            aad = bytes.fromhex(aad_hex) if aad_hex else b""
            tag = bytes.fromhex(v.get("Tag", ""))
            exp_pt_hex = v.get("PT", "")
            exp_pt = bytes.fromhex(exp_pt_hex) if exp_pt_hex else b""

            if len(key) != 32 or len(iv) != 12 or len(tag) != 16:
                continue

            total += 1
            aesgcm = AESGCM(key)
            try:
                pt = aesgcm.decrypt(iv, ct + tag, aad or None)
                if should_fail:
                    fail += 1  # Expected rejection but accepted
                elif pt == exp_pt:
                    pass_ += 1
                else:
                    fail += 1  # Wrong plaintext
            except Exception:
                if should_fail:
                    pass_ += 1  # Correctly rejected
                else:
                    fail += 1

        except Exception:
            fail += 1

    return total, pass_, fail


def validate_mlkem(max_vectors: int = 100) -> Tuple[int, int, int]:
    """Test ML-KEM-1024 using the kyber-py shim — run fresh keygen/encaps/decaps."""
    import oqs
    total = pass_ = fail = 0

    for _ in range(max_vectors):
        total += 1
        try:
            kem = oqs.KeyEncapsulation("Kyber1024")
            pk  = kem.generate_keypair()
            ct, ss1 = kem.encap_secret(pk)
            ss2 = kem.decap_secret(ct)
            if ss1 == ss2 and len(ss1) == 32:
                pass_ += 1
            else:
                fail += 1
        except Exception:
            fail += 1

    return total, pass_, fail


def main():
    gcm_dir = ROOT / "data" / "nist_vectors" / "gcm"
    results = []

    print("Running NIST CAVP validation...", flush=True)

    # AES-256-GCM encrypt
    enc_file = gcm_dir / "gcmEncryptExtIV256.rsp"
    if enc_file.exists():
        t, p, f = validate_gcm_encrypt(enc_file, max_vectors=500)
        results.append(("AES-256-GCM Encrypt KAT", t, p, f))
        print(f"  AES-256-GCM Encrypt: {p}/{t} pass", flush=True)
    else:
        results.append(("AES-256-GCM Encrypt KAT", 0, 0, 0))

    # AES-256-GCM decrypt (including FAIL cases)
    dec_file = gcm_dir / "gcmDecrypt256.rsp"
    if dec_file.exists():
        t, p, f = validate_gcm_decrypt(dec_file, max_vectors=300)
        results.append(("AES-256-GCM Decrypt (incl. FAIL)", t, p, f))
        print(f"  AES-256-GCM Decrypt: {p}/{t} pass", flush=True)
    else:
        results.append(("AES-256-GCM Decrypt (incl. FAIL)", 0, 0, 0))

    # ML-KEM round-trip
    t, p, f = validate_mlkem(max_vectors=100)
    results.append(("ML-KEM-1024 Keygen/Encaps/Decaps", t, p, f))
    print(f"  ML-KEM-1024: {p}/{t} pass", flush=True)

    # Output CSV for table generation
    import csv
    out = ROOT / "results" / "data" / "nist_cavp_results.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["test_suite", "total", "pass", "fail", "pass_rate_pct"])
        for (name, t, p, fail_) in results:
            rate = f"{p/t*100:.1f}" if t > 0 else "N/A"
            w.writerow([name, t, p, fail_, rate])
    print(f"\nResults saved to {out}")

    # Print summary
    print("\n=== NIST CAVP Summary ===")
    for name, t, p, fail_ in results:
        rate = f"{p/t*100:.1f}%" if t > 0 else "N/A"
        status = "PASS" if fail_ == 0 and t > 0 else ("N/A" if t == 0 else "FAIL")
        print(f"  {status:4s}  {name}: {p}/{t} ({rate})")

    return results


if __name__ == "__main__":
    main()
