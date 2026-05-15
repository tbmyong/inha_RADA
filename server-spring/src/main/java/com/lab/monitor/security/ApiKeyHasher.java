package com.lab.monitor.security;

import jakarta.annotation.PostConstruct;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

/**
 * Deterministic API-key hasher: SHA-256(pepper || ":" || rawKey), lowercase hex.
 *
 * The pepper is supplied at runtime via the {@code security.api-key.pepper}
 * property (env: {@code API_KEY_PEPPER}). The same value is injected into
 * Flyway placeholders so the V4 migration produces identical digests for
 * pre-existing rows.
 *
 * The output is a 64-character lowercase hex string, matching the
 * {@code pc_info.api_key VARCHAR(64)} column width set by V4.
 */
@Slf4j
@Component
public class ApiKeyHasher {

    public static final int HASH_HEX_LENGTH = 64;

    private final String pepper;

    public ApiKeyHasher(@Value("${security.api-key.pepper:}") String pepper) {
        this.pepper = pepper == null ? "" : pepper;
    }

    @PostConstruct
    void warn_if_pepper_blank() {
        if (pepper.isBlank()) {
            log.warn("security.api-key.pepper is blank; API-key hashing is unsalted. "
                    + "Set API_KEY_PEPPER for production.");
        }
    }

    /**
     * @return lowercase hex SHA-256 of {@code pepper + ":" + rawKey},
     *         or null when rawKey is null.
     */
    public String hash(String rawKey) {
        if (rawKey == null) return null;
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            md.update(pepper.getBytes(StandardCharsets.UTF_8));
            md.update((byte) ':');
            md.update(rawKey.getBytes(StandardCharsets.UTF_8));
            byte[] digest = md.digest();
            StringBuilder sb = new StringBuilder(HASH_HEX_LENGTH);
            for (byte b : digest) {
                sb.append(Character.forDigit((b >> 4) & 0xF, 16));
                sb.append(Character.forDigit(b & 0xF, 16));
            }
            return sb.toString();
        } catch (NoSuchAlgorithmException e) {
            // SHA-256 is mandated by the JCA spec; impossible to reach.
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
