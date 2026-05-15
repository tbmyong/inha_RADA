package com.lab.monitor.security;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ApiKeyHasherTest {

    @Test
    void hash_is_deterministic_for_same_pepper_and_key() {
        ApiKeyHasher h = new ApiKeyHasher("pepper-1");
        assertThat(h.hash("k")).isEqualTo(h.hash("k"));
    }

    @Test
    void hash_differs_when_pepper_differs() {
        ApiKeyHasher a = new ApiKeyHasher("pepper-A");
        ApiKeyHasher b = new ApiKeyHasher("pepper-B");
        assertThat(a.hash("k")).isNotEqualTo(b.hash("k"));
    }

    @Test
    void hash_differs_when_key_differs() {
        ApiKeyHasher h = new ApiKeyHasher("pepper");
        assertThat(h.hash("k1")).isNotEqualTo(h.hash("k2"));
    }

    @Test
    void hash_is_64_char_lowercase_hex() {
        ApiKeyHasher h = new ApiKeyHasher("pepper");
        String out = h.hash("any-key");
        assertThat(out).hasSize(ApiKeyHasher.HASH_HEX_LENGTH);
        assertThat(out).matches("^[0-9a-f]{64}$");
    }

    @Test
    void blank_pepper_still_produces_valid_hash() {
        ApiKeyHasher h = new ApiKeyHasher("");
        String out = h.hash("key");
        assertThat(out).matches("^[0-9a-f]{64}$");
    }

    @Test
    void null_raw_key_returns_null() {
        ApiKeyHasher h = new ApiKeyHasher("pepper");
        assertThat(h.hash(null)).isNull();
    }

    @Test
    void matches_sql_digest_contract() {
        // pgcrypto: encode(digest('pep:rawkey', 'sha256'), 'hex')
        // Expected hex computed with: SHA-256 over the bytes "pep:rawkey".
        // The hasher concatenates pepper + ':' + raw with UTF-8 bytes,
        // so its output must be exactly that hash.
        ApiKeyHasher h = new ApiKeyHasher("pep");
        // pre-computed SHA-256 of "pep:rawkey"
        String expected = java.util.HexFormat.of().formatHex(
                sha256("pep:rawkey".getBytes(java.nio.charset.StandardCharsets.UTF_8)));
        assertThat(h.hash("rawkey")).isEqualTo(expected);
    }

    private static byte[] sha256(byte[] in) {
        try {
            return java.security.MessageDigest.getInstance("SHA-256").digest(in);
        } catch (Exception e) {
            throw new AssertionError(e);
        }
    }
}
