from repomentor.utils.text_utils import decode_bytes, is_placeholder, mask_secrets, tr_number

# Token-shaped strings are assembled at runtime so this file never contains a
# literal that looks like a real credential.
FAKE_GITHUB_TOKEN = "ghp_" + "a1B2" * 9


def test_mask_assignment():
    masked = mask_secrets('API_KEY = "abc123def456"\nname = "Ada"')
    assert "abc123def456" not in masked
    assert "***MASKED***" in masked
    assert 'name = "Ada"' in masked


def test_mask_known_token_format():
    assert FAKE_GITHUB_TOKEN not in mask_secrets(f"token: {FAKE_GITHUB_TOKEN}")


def test_mask_bare_credential_names_without_a_prefix():
    for name in ("password", "TOKEN", "secret", "key", "pwd", "passwd", "credentials"):
        masked = mask_secrets(f'{name}="production-value-123"')
        assert "production-value-123" not in masked
        assert "***MASKED***" in masked


def test_placeholders_are_not_secrets():
    for value in ["your_api_key_here", "xxxx", "<API_KEY>", "changeme", "${TOKEN}"]:
        assert is_placeholder(value)
    assert not is_placeholder("k8s-prod-2f9a77c1")


def test_decode_bytes():
    assert decode_bytes("çalışma".encode("utf-8")) == "çalışma"
    assert decode_bytes(b"\x00\x01binary") is None


def test_turkish_numbers():
    assert tr_number(3.456, 2) == "3,46"
    assert tr_number(12345) == "12.345"
    assert tr_number(None) == "-"
