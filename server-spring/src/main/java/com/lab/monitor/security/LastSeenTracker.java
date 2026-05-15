package com.lab.monitor.security;

import org.springframework.stereotype.Component;

import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Throttles last_seen_at updates to at most once per TTL (30s) per pc_id.
 * In-memory only; on JVM restart all PCs are eligible for one update.
 */
@Component
public class LastSeenTracker {

    private static final Duration TTL = Duration.ofSeconds(30);

    private final ConcurrentHashMap<String, Instant> cache = new ConcurrentHashMap<>();

    public boolean shouldUpdate(String pcId) {
        if (pcId == null) return false;
        Instant now = Instant.now();
        Instant last = cache.get(pcId);
        if (last != null && Duration.between(last, now).compareTo(TTL) < 0) {
            return false;
        }
        cache.put(pcId, now);
        return true;
    }
}
