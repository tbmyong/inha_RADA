package com.lab.monitor.security;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class LastSeenTrackerTest {

    @Test
    void first_call_returns_true_subsequent_within_ttl_return_false() {
        LastSeenTracker t = new LastSeenTracker();
        assertThat(t.shouldUpdate("pc-1")).isTrue();
        assertThat(t.shouldUpdate("pc-1")).isFalse();
        assertThat(t.shouldUpdate("pc-1")).isFalse();
    }

    @Test
    void different_pcIds_are_tracked_independently() {
        LastSeenTracker t = new LastSeenTracker();
        assertThat(t.shouldUpdate("pc-1")).isTrue();
        assertThat(t.shouldUpdate("pc-2")).isTrue();
        assertThat(t.shouldUpdate("pc-1")).isFalse();
        assertThat(t.shouldUpdate("pc-2")).isFalse();
    }

    @Test
    void null_pcId_returns_false() {
        LastSeenTracker t = new LastSeenTracker();
        assertThat(t.shouldUpdate(null)).isFalse();
    }
}
