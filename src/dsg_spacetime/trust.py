from __future__ import annotations


# This placeholder is overwritten in the CI/release workspace immediately before
# compiling the customer binary. The committed source intentionally contains no
# seller trust root so source history does not need to change when keys rotate.
BUILTIN_LICENSE_PUBLIC_KEY_B64 = ""


def get_builtin_license_public_key() -> str:
    value = BUILTIN_LICENSE_PUBLIC_KEY_B64.strip()
    if not value:
        raise RuntimeError("BUILTIN_LICENSE_TRUST_ROOT_MISSING")
    return value
