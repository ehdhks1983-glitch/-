from centumhi_license.hwid import get_hwid


def test_hwid_is_stable_and_well_formed():
    h1 = get_hwid()
    h2 = get_hwid()
    assert h1 == h2
    assert len(h1) == 32
    assert all(c in "0123456789ABCDEF" for c in h1)
