from app.core.key_generator import (
    generate_license_key,
    hash_license_key,
    key_prefix,
    plan_code,
    verify_checksum,
)


def test_format_has_five_segments_and_valid_checksum():
    for plan, days in [
        ("trial_7", None),
        ("monthly_30", None),
        ("unlimited", None),
        ("custom", 90),
    ]:
        key = generate_license_key("CW", plan, days)
        segments = key.split("-")
        assert len(segments) == 5, key
        assert segments[0] == "CW"
        assert len(segments[2]) == 8 and len(segments[3]) == 8
        assert verify_checksum(key)
        assert len(key_prefix(key)) == 12


def test_plan_codes():
    assert plan_code("trial_7", None) == "T07"
    assert plan_code("monthly_30", None) == "M30"
    assert plan_code("unlimited", None) == "U00"
    assert plan_code("custom", 90) == "C90"


def test_checksum_detects_tampering():
    key = generate_license_key("CT", "unlimited", None)
    tampered = key[:-1] + ("A" if key[-1] != "A" else "B")
    assert verify_checksum(key)
    assert not verify_checksum(tampered)


def test_keys_are_unique_and_hash_is_stable():
    keys = {generate_license_key("CB", "trial_7", None) for _ in range(300)}
    assert len(keys) == 300
    sample = next(iter(keys))
    assert len(hash_license_key(sample)) == 64
    assert hash_license_key(sample) == hash_license_key(sample)
    assert hash_license_key(sample) != hash_license_key(generate_license_key("CB", "trial_7", None))
