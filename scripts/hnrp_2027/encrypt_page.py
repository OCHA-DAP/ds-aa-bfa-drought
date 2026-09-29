"""Encrypt a self-contained HTML page for the password gate (client-side decryption).

Format (same as ds-aa-tcd-drought w3_resultat_2026): base64(salt[16] | iv[12] | AES-256-GCM
ciphertext+tag), key = PBKDF2-HMAC-SHA256(password, salt, 300 000 iterations).

Usage: encrypt_page.py <plain.html> <out.enc>   (password from env PAGE_PASSWORD)
"""

import base64
import os
import sys

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITER = 300_000
src, dst = sys.argv[1], sys.argv[2]
pw = os.environ["PAGE_PASSWORD"].encode()
salt, iv = os.urandom(16), os.urandom(12)
key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER).derive(pw)
ct = AESGCM(key).encrypt(iv, open(src, "rb").read(), None)
open(dst, "w").write(base64.b64encode(salt + iv + ct).decode())
print(f"{dst}: {os.path.getsize(dst) / 1e6:.2f} MB")
